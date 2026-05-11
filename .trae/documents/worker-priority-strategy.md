# Web Worker 优先策略 + 前端任务 Worker 化

## Summary

在项目规则中添加"前端优先使用 Worker"原则，并识别当前适合迁移到 Worker 的前端计算任务，制定实施方案。

## Current State Analysis

### 当前前端计算任务清单

| 任务 | 位置 | 计算量 | 主线程阻塞 | Worker 适合度 |
|------|------|--------|-----------|-------------|
| **WAV PCM 解码** (`decodeWavPcm`) | `wavParser.ts` | 高（逐样本 deinterleave，5min 48kHz 立体声 ≈ 28M 次运算） | ⚠️ 阻塞 | ⭐⭐⭐ 高 |
| **音频分析** (`detectAudioIssues`) | `advancedAudioProcessing.ts` | 高（逐样本遍历 + 频谱平坦度计算，5min ≈ 14M 次运算） | ⚠️ 阻塞 | ⭐⭐⭐ 高 |
| **频谱可视化** (`SpectrumVisualizer`) | `SpectrumVisualizer.tsx` | 低（32 段柱状图，requestAnimationFrame 驱动） | ✅ 不阻塞 | ❌ 不适合 |
| **IndexedDB 操作** (`sessionDB.ts`) | `sessionDB.ts` | 低（异步 API，数据量小） | ✅ 不阻塞 | ❌ 不适合 |
| **WAV 头解析** (`parseWavHeader`) | `wavParser.ts` | 极低（只读几十字节） | ✅ 不阻塞 | ❌ 不适合 |

### 关键发现

1. **`decodeWavPcm`** 是最大的主线程阻塞源：对 5min 48kHz 立体声 16bit WAV，需要遍历 28,800,000 个样本做 int16→float32 转换和 deinterleave，在低端设备上可能阻塞 100-300ms
2. **`detectAudioIssues`** 是第二大阻塞源：逐样本遍历 + 块 RMS 计算 + 频谱平坦度，5min 音频约阻塞 50-150ms
3. 两者都在 `loadAudioFile` 中同步调用，用户上传文件时 UI 会卡顿
4. 频谱可视化使用 `requestAnimationFrame` + AnalyserNode，已经是非阻塞模式，不适合 Worker（Canvas API 不可用）
5. IndexedDB 操作本身是异步的，不需要 Worker

### 现有 Worker 基础设施

- `src/workers/` 目录已删除（之前删除了 `audioRepairWorker.ts` 和 `fftWorker.ts`）
- Vite 原生支持 Worker：`new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })`
- 无需额外 Vite 配置

## Proposed Changes

### 1. 更新项目规则 — 添加 Worker 优先原则

**文件**: `/workspace/.trae/rules/project_rules.md`

在 Architecture 部分添加：

```markdown
## Web Worker 策略

前端计算密集型任务**必须优先考虑使用 Web Worker**，避免阻塞主线程导致 UI 卡顿。

适合 Worker 的任务特征：
- 逐样本音频数据处理（解码、分析、编码）
- 大数组遍历/变换（>1M 次运算）
- 可脱离 DOM 独立完成的纯计算

不适合 Worker 的任务：
- 需要 DOM/Canvas API 的操作
- 已由 requestAnimationFrame 驱动的轻量渲染
- 异步 I/O 操作（fetch、IndexedDB）
- 计算量极低（<10ms）的任务

当前 Worker 使用：
- `src/workers/audioWorker.ts` — WAV PCM 解码 + 音频分析
```

### 2. 创建统一音频 Worker

**新文件**: `/workspace/src/workers/audioWorker.ts`

将 `decodeWavPcm` 和 `detectAudioIssues` 合并到一个 Worker 中，理由：
- 两者都在 `loadAudioFile` 中顺序调用
- 共享 `parseWavHeaderFull` 逻辑
- 减少 Worker 创建开销（1 个 Worker 复用 vs 2 个 Worker）

Worker 消息协议：

```typescript
// 主线程 → Worker
type WorkerRequest =
  | { type: 'decode-wav'; buffer: ArrayBuffer }
  | { type: 'analyze-audio'; channelData: Float32Array[]; sampleRate: number; channels: number }
  | { type: 'decode-and-analyze'; buffer: ArrayBuffer }

// Worker → 主线程
type WorkerResponse =
  | { type: 'decode-wav'; id: number; result: DecodedWavResult | null }
  | { type: 'analyze-audio'; id: number; result: AudioAnalysisResult }
  | { type: 'decode-and-analyze'; id: number; decode: DecodedWavResult | null; analysis: AudioAnalysisResult | null }
```

关键设计决策：
- **`decode-and-analyze`**：一步完成解码+分析，避免两次 `postMessage` 传输开销
- **Transferable**：ArrayBuffer 使用 Transferable 传输，零拷贝
- **结果不含 AudioBuffer**：Worker 无法创建 AudioBuffer（需要 AudioContext），返回原始 Float32Array[] + 参数，主线程组装 AudioBuffer

### 3. 创建 Worker 管理工具

**新文件**: `/workspace/src/workers/useAudioWorker.ts`

封装 Worker 生命周期和消息通信：

```typescript
export function useAudioWorker() {
  // Worker 实例管理（懒初始化）
  // Promise 化的消息通信（自动 id 匹配）
  // decodeWav(buffer) → { channelData, sampleRate, channels, bitDepth, totalFrames }
  // analyzeAudio(channelData, sampleRate, channels) → AudioAnalysisResult
  // decodeAndAnalyze(buffer) → 两者结果
  // terminate() 清理
}
```

### 4. 修改 useAudioProcessor.ts

**文件**: `/workspace/src/hooks/useAudioProcessor.ts`

修改 `loadAudioFile` 中的两处同步调用：

**Before** (同步，阻塞主线程):
```typescript
const fastDecoded = decodeWavPcm(context, arrayBuf);
// ...
const analysis = cachedAnalysis || detectAudioIssues(buffer);
```

**After** (异步，Worker 处理):
```typescript
const fastDecoded = await audioWorker.decodeWav(arrayBuf);
// decodeWav 返回 Float32Array[] + 参数，主线程组装 AudioBuffer
// ...
const analysis = cachedAnalysis || await audioWorker.analyzeAudio(channelData, sampleRate, channels);
```

同时修改 session 恢复路径中的 `decodeWavPcm` 调用。

### 5. Worker 内部实现

**文件**: `/workspace/src/workers/audioWorker.ts`

从现有代码迁移：
- `wavParser.ts` 中的 `parseWavHeaderFull`、`deinterleaveInt16/24/32/8` → Worker 内部函数
- `advancedAudioProcessing.ts` 中的 `detectAudioIssues`、`calculateSpectralFlatness` → Worker 内部函数

主线程的 `wavParser.ts` 和 `advancedAudioProcessing.ts` 保留（类型定义和轻量函数仍需在主线程使用），但重型函数标记为 Worker-only。

## Assumptions & Decisions

1. **统一 Worker vs 独立 Worker**：选择统一 Worker，因为解码和分析总是顺序执行，合并可减少通信开销
2. **Worker 懒初始化**：首次调用时创建，页面卸载时销毁，避免空闲资源占用
3. **Transferable 传输**：ArrayBuffer 使用 Transferable 零拷贝传输，但注意传输后主线程不可访问原 buffer（需 clone 或提前读取）
4. **AudioBuffer 组装在主线程**：Worker 无法访问 AudioContext，返回 Float32Array[] + 参数，主线程用 `audioContext.createBuffer()` + `copyToChannel()` 组装
5. **降级策略**：Worker 创建失败时 fallback 到主线程同步处理（确保功能不中断）
6. **`advancedAudioProcessing.ts` 类型保留**：`AIRepairParams`、`RepairMode`、`AudioIssue` 等类型仍在主线程使用，只迁移计算函数

## Verification Steps

1. `npm run build` — 确保构建通过
2. `bash scripts/build_android_release.sh` — 确保 Android 打包通过
3. 手动测试：上传 5min+ WAV 文件，验证解码和分析正常，UI 无卡顿
4. 手动测试：上传非 WAV 文件（MP3/FLAC），验证 fallback 路径正常
5. 手动测试：session 恢复场景，验证缓存命中和未命中路径

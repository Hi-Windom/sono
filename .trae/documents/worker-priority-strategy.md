# Web Worker 优先策略 + 前端任务 Worker 化

## Summary

在项目规则中添加"前端优先使用 Worker"原则，识别适合迁移到 Worker 的前端计算任务，并结合前端状态缓存体系优化 Worker 与缓存的交互，制定实施方案。

## Current State Analysis

### 前端计算任务清单

| 任务 | 位置 | 计算量 | 主线程阻塞 | Worker 适合度 |
|------|------|--------|-----------|-------------|
| **WAV PCM 解码** (`decodeWavPcm`) | `wavParser.ts` | 高（逐样本 deinterleave，5min 48kHz 立体声 ≈ 28M 次运算） | ⚠️ 阻塞 | ⭐⭐⭐ 高 |
| **音频分析** (`detectAudioIssues`) | `advancedAudioProcessing.ts` | 高（逐样本遍历 + 频谱平坦度计算，5min ≈ 14M 次运算） | ⚠️ 阻塞 | ⭐⭐⭐ 高 |
| **频谱可视化** (`SpectrumVisualizer`) | `SpectrumVisualizer.tsx` | 低（32 段柱状图，requestAnimationFrame 驱动） | ✅ 不阻塞 | ❌ 不适合 |
| **IndexedDB 操作** (`sessionDB.ts`) | `sessionDB.ts` | 低（异步 API，数据量小） | ✅ 不阻塞 | ❌ 不适合 |
| **WAV 头解析** (`parseWavHeader`) | `wavParser.ts` | 极低（只读几十字节） | ✅ 不阻塞 | ❌ 不适合 |

### 前端状态缓存体系现状

当前前端有 **4 层缓存**，分布在主线程和后端：

```
┌─────────────────────────────────────────────────────────┐
│                    前端缓存体系                           │
├─────────────────────────────────────────────────────────┤
│ 1. IndexedDB 会话缓存 (sessionDB.ts)                     │
│    - 保存当前会话状态 (file, taskId, wavInfo, repairResult) │
│    - 页面刷新后恢复会话                                    │
│    - 异步操作，不阻塞主线程                                │
├─────────────────────────────────────────────────────────┤
│ 2. IndexedDB 分析缓存 (sessionDB.ts analysis_cache)      │
│    - 按 fileHash 缓存 wavInfo + analysis                  │
│    - 避免重复分析同一文件                                  │
│    - 异步操作，不阻塞主线程                                │
├─────────────────────────────────────────────────────────┤
│ 3. 后端分析缓存 (/api/v1/analysis-cache)                  │
│    - 服务端持久化 wavInfo + analysis                       │
│    - 跨设备/跨浏览器共享                                   │
│    - loadAudioFile 时优先查询，命中则跳过 detectAudioIssues │
├─────────────────────────────────────────────────────────┤
│ 4. 后端修复/渲染缓存 (lookupRepairCache, fetchRenderCache) │
│    - 修复结果按 fileHash+params 匹配                      │
│    - 渲染结果按 taskId+sampleRate+bitDepth 匹配            │
│    - 缓存命中时弹出 RepairCacheModal 供用户选择            │
└─────────────────────────────────────────────────────────┘
```

### 缓存与 Worker 的交互分析

**关键发现：缓存命中可完全跳过 Worker 计算**

当前 `loadAudioFile` 流程：

```
用户上传文件
  → computeFileHash()              [主线程，轻量]
  → 查询后端分析缓存                [异步 fetch]
  → 命中？→ 跳过 detectAudioIssues  ✅ 已优化
  → 未命中？→ decodeWavPcm()        ⚠️ 主线程阻塞
             → detectAudioIssues()  ⚠️ 主线程阻塞
             → POST analysis-cache  [异步 fetch]
```

**优化后的流程（Worker + 缓存协同）：**

```
用户上传文件
  → computeFileHash()              [主线程，轻量]
  → 查询后端分析缓存                [异步 fetch]
  → 命中？→ 跳过 Worker 分析        ✅
  → 未命中？→ Worker: decodeWavPcm + detectAudioIssues  ✅ 不阻塞
             → 主线程组装 AudioBuffer
             → POST analysis-cache  [异步 fetch]
```

**session 恢复路径也需要 Worker 化：**

当前 session 恢复流程（`useAudioProcessor.ts` L480-560）：
```
loadSession() → 读取 File → decodeWavPcm() ⚠️ → detectAudioIssues() ⚠️
```
此路径没有后端分析缓存查询（因为 File 对象可能已失效，先验证再处理），所以 Worker 化收益更明显。

### 现有 Worker 基础设施

- `src/workers/` 目录已删除（之前删除了 `audioRepairWorker.ts` 和 `fftWorker.ts`）
- Vite 原生支持 Worker：`new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })`
- 无需额外 Vite 配置

## Proposed Changes

### 1. 更新项目规则 — 添加 Worker 优先原则

**文件**: `/workspace/.trae/rules/project_rules.md`

在 Architecture 部分之后添加：

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

Worker 与缓存协同：
- 缓存命中时跳过 Worker 计算（避免不必要的通信开销）
- 缓存未命中时 Worker 异步计算，结果写回缓存
- Worker 结果不直接写缓存，由主线程负责缓存写入（Worker 无法访问 fetch/IndexedDB）

当前 Worker 使用：
- `src/workers/audioWorker.ts` — WAV PCM 解码 + 音频分析
```

### 2. 创建统一音频 Worker

**新文件**: `/workspace/src/workers/audioWorker.ts`

将 `decodeWavPcm` 和 `detectAudioIssues` 合并到一个 Worker 中，理由：
- 两者都在 `loadAudioFile` 中顺序调用
- 共享 `parseWavHeaderFull` 逻辑
- 减少 Worker 创建开销（1 个 Worker 复用 vs 2 个 Worker）
- `decode-and-analyze` 一步完成，避免两次 postMessage 传输开销

Worker 消息协议：

```typescript
// 主线程 → Worker
type WorkerRequest =
  | { type: 'decode-wav'; id: number; buffer: ArrayBuffer }
  | { type: 'analyze-audio'; id: number; channelData: Float32Array[]; sampleRate: number; channels: number }
  | { type: 'decode-and-analyze'; id: number; buffer: ArrayBuffer }

// Worker → 主线程
type WorkerResponse =
  | { type: 'decode-wav'; id: number; result: DecodedWavResult | null }
  | { type: 'analyze-audio'; id: number; result: AudioAnalysisResult }
  | { type: 'decode-and-analyze'; id: number; decode: DecodedWavResult | null; analysis: AudioAnalysisResult | null }

// 解码结果（不含 AudioBuffer，主线程组装）
interface DecodedWavResult {
  channelData: Float32Array[];  // Transferable
  sampleRate: number;
  channels: number;
  bitDepth: number;
  totalFrames: number;
}

// 分析结果（与现有 AudioAnalysis 兼容 + 扩展字段）
interface AudioAnalysisResult {
  spectralFlatness: number;
  dynamicRange: number;
  stereoBalance: number;
  peakLevel: number;
  issues: string[];
  clippingCount: number;
  crackleRegions: number[];
  popRegions: number[];
  detailedIssues: AudioIssue[];
}
```

关键设计决策：
- **`decode-and-analyze`**：一步完成解码+分析，避免两次 `postMessage` 传输开销
- **Transferable**：ArrayBuffer 和 Float32Array 使用 Transferable 传输，零拷贝
- **结果不含 AudioBuffer**：Worker 无法创建 AudioBuffer（需要 AudioContext），返回原始 Float32Array[] + 参数，主线程组装 AudioBuffer
- **缓存写入在主线程**：Worker 不直接写缓存，主线程收到结果后负责 `POST /api/v1/analysis-cache`

### 3. 创建 Worker 管理工具

**新文件**: `/workspace/src/workers/useAudioWorker.ts`

封装 Worker 生命周期和消息通信：

```typescript
interface AudioWorkerAPI {
  decodeWav(buffer: ArrayBuffer): Promise<DecodedWavResult | null>;
  analyzeAudio(channelData: Float32Array[], sampleRate: number, channels: number): Promise<AudioAnalysisResult>;
  decodeAndAnalyze(buffer: ArrayBuffer): Promise<{
    decode: DecodedWavResult | null;
    analysis: AudioAnalysisResult | null;
  }>;
  terminate(): void;
}

export function useAudioWorker(): AudioWorkerAPI {
  // Worker 实例管理（懒初始化，首次调用时创建）
  // Promise 化的消息通信（自动 id 匹配）
  // Transferable 传输优化
  // Worker 创建失败时 fallback 到主线程同步处理
}
```

### 4. 修改 useAudioProcessor.ts — loadAudioFile 路径

**文件**: `/workspace/src/hooks/useAudioProcessor.ts`

#### 4a. 新文件上传路径（L760-L920）

**Before** (同步，阻塞主线程):
```typescript
const fastDecoded = decodeWavPcm(context, arrayBuf);
// ... 组装 AudioBuffer ...
const analysis = cachedAnalysis || detectAudioIssues(buffer);
// ... POST analysis-cache ...
```

**After** (异步，Worker 处理 + 缓存协同):
```typescript
if (cachedAnalysis) {
  // 缓存命中：跳过 Worker 分析，只需解码
  const decoded = await audioWorker.decodeWav(arrayBuf);
  // 组装 AudioBuffer
} else {
  // 缓存未命中：Worker 一步完成解码+分析
  const { decode, analysis } = await audioWorker.decodeAndAnalyze(arrayBuf);
  // 组装 AudioBuffer
  // POST analysis-cache（主线程负责缓存写入）
}
```

#### 4b. Session 恢复路径（L480-L560）

**Before**:
```typescript
const fastDecoded = decodeWavPcm(context, arrayBuf);
const buffer = fastDecoded || await context.decodeAudioData(arrayBuf);
const analysis = detectAudioIssues(buffer);
```

**After**:
```typescript
const { decode, analysis } = await audioWorker.decodeAndAnalyze(arrayBuf);
// decode 为 null 时 fallback 到 context.decodeAudioData
// analysis 为 null 时跳过设置
```

#### 4c. 后端解码 WAV 缓存路径（L795-L810）

**Before**:
```typescript
const wavBuf = await downloadWithProgress(decodedWavUrl);
const fastBuf = decodeWavPcm(context, wavBuf);
```

**After**:
```typescript
const wavBuf = await downloadWithProgress(decodedWavUrl);
const decoded = await audioWorker.decodeWav(wavBuf);
// 组装 AudioBuffer
```

### 5. Worker 内部实现

**文件**: `/workspace/src/workers/audioWorker.ts`

从现有代码迁移：
- `wavParser.ts` 中的 `parseWavHeaderFull`、`deinterleaveInt16/24/32/8` → Worker 内部函数
- `advancedAudioProcessing.ts` 中的 `detectAudioIssues`、`calculateSpectralFlatness` → Worker 内部函数

主线程的 `wavParser.ts` 保留（`parseWavHeader` 轻量函数仍需在主线程使用，如 L532 `parseWavHeader(arrayBuf.slice(0, 44 + 4096))`），但 `decodeWavPcm` 和重型 deinterleave 函数标记为 Worker-only。

主线程的 `advancedAudioProcessing.ts` 保留（`AIRepairParams`、`RepairMode`、`AudioIssue` 等类型仍在主线程使用），`detectAudioIssues` 标记为 Worker-only，主线程不再直接调用。

### 6. 缓存体系与 Worker 的协同优化

**核心原则：缓存命中 > Worker 计算 > 主线程同步**

```
查询缓存层级：
  1. 后端分析缓存命中 → 跳过 Worker（零计算开销）
  2. 后端分析缓存未命中 → Worker 异步计算（不阻塞 UI）
  3. Worker 不可用 → 主线程同步 fallback（功能不中断）
```

**缓存写入策略不变**：
- Worker 计算结果返回主线程后，主线程负责 `POST /api/v1/analysis-cache`
- IndexedDB 分析缓存写入也在主线程（`saveAnalysisCache`）
- Worker 不直接访问任何缓存 API

**新增优化：Worker 结果的 IndexedDB 缓存**

当前 `loadAudioFile` 只写后端分析缓存，不写前端 IndexedDB 分析缓存。Worker 化后增加前端缓存写入：

```typescript
// Worker 返回分析结果后
if (!cachedAnalysis && analysis) {
  // 写后端缓存（已有）
  fetch('/api/v1/analysis-cache', { method: 'POST', ... });
  // 新增：写前端 IndexedDB 缓存
  saveAnalysisCache({ fileHash: hash, fileName: file.name, fileSize: file.size, wavInfo: ..., analysis: ... });
}
```

这样下次加载同一文件时，即使后端不可用，也能从 IndexedDB 命中缓存。

## Assumptions & Decisions

1. **统一 Worker vs 独立 Worker**：选择统一 Worker，因为解码和分析总是顺序执行，合并可减少通信开销
2. **Worker 懒初始化**：首次调用时创建，页面卸载时销毁，避免空闲资源占用
3. **Transferable 传输**：ArrayBuffer 使用 Transferable 零拷贝传输，但注意传输后主线程不可访问原 buffer（需 clone 或提前读取 wavHeader）
4. **AudioBuffer 组装在主线程**：Worker 无法访问 AudioContext，返回 Float32Array[] + 参数，主线程用 `audioContext.createBuffer()` + `copyToChannel()` 组装
5. **降级策略**：Worker 创建失败时 fallback 到主线程同步处理（确保功能不中断）
6. **`advancedAudioProcessing.ts` 类型保留**：`AIRepairParams`、`RepairMode`、`AudioIssue` 等类型仍在主线程使用，只迁移计算函数
7. **缓存优先于 Worker**：后端分析缓存命中时完全跳过 Worker，避免不必要的通信和计算开销
8. **新增前端 IndexedDB 分析缓存写入**：当前只写后端，Worker 化后同时写前端，提升离线/弱网场景的缓存命中率

## Verification Steps

1. `npm run build` — 确保构建通过
2. `bash scripts/build_android_release.sh` — 确保 Android 打包通过
3. 手动测试：上传 5min+ WAV 文件，验证解码和分析正常，UI 无卡顿
4. 手动测试：上传非 WAV 文件（MP3/FLAC），验证 fallback 路径正常
5. 手动测试：session 恢复场景，验证缓存命中和未命中路径
6. 手动测试：同一文件二次上传，验证后端分析缓存命中跳过 Worker
7. 手动测试：后端不可用时，验证 IndexedDB 分析缓存命中

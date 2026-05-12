# Sono 缓存架构技术文档

## 概述

Sono 采用多层缓存架构，覆盖前端（IndexedDB、React State、Web Worker）和后端（SQLite、文件系统），确保相同文件和参数不重复计算。本文档描述所有缓存层的架构设计、数据流、一致性策略和经验教训。

---

## 一、缓存层级总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        前端缓存层                                    │
├─────────────────────────────────────────────────────────────────────┤
│ L1. React State（内存，瞬时）                                        │
│    audioBuffer / backendProcessedBuffer / audioAnalysis / wavInfo    │
│    生命周期：组件挂载 → 卸载                                          │
├─────────────────────────────────────────────────────────────────────┤
│ L2. IndexedDB 会话缓存（浏览器持久化）                                │
│    sessionDB.ts → 'session' store                                    │
│    保存当前工作流状态，页面刷新后恢复                                   │
├─────────────────────────────────────────────────────────────────────┤
│ L3. IndexedDB 分析缓存（浏览器持久化）                                │
│    sessionDB.ts → 'analysis_cache' store                             │
│    按 fileHash 缓存 wavInfo + analysis，避免重复分析                   │
├─────────────────────────────────────────────────────────────────────┤
│ L4. Web Worker 计算缓存（隐式）                                      │
│    Worker 结果通过 postMessage 返回主线程后，                          │
│    由主线程写入 L2/L3/后端缓存                                        │
│    Worker 本身不持有缓存，不直接访问任何存储 API                        │
└─────────────────────────────────────────────────────────────────────┘
                              ↕ fetch / WebSocket
┌─────────────────────────────────────────────────────────────────────┐
│                        后端缓存层                                    │
├─────────────────────────────────────────────────────────────────────┤
│ L5. 后端分析缓存（SQLite: analysis_cache 表）                        │
│    GET/POST /api/v1/analysis-cache/{hash}                            │
│    按 fileHash 缓存 wavInfo + analysis + waveform_peaks              │
│    跨设备/跨浏览器共享                                                │
├─────────────────────────────────────────────────────────────────────┤
│ L6. 上传去重缓存（SQLite: tasks 表 file_hash 索引）                   │
│    POST /api/v1/check-hash                                           │
│    相同文件只上传一次，复用 task_id                                    │
├─────────────────────────────────────────────────────────────────────┤
│ L7. 修复结果缓存（SQLite: tasks 表 + 文件系统）                       │
│    POST /api/v1/cache/lookup                                         │
│    (fileHash + repairParams) → (outputPath + repairResult)           │
├─────────────────────────────────────────────────────────────────────┤
│ L8. 渲染缓存（文件系统: output/ 目录）                                │
│    GET /api/v1/render-cache/{task_id}                                 │
│    (taskId + sampleRate + bitDepth + algorithmVersion) → WAV file    │
├─────────────────────────────────────────────────────────────────────┤
│ L9. 解码 WAV 缓存（文件系统: decoded_wav/ 目录）                     │
│    GET /api/v1/decoded-wav/{hash}                                    │
│    非 WAV 文件解码后缓存为 WAV，前端可快速 PCM 解码                    │
├─────────────────────────────────────────────────────────────────────┤
│ L10. 波形缓存（SQLite: analysis_cache 表 waveform_peaks 字段）       │
│     GET /api/v1/waveform/{hash}                                      │
│     服务端预计算的波形峰值数据                                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、数据流与缓存命中路径

### 2.1 文件上传流程

```
用户选择文件
  │
  ├─ 1. computeFileHash(file) → SHA-256
  │
  ├─ 2. 查询后端分析缓存
  │     GET /api/v1/analysis-cache/{hash}
  │     命中 → 跳过 Worker 分析（零计算开销）
  │     未命中 → 继续
  │
  ├─ 3. WAV PCM 解码（Web Worker）
  │     audioWorker.decodeWav(context, arrayBuf)
  │     成功 → AudioBuffer（零主线程阻塞）
  │     失败 → 尝试后端解码缓存 / context.decodeAudioData
  │
  ├─ 4. 音频分析（Web Worker，仅缓存未命中时）
  │     audioWorker.analyzeAudio(channelData, sampleRate, channels)
  │     返回 AudioAnalysisResult（零主线程阻塞）
  │
  ├─ 5. 缓存写入（主线程负责）
  │     POST /api/v1/analysis-cache → 后端分析缓存
  │     saveAnalysisCache() → 前端 IndexedDB 分析缓存
  │
  └─ 6. 后台上传 + 波形缓存
        POST /api/v1/upload → 上传去重
        GET /api/v1/waveform/{hash} → 波形缓存
```

### 2.2 修复流程

```
用户点击"应用修复"
  │
  ├─ 1. 查询修复缓存
  │     POST /api/v1/cache/lookup { file_hash, params }
  │     命中 → 弹出 RepairCacheModal，用户选择使用/重新修复
  │     未命中 → 继续
  │
  ├─ 2. 上传 + 修复
  │     POST /api/v1/repair → WebSocket 进度推送
  │
  ├─ 3. 修复完成 → 加载预览 + 自动渲染
  │     GET /api/v1/preview/{task_id} → AudioBuffer
  │     POST /api/v1/render → 渲染交付规格
  │
  └─ 4. 渲染缓存查询
        GET /api/v1/render-cache/{task_id}
        命中 → 秒下载
        未命中 → 重新渲染
```

### 2.3 Session 恢复流程

```
页面刷新 / 组件挂载
  │
  ├─ 1. loadSession() → IndexedDB 读取会话
  │     无会话 → 结束
  │     有会话 → 继续
  │
  ├─ 2. 验证 File 对象有效性
  │     无效（移动端暂离后 File 失效）→ 清除会话
  │     有效 → 继续
  │
  ├─ 3. Worker 解码 + 分析
  │     audioWorker.decodeAndAnalyze(context, arrayBuf)
  │     一步完成，避免两次 postMessage
  │
  └─ 4. 恢复修复后音频（如果已完成）
        GET /api/v1/preview/{task_id} → AudioBuffer
```

---

## 三、Web Worker 与缓存协同

### 3.1 核心原则：缓存命中 > Worker 计算 > 主线程同步

```
优先级：
  1. 后端分析缓存命中 → 跳过 Worker（零计算开销）
  2. 前端 IndexedDB 分析缓存命中 → 跳过 Worker（零网络开销）
  3. 缓存未命中 → Worker 异步计算（不阻塞 UI）
  4. Worker 不可用 → 主线程同步 fallback（功能不中断）
```

### 3.2 Worker 不直接写缓存

Worker 运行在独立线程，无法访问 `fetch`、`IndexedDB` 等浏览器 API。所有缓存写入由主线程负责：

```
Worker 计算结果 → postMessage → 主线程收到
  → POST /api/v1/analysis-cache（后端缓存）
  → saveAnalysisCache()（前端 IndexedDB 缓存）
```

### 3.3 Transferable 传输优化

Worker 与主线程之间的大数组（Float32Array、ArrayBuffer）使用 Transferable 传输，零拷贝：

```typescript
// Worker → 主线程
self.postMessage(response, [...channelData.map(ch => ch.buffer)]);

// 主线程 → Worker
worker.postMessage({ type: 'decode-wav', id, buffer }, [buffer]);
```

注意：Transferable 传输后，发送方不可再访问该 buffer。

---

## 四、各缓存层详细说明

### 4.1 前端 IndexedDB 会话缓存

**文件**: `src/utils/sessionDB.ts`

**Object Store**: `session`（keyPath: `'id'`，固定 id=`'current'`）

**存储内容**:
```typescript
interface SessionData {
  id: 'current';
  file: File | null;
  fileName: string;
  fileSize: number;
  fileHash: string;
  taskId: string;
  backendAvailable: boolean;
  hasBeenProcessed: boolean;
  wavInfo: string;             // JSON
  repairResult: string;        // JSON
  originalDetectTime: string;
  repairedDetectTime: string;
  processingOptions: string;   // JSON { sampleRate, bitDepth }
}
```

**关键问题**：移动端暂离后 `File` 对象可能失效（`file.size === 0`），恢复时需验证。

### 4.2 前端 IndexedDB 分析缓存

**文件**: `src/utils/sessionDB.ts`

**Object Store**: `analysis_cache`（keyPath: `'fileHash'`，index: `timestamp`）

**存储内容**:
```typescript
interface AnalysisCacheEntry {
  fileHash: string;
  fileName: string;
  fileSize: number;
  wavInfo: string;     // JSON
  analysis: string;    // JSON
  timestamp: number;
}
```

**写入时机**: Worker 分析完成后，主线程调用 `saveAnalysisCache()`

**查询时机**: `loadAudioFile` 中优先查询后端分析缓存，后端不可用时查询前端 IndexedDB

### 4.3 后端分析缓存

**API**:
- `GET /api/v1/analysis-cache/{quick_hash}` — 查询
- `POST /api/v1/analysis-cache` — 写入
- `GET /api/v1/analysis-cache-list` — 列表
- `DELETE /api/v1/analysis-cache/{quick_hash}` — 删除
- `POST /api/v1/analysis-cache-clear` — 清空

**存储**: SQLite `analysis_cache` 表

**字段**: `quick_hash`, `file_name`, `file_size`, `wav_info`, `analysis`, `waveform_peaks`, `created_at`

### 4.4 修复结果缓存

**API**: `POST /api/v1/cache/lookup`

**匹配规则**: `(file_hash + repair_params)` → `(output_path + repair_result + detection_results)`

**查询实现**: `backend/database.py::find_repair_cache()`

**关键设计**:
- 不依赖 `status` 字段（状态会变化）
- 依赖输出文件存在性 + 大小 > 10KB
- JSON 规范化比较参数（`sort_keys=True`）

### 4.5 渲染缓存

**API**: `GET /api/v1/render-cache/{task_id}`

**匹配规则**: `(task_id + sample_rate + bit_depth + algorithm_version)` → WAV 文件

**存储**: 文件系统 `output/` 目录

**秒下载**: 缓存命中时直接返回下载 URL，无需重新渲染

### 4.6 解码 WAV 缓存

**API**:
- `GET /api/v1/decoded-wav/{hash}` — 下载已解码 WAV
- `POST /api/v1/decoded-wav/{hash}` — 触发解码缓存创建

**目的**: 非 WAV 文件（MP3/FLAC）解码后缓存为 WAV，前端可使用快速 PCM 解码路径

### 4.7 波形缓存

**API**: `GET /api/v1/waveform/{hash}`

**存储**: `analysis_cache` 表的 `waveform_peaks` 字段

**计算时机**: 首次上传时后端计算并缓存

---

## 五、缓存一致性策略

### 5.1 写入时验证

- 后端：修复完成后验证输出文件大小 > 10KB，无效输出不写入缓存
- 前端：缓存命中后二次确认（RepairCacheModal 弹窗）

### 5.2 读取时验证

```python
# 1. 文件存在性检查
if not os.path.exists(output_path):
    return None

# 2. 文件大小检查（防止损坏）
if size < 10240:
    return None

# 3. 参数精确匹配
if json.dumps(stored_params, sort_keys=True) != json.dumps(params, sort_keys=True):
    return None
```

### 5.3 清理策略

**手动清理**: CacheManagerPage 提供以下操作：
- 清空所有缓存 (`POST /api/v1/cache/clear-all`)
- 清空输出缓存 (`POST /api/v1/cache/clear-output`)
- 清空渲染缓存 (`POST /api/v1/cache/clear-render`)
- 清空上传缓存 (`POST /api/v1/cache/clear-upload`)
- 删除指定任务 (`POST /api/v1/cache/delete/{task_id}`)
- 清理无效缓存 (`POST /api/v1/cache/clean-invalid`)

---

## 六、经验教训

### ❌ 错误1：缓存查询依赖任务状态

早期实现加了 `status='completed'` 过滤，导致任务状态变化时缓存失效。正确做法是查所有任务，用输出文件存在性判断。

### ❌ 错误2：会话恢复覆盖新文件

上传新文件后 `backendAvailable` 变化触发旧会话恢复。修复：上传成功后清除 `pendingSessionRef`。

### ❌ 错误3：前端只写后端分析缓存，不写前端 IndexedDB

导致后端不可用时无法命中分析缓存。修复：Worker 化后同时写入前端 IndexedDB 分析缓存。

### ❌ 错误4：Session 恢复用旧数据覆盖实时解析结果

Session restore 流程中，`wavInfo` 先从实际文件头解析（`parseWavHeader`）和/或后端 API 获取，最后又用 session 中保存的旧 `wavInfo` 覆盖。这导致：
- 非 WAV 文件：session 中 `wavInfo` 为空字符串（`parseWavHeader` 返回 null），覆盖了 API 获取的准确数据
- WAV 文件：session 中 `wavInfo` 可能缺少字段或 duration 不精确，覆盖了更准确的数据
- 交付规格块因 `duration <= 0` 显示"加载音频后显示预估大小"

**修复**：删除 session restore 中 `setWavInfo(JSON.parse(session.wavInfo))`，不再用旧数据覆盖实时解析结果。

### ❌ 错误5：saveSession 保存中间变量而非最终 state

`saveSession` 在 async 函数中调用时，使用闭包捕获的 `wavHeaderInfo`（中间变量）而非最终的 `wavInfo` state。由于 React 18 批量更新，`setWavInfo(infoFromApi)` 调用后 state 尚未更新，闭包中的 `wavHeaderInfo` 仍为旧值。

**修复**：使用 `wavInfoRef` 追踪最新 `wavInfo`，`saveSession` 时读取 `wavInfoRef.current`。

### ❌ 错误6：processingOptions 未纳入 session 持久化

`processingOptions`（sampleRate/bitDepth）只从 localStorage `loadSettings()` 初始化，不保存在 session 中。用户修改导出选项后刷新页面，选项丢失。AIRepairPanel 的预估大小计算依赖 `processingOptions`，恢复后可能显示错误。

**修复**：在 `SessionData` 中添加 `processingOptions` 字段，`saveSession` 时写入，session restore 时恢复。

### ❌ 错误7：File 对象在 IndexedDB 中跨刷新失效

`File` 对象通过结构化克隆算法存入 IndexedDB，但页面刷新后底层 Blob 数据可能不可读（`file.arrayBuffer()` 抛异常）。旧代码在读取失败时直接 `clearSession()`，导致 session 被永久删除，后续刷新无法恢复。

**修复**：当 `file.arrayBuffer()` 失败时，从后端重新下载原始音频（`/api/v1/preview/{task_id}?type=original`），创建新 File 对象继续恢复流程。成功恢复后重新 `saveSession` 刷新 IndexedDB 中的 File 对象。

### ❌ 错误8：两个 useEffect 之间的时序竞态

原设计用两个 useEffect 协调 session 恢复：
- useEffect #1 (deps=[])：异步 `loadSession()` → 写入 `pendingSessionRef`
- useEffect #2 (deps=[backendAvailable])：检查 `pendingSessionRef` 有值后恢复

当后端快速响应时，`backendAvailable` 在 `loadSession()` 完成前就变为 `true`，useEffect #2 提前触发并跳过（`pendingSessionRef` 还是 null），之后不再重新触发。

**修复**：合并为单个 useEffect (deps=[backendAvailable])，在 `backendAvailable` 变为 true 时同步执行 `loadSession()` + 恢复，消除竞态。

### ✅ 最佳实践1：数据驱动缓存

缓存应是纯数据映射，与业务逻辑状态解耦：
```
(fileHash + params) → (outputFile)
```

### ✅ 最佳实践2：参数规范化

使用 JSON `sort_keys` 确保参数比较不受键顺序影响。

### ✅ 最佳实践3：缓存优先于 Worker

后端分析缓存命中时完全跳过 Worker，避免不必要的通信和计算开销。

### ✅ 最佳实践4：Worker fallback

Worker 创建失败时 fallback 到主线程同步处理，确保功能不中断。

---

## 七、相关文件

| 文件 | 说明 |
|------|------|
| `src/workers/audioWorker.ts` | Web Worker：WAV PCM 解码 + 音频分析 |
| `src/workers/useAudioWorker.ts` | Worker 管理 hook：生命周期、消息通信、fallback |
| `src/utils/sessionDB.ts` | IndexedDB 会话缓存 + 分析缓存 |
| `src/utils/wavParser.ts` | WAV 头解析（主线程轻量使用） |
| `src/utils/advancedAudioProcessing.ts` | 类型定义（AIRepairParams, RepairMode 等） |
| `src/hooks/useAudioProcessor.ts` | 核心状态管理，缓存查询与写入 |
| `src/services/backendApi.ts` | 后端 API 调用（缓存查询、上传、渲染） |
| `src/components/RepairCacheModal.tsx` | 修复缓存命中弹窗 |
| `src/pages/CacheManagerPage.tsx` | 缓存管理页面 |
| `backend/database.py` | 数据库操作，含 `find_repair_cache()` |
| `backend/api/routes.py` | API 端点，含所有缓存相关路由 |

---

## 八、版本历史

- **v1.0**: 基础修复结果缓存（有 status 过滤 bug）
- **v2.0**: 重构为纯数据驱动缓存，去掉 status 依赖
- **v2.1**: 修复文件替换后会话覆盖问题
- **v3.0**: Web Worker 化 + 前端 IndexedDB 分析缓存 + 缓存协同优化
- **v3.1**: 修复 session restore 覆盖问题 + processingOptions 持久化 + wavInfoRef 追踪
- **v3.2**: File 对象失效后端兜底下载 + useEffect 合并消除竞态 + 恢复后刷新 session

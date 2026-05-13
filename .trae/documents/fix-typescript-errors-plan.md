# TypeScript 类型错误修复计划

## 概述

当前项目中存在 12 个 TypeScript 类型错误，分布在 4 个文件中。这些错误并非本次双轨重构引入的新问题，而是项目中已经存在的存量错误。本计划旨在系统地修复这些错误。

## 当前状态分析

### 错误清单

#### 1. `src/hooks/useAudioProcessor.ts` — 7 个错误

| 行号 | 错误 | 原因 |
|------|------|------|
| 636 | `missing originalDetectTime, repairedDetectTime` | `saveSession()` 需要 `SessionData` 类型，但调用时缺少这两个字段 |
| 973 | 同上 | 同上（另一处调用） |
| 1111 | `BackendRepairResult` 不能赋值给 `{ [key: string]: unknown; issues_found?: string[]; }` | `cacheHitInfo.repair.repair_result` 是 `BackendRepairResult` 类型，但 `setCacheHitInfo` 期望的 `repair_result` 是 `{ [key: string]: unknown; issues_found?: string[]; }` |
| 1279 | `missing originalDetectTime, repairedDetectTime` | 同上（另一处调用） |
| 1909 | `{ completed_at: string; issues_found?: string[]; }` 缺少必要属性 | `setRepairResult()` 期望完整对象，但只传了部分字段 |
| 1914 | `unknown` 不能赋值给 `SetStateAction<number[][]>` | `cache.repair_result.waveform_peaks` 在上下文中被推断为 `unknown` |
| 1931 | `missing originalDetectTime, repairedDetectTime` | 同上（另一处调用） |

#### 2. `src/pages/DetectPage.tsx` — 3 个错误

| 行号 | 错误 | 原因 |
|------|------|------|
| 71 | `Cannot find name 'useBackend'` | `DetectPage.tsx` 没有导入 `useBackend` |
| 181 | `missing detectTime` | `setSlot()` 设置状态时缺少 `detectTime` 字段 |
| 198 | `missing detectTime` | 同上 |

#### 3. `src/workers/audioWorker.ts` — 2 个错误

| 行号 | 错误 | 原因 |
|------|------|------|
| 318 | `ArrayBuffer[]` 不能作为 `postMessage` 的第二个参数 | Worker `postMessage` 的 transfer 参数类型是 `Transferable[]`，但 `ArrayBuffer[]` 不被接受 |
| 334 | 同上 | 同上 |

## 修复方案

### 修复 1：`src/hooks/useAudioProcessor.ts` — `saveSession()` 缺少字段

**问题**：`saveSession()` 的签名是 `(data: Omit<SessionData, 'id'>)`，但 `SessionData` 包含 `originalDetectTime` 和 `repairedDetectTime` 字段。

**方案 A（推荐）**：将 `SessionData` 中这两个字段改为可选 (`originalDetectTime?: string`)，因为它们不是必填的。

**方案 B**：在所有 `saveSession()` 调用处补上这两个字段，传入空字符串。

**选择方案 A**，因为这两个检测时间字段对于会话恢复不是必需的，改为可选更合理。

**文件**：
- `src/utils/sessionDB.ts` — 修改 `SessionData` 接口

### 修复 2：`src/hooks/useAudioProcessor.ts` — `BackendRepairResult` 类型不匹配

**问题**：`CacheHitInfo.repair.repair_result` 的类型是 `{ [key: string]: unknown; issues_found?: string[]; }`，但实际赋值的 `cacheResult.repair_result` 是 `BackendRepairResult`。

**方案**：在 `RepairCacheModal.tsx` 中修改 `CacheHitInfo` 的 `repair_result` 类型为 `BackendRepairResult | undefined`，或者在赋值时做类型断言。

**选择**：修改 `CacheHitInfo` 类型，使用 `BackendRepairResult` 替代 `{ [key: string]: unknown; ... }`。

**文件**：
- `src/components/RepairCacheModal.tsx` — 修改 `CacheHitInfo` 接口中的 `repair_result` 类型

### 修复 3：`src/hooks/useAudioProcessor.ts` — `setRepairResult()` 参数不完整

**问题**：第 1909 行 `setRepairResult({ ...cache.repair_result, completed_at: ... })` 中，`cache.repair_result` 的类型不够精确，导致展开后的对象缺少部分必需属性。

**方案**：使用类型断言 `cache.repair_result as BackendRepairResult` 确保展开后类型正确。

**文件**：
- `src/hooks/useAudioProcessor.ts` — 在第 1909 行添加类型断言

### 修复 4：`src/hooks/useAudioProcessor.ts` — `waveform_peaks` 类型为 `unknown`

**问题**：`cache.repair_result.waveform_peaks` 被推断为 `unknown`，不能传给 `setBackendWaveformPeaks`。

**方案**：添加类型断言 `as number[][] | undefined`。

**文件**：
- `src/hooks/useAudioProcessor.ts` — 在第 1914 行添加类型断言

### 修复 5：`src/pages/DetectPage.tsx` — 缺少 `useBackend` 导入

**问题**：第 71 行使用了 `useBackend()` 但没有导入。

**方案**：添加导入语句。

**文件**：
- `src/pages/DetectPage.tsx` — 添加 `import { useBackend } from '../contexts/BackendContext';`

### 修复 6：`src/pages/DetectPage.tsx` — `setSlot()` 缺少 `detectTime`

**问题**：`DetectSlotState` 要求 `detectTime: string`，但 `setSlot()` 调用时没有包含此字段。

**方案**：在两个 `setSlot()` 调用处添加 `detectTime: ''`。

**文件**：
- `src/pages/DetectPage.tsx` — 第 181 行和第 198 行添加 `detectTime: ''`

### 修复 7：`src/workers/audioWorker.ts` — `postMessage` transfer 参数类型

**问题**：`self.postMessage(response, transfer)` 中 `transfer` 是 `ArrayBuffer[]`，但 TypeScript 的 `postMessage` 重载期望第二个参数是 `string`（targetOrigin）或 `WindowPostMessageOptions`。

**方案**：在 Worker 环境中，`self.postMessage()` 的正确签名是 `postMessage(message: any, transfer?: Transferable[])`。需要添加类型断言 `transfer as unknown as Transferable[]` 或使用 `(transfer as any)`。

**文件**：
- `src/workers/audioWorker.ts` — 第 318 行和第 334 行添加类型断言

## 修改清单

| 文件 | 修改内容 | 风险 |
|------|---------|------|
| `src/utils/sessionDB.ts` | `SessionData.originalDetectTime` 和 `repairedDetectTime` 改为可选 | 低 — 下游使用处已有空字符串默认值 |
| `src/components/RepairCacheModal.tsx` | `CacheHitInfo.repair_result` 类型改为 `BackendRepairResult \| undefined` | 低 — 类型更精确 |
| `src/hooks/useAudioProcessor.ts` | 4 处类型断言修复 | 低 — 运行时行为不变 |
| `src/pages/DetectPage.tsx` | 添加 import + 2 处补字段 | 低 |
| `src/workers/audioWorker.ts` | 2 处类型断言 | 低 — Worker 运行时正确 |

## 验证步骤

1. 运行 `npm run check` 确认所有类型错误已修复
2. 运行 `npm run build` 确认构建成功
3. 启动开发服务器 `bash scripts/start_dev.sh` 验证页面正常加载

## 未包含的范围

- 本次不重构 `useAudioProcessor.ts` 的类型系统
- 不修改运行时逻辑，仅修复类型定义
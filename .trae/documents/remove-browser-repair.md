# 彻底移除浏览器修复功能

## 摘要

后端修复速度和效果已足够好，浏览器修复不再需要。彻底移除所有浏览器修复相关代码，包括 Worker、状态、UI 控件、下载逻辑等。

## 当前状态分析

浏览器修复涉及以下文件和代码：

### 1. `/workspace/src/hooks/useAudioProcessor.ts`（核心）
- `PlayMode` 类型包含 `'browser'`（L47）
- `createRepairWorker()` 函数（L56-58）
- `browserProcessedBuffer` 状态（L130）
- `browserRepairInfo` 状态（L172-175）
- `enableBrowserRepair` / `setEnableBrowserRepair` 状态（L186）
- `browserProcessedBufferRef` ref（L216）
- `workerRef` ref（L207）— 仅用于浏览器修复 Worker
- `repairWithWorker` 函数（L1016-1081）— 浏览器修复核心
- `encodeWavWithWorker` 函数（L1083-1140）— 浏览器 WAV 编码
- `browserRepairPromise` 整个分支（L1314-1412）— applySettings 中的浏览器修复并行逻辑
- `browserResult` 处理（L1456-1460）
- `downloadProcessedAudio('browser')` 函数（L2061-2100）
- `getCurrentBuffer` 中的 `'browser'` 分支（L1668）
- `switchPlayMode` 中的 `'browser'` 分支（L1865）
- `currentSampleRate` 中的 `'browser'` 分支（L2110）
- `processingSource` 类型包含 `'browser'`（L139）
- return 对象中的 `browserProcessedBuffer`, `browserRepairInfo`, `enableBrowserRepair`, `setEnableBrowserRepair`
- `audioBufferToWav` 辅助函数（L2295+）— 仅被浏览器下载 fallback 使用
- `highFrequencyEnhancer` 动态 import（L1319）— 仅浏览器修复使用

### 2. `/workspace/src/components/AIRepairPanel.tsx`
- `enableBrowserRepair` prop（L20）
- `onEnableBrowserRepairChange` prop（L27）
- 浏览器修复开关 UI（L784-795）

### 3. `/workspace/src/pages/RepairPage.tsx`
- `browserProcessedBuffer` 解构（L16）
- `browserRepairInfo`, `enableBrowserRepair`, `setEnableBrowserRepair` 解构（L58-60）
- `hasBrowserResult` 变量（L170）
- `browserBufferInfo` 变量（L173-177）
- `enableBrowserRepair` prop 传递（L380）
- `onEnableBrowserRepairChange` prop 传递（L387）
- DownloadModal 的 `browserInfo` 和 `browserDownloadAction`（L463-480）

### 4. `/workspace/src/pages/Home.tsx`
- `browserProcessedBuffer` 解构（L15）
- `enableBrowserRepair` 解构（L54）
- `browserRepairInfo` 解构（L59）
- `hasBrowserResult` 变量（L72）
- `activeBuffer` 中的 `'browser'` 分支（L75）
- `browserBufferInfo` 变量（L79-83）
- `enableBrowserRepair` prop 传递（L251）
- DownloadModal 的 `browserInfo` 和 `browserDownloadAction`（L333-340）

### 5. `/workspace/src/components/DownloadModal.tsx`
- `browserInfo` 和 `browserDownloadAction` props
- 浏览器下载 UI 区域

### 6. 可删除的文件
- `/workspace/src/utils/highFrequencyEnhancer.ts` — 仅浏览器修复使用
- `/workspace/src/utils/advancedAudioProcessing.ts` 中的 `processWithAIRepair` 函数 — 死代码

### 7. Worker 文件
- `audioRepairWorker` 通过 `new URL('../workers/audioRepairWorker.ts', import.meta.url)` 动态引用，但实际文件不在 workers/ 目录中（可能由 Vite 虚拟模块处理或已被删除）。`createRepairWorker` 函数需要移除。

## 实施计划

### Step 1: useAudioProcessor.ts — 移除浏览器修复核心

1. **PlayMode 类型**：`'original' | 'browser' | 'backend'` → `'original' | 'backend'`
2. **移除 `createRepairWorker` 函数**（L56-58）
3. **移除状态变量**：
   - `browserProcessedBuffer` / `setBrowserProcessedBuffer`
   - `browserRepairInfo` / `setBrowserRepairInfo`
   - `enableBrowserRepair` / `setEnableBrowserRepair`
   - `workerRef`
4. **移除 ref**：`browserProcessedBufferRef`
5. **移除 `repairWithWorker` 函数**（L1016-1081）
6. **移除 `encodeWavWithWorker` 函数**（L1083-1140）
7. **简化 `applySettings`**：
   - 移除 `browserRepairPromise` 整个分支（L1314-1412）
   - 移除 `browserProg` 相关逻辑
   - `Promise.allSettled` 改为只等 `backendRepairPromise`
   - 移除 `browserResult` 处理（L1456-1460）
   - 移除依赖数组中的 `repairWithWorker`, `enableBrowserRepair`
8. **移除 `downloadProcessedAudio` 函数**（L2061-2100）— 浏览器下载
9. **简化 `getCurrentBuffer`**：移除 `'browser'` 分支
10. **简化 `switchPlayMode`**：移除 `'browser'` 分支
11. **简化 `currentSampleRate`**：移除 `'browser'` 分支
12. **`processingSource` 类型**：`'backend' | 'browser' | null` → `'backend' | null`
13. **移除 `setBrowserProcessedBuffer(null)` 调用**（loadAudioFile 中）
14. **移除 `audioBufferToWav` 辅助函数**（文件末尾）
15. **移除 return 对象中的**：`browserProcessedBuffer`, `browserRepairInfo`, `enableBrowserRepair`, `setEnableBrowserRepair`, `downloadProcessedAudio`
16. **移除 `highFrequencyEnhancer` 动态 import**

### Step 2: AIRepairPanel.tsx — 移除浏览器修复开关

1. 移除 `enableBrowserRepair` prop
2. 移除 `onEnableBrowserRepairChange` prop
3. 移除浏览器修复开关 UI（checkbox + label）

### Step 3: RepairPage.tsx — 移除浏览器修复引用

1. 移除解构中的 `browserProcessedBuffer`, `browserRepairInfo`, `enableBrowserRepair`, `setEnableBrowserRepair`
2. 移除 `hasBrowserResult`, `browserBufferInfo` 变量
3. 移除 AIRepairPanel 的 `enableBrowserRepair` / `onEnableBrowserRepairChange` props
4. 移除 DownloadModal 的 `browserInfo` / `browserDownloadAction` props

### Step 4: Home.tsx — 移除浏览器修复引用

1. 移除解构中的 `browserProcessedBuffer`, `enableBrowserRepair`, `browserRepairInfo`
2. 移除 `hasBrowserResult`, `browserBufferInfo` 变量
3. 移除 `activeBuffer` 中的 `'browser'` 分支
4. 移除 AIRepairPanel 的 `enableBrowserRepair` prop
5. 移除 DownloadModal 的 `browserInfo` / `browserDownloadAction` props

### Step 5: DownloadModal.tsx — 移除浏览器下载

1. 移除 `browserInfo` / `browserDownloadAction` props
2. 移除浏览器下载 UI 区域
3. 移除 `browserFilename` 状态和相关逻辑

### Step 6: 删除仅浏览器修复使用的文件

1. 删除 `/workspace/src/utils/highFrequencyEnhancer.ts`

### Step 7: 清理 advancedAudioProcessing.ts

1. 移除 `processWithAIRepair` 函数（死代码）

### Step 8: 构建验证

```bash
npm run build
bash scripts/build_android_release.sh
```

## 假设与决策

- **`encodeWavWithWorker` 也移除**：该函数仅被浏览器下载使用，后端下载走 render API 不需要 Worker 编码
- **`audioBufferToWav` 也移除**：仅被浏览器下载 fallback 使用
- **`workerRef` 也移除**：仅用于浏览器修复 Worker
- **DownloadModal 的浏览器部分也移除**：不再有浏览器修复结果可下载
- **`processingSource` 保留 `'backend' | null`**：仍需显示后端处理进度
- **`detectAudioIssues` 保留**：这是音频分析功能，不是浏览器修复

# 诊断修复 + 双轨界面补全 + 打包启动

## 当前状态分析

### 已完成
1. **BackendContext.tsx** - `FrontendDiag` 接口已定义，`getFrontendDiag()` 已实现，catch 块已构建前端诊断数据
2. **Header.tsx** - 复制按钮条件改为 `!isDiagLoading`，前端诊断区块已添加
3. **后端 /api/v1/diag** - 已实现，返回 backend/python/ffmpeg/memory/storage/gpu/system/runtime/directories/process

### 待修复问题

#### 问题1：复制按钮不可见
- **根因**：Header.tsx L257 复制按钮条件 `{!isDiagLoading && (...)}` — 当诊断面板首次打开时 `isDiagLoading=true`，按钮不显示；但更关键的是 L392 的 else 分支 `backendDiag` 为 null 时显示 `$ error: no response from backend`，此时复制按钮确实不可见（因为 `backendDiag` 为 null，handleCopy 函数 L113-117 检查 `if (backendDiag)` 不会执行复制）
- **修复**：
  1. 复制按钮改为始终显示（不受 `isDiagLoading` 限制），加载中时 disabled
  2. handleCopy 在 `backendDiag` 为 null 时也生成前端诊断文本
  3. else 分支（`backendDiag` 为 null）显示前端本地诊断信息而非仅 `$ error: no response from backend`

#### 问题2：诊断信息不足
- **根因**：`runBackendDiag` 首次打开面板时如果后端不可达，`backendDiag` 仍为 null（因为 `runBackendDiag` 是异步的，`setIsDiagLoading(false)` 后才设置 `backendDiag`）
- **修复**：在 `handleDiagnose` 中，打开面板时立即设置一个包含前端诊断的初始 `backendDiag`，不等后端响应

#### 问题3：双轨修复界面不完整
- **现状**：AIRepairPanel 在 `isDualTrackMode` 时 `onApply={undefined}`，"开始修复"按钮无功能；修复参数区域在双轨模式下仍然显示通用参数
- **需要**：
  1. 双轨模式显示独立的参数面板：人声参数 + 伴奏参数 + 混合比例
  2. "开始修复"按钮在双轨模式下触发 `handleDualTrackUpload`（重新修复）
  3. RepairPage 需要管理双轨参数状态

## 实施计划

### Step 1: 修复 Header.tsx 复制按钮 + 诊断信息

**文件**: `/workspace/src/components/Header.tsx`

1. 复制按钮始终显示，加载中时 disabled + 显示加载图标
2. `handleCopy` 函数：当 `backendDiag` 为 null 时，生成纯前端诊断文本
3. else 分支（`backendDiag` 为 null）：显示前端本地诊断信息（浏览器、网络、视口等），而非仅 `$ error: no response from backend`
4. `buildCopyText` 函数增加无后端数据时的纯前端报告格式

### Step 2: 修复 BackendContext.tsx 诊断初始化

**文件**: `/workspace/src/contexts/BackendContext.tsx`

1. 新增 `setBackendDiagDirect` 方法，允许外部直接设置 `backendDiag`（用于面板打开时立即显示前端诊断）
2. 或在 `runBackendDiag` 开始时立即设置一个前端诊断初始值

### Step 3: AIRepairPanel 双轨参数面板

**文件**: `/workspace/src/components/AIRepairPanel.tsx`

1. 新增 props：
   - `vocalParams: AIRepairParams` — 人声修复参数
   - `accompanimentParams: AIRepairParams` — 伴奏修复参数
   - `mixRatio: number` — 人声/伴奏混合比例 (0-1, 0=纯伴奏, 1=纯人声, 0.5=均衡)
   - `onVocalParamChange: (key: keyof AIRepairParams, value: number) => void`
   - `onAccompanimentParamChange: (key: keyof AIRepairParams, value: number) => void`
   - `onMixRatioChange: (ratio: number) => void`
   - `onDualTrackRepair?: () => void` — 双轨修复触发

2. 双轨模式下：
   - 隐藏通用"修复参数"区域
   - 显示"人声参数"折叠区 + "伴奏参数"折叠区 + "混合比例"滑块
   - "开始修复"按钮调用 `onDualTrackRepair`
   - 预设模式仍然可用（同时应用到人声和伴奏参数）

3. 人声参数标签使用粉色/红色系标识
4. 伴奏参数标签使用紫色/蓝色系标识
5. 混合比例滑块：0=纯伴奏 ← → 1=纯人声，中间标注"均衡"

### Step 4: RepairPage 双轨参数状态管理

**文件**: `/workspace/src/pages/RepairPage.tsx`

1. 新增状态：
   - `dualTrackVocalParams: AIRepairParams` — 初始值 `defaultAIRepairParams`
   - `dualTrackAccompanimentParams: AIRepairParams` — 初始值 `defaultAIRepairParams`
   - `mixRatio: number` — 初始值 0.5

2. 传递给 AIRepairPanel：
   - `vocalParams={dualTrackVocalParams}`
   - `accompanimentParams={dualTrackAccompanimentParams}`
   - `mixRatio={mixRatio}`
   - `onVocalParamChange` / `onAccompanimentParamChange` / `onMixRatioChange`
   - `onDualTrackRepair` — 触发双轨修复（调用已有的 `handleDualTrackUpload` 或新逻辑）

3. 双轨修复触发逻辑：
   - 如果已上传文件（`dualTrackVocalFile` 和 `dualTrackAccompanimentFile` 存在），直接调用 `repairDualAudio`
   - 如果未上传，提示先上传文件

### Step 5: 验证后端 /api/v1/diag 接口

1. 启动后端，`curl /api/v1/diag` 验证返回数据格式
2. 确认前端能正确解析

### Step 6: 打包 + 启动 dev

1. `bash scripts/build_android_release.sh`
2. `bash scripts/start_dev.sh`
3. 使用 OpenPreview 激活预览

## 假设与决策

- 双轨参数独立于人声/伴奏，不共享单轨的 `params` 状态
- 混合比例默认 0.5（均衡），范围 0-1
- 双轨修复按钮只在已上传文件后可用
- 预设模式在双轨模式下同时应用到人声和伴奏参数
- 复制按钮始终可见，加载中 disabled

# 双轨界面修复：模式切换常驻 + 去掉独立处理按钮 + 复用组件

## 当前状态分析

### 问题1：模式切换只在无文件时显示
- RepairPage.tsx L436: `{!audioFile && !dualTrackHasBeenProcessed ? (上传区) : (工作区)}`
- 模式切换按钮（单轨上传/双轨上传）在上传区里，一旦上传文件进入工作区就消失了
- 用户要求：**模式切换始终显示**，无论是否已上传文件

### 问题2：DualTrackUploader 有独立的"开始双轨处理"按钮
- DualTrackUploader.tsx L155-165: 有自己的 `handleSubmit` 按钮
- 但这个按钮的 `onFilesSelect` 回调在之前 prop 名不匹配（已修复为 `onFilesSelect`）
- 用户要求：**去掉这个按钮**，统一用 AIRepairPanel 的"开始修复"按钮
- 上传文件后应直接进入工作区，由 AIRepairPanel 的"双轨修复"按钮触发处理

### 问题3：双轨上传后不进入工作区
- `handleDualTrackUpload` 只上传文件并触发修复，但没有设置 `audioFile` 等状态让页面切换到工作区
- 上传后仍停留在上传区，看不到 AIRepairPanel 的双轨参数面板

### 问题4：模式切换应始终可见
- 需要将模式切换从上传区提取出来，放到页面顶部始终显示
- 切换模式时应重置状态回到上传区

## 实施计划

### Step 1: 将模式切换提取到页面顶部（始终显示）

**文件**: `/workspace/src/pages/RepairPage.tsx`

1. 将模式切换按钮（单轨上传/双轨上传）从 L438-461 的上传区移到 L435 `<div className="container">` 的最顶部
2. 模式切换始终可见，不受 `audioFile` 或 `dualTrackHasBeenProcessed` 影响
3. 切换模式时：
   - 单轨→双轨：`setIsDualTrackMode(true)` + 重置单轨状态
   - 双轨→单轨：`setIsDualTrackMode(false)` + 重置双轨状态

### Step 2: DualTrackUploader 去掉"开始双轨处理"按钮

**文件**: `/workspace/src/components/DualTrackUploader.tsx`

1. 删除 L155-165 的"开始双轨处理"按钮
2. 删除 L167-172 的提示文字
3. 修改 `onFilesSelect` 回调语义：**两个文件都选好后自动触发**（不再需要手动点按钮）
4. 或者保留手动触发但改为更轻量的"确认上传"按钮

**决策**：两个文件都选好后自动触发 `onFilesSelect`，去掉按钮。这样用户体验更流畅——选好文件即上传，然后在 AIRepairPanel 中点"双轨修复"开始处理。

### Step 3: 修复双轨上传后进入工作区

**文件**: `/workspace/src/pages/RepairPage.tsx`

1. `handleDualTrackUpload` 中，上传成功后设置一个标记让页面切换到工作区
2. 方案：设置一个 `dualTrackFilesSelected` 状态，当双轨文件选择后为 true
3. 修改页面条件渲染：`{(!audioFile && !dualTrackFilesSelected) ? (上传区) : (工作区)}`
4. 在工作区中，双轨模式显示已上传的文件信息 + AIRepairPanel（含双轨参数）

### Step 4: AIRepairPanel 双轨模式"开始修复"按钮

**文件**: `/workspace/src/components/AIRepairPanel.tsx`

- 已有 `onDualTrackRepair` 回调，按钮已改为"双轨修复"
- 确保按钮在双轨模式下正确触发 `handleDualTrackRepair`

## 假设与决策

- 模式切换始终在页面顶部，不在上传区内部
- DualTrackUploader 两个文件选好后自动回调，不需要额外按钮
- 双轨上传后自动进入工作区（显示文件信息 + AIRepairPanel）
- AIRepairPanel 的"双轨修复"按钮是唯一的修复触发点

# 双轨模式修复计划

## 问题描述

1. 双轨模式下预估大小显示占位符（"—"），没有正确计算
2. 渲染缓存详情卡片没有适配双轨模式
3. 双轨修复后会自动合并，根据用户要求应该保持独立轨道，最后根据前端请求决定是否合并
4. 占位符需要修改，每个规格格子内单独显示占位，缓存详情卡片依赖规格格子显示

## 核心原则

- 修复后保持独立的人声和伴奏轨道，不自动合并
- 渲染时缓存两个独立轨道
- 根据前端请求决定交付时是否合并
- 双轨模式下预估大小按双倍计算（人声+伴奏）

## 实施步骤

### 1. 前端：保存双轨音频信息（RepairPage）

在 `src/pages/RepairPage.tsx` 中：
- 上传双轨后，保存返回的 `vocal_info` 和 `accompaniment_info`
- 计算双轨的总 duration（取人声和伴奏中较长的那一个）
- 将双轨 duration 和相关信息传递给 AIRepairPanel

### 2. 前端：适配 AIRepairPanel 组件

在 `src/components/AIRepairPanel.tsx` 中：
- 双轨模式下使用双轨 duration 计算预估大小
- 双轨模式下预估大小按双倍计算（人声+伴奏各一份）
- 修改渲染缓存查询，支持双轨缓存
- 每个规格格子内显示单独的占位符

### 3. 后端：修改双轨修复逻辑

在 `backend/api/routes.py` 中：
- 双轨修复时保存两个独立轨道（人声和伴奏）
- 不自动合并
- 在任务信息中保存两个轨道的文件路径

### 4. 后端：修改双轨渲染和缓存逻辑

在 `backend/api/routes.py` 和 `backend/services/render.py` 中：
- 支持双轨渲染缓存查询
- 支持双轨渲染（分别缓存人声和伴奏）
- 添加合并选项到渲染请求中
- 保存双轨的缓存信息

### 5. 前端：修改下载逻辑，支持双轨交付

在 `src/pages/RepairPage.tsx` 和相关下载组件中：
- 支持双轨交付（人声+伴奏）
- 支持合并后单轨交付
- 更新下载选项UI

## 需要修改的文件

### 前端
1. `src/pages/RepairPage.tsx`
2. `src/components/AIRepairPanel.tsx`
3. `src/services/backendApi.ts`（可能需要）

### 后端
1. `backend/api/routes.py`
2. `backend/services/render.py`
3. `backend/services/task_manager.py`（可能需要）
4. `backend/services/repair/repair_v3_0/core.py`
5. `backend/services/repair/repair_v3_0a/core.py`

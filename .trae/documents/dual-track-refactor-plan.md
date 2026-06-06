# 双轨模式适配计划

## 问题分析

根据用户需求，当前双轨模式存在以下问题：

1. **修复后自动合并**：目前修复后会自动将人声和伴奏混合成单轨
2. **预估大小计算不准确**：在双轨模式下，预估文件大小没有考虑双轨的情况
3. **渲染缓存适配不足**：没有针对双轨模式的渲染缓存处理
4. **缓存详情卡片未适配**：渲染缓存详情卡片在双轨模式下显示异常

## 正确的处理逻辑

用户明确要求：
- 修复后保持双轨，不合并
- 渲染也是双轨，需要缓存
- 最后根据前端请求决定是否合并交付

## 需要修改的文件

### 后端

1. **`/workspace/backend/services/repair/repair_v3_0/core.py`**
   - 修改 `repair_audio` 函数，保存单独的人声和伴奏修复结果，而不是混合
   - 确保人声和伴奏都以各自的轨道保存

2. **`/workspace/backend/services/repair/repair_v3_0a/core.py`**
   - 对 v3.0a 做同样的修改

3. **`/workspace/backend/api/routes.py`**
   - 修改渲染相关的 API，支持双轨渲染
   - 修改 `get_render_cache` API，支持双轨渲染缓存查询
   - 修改 `render_audio_endpoint` API，支持双轨渲染
   - 添加支持合并交付的选项

4. **`/workspace/backend/services/render.py`**
   - 修改渲染函数，支持处理双轨输入

### 前端

5. **`/workspace/src/components/AIRepairPanel.tsx`**
   - 修改预估文件大小计算，在双轨模式下计算两个轨道的总大小
   - 适配渲染缓存查询和显示，支持双轨缓存
   - 修改缓存详情卡片，支持双轨显示

6. **`/workspace/src/pages/RepairPage.tsx`**
   - 调整双轨修复后的处理逻辑
   - 添加选项让用户选择是否合并交付
   - 适配双轨渲染和下载流程

7. **`/workspace/src/hooks/useAudioProcessor.ts`**
   - 支持双轨模式的渲染缓存查询和处理

## 实现步骤

### 步骤 1: 修改后端修复逻辑

- 修改 `repair_v3_0/core.py` 和 `repair_v3_0a/core.py` 的 `repair_audio` 函数
- 确保保存独立的人声和伴奏轨道，而不是自动合并
- 在任务结果中记录人声和伴奏的输出路径

### 步骤 2: 修改后端渲染和缓存逻辑

- 更新 `render_audio_endpoint` 支持双轨渲染
- 更新 `get_render_cache` 支持查询双轨渲染缓存
- 修改 `render.py` 支持处理双轨输入

### 步骤 3: 修改前端预估大小计算

- 更新 `AIRepairPanel.tsx` 中的 `estimateFileSize` 和相关逻辑
- 在双轨模式下，计算两个轨道的总大小
- 更新显示逻辑

### 步骤 4: 修改前端渲染缓存处理

- 更新渲染缓存查询，支持双轨
- 修改缓存详情卡片显示
- 适配下载逻辑

### 步骤 5: 修改前端交付逻辑

- 添加选项让用户选择是否合并交付
- 更新下载逻辑以支持双轨交付

## 注意事项

- 保持向后兼容，单轨模式应正常工作
- 确保内存优化在双轨模式下也生效
- 缓存策略需要适配双轨模式


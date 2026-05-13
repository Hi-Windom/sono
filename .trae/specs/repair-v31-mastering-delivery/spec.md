# 修复算法 v3.1/v3.1a + 交付渲染列表 Spec

## Why

当前 v3.0/v3.0a 双轨处理已实现基础的人声/伴奏分离处理链，但人声修复效果仍有提升空间，缺少丰富的声乐效果器（如激励器、压缩器、空间感增强等），伴奏处理也较为基础。同时，多轨交付场景下用户需要独立获取人声轨、伴奏轨和合并轨的交付文件，而非仅限合并输出。此外，缓存管理页面缺少交付渲染文件的独立管理视图。

## What Changes

### 1. 后端算法 — v3.1/v3.1a

- **新增** `backend/services/repair/repair_v3_1/core.py`：v3.1 桌面版，在 v3.0 基础上增强
- **新增** `backend/services/repair/repair_v3_1a/core.py`：v3.1a 移动版，在 v3.0a 基础上增强
- **修改** `backend/services/audio_repair.py`：注册 v3.1/v3.1a 版本
- **修改** `backend/services/memory_guard.py`：增加 v3.1/v3.1a 内存估算

#### v3.1 增强内容（相对 v3.0）

- **AI 人声修复增强**：`_vocal_ai_repair_enhanced` — 频谱修复算法升级，使用自适应阈值和动态增益衰减，对 AI 伪影（毛刺、撕裂、数字噪声）的压制效果提升
- **新增人声效果器**：
  - `_vocal_exciter` — 人声激励器，增加中高频谐波，提升人声穿透力
  - `_vocal_compressor` — 人声压缩器，动态范围控制，使音量更平稳
  - `_vocal_de_esser_advanced` — 高级齿音抑制，多频段检测+侧链压缩式衰减
  - `_vocal_spatial` — 人声空间感增强（混响/立体声加宽）
  - `_vocal_warmth` — 人声温暖度（电子管模拟饱和）
- **伴奏处理增强**：`_instrument_stereo_enhance` — 伴奏立体声场增强
- **母带风格**：合并轨道支持三种母带风格
  - `mastering_style: "standard"` — 标准模式，均衡处理
  - `mastering_style: "powerful"` — 强劲模式，增加动态范围和低频冲击力
  - `mastering_style: "warm"` — 温暖模式，柔和高频、增强中低频温暖度

#### v3.1a 增强内容（相对 v3.0a）

- 精简版 AI 人声修复增强
- 精简版人声激励器
- 精简版人声压缩器
- 三种母带风格支持（与 v3.1 相同算法，移动端优化）

### 2. 后端 API — 交付渲染列表

- **新增** `GET /api/v1/delivery-files` — 获取所有交付渲染文件列表（含父项/子项关系）
  - 返回结构：`{ files: [{ filename, size, mtime, task_id, track_type, parent_filename?, is_parent, children? }] }`
  - 合并轨（`track_type="both"` 或未标注的合并渲染）作为父项
  - 人声轨（`track_type="vocal"`）和伴奏轨（`track_type="accompaniment"`）作为子项
- **新增** `DELETE /api/v1/delivery-files/{filename}` — 删除单个交付文件（删除子项时自动解除父子关联）
- **新增** `DELETE /api/v1/delivery-files/parent/{filename}` — 删除父项及其所有子项
- **修改** `POST /api/v1/render` — 双轨模式下支持同时渲染人声轨、伴奏轨和合并轨（合并轨作为父项，人声/伴奏轨作为子项）

### 3. 前端 — 修复页面 v3.1/v3.1a

- **修改** `src/components/AIRepairPanel.tsx`：
  - 双轨模式下支持 v3.1/v3.1a 算法选择
  - v3.1/v3.1a 人声参数面板增加：激励器、压缩器、空间感、温暖度参数
  - v3.1/v3.1a 伴奏参数面板增加：立体声增强参数
  - 合并输出区域增加母带风格选择器（标准/强劲/温暖）
- **修改** `src/services/backendApi.ts`：
  - 增加 v3.1/v3.1a 参数类型（VocalRepairParams 增加 exciter/compressor/spatial/warmth，增加 masteringStyle 参数）
  - 增加 `fetchDeliveryFiles()` API 调用
  - 增加 `deleteDeliveryFile()` API 调用
  - 增加 `deleteDeliveryParent()` API 调用

### 4. 前端 — 缓存管理页面新增交付渲染列表 Tab

- **修改** `src/pages/CacheManagerPage.tsx`：
  - 增加第 4 个 Tab：「交付渲染」
  - 列表显示所有交付渲染文件，按父项分组
  - 父项（合并轨）可展开显示子项（人声轨、伴奏轨）
  - 每项支持下载和删除操作
  - 删除父项时级联删除所有子项

## Impact

- Affected specs: 修复算法质量保障体系（`QUALITY_RULES.md`）
- Affected code:
  - `backend/services/repair/repair_v3_1/` (新建)
  - `backend/services/repair/repair_v3_1a/` (新建)
  - `backend/services/audio_repair.py` (修改：注册新版本)
  - `backend/services/memory_guard.py` (修改：v3.1/v3.1a 内存估算)
  - `backend/api/routes.py` (修改：交付渲染 API)
  - `src/components/AIRepairPanel.tsx` (修改：v3.1 参数面板 + 母带风格)
  - `src/services/backendApi.ts` (修改：v3.1 类型 + 交付 API)
  - `src/pages/CacheManagerPage.tsx` (修改：交付渲染 Tab)
  - `src/hooks/useAudioProcessor.ts` (修改：母带风格参数传递)

## ADDED Requirements

### Requirement: v3.1 桌面版算法
The system SHALL provide v3.1 repair algorithm for desktop with enhanced AI vocal repair, vocal effects, and mastering styles.

#### Scenario: AI 人声修复增强
- **WHEN** 用户选择 v3.1 算法并设置 aiRepair > 0
- **THEN** 后端使用增强型频谱修复算法处理人声轨，自适应阈值检测 AI 伪影

#### Scenario: 人声效果器
- **WHEN** 用户设置 exciter/compressor/spatial/warmth 参数 > 0
- **THEN** 后端对人声轨依次应用激励器、压缩器、空间感、温暖度处理

#### Scenario: 母带风格
- **WHEN** 用户选择母带风格（standard/powerful/warm）并渲染合并轨
- **THEN** 后端在混音后应用对应的母带处理链

### Requirement: 交付渲染列表
The system SHALL provide a delivery files management view in CacheManagerPage.

#### Scenario: 交付文件列表
- **WHEN** 用户切换到「交付渲染」Tab
- **THEN** 显示所有交付渲染文件列表，合并轨作为父项，人声/伴奏轨作为子项，支持展开/折叠

#### Scenario: 交付文件下载
- **WHEN** 用户点击任意交付文件的下载按钮
- **THEN** 触发文件下载

#### Scenario: 交付文件删除
- **WHEN** 用户点击子项的删除按钮
- **THEN** 仅删除该子项文件
- **WHEN** 用户点击父项的删除按钮
- **THEN** 级联删除父项及其所有子项

## MODIFIED Requirements

### Requirement: 渲染交付 API（修改）
The system SHALL support multi-track rendering with parent-child relationships.

**修改前**：render 端点仅渲染单个文件，双轨模式下通过 track_type 参数选择渲染人声/伴奏/合并

**修改后**：render 端点双轨模式下自动渲染人声轨、伴奏轨和合并轨三个文件。合并轨作为父项（cache 缓存），人声轨和伴奏轨作为子项。单轨模式下行为不变。

## REMOVED Requirements

无
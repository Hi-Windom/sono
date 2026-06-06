# Tasks

## Task 1: 后端 — 新增 v3.1 算法核心实现

在 `backend/services/repair/repair_v3_1/` 下创建核心算法，以 `repair_v3_0/core.py` 为基础进行增强：
- [x] **Task 1.1**: 创建 `backend/services/repair/repair_v3_1/__init__.py`
- [x] **Task 1.2**: 创建 `backend/services/repair/repair_v3_1/core.py`

## Task 2: 后端 — 新增 v3.1a 算法核心实现

在 `backend/services/repair/repair_v3_1a/` 下创建精简版算法：
- [x] **Task 2.1**: 创建 `backend/services/repair/repair_v3_1a/__init__.py`
- [x] **Task 2.2**: 创建 `backend/services/repair/repair_v3_1a/core.py`

## Task 3: 后端 — 注册 v3.1/v3.1a 算法版本

- [x] **Task 3.1**: 修改 `backend/services/audio_repair.py`：在 `ALGORITHM_VERSIONS` 中添加 v3.1/v3.1a
- [x] **Task 3.2**: 修改 `backend/services/memory_guard.py`：增加 v3.1/v3.1a 的 peak_temp 系数（参考 v3.0 +5%）
- [x] **Task 3.3**: 修改 `backend/api/routes.py` 中 render 端点的参数解析，支持 mastering_style 和 v3.1/v3.1a 新增参数

## Task 4: 后端 — 交付渲染列表 API

- [x] **Task 4.1**: 在 `backend/api/routes.py` 中新增 `GET /api/v1/delivery-files` 端点
- [x] **Task 4.2**: 新增 `DELETE /api/v1/delivery-files/{filename}` 端点
- [x] **Task 4.3**: 新增 `DELETE /api/v1/delivery-files/parent/{filename}` 端点
- [x] **Task 4.4**: 修改 `POST /api/v1/render` 双轨渲染逻辑

## Task 5: 前端 — backendApi.ts 类型与 API 扩展

- [x] **Task 5.1**: 扩展 `VocalRepairParams` 接口
- [x] **Task 5.2**: 扩展 `InstrumentRepairParams` 接口
- [x] **Task 5.3**: 扩展 `ProcessingOptions` 接口
- [x] **Task 5.4**: 增加 `DeliveryFile` 接口和 API 调用
- [x] **Task 5.5**: 在 `ALGORITHM_VERSIONS` 中添加 v3.1/v3.1a

## Task 6: 前端 — AIRepairPanel v3.1 参数面板

- [x] **Task 6.1**: 双轨模式下，当算法为 v3.1/v3.1a 时，人声参数面板显示激励器、压缩器、空间感、温暖度滑块
- [x] **Task 6.2**: 伴奏参数面板显示立体声增强滑块
- [x] **Task 6.3**: 合并输出区域增加母带风格选择器（三个按钮：标准/强劲/温暖）
- [x] **Task 6.4**: 渲染请求参数中传递 mastering_style 和新效果器参数

## Task 7: 前端 — 缓存管理页面交付渲染 Tab

- [x] **Task 7.1**: 修改 `CacheManagerPage.tsx`，增加第 4 个 Tab「交付渲染」
- [x] **Task 7.2**: 渲染交付文件列表，合并轨作为父项可展开显示子项（人声轨、伴奏轨）
- [x] **Task 7.3**: 每项支持下载按钮（触发文件下载）
- [x] **Task 7.4**: 每项支持删除按钮（子项仅删自身，父项级联删除）

# Task Dependencies

- Task 1 (v3.1 算法) 和 Task 2 (v3.1a 算法) 可并行开发
- Task 3 (注册版本) 依赖 Task 1 和 Task 2
- Task 4 (交付 API) 可独立于 Task 1-3 开发（不依赖算法版本）
- Task 5 (前端类型) 可独立于 Task 1-3 开发
- Task 6 (AIRepairPanel) 依赖 Task 5
- Task 7 (CacheManagerPage) 依赖 Task 4 和 Task 5
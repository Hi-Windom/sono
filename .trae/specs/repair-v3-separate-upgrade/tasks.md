# Tasks: v3.0/v3.0a 人声伴奏双轨处理

## Phase 1: 后端算法实现

- [ ] Task 1.1: 创建 `backend/services/repair/repair_v3_0/` 包
  - [ ] SubTask 1.1.1: 创建人声处理链核心模块
  - [ ] SubTask 1.1.2: 创建伴奏处理链核心模块
  - [ ] SubTask 1.1.3: 实现口型修复算法 `_vocal_formant_repair`
  - [ ] SubTask 1.1.4: 实现气息增强算法 `_vocal_breath_enhance`
  - [ ] SubTask 1.1.5: 实现器乐音色保护算法 `_instrument_timbre_protect`
  - [ ] SubTask 1.1.6: 实现混音模块 `_mix_tracks`
  - [ ] SubTask 1.1.7: 创建 `__init__.py` 导出

- [ ] Task 1.2: 创建 `backend/services/repair/repair_v3_0a/` 包
  - [ ] SubTask 1.2.1: 创建简化人声处理链
  - [ ] SubTask 1.2.2: 创建简化伴奏处理链
  - [ ] SubTask 1.2.3: 实现移动端混音模块
  - [ ] SubTask 1.2.4: 创建 `__init__.py` 导出

## Phase 2: 版本注册和配置

- [ ] Task 2.1: 修改 `backend/services/audio_repair.py`
  - [ ] SubTask 2.1.1: 注册 v3.0 模块到 `_REPAIR_MODULES`
  - [ ] SubTask 2.1.2: 注册 v3.0a 模块到 `_REPAIR_MODULES`
  - [ ] SubTask 2.1.3: 添加 v3.0 版本配置（6 个模式）
  - [ ] SubTask 2.1.4: 添加 v3.0a 版本配置（4 个模式）
  - [ ] SubTask 2.1.5: 添加双轨处理参数定义

- [ ] Task 2.2: 修改 `backend/services/memory_guard.py`
  - [ ] SubTask 2.2.1: 添加 v3.0 内存估算（peak_temp +100%）
  - [ ] SubTask 2.2.2: 添加 v3.0a 内存估算（peak_temp +50%）

## Phase 3: 后端 API

- [ ] Task 3.1: 修改 `backend/api/routes.py`
  - [ ] SubTask 3.1.1: 添加双轨上传端点 `/upload-dual`
  - [ ] SubTask 3.1.2: 添加双轨处理端点 `/repair-dual`
  - [ ] SubTask 3.1.3: 添加轨道状态查询端点 `/track-status/{task_id}`

- [ ] Task 3.2: 修改 `backend/services/task_manager.py`
  - [ ] SubTask 3.2.1: 添加双轨任务处理函数
  - [ ] SubTask 3.2.2: 实现进度追踪（人声处理 + 伴奏处理 + 混音进度）

## Phase 4: 前端实现

- [ ] Task 4.1: 修改 `src/services/backendApi.ts`
  - [ ] SubTask 4.1.1: 添加双轨参数类型定义
  - [ ] SubTask 4.1.2: 添加双轨上传 API 函数
  - [ ] SubTask 4.1.3: 添加双轨处理 API 函数

- [ ] Task 4.2: 修改 `src/hooks/useAudioProcessor.ts`
  - [ ] SubTask 4.2.1: 添加双轨处理状态管理
  - [ ] SubTask 4.2.2: 添加双轨参数更新逻辑

- [ ] Task 4.3: 修改前端组件
  - [ ] SubTask 4.3.1: 添加双轨模式切换 UI
  - [ ] SubTask 4.3.2: 添加人声轨/伴奏轨分别上传 UI
  - [ ] SubTask 4.3.3: 添加人声/伴奏独立参数滑块
  - [ ] SubTask 4.3.4: 添加混音比例调节 UI
  - [ ] SubTask 4.3.5: 添加输出轨道选择 UI

## Phase 5: 测试

- [ ] Task 5.1: 修改 `backend/tests/test_repair_quality.py`
  - [ ] SubTask 5.1.1: 添加 v3.0 逐步测试类
  - [ ] SubTask 5.1.2: 添加 v3.0a 逐步测试类
  - [ ] SubTask 5.1.3: 添加口型修复测试
  - [ ] SubTask 5.1.4: 添加气息增强测试
  - [ ] SubTask 5.1.5: 添加双轨混音测试

## Phase 6: 验证

- [ ] Task 6.1: 运行完整测试套件
- [ ] Task 6.2: 内存占用验证
- [ ] Task 6.3: 性能速度验证
- [ ] Task 6.4: Android 打包验证（使用 `bash scripts/build_android_release.sh`）

# Task Dependencies

- Task 1.1 和 Task 1.2 可并行执行（桌面版和移动版独立）
- Task 2.1 依赖 Task 1.1 和 Task 1.2（需要先实现算法模块）
- Task 3.1 依赖 Task 2.1（需要先注册版本）
- Task 4.1 依赖 Task 3.1（API 完成后前端接入）
- Task 4.3 依赖 Task 4.1 和 Task 4.2（API 和状态管理完成后 UI）
- Task 5.1 可在 Task 1.1/1.2 完成后开始（并行）

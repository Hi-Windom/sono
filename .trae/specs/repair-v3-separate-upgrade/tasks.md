# Tasks: v3.0/v3.0a 人声伴奏分轨处理

## Phase 1: 音频分离服务 (Audio Separator)

- [ ] Task 1.1: 创建 `backend/services/audio_separator.py` 音频分离服务
  - [ ] SubTask 1.1.1: 实现 Demucs 分离接口（v3.0 桌面版）
  - [ ] SubTask 1.1.2: 实现简化频谱分离接口（v3.0a 移动版）
  - [ ] SubTask 1.1.3: 实现流式/渐进式处理支持
  - [ ] SubTask 1.1.4: 实现缓存机制（分离结果缓存）

- [ ] Task 1.2: 创建分离结果模型和数据结构
  - [ ] SubTask 1.2.1: 定义分离结果数据结构（vocal_path, accompaniment_path）
  - [ ] SubTask 1.2.2: 实现临时文件管理

## Phase 2: 后端算法实现

- [ ] Task 2.1: 创建 `backend/services/repair/repair_v3_0/` 包
  - [ ] SubTask 2.1.1: 创建人声处理链核心模块
  - [ ] SubTask 2.1.2: 创建伴奏处理链核心模块
  - [ ] SubTask 2.1.3: 实现口型修复算法 `_vocal_formant_repair`
  - [ ] SubTask 2.1.4: 实现气息增强算法 `_vocal_breath_enhance`
  - [ ] SubTask 2.1.5: 实现器乐音色保护算法 `_instrument_timbre_protect`
  - [ ] SubTask 2.1.6: 实现混音模块 `_mix_tracks`
  - [ ] SubTask 2.1.7: 创建 `__init__.py` 导出

- [ ] Task 2.2: 创建 `backend/services/repair/repair_v3_0a/` 包
  - [ ] SubTask 2.2.1: 创建简化人声处理链
  - [ ] SubTask 2.2.2: 创建简化伴奏处理链
  - [ ] SubTask 2.2.3: 实现移动端混音模块
  - [ ] SubTask 2.2.4: 创建 `__init__.py` 导出

## Phase 3: 版本注册和配置

- [ ] Task 3.1: 修改 `backend/services/audio_repair.py`
  - [ ] SubTask 3.1.1: 注册 v3.0 模块到 `_REPAIR_MODULES`
  - [ ] SubTask 3.1.2: 注册 v3.0a 模块到 `_REPAIR_MODULES`
  - [ ] SubTask 3.1.3: 添加 v3.0 版本配置（6 个模式）
  - [ ] SubTask 3.1.4: 添加 v3.0a 版本配置（4 个模式）
  - [ ] SubTask 3.1.5: 添加分轨处理参数定义

- [ ] Task 3.2: 修改 `backend/services/memory_guard.py`
  - [ ] SubTask 3.2.1: 添加 v3.0 内存估算（peak_temp +100%）
  - [ ] SubTask 3.2.2: 添加 v3.0a 内存估算（peak_temp +50%）

## Phase 4: 后端 API

- [ ] Task 4.1: 修改 `backend/api/routes.py`
  - [ ] SubTask 4.1.1: 添加分轨处理参数验证
  - [ ] SubTask 4.1.2: 修改 `/repair` 端点支持分轨参数
  - [ ] SubTask 4.1.3: 添加 `/separate` 端点（独立分离 API）
  - [ ] SubTask 4.1.4: 添加 `/tracks/{task_id}` 端点（查询分离轨道）

- [ ] Task 4.2: 修改 `backend/services/task_manager.py`
  - [ ] SubTask 4.2.1: 添加分轨任务处理函数
  - [ ] SubTask 4.2.2: 实现进度追踪（分离进度 + 各轨处理进度）

## Phase 5: 前端实现

- [ ] Task 5.1: 修改 `src/services/backendApi.ts`
  - [ ] SubTask 5.1.1: 添加分轨参数类型定义
  - [ ] SubTask 5.1.2: 修改 `mapParamsToBackend` 支持分轨参数
  - [ ] SubTask 5.1.3: 添加分轨 API 调用函数

- [ ] Task 5.2: 修改 `src/hooks/useAudioProcessor.ts`
  - [ ] SubTask 5.2.1: 添加分轨处理状态管理
  - [ ] SubTask 5.2.2: 添加分轨参数更新逻辑

- [ ] Task 5.3: 修改前端组件
  - [ ] SubTask 5.3.1: 添加分轨开关 UI（`src/components/AIRepairPanel.tsx`）
  - [ ] SubTask 5.3.2: 添加分轨参数滑块（人声/伴奏独立参数）
  - [ ] SubTask 5.3.3: 添加输出轨道选择 UI

## Phase 6: 测试

- [ ] Task 6.1: 修改 `backend/tests/test_repair_quality.py`
  - [ ] SubTask 6.1.1: 添加 v3.0 逐步测试类
  - [ ] SubTask 6.1.2: 添加 v3.0a 逐步测试类
  - [ ] SubTask 6.1.3: 添加口型修复测试
  - [ ] SubTask 6.1.4: 添加气息增强测试
  - [ ] SubTask 6.1.5: 添加分轨混音测试

## Phase 7: 验证

- [ ] Task 7.1: 运行完整测试套件
- [ ] Task 7.2: 内存占用验证
- [ ] Task 7.3: 性能速度验证
- [ ] Task 7.4: Android 打包验证（使用 `bash scripts/build_android_release.sh`）

# Task Dependencies

- Task 1.1 必须在 Task 2.1 和 Task 2.2 之前完成（分离服务是分轨处理的基础）
- Task 3.1 必须在 Task 4.1 之前完成（版本注册是 API 的基础）
- Task 5.1 必须在 Task 5.3 之前完成（API 是 UI 的基础）
- Task 6.1 可以在 Task 2.1/2.2 完成后开始（并行）

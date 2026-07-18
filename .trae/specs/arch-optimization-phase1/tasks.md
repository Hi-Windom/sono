# 架构优化 Phase 1：统一任务生命周期 - The Implementation Plan

## [x] Task 1: 创建 BaseTask 抽象基类和 TaskExecutor
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 新建 `services/task_executor.py`
  - 定义 `BaseTask` 抽象基类：`execute()` 抽象方法，`cancel()` 可重写，`cleanup()` 可重写
  - 定义标准状态枚举：`pending / processing / completed / error / cancelled`
  - 实现 `TaskExecutor`：统一的提交、并发控制、取消、状态流转
  - 实现标准的生命周期：pending → processing → (completed/error/cancelled)
  - 统一的 WebSocket 消息发送（progress + final）
  - 统一的异常处理和 finally 清理
  - 保留 `task_manager.py` 作为兼容层，内部委托给 TaskExecutor
- **Acceptance Criteria Addressed**: AC-1, AC-6
- **Test Requirements**:
  - `programmatic` TR-1.1: BaseTask 不能直接实例化，必须继承并实现 execute()
  - `programmatic` TR-1.2: TaskExecutor 正确管理并发（_track_task_start/_track_task_end）
  - `programmatic` TR-1.3: TaskExecutor 正确处理取消（_cancelled_tasks）
  - `programmatic` TR-1.4: 任务正常完成时状态流转正确（pending→processing→completed）
  - `programmatic` TR-1.5: 任务失败时状态流转正确（pending→processing→error）
  - `programmatic` TR-1.6: 任务取消时状态流转正确（pending→cancelled 或 processing→cancelled）
  - `programmatic` TR-1.7: 任务执行期间 progress_callback 正确调用
  - `programmatic` TR-1.8: finally 块正确清理资源（_active_tasks + _cancelled_tasks）
  - `human-judgement` TR-1.9: 代码结构清晰，易于扩展新任务类型
- **Notes**: 这是基础架构，必须先做对，后面的迁移才有意义

## [x] Task 2: 创建 TaskConformanceTest 一致性测试基类
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 在 `tests/` 下创建一致性测试基类 `TaskConformanceTest`
  - 覆盖 10+ 个标准测试场景：
    - 正常提交和完成
    - 任务失败处理
    - 任务取消（pending 时取消 / processing 时取消）
    - 并发限制（超过 MAX_CONCURRENT_TASKS 时拒绝）
    - WebSocket 消息发送（progress + final）
    - 状态流转正确性
    - 活跃任务计数正确性
    - finally 清理正确性
  - 新任务类型只需继承此基类 + 提供 task factory 即可自动获得所有测试
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-2.1: 用一个简单的 FakeTask 验证一致性测试基类本身能正常工作
  - `programmatic` TR-2.2: 所有 10+ 个测试场景都能正确通过/失败
  - `human-judgement` TR-2.3: 测试覆盖全面，包含正常/异常/边界场景
- **Notes**: 先有测试，再迁移，确保迁移质量

## [x] Task 3: 迁移 Repair 任务到新架构
- **Priority**: high
- **Depends On**: Task 1, Task 2
- **Description**:
  - 创建 `RepairTask` 继承 `BaseTask`
  - 将 `_run_repair` 的核心逻辑迁移到 `execute()` 方法
  - `submit_repair_task` 改为内部使用 `TaskExecutor.submit(RepairTask(...))`
  - 保持外部 API 和行为完全一致
  - 运行所有现有测试确保不退化
- **Acceptance Criteria Addressed**: AC-2, AC-7
- **Test Requirements**:
  - `programmatic` TR-3.1: 所有 repair 相关的现有测试通过
  - `programmatic` TR-3.2: RepairTask 通过 TaskConformanceTest
  - `programmatic` TR-3.3: submit_repair_task 行为与重构前完全一致（状态、进度、错误）
  - `programmatic` TR-3.4: 回归测试全通过
  - `human-judgement` TR-3.5: 代码比重构前更简洁清晰
- **Notes**: repair 是最复杂的任务，迁移后作为其他任务的参考

## [x] Task 4: 迁移 Detect 任务到新架构
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - 创建 `DetectTask` 继承 `BaseTask`
  - 将 `_run_detect` 的核心逻辑迁移到 `execute()` 方法
  - `submit_detect_task` 改为内部使用 `TaskExecutor.submit(DetectTask(...))`
  - 保持外部 API 和行为完全一致
- **Acceptance Criteria Addressed**: AC-3, AC-7
- **Test Requirements**:
  - `programmatic` TR-4.1: 所有 detect 相关的现有测试通过
  - `programmatic` TR-4.2: DetectTask 通过 TaskConformanceTest
  - `programmatic` TR-4.3: submit_detect_task 行为与重构前完全一致
  - `programmatic` TR-4.4: 回归测试全通过
- **Notes**: detect 相对简单，作为第二个迁移验证架构通用性

## [x] Task 5: 迁移 Render 任务到新架构
- **Priority**: high
- **Depends On**: Task 4
- **Description**:
  - 创建 `RenderTask` 继承 `BaseTask`
  - 将 `_run_render` 和 `_run_render_dual` 的核心逻辑迁移到 `execute()`
  - 渲染接口改为内部使用 `TaskExecutor.submit(RenderTask(...))`
  - 保持外部 API 和行为完全一致
- **Acceptance Criteria Addressed**: AC-4, AC-7
- **Test Requirements**:
  - `programmatic` TR-5.1: 所有 render 相关的现有测试通过
  - `programmatic` TR-5.2: RenderTask 通过 TaskConformanceTest
  - `programmatic` TR-5.3: 渲染接口行为与重构前完全一致
  - `programmatic` TR-5.4: 回归测试全通过
- **Notes**: render 有单轨和双轨两种模式，注意都要覆盖

## [ ] Task 6: 清理旧代码和验证
- **Priority**: medium
- **Depends On**: Task 5
- **Description**:
  - 清理 `task_manager.py` 中重复的旧代码（保留必要的兼容层）
  - 清理 `render.py` 中重复的生命周期代码
  - 运行完整测试套件
  - 代码量统计对比（重构前后）
- **Acceptance Criteria Addressed**: AC-5, AC-7
- **Test Requirements**:
  - `programmatic` TR-6.1: 完整测试套件通过（回归 + API + 其他）
  - `programmatic` TR-6.2: 任务管理相关代码行数减少 30%+
  - `human-judgement` TR-6.3: 代码结构清晰，没有遗留的死代码
- **Notes**: 最后清理，确保没有遗留问题

# 架构优化 Phase 1：统一任务生命周期 - Product Requirement Document

## Overview
- **Summary**: 重构后端任务管理架构，引入统一的任务基类和执行器，消除 repair/detect/render 三类任务的重复代码和不一致性
- **Purpose**: 从根本上解决"每种任务各自实现一套状态管理/并发控制/取消机制"导致的 bug 频发问题，降低维护成本，提升系统可靠性
- **Target Users**: 开发者（提升开发效率和代码质量）、最终用户（减少 bug，提升稳定性）

## Goals
- 建立统一的任务基类 `BaseTask`，定义标准的任务生命周期
- 建立统一的任务执行器 `TaskExecutor`，统一管理提交、并发、取消、状态流转
- 迁移 repair、detect、render 三类任务到新架构
- 确保所有任务类型的行为一致性（状态流转、并发控制、取消机制、WebSocket 消息）
- 不改变外部 API 接口，向后兼容

## Non-Goals (Out of Scope)
- 不重构前端
- 不改变修复算法本身
- 不引入新的依赖库（如 Celery、RQ 等任务队列）
- 不做分布式任务调度（保持单进程线程池模型）
- 不重构缓存系统（Phase 4 的内容）
- 不做完整的消息总线（Phase 3 的内容）

## Background & Context
### 现状问题
通过两轮 bug 挖掘，共发现 18 个严重 bug，其中约 50% 源于"任务生命周期管理不一致"：

1. **重复代码**：`_run_repair`、`_run_detect`、`_run_render` 每个都有自己的 try/except/finally、状态更新、WebSocket 消息发送，写法略有不同
2. **行为不一致**：
   - render 任务之前完全游离在 `_active_tasks` 计数之外（已修复）
   - render 任务之前没有取消机制（已修复）
   - `_run_repair` 的 finally 之前没有清理 `_cancelled_tasks`（已修复）
3. **新增任务成本高**：每加一种新任务类型，都要复制粘贴一套状态管理逻辑，很容易漏东西
4. **难以测试**：每个任务类型的逻辑分散在不同文件，没有统一的测试入口

### 技术约束
- 保持单进程 + 线程池模型（适配 Android/Termux 环境）
- 不引入新的外部依赖
- 外部 API 接口完全向后兼容
- 渐进式重构，每一步都可回滚

## Functional Requirements
- **FR-1**: 定义 `BaseTask` 抽象基类，包含标准生命周期钩子
- **FR-2**: 实现 `TaskExecutor` 统一任务执行器，管理并发、取消、状态流转
- **FR-3**: 迁移 repair 任务到新架构（`RepairTask` 继承 `BaseTask`）
- **FR-4**: 迁移 detect 任务到新架构（`DetectTask` 继承 `BaseTask`）
- **FR-5**: 迁移 render 任务到新架构（`RenderTask` 继承 `BaseTask`）
- **FR-6**: 保持现有外部 API 接口不变（REST + WebSocket）
- **FR-7**: 所有任务类型行为完全一致（状态流转、并发控制、取消机制、错误处理）

## Non-Functional Requirements
- **NFR-1**: 性能零退化：任务执行延迟和吞吐量与重构前一致
- **NFR-2**: 代码量减少：任务管理相关代码减少 30% 以上
- **NFR-3**: 向后兼容：所有现有测试无需修改即可通过
- **NFR-4**: 可测试性：新增 `TaskConformanceTest` 基类，新任务类型只需继承即可获得一致性测试
- **NFR-5**: 可观测性：每个状态变更都有结构化日志

## Constraints
- **Technical**: Python 3.10+, FastAPI, SQLite, 线程池模型
- **Business**: 必须在 1-2 周内完成，不能阻塞功能开发
- **Compatibility**: 外部 API 零改动，前端无感知
- **Safety**: 渐进式迁移，每迁移一类任务都可独立回滚

## Assumptions
- 现有功能测试覆盖足够，可以作为重构安全网
- 任务类型数量有限（目前 3 种，可预见的未来不超过 5 种）
- 单进程线程池模型足够支撑并发需求（MAX_WORKERS=4）
- 用户主要关心功能正确性和稳定性，不关心内部架构如何

## Acceptance Criteria

### AC-1: BaseTask 抽象正确
- **Given**: 一个新的任务类型
- **When**: 继承 `BaseTask` 并实现 `execute()` 方法
- **Then**: 自动获得完整的生命周期管理（状态流转、并发控制、取消、WS 消息、错误处理）
- **Verification**: `programmatic`
- **Notes**: 通过一致性测试套件验证

### AC-2: Repair 任务迁移后行为一致
- **Given**: 修复任务
- **When**: 提交、执行、取消、失败
- **Then**: 状态流转、WS 消息、数据库更新、并发控制与重构前完全一致
- **Verification**: `programmatic`
- **Notes**: 所有现有测试必须通过

### AC-3: Detect 任务迁移后行为一致
- **Given**: 检测任务
- **When**: 提交、执行、取消、失败
- **Then**: 状态流转、WS 消息、数据库更新、并发控制与重构前完全一致
- **Verification**: `programmatic`
- **Notes**: 所有现有测试必须通过

### AC-4: Render 任务迁移后行为一致
- **Given**: 渲染任务
- **When**: 提交、执行、取消、失败
- **Then**: 状态流转、WS 消息、数据库更新、并发控制与重构前完全一致
- **Verification**: `programmatic`
- **Notes**: 所有现有测试必须通过

### AC-5: 代码复用率提升
- **Given**: 任务管理相关代码
- **When**: 对比重构前后
- **Then**: 重复代码减少 30% 以上
- **Verification**: `human-judgment`
- **Notes**: 统计 task_manager.py + render.py 中任务生命周期相关代码行数

### AC-6: 一致性测试套件
- **Given**: 新任务类型
- **When**: 继承 `TaskConformanceTest` 基类
- **Then**: 自动获得 10+ 个一致性测试用例
- **Verification**: `programmatic`
- **Notes**: 包括：提交、取消、失败、并发限制、状态流转、WS 消息等

### AC-7: 现有测试全通过
- **Given**: 所有现有测试
- **When**: 运行完整测试套件
- **Then**: 所有测试通过（重构前通过的，重构后仍然通过）
- **Verification**: `programmatic`

## Open Questions
- [ ] 是先在 `task_manager.py` 内重构，还是新建 `task_executor.py` 文件？ → 新建 `services/task_executor.py`，`task_manager.py` 保留兼容层
- [ ] 取消检查是在 progress_callback 里做，还是统一由执行器做？ → 统一由执行器做，progress_callback 自动注入取消检查
- [ ] 旧的 `submit_repair_task` 等函数是保留兼容层还是直接改调用方？ → 保留兼容层，内部委托给 TaskExecutor，调用方无需修改

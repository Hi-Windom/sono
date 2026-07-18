# 修复 Bug 16/17/18 - Product Requirement Document

## Overview
- **Summary**: 修复三个新发现的严重 bug：事件循环静默失败、MP3 转码并发安全、双轨混音采样率不匹配
- **Purpose**: 消除 WebSocket 消息静默丢失、MP3 转码文件损坏、双轨混音速度错误三个高影响问题，提升系统稳定性和用户体验
- **Target Users**: 所有使用音频修复功能的用户，尤其是使用双轨模式和 MP3 下载的用户

## Goals
- 修复 Bug 16：`_get_loop()` 兜底逻辑导致 WebSocket 消息静默丢失
- 修复 Bug 17：`download_mp3` 接口无并发控制导致文件损坏
- 修复 Bug 18：`_merge_wavs` 不检查采样率一致性导致混音错误
- 补充对应的回归测试，防止复发

## Non-Goals (Out of Scope)
- 不做完整的任务生命周期架构重构（见架构优化方案文档）
- 不引入新的依赖库
- 不重构整个 download 模块
- 不实现完整的消息总线（这是架构优化 Phase 3 的内容）

## Background & Context
通过系统性 bug 挖掘，发现了 18 个严重 bug。前 12 个已修复，本次修复第 16、17、18 号：

1. **Bug 16（事件循环）**：`_get_loop()` 在 `_loop` 为 None 时会兜底创建新事件循环，但新循环未运行，导致 `run_coroutine_threadsafe` 投递的协程永远不执行，WebSocket 消息静默丢失。正常情况 `set_event_loop` 会在 lifespan 设置，但测试环境或异常场景会触发兜底。

2. **Bug 17（MP3 转码并发）**：`download_mp3` 接口在 MP3 文件不存在时直接开始转码，没有并发控制。多个请求同时触发会写入同一个文件，导致文件损坏；长音频转码期间请求一直挂着，占用连接资源。

3. **Bug 18（混音采样率）**：`_merge_wavs` 函数混音时不检查人声和伴奏的采样率是否一致，直接相加并用人声的采样率输出。如果两者采样率不同（如 44.1kHz vs 48kHz），会导致音高/速度错误，输出时长也不对。已验证：44100Hz + 48000Hz → 输出时长 1.088s 而非 1.0s。

## Functional Requirements
- **FR-1**: 修复 `_get_loop()` 的危险兜底逻辑，没有设置事件循环时应明确告警而非静默失败
- **FR-2**: `download_mp3` 接口增加并发控制，同一 task_id 的转码只执行一次
- **FR-3**: `download_mp3` 使用"临时文件+原子重命名"模式，避免半写文件
- **FR-4**: `_merge_wavs` 函数检查采样率一致性，不一致时重采样到统一采样率
- **FR-5**: 每个修复都补充对应的回归测试

## Non-Functional Requirements
- **NFR-1**: 修复后回归测试 100% 通过
- **NFR-2**: 不引入新的依赖
- **NFR-3**: 性能影响可忽略（文件锁+双重检查的开销极低）
- **NFR-4**: 向后兼容，不改变现有 API 接口

## Constraints
- **Technical**: Python 3.10+, FastAPI, SQLite
- **Business**: 必须在现有架构内修复，不做大规模重构
- **Dependencies**: 只能使用已有的 numpy/soundfile/scipy 库

## Assumptions
- `set_event_loop` 在正常生产环境的 lifespan 中会被正确调用
- MP3 转码失败的临时文件应该被清理，不留在磁盘上
- 双轨混音时，人声和伴奏的采样率理论上应该一致，但实际中可能因各种原因不一致
- 重采样应该使用 scipy.signal.resample_poly（项目中已在使用）

## Acceptance Criteria

### AC-1: 事件循环兜底移除/告警
- **Given**: 后台线程调用 `_ws_send_progress` 或 `_ws_send_final`
- **When**: `_loop` 为 None（没有调用过 `set_event_loop`）
- **Then**: 不应该创建未运行的事件循环；应该打 warning 日志说明 WebSocket 消息无法发送；不抛出异常影响任务执行
- **Verification**: `programmatic`
- **Notes**: 测试环境下可以退回轮询模式，不能静默失败

### AC-2: MP3 转码并发安全
- **Given**: 同一个 task_id 同时收到多个 MP3 下载请求，且 MP3 文件不存在
- **When**: 多个请求同时进入转码逻辑
- **Then**: 只有一个请求执行转码，其他请求等待或直接使用结果；最终文件完整正确；不会出现半写文件
- **Verification**: `programmatic`
- **Notes**: 使用文件锁+双重检查模式；先写临时文件再 rename

### AC-3: 混音采样率一致性
- **Given**: 人声和伴奏的采样率不同
- **When**: 调用 `_merge_wavs` 进行混音
- **Then**: 自动将低采样率重采样到高采样率（或统一到人声采样率），输出时长正确，音高正确
- **Verification**: `programmatic`
- **Notes**: 已验证当前 bug：44100Hz + 48000Hz → 输出 1.088s，修复后应为 1.0s

### AC-4: 回归测试覆盖
- **Given**: 每个修复的 bug
- **When**: 运行回归测试
- **Then**: 有对应的测试用例能复现 bug 并验证修复；测试命名符合规范（`Test<Bug类别>`）
- **Verification**: `programmatic`
- **Notes**: 测试文件：`backend/tests/test_regression.py`

### AC-5: 现有功能不退化
- **Given**: 所有现有测试
- **When**: 运行完整测试套件
- **Then**: 所有已有测试继续通过
- **Verification**: `programmatic`

## Open Questions
- [ ] MP3 转码的并发控制使用文件锁还是内存锁？→ 文件锁更可靠，支持多进程
- [ ] `_merge_wavs` 应该重采样到哪个采样率？→ 统一到人声的采样率（保持现有行为的预期）
- [ ] 转码失败时临时文件是否需要清理？→ 需要，在 except 块中清理

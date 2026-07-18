# 修复 Bug 16/17/18 - The Implementation Plan (Decomposed and Prioritized Task List)

## [ ] Task 1: 修复 Bug 16 - 事件循环兜底静默失败
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 修改 `_get_loop()` 函数，移除创建未运行事件循环的兜底逻辑
  - 当 `_loop` 为 None 时，打 warning 日志并返回 None
  - 修改 `_ws_send_progress` 和 `_ws_send_final`，处理 `_get_loop()` 返回 None 的情况
  - 确保 WebSocket 消息发送失败不会影响任务正常执行（任务本身继续，只是前端需要靠轮询）
- **Acceptance Criteria Addressed**: AC-1, AC-5
- **Test Requirements**:
  - `programmatic` TR-1.1: 在线程中调用 `_ws_send_progress` 且未设置 event loop 时，不抛出异常，打 warning 日志
  - `programmatic` TR-1.2: 设置 event loop 后，WebSocket 消息能正常发送
  - `programmatic` TR-1.3: 所有现有回归测试通过
  - `human-judgement` TR-1.4: 代码审查：确认不会创建未运行的事件循环；确认异常处理正确
- **Notes**: 关键是"不静默失败"，要打日志让运维知道 WebSocket 不通了

## [ ] Task 2: 修复 Bug 17 - MP3 转码并发安全
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 为 `download_mp3` 添加文件级锁（按 task_id 粒度）
  - 实现"双重检查锁定"模式：先检查文件是否存在，加锁后再检查一次
  - 使用"临时文件 + 原子重命名"模式：先写到 `{task_id}_repaired.mp3.tmp`，转码成功后 rename 为最终文件
  - 转码失败时清理临时文件
- **Acceptance Criteria Addressed**: AC-2, AC-5
- **Test Requirements**:
  - `programmatic` TR-2.1: 并发调用 `download_mp3` 同一 task_id，最终文件完整不损坏
  - `programmatic` TR-2.2: 转码失败后没有残留的 .tmp 文件
  - `programmatic` TR-2.3: 所有现有回归测试通过
  - `human-judgement` TR-2.4: 代码审查：确认锁粒度正确；确认临时文件清理完整
- **Notes**: 文件锁用 `threading.Lock` 按文件名维护一个锁字典即可（单进程场景）

## [ ] Task 3: 修复 Bug 18 - 混音采样率不匹配
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 修改 `_merge_wavs` 函数，在混音前检查 `vocal_sr == acc_sr`
  - 如果不一致，将伴奏重采样到人声的采样率（保持现有行为：输出采样率 = 人声采样率）
  - 使用 `scipy.signal.resample_poly` 进行重采样（项目中已在使用）
  - 重采样后再做长度对齐和混音
- **Acceptance Criteria Addressed**: AC-3, AC-5
- **Test Requirements**:
  - `programmatic` TR-3.1: 44100Hz 人声 + 48000Hz 伴奏，输出时长约为 1.0s（误差<1%），而不是 1.088s
  - `programmatic` TR-3.2: 采样率相同时行为和之前完全一致
  - `programmatic` TR-3.3: 所有现有回归测试通过
  - `human-judgement` TR-3.4: 代码审查：确认重采样算法选择正确；确认多声道处理正确
- **Notes**: 已验证 bug 存在：44100Hz + 48000Hz → 输出 1.088s

## [ ] Task 4: 补充回归测试
- **Priority**: high
- **Depends On**: Task 1, Task 2, Task 3
- **Description**:
  - 在 `test_regression.py` 中添加 Bug 16/17/18 对应的回归测试
  - 测试命名规范：`Test<Bug类别>` + 明确的测试用例
  - 每个测试添加注释说明对应的历史 bug
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-4.1: Bug 16 有对应的回归测试
  - `programmatic` TR-4.2: Bug 17 有对应的回归测试
  - `programmatic` TR-4.3: Bug 18 有对应的回归测试
  - `programmatic` TR-4.4: 所有回归测试通过
- **Notes**: 按照项目规则：每修一个 bug 必须补对应的回归测试

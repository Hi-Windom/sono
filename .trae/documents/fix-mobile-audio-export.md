# 修复移动端导出音频没有反应

## 问题分析

移动端点击"导出后端修复音频"或"导出浏览器修复音频"按钮后，没有可见的反应。

目标浏览器：Chromium 94+ 和 Firefox 对等版本。这些浏览器都支持 `a.click()` + blob URL、Web Worker、AudioContext 等标准 API。

### 根因分析

#### 问题1：`encodeWavWithWorker` 可能挂起（最可能的主因）
- 文件：`src/hooks/useAudioProcessor.ts` L754-802
- Worker 编码没有超时机制
- 如果 Worker 在移动端初始化失败或消息传递失败，Promise 永远不会 resolve/reject
- 整个 `downloadProcessedAudio` 函数会挂起，用户看不到任何反馈
- 虽然 fallback `audioBufferToWav` 存在，但只在 Worker 抛出错误时触发，不会在 Worker 无响应时触发

#### 问题2：导出过程无用户反馈
- `downloadProcessedAudio` 函数在编码阶段没有设置 `processingStep` 状态
- 用户点击按钮后，如果编码耗时较长（移动端常见），看起来就像"没有反应"
- 只有从服务器下载的路径（L1560）才设置了 `setProcessingStep('下载中...')`

#### 问题3：`backendProcessedBuffer` 可能为 null
- 文件：`src/hooks/useAudioProcessor.ts` L1107-1112
- `loadAudioFromUrl` 失败时只打印 `console.warn`，`backendProcessedBuffer` 保持 null
- 移动端 AudioContext 可能处于 suspended 状态，`decodeAudioData` 会失败
- 如果 `backendProcessedBuffer` 为 null，`hasBackendResult` 为 false，导出按钮不显示
- 即使按钮不显示，用户可能看到修复完成但无法导出，也会描述为"没有反应"

## 修复方案

### 修改1：为 `encodeWavWithWorker` 添加超时机制
**文件**: `src/hooks/useAudioProcessor.ts`

在 `encodeWavWithWorker` 中：
1. 添加 30 秒超时（使用 `Promise.race`）
2. 超时后自动终止 Worker 并 fallback 到主线程 `audioBufferToWav`
3. 确保 Worker 在任何情况下都会被清理

### 修改2：添加导出过程的用户反馈
**文件**: `src/hooks/useAudioProcessor.ts`

在 `downloadProcessedAudio` 函数中：
1. 开始编码前设置 `setProcessingStep('正在编码导出...')`
2. 编码完成后清除状态
3. 如果下载失败，显示明确的错误提示

### 修改3：确保 `backendProcessedBuffer` 可靠设置
**文件**: `src/hooks/useAudioProcessor.ts`

在 `loadAudioFromUrl` 和后端处理完成回调中：
1. 在调用 `decodeAudioData` 前确保 AudioContext 已 resume
2. 在 `downloadProcessedAudio` 的服务器下载路径中，也先 resume AudioContext

## 验证步骤

1. 在桌面浏览器测试：导出功能正常工作
2. 在 Android Chrome 测试：点击导出按钮后能看到"正在编码导出..."提示
3. 在 Android Chrome 测试：编码完成后文件能正常下载
4. 在 Android Chrome 测试：如果 Worker 编码超时，能自动 fallback 到主线程编码
5. 运行 `bash scripts/build_android_release.sh` 重新打包

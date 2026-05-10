# 三个核心问题的真正修复

## 根因分析

### 问题1：播放不立即就绪
**之前的修改无效原因**：`play()` 是 `useCallback`，依赖列表为 `[playMode, getCurrentBuffer, getAudioContext, stopPlaying, stopAllModeNodes]`，**不包含 `duration` 和 `startStreamingPlayback`**。因此：
- `play()` 闭包中的 `duration` 永远是初始值 0
- `if (duration > 0 && pendingObjectURLRef.current)` 永远为 false
- `startStreamingPlayback` 引用也是旧的闭包
- `pendingPlayRef` 永远不会被设置

**修复**：将 `duration` 和 `startStreamingPlayback` 加入 `play` 的依赖列表。但 `duration` 是 state，加入依赖会导致 `play` 频繁重建。更好的方案是用 `durationRef` 来避免闭包问题。

### 问题2：频谱卡顿
**之前的修改无效原因**：
1. `currentTime` 节流到 100ms 确实减少了重渲染，但 SpectrumVisualizer 的 `useEffect` 依赖 `[analyser, color]`，其中 `analyser` 是 `analyserRef.current` 作为 prop 传入。**每次父组件重渲染时，`analyserRef.current` 虽然是同一个对象，但 React 的 JSX 表达式 `analyser={analyserRef.current}` 每次求值都会产生新的 prop 传递**——不过实际上 React 对 props 做浅比较，同一个 AnalyserNode 对象不会触发 useEffect 重执行。
2. 真正的卡顿原因可能是：**SpectrumVisualizer 的 `draw` 函数中，每帧都调用 `ctx.fillRect(x, height - barHeight, barWidth - 2, barHeight)` 128 次**。在移动端（特别是 ARM 设备），Canvas 2D 的 fillRect 调用开销比桌面大得多。加上 `ctx.clearRect` + `ctx.fillRect` 背景填充，每帧 130 次 fillRect 调用。
3. 更关键的是：**`analyser.getByteFrequencyData(dataArray)` 在没有音频播放时返回全零**，但 draw 循环仍在运行（30fps），每帧 130 次 fillRect 仍然执行。当开始播放时，频谱数据变化大，绘制开销增加。

**修复方案**：
- 使用 `ctx.beginPath()` + `ctx.rect()` + `ctx.fill()` 批量绘制，减少 fillStyle 切换
- 或者使用 `ImageData` 直接操作像素，避免多次 fillRect
- 当没有播放时暂停 draw 循环

### 问题3：服务器数据不独立显示
**之前的修改无效原因**：`loadAudioFile` 不再清除 `backendAvailable`，但 AIRepairPanel 的 effect 中 `if (duration <= 0) return` 仍然阻止了请求。`duration` 在 `loadAudioFile` 开头被设为 0（L687），WAV header 解析后恢复（L698）。但 `backendAvailable` 为 true + `duration > 0` 的条件要等到 WAV header 解析后才满足，和预估大小同时出现。

**真正的问题**：用户期望服务器数据（内存总量、存储总量）在连接后端时就立即可用，不需要等 duration。当前 API `/memory/info` 和 `/storage/estimate` 都需要 duration 参数，但"服务器有多少内存/存储"这个信息不需要 duration。

**修复方案**：
- 新增一个轻量 API `/system/info`，不需要 duration，只返回服务器内存/存储总量
- 或者在 AIRepairPanel 中，当 `backendAvailable` 为 true 但 `duration <= 0` 时，仍然请求服务器基础信息（用 duration=0 或默认值）
- 最简单的方案：修改 effect，当 `backendAvailable` 为 true 时，即使 `duration <= 0` 也请求（后端 API 已处理 duration=0 的情况，返回 available_memory_bytes 和 total_memory_bytes）

## 实施步骤

### 步骤1：修复 play() 闭包问题
**文件**：`/workspace/src/hooks/useAudioProcessor.ts`

1. 新增 `durationRef = useRef(0)`，在 `setDuration()` 时同步更新
2. `play()` 中用 `durationRef.current` 替代闭包 `duration`
3. `play()` 中用 `startStreamingPlaybackRef.current` 替代闭包引用（或直接将 `startStreamingPlayback` 加入依赖）
4. `play` 的依赖列表加入 `startStreamingPlayback`

### 步骤2：频谱性能优化（移动端）
**文件**：`/workspace/src/components/SpectrumVisualizer.tsx`

1. 使用 `Path2D` 批量绘制所有 bar，一次 `ctx.fill()` 调用替代 128 次 `ctx.fillRect()`
2. 背景用 `ctx.fillStyle` 一次填充
3. 当 analyser 没有数据时（全零），跳过 bar 绘制
4. 添加 `isPlaying` prop，不播放时暂停 draw 循环

### 步骤3：服务器数据独立于 duration
**文件**：`/workspace/src/components/AIRepairPanel.tsx`

修改两个 fetch effect：
- 当 `backendAvailable` 为 true 时，即使 `duration <= 0` 也请求服务器数据
- 后端 API 对 `duration=0` 已有处理（返回 available_memory_bytes 和 total_memory_bytes，estimated=0）
- 这样服务器数据在连接后端时就立即可用

### 步骤4：构建验证 + 打包

# 播放即时就绪 + 波形性能 + 服务器数据重连

## 问题分析

### 问题1：播放没有立即就绪
- **根因**：`loadAudioFile` 中，WAV头解析后立即 `setIsProcessing(false)` 释放UI，但 `audioBuffer` 仍为 null。`play()` 函数在 L1782-1786 检查 `if (!buffer) return;`，静默返回。用户点击播放无反应。
- **期望**：WAV头解析后，播放按钮应可点击，但由于 `audioBuffer` 尚未就绪，应显示加载提示或自动等待解码完成后播放。

### 问题2：1小时FLAC音频频谱卡顿
- **根因**：`WaveformVisualizer` 的 `drawWaveform` 在每次 `currentTime` 变化时（~60fps），都重新扫描整个 `Float32Array` 求峰值（L67-68），然后逐像素重绘整个波形。1小时44.1kHz音频有~1.58亿样本，每帧全量扫描导致严重卡顿。
- **关键问题**：
  1. 峰值归一化（L67-68）每帧重复计算，应缓存
  2. 波形数据每帧全量重绘，应只更新进度条部分
  3. 长音频的 step 计算不够激进（`width * 2` 仍太小）

### 问题3：服务器数据恢复连接后不获取
- **根因**：`AIRepairPanel` 中 `fetchMemoryInfo` 和 `fetchStorageEstimate` 的 effect 依赖 `[duration, channels, sampleRate, algorithmVersion]`，不依赖 `backendAvailable`。当后端断开再恢复时，这些 effect 不会重新触发。
- **额外问题**：effect 中 `if (duration <= 0) { setMemoryInfo(null); return; }` 会清除已有数据，但服务器数据（磁盘/内存总量）不依赖 duration，不应被清除。

## 修改方案

### 1. 播放即时就绪（useAudioProcessor.ts）

**方案**：在 `loadAudioFile` 中，WAV头解析后立即设置 `duration`，解码完成后设置 `audioBuffer`。播放按钮始终可用，点击时：
- 若 `audioBuffer` 已就绪 → 正常播放
- 若 `audioBuffer` 尚未就绪 → 标记 `pendingPlayRef = true`，解码完成后自动播放

具体改动：
- 新增 `pendingPlayRef = useRef(false)`
- `play()` 中：若 buffer 为 null 且 duration > 0，设置 `pendingPlayRef.current = true` 并返回（不静默失败）
- `loadAudioFile` 解码完成后：检查 `pendingPlayRef.current`，若为 true 则自动调用 `play()`

### 2. 波形性能优化（WaveformVisualizer.tsx）

**方案**：缓存波形峰值数据，播放时只更新进度区域，避免每帧全量重绘。

具体改动：
- 新增 `peaksCacheRef` 缓存降采样后的峰值数组（每像素一个 min/max 对）
- `audioBuffer` 或 `waveformPeaks` 变化时，计算并缓存峰值
- 播放时（currentTime 变化），只重绘进度条和进度线，不重绘波形数据
- 峰值归一化值一并缓存，不每帧重算
- 长音频（>5min）的峰值采样步长更激进：`width * 1` 而非 `width * 2`

### 3. 服务器数据重连获取（AIRepairPanel.tsx）

**方案**：将 `backendAvailable` 作为 effect 依赖，后端恢复时重新获取数据。

具体改动：
- AIRepairPanel props 新增 `backendAvailable?: boolean`
- memory/storage fetch effect 依赖新增 `backendAvailable`
- 当 `backendAvailable` 从 false 变为 true 时，重新获取数据
- 移除 `if (duration <= 0) { setMemoryInfo(null); return; }` 中的 `setMemoryInfo(null)` —— 服务器数据不依赖 duration，不应清除
- 同理移除 `setStorageEstimate(null)` —— 保留上次数据直到新数据到达

## 涉及文件

1. `/workspace/src/hooks/useAudioProcessor.ts` - pendingPlay 逻辑
2. `/workspace/src/components/WaveformVisualizer.tsx` - 峰值缓存 + 增量绘制
3. `/workspace/src/components/AIRepairPanel.tsx` - backendAvailable 依赖 + 数据不清除
4. `/workspace/src/pages/Home.tsx` - 传递 backendAvailable 给 AIRepairPanel
5. `/workspace/src/pages/RepairPage.tsx` - 传递 backendAvailable 给 AIRepairPanel

## 验证步骤

1. 上传500MB音频，确认WAV头解析后播放按钮可点击，解码完成后自动播放
2. 上传1小时FLAC，播放时波形流畅无卡顿
3. 断开后端，确认预估卡片保留上次数据；恢复后端，确认数据自动刷新
4. `npx tsc --noEmit` 编译通过
5. `bash scripts/build_android_release.sh` 打包成功

# 修复三个核心问题 v3 — 根因修复

## 问题概述

用户反馈三个问题经过两轮修复仍然存在（"解决了0个问题"），根本原因是之前的修复没有触及真正的 bug：

1. **播放没有立即就绪**：`play()` 是 `useCallback`，依赖列表缺少 `duration` 和 `startStreamingPlayback`，闭包内 `duration` 永远是 0，导致 streaming 播放和 pendingPlay 机制全部是死代码
2. **频谱卡顿**：SpectrumVisualizer 每帧 128 次独立 `ctx.fillRect()` 调用，在移动端 ARM 上开销巨大
3. **服务器数据不独立**：AIRepairPanel 的 effect 有 `if (duration <= 0) return`，即使后端已连接也不获取数据

## 修复方案

### 修复 1：play() 闭包过期问题

**文件**：`/workspace/src/hooks/useAudioProcessor.ts`

**根因**：`play()` 的 `useCallback` 依赖列表是 `[playMode, getCurrentBuffer, getAudioContext, stopPlaying, stopAllModeNodes]`，不包含 `duration` 和 `startStreamingPlayback`。闭包内的 `duration` 永远是初始值 0，`startStreamingPlayback` 也是过期引用。

**修复**：
1. L1827: `if (duration > 0 && pendingObjectURLRef.current)` → `if (durationRef.current > 0 && pendingObjectURLRef.current)`
2. L1833: `if (duration > 0)` → `if (durationRef.current > 0)`
3. L734: `setDuration(buffer.duration)` 后补充 `durationRef.current = buffer.duration`（第4处同步遗漏）
4. 依赖列表添加 `startStreamingPlayback`：`[playMode, getCurrentBuffer, getAudioContext, stopPlaying, stopAllModeNodes, startStreamingPlayback]`

**注意**：不添加 `duration` 到依赖列表（避免 play 函数因 duration 变化而重建），而是用 `durationRef.current` 读取最新值。`startStreamingPlayback` 本身是 useCallback，添加到依赖列表不会导致频繁重建。

### 修复 2：SpectrumVisualizer 批量绘制

**文件**：`/workspace/src/components/SpectrumVisualizer.tsx`

**根因**：每帧 128 次独立 `ctx.fillRect()` 调用，每次都切换 fillStyle 并绘制，在移动端 ARM GPU 上是性能瓶颈。

**修复**：将 128 次独立绘制改为单次批量绘制：
```typescript
// 替换 L78-83 的循环
ctx.beginPath();
for (let i = 0; i < bufferLength; i++) {
  const barHeight = (dataArray[i] / 255) * height;
  ctx.rect(x, height - barHeight, barWidth - 2, barHeight);
  x += barWidth;
}
ctx.fillStyle = gradient;
ctx.fill();
```

原理：`ctx.beginPath()` + 多次 `ctx.rect()` + 单次 `ctx.fill()` 将 128 次 GPU draw call 合并为 1 次，大幅减少 GPU 状态切换开销。

### 修复 3：AIRepairPanel 移除 duration<=0 阻断

**文件**：`/workspace/src/components/AIRepairPanel.tsx`

**根因**：L124 和 L137 的 `if (duration <= 0) return` 阻止了在后端已连接但本地音频未加载时获取服务器数据。

**修复**：
1. L119-130 的 memoryInfo effect：移除 `if (duration <= 0) return`（L124），改为在 fetchMemoryInfo 调用前检查 duration，duration<=0 时使用默认参数（如 duration=300, channels=2）
2. L132-143 的 storageEstimate effect：移除 `if (duration <= 0) return`（L137），同样使用默认参数

具体实现：
```typescript
// memoryInfo effect
useEffect(() => {
  if (!backendAvailable) {
    setMemoryInfo(null);
    return;
  }
  const fetchDuration = duration > 0 ? duration : 300;
  const fetchChannels = channels > 0 ? channels : 2;
  if (memoryFetchRef.current) clearTimeout(memoryFetchRef.current);
  memoryFetchRef.current = setTimeout(() => {
    fetchMemoryInfo(fetchDuration, fetchChannels, processingOptions.sampleRate, algorithmVersion).then(setMemoryInfo);
  }, 300);
  return () => { if (memoryFetchRef.current) clearTimeout(memoryFetchRef.current); };
}, [duration, channels, processingOptions.sampleRate, algorithmVersion, backendAvailable]);

// storageEstimate effect 同理
```

这样后端连接后即使没有加载音频，也能立即获取服务器内存/存储信息。

## 验证步骤

1. `npm run build` 确认编译通过
2. `bash scripts/build_android_release.sh` 确认 Android 打包通过
3. 手动验证：
   - 加载大 FLAC 文件后，点击播放应立即开始（streaming 播放），不需要等完整解码
   - 播放过程中频谱应流畅无卡顿
   - 后端连接后，即使未加载音频，服务器内存/存储信息应立即显示

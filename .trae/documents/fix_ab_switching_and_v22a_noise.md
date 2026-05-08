# 修复计划：A/B切换问题 + v2.2a电流声

## 当前状态分析

### A/B切换问题

**已确认的问题：**
1. 修复完成后自动播放的是原始音频而非修复后音频（已修复：`startStreamingPlayback` 现在正确设置 `activeModeRef` 和 `playMode`）
2. 用户反馈"同时在播放的问题又出现了"——切换时旧音频没有正确停止，导致两个音频同时播放

**根本原因：**
- `switchPlayMode` 中停止旧节点使用 `currentNode.source.stop(now + fadeDuration + 0.01)`，但新节点在 `now` 时刻就开始播放
- 旧节点在新节点开始后还会运行 30ms，造成短暂重叠
- `stopAllModeNodes` 中 `immediate=false` 分支（seek时使用）有 `setTimeout`，但 `switchPlayMode` 调用的是 `immediate=true`
- `play` 函数中移除了"复用已有节点"逻辑后，每次播放都重新创建节点，但 `modeNodesRef` 中可能残留旧节点引用

**当前代码流程：**
```
switchPlayMode('backend'):
  1. targetBuffer = backendProcessedBuffer
  2. 检查 isPlayingRef.current
  3. 获取 currentPosition
  4. 停止当前节点（淡出20ms，30ms后stop）
  5. 创建新节点（targetBuffer）
  6. 新节点在 now 时刻 start
  7. 清理 modeNodesRef（所有设为null）
  8. 设置 modeNodesRef[mode] = newNode
  9. 设置 activeModeRef.current = mode
  10. setPlayMode(mode)
```

**问题：** 第4步旧节点30ms后才stop，第6步新节点立即start，重叠30ms。且旧节点的 `onended` 被设为null，但 `stopPlaying` 中的逻辑可能触发。

### v2.2a电流声问题

**当前实现：** `backend/services/repair/repair_v2_2a/core.py`
- 纯时域处理链：declip → depop → compress → dc remove → lowpass(17kHz) → normalize
- 使用 `lfilter` 进行包络检测和滤波
- 硬限幅到 0.95

**可能原因：**
1. `_smooth_compress` 的 makeup gain 计算：gain = 1.0 + min((1.0 - 1.0/ratio) * amount * 0.03, 0.04)，最大1.04倍（+0.35dB），过于保守
2. `_loudness_normalize` 目标响度 -16 LUFS，可能过度放大噪声底
3. `_simple_declip` 软限幅后可能引入高频谐波
4. `_simple_depop` 线性插值修复爆音时可能引入高频成分
5. 低通滤波截止频率 17kHz 可能不够低，高频artifacts未被完全消除

---

## 方案对比：停止重建 vs 静音

### 方案A：停止重建（当前方案）

**原理：** 切换时停止旧AudioBufferSourceNode，创建新的播放目标音频

**优点：**
- 逻辑简单，只有一个节点在运行
- 不会出现多个节点同时输出导致音量叠加
- AnalyserNode显示的是单一音频源的频谱
- 内存占用低，旧节点及时释放

**缺点：**
- 旧节点stop和新节点start之间有间隙（即使只有20-30ms）
- 如果旧节点stop时机不对，可能产生click/pop噪声
- 需要精确控制淡出/淡入时间

**处理难度：** 低。只需确保旧节点正确停止，新节点正确创建。

### 方案B：静音策略（之前方案）

**原理：** 为每种模式创建独立的source+gain节点，通过控制gain值（0或1）来切换

**优点：**
- 切换瞬间完成，无间隙
- 可以实现交叉淡入淡出（crossfade）

**缺点：**
- 多个节点同时连接到AnalyserNode，频谱显示混合数据
- 内存占用高，所有模式的音频buffer都需保持
- 如果gain控制不精确，可能出现泄漏（两个模式同时出声）
- 代码复杂度高，需要维护modeNodesRef映射
- 之前实现中setTimeout导致卡顿

**处理难度：** 高。需要解决analyser混合、内存管理、时序同步等问题。

### 结论

**选择方案A（停止重建）**，但需修复以下问题：
1. 旧节点停止和新节点开始之间的时序问题
2. 添加日志调试以便定位问题

---

## 修复计划

### 阶段1：A/B切换修复（高优先级）

#### 1.1 修复切换时重叠播放问题

**文件：** `src/hooks/useAudioProcessor.ts`

**修改 `switchPlayMode`：**
```typescript
const switchPlayMode = useCallback(async (mode: PlayMode) => {
  writeLog(`[switchPlayMode] 开始切换: target=${mode}, current=${activeModeRef.current}, isPlaying=${isPlayingRef.current}`);
  
  const targetBuffer = mode === 'browser' ? browserProcessedBuffer
    : mode === 'backend' ? backendProcessedBuffer
    : audioBuffer;
  
  if (!targetBuffer) {
    writeLog(`[switchPlayMode] 目标buffer为空，只切换状态`);
    setPlayMode(mode);
    return;
  }

  if (!isPlayingRef.current) {
    writeLog(`[switchPlayMode] 未在播放，直接切换状态`);
    setPlayMode(mode);
    return;
  }

  if (activeModeRef.current === mode) {
    writeLog(`[switchPlayMode] 已是目标模式，无需操作`);
    setPlayMode(mode);
    return;
  }

  const currentPosition = currentTime;
  const context = getAudioContext();
  if (context.state === 'suspended') {
    await context.resume();
  }

  const now = context.currentTime;
  const fadeDuration = 0.02;
  const startPosition = Math.min(currentPosition, targetBuffer.duration - 0.01);

  writeLog(`[switchPlayMode] 停止当前节点: mode=${activeModeRef.current}, position=${currentPosition.toFixed(3)}`);

  // 1. 立即停止当前播放（不淡出，避免重叠）
  const currentNode = modeNodesRef.current[activeModeRef.current];
  if (currentNode) {
    try {
      currentNode.source.onended = null;
      currentNode.source.stop(now);
      currentNode.source.disconnect();
      currentNode.gain.disconnect();
      writeLog(`[switchPlayMode] 旧节点已停止并断开`);
    } catch (e) {
      writeLog(`[switchPlayMode] 停止旧节点出错: ${e}`);
    }
  }

  // 2. 清理所有旧节点引用
  (Object.keys(modeNodesRef.current) as PlayMode[]).forEach((m) => {
    modeNodesRef.current[m] = null;
  });

  // 3. 创建新节点
  writeLog(`[switchPlayMode] 创建新节点: mode=${mode}, bufferDuration=${targetBuffer.duration.toFixed(3)}`);
  const newSource = context.createBufferSource();
  const newGain = context.createGain();
  newSource.buffer = targetBuffer;
  newSource.connect(newGain);
  newGain.connect(analyserRef.current!);
  analyserRef.current!.connect(context.destination);

  // 使用极短淡入避免click
  newGain.gain.setValueAtTime(0, now);
  newGain.gain.linearRampToValueAtTime(1.0, now + 0.01);

  newSource.onended = () => {
    writeLog(`[switchPlayMode] 新节点播放结束`);
    if (isPlayingRef.current) {
      stopPlaying();
      setCurrentTime(0);
      pausedAtRef.current = 0;
    }
  };

  modeNodesRef.current[mode] = { source: newSource, gain: newGain };
  sourceNodeRef.current = newSource;
  gainNodeRef.current = newGain;
  activeModeRef.current = mode;

  startTimeRef.current = now - startPosition;
  newSource.start(now, startPosition);
  writeLog(`[switchPlayMode] 新节点已启动: startTime=${startTimeRef.current.toFixed(3)}, offset=${startPosition.toFixed(3)}`);

  setPlayMode(mode);

  if (animationFrameRef.current) {
    cancelAnimationFrame(animationFrameRef.current);
  }

  const updateTime = () => {
    if (isPlayingRef.current) {
      const elapsed = context.currentTime - startTimeRef.current;
      if (elapsed >= targetBuffer.duration) {
        stopPlaying();
        setCurrentTime(0);
        pausedAtRef.current = 0;
      } else {
        setCurrentTime(elapsed);
        animationFrameRef.current = requestAnimationFrame(updateTime);
      }
    }
  };
  updateTime();
}, [...]);
```

**关键修改：**
- 旧节点使用 `stop(now)` 立即停止（不淡出），避免与新节点重叠
- 新节点使用 10ms 淡入（比之前的 20ms 更短）
- 添加详细日志便于调试

#### 1.2 修复 `stopAllModeNodes` 中的 setTimeout

**文件：** `src/hooks/useAudioProcessor.ts`

**修改：**
```typescript
const stopAllModeNodes = useCallback((immediate = true) => {
  const context = audioContextRef.current;
  (Object.keys(modeNodesRef.current) as PlayMode[]).forEach((mode) => {
    const node = modeNodesRef.current[mode];
    if (!node) return;
    try {
      node.source.onended = null;
      if (!immediate && context) {
        // 使用 AudioParam 调度淡出，不依赖 setTimeout
        const now = context.currentTime;
        node.gain.gain.setValueAtTime(node.gain.gain.value, now);
        node.gain.gain.linearRampToValueAtTime(0.0001, now + 0.03);
        node.source.stop(now + 0.03);
      } else {
        node.source.stop();
        node.source.disconnect();
        node.gain.disconnect();
      }
    } catch {}
    modeNodesRef.current[mode] = null;
  });
  sourceNodeRef.current = null;
  gainNodeRef.current = null;
}, []);
```

**关键修改：**
- 非 immediate 模式使用 Web Audio API 的调度（`stop(now + 0.03)`）代替 setTimeout
- 避免 JavaScript 定时器带来的延迟和卡顿

#### 1.3 修复 `play` 函数中的 seek 逻辑

**文件：** `src/hooks/useAudioProcessor.ts`

**当前问题：** seek 时调用 `stopAllModeNodes()`（immediate=true），然后重新创建节点。但如果 `seekInProgressRef` 没有正确重置，可能导致问题。

**修改：**
```typescript
const play = useCallback(async () => {
  writeLog(`[play] 开始播放: playMode=${playMode}, isPlaying=${isPlayingRef.current}`);
  
  // ... streaming 处理 ...

  const buffer = getCurrentBuffer() ?? audioBufferRef.current;
  if (!buffer) {
    writeLog(`[play] 没有可用buffer，返回`);
    return;
  }

  const context = getAudioContext();
  if (context.state === 'suspended') {
    await context.resume();
    await new Promise(resolve => setTimeout(resolve, 50));
  }

  // seek 时停止所有节点
  if (seekInProgressRef.current) {
    writeLog(`[play] seek模式，停止所有节点`);
    stopAllModeNodes();
    seekInProgressRef.current = false;
  }

  // 检查是否已有节点在运行（不应该发生，但做保护）
  if (modeNodesRef.current[playMode]) {
    writeLog(`[play] 警告: 当前模式已有节点，先停止`);
    try {
      const node = modeNodesRef.current[playMode]!;
      node.source.onended = null;
      node.source.stop();
      node.source.disconnect();
      node.gain.disconnect();
    } catch {}
    modeNodesRef.current[playMode] = null;
  }

  // 创建新节点
  writeLog(`[play] 创建新节点: mode=${playMode}, bufferDuration=${buffer.duration.toFixed(3)}`);
  const source = context.createBufferSource();
  const gain = context.createGain();

  source.buffer = buffer;
  source.connect(gain);
  gain.connect(analyserRef.current!);
  analyserRef.current!.connect(context.destination);

  const fadeInDuration = 0.015;
  gain.gain.setValueAtTime(0, context.currentTime);
  gain.gain.linearRampToValueAtTime(1.0, context.currentTime + fadeInDuration);

  // ... 其余逻辑不变 ...
}, [...]);
```

#### 1.4 修复 `applySettings` 中修复完成后的播放逻辑

**文件：** `src/hooks/useAudioProcessor.ts`

**当前问题：** `startStreamingPlayback` 播放修复后音频，但 `loadAudioFromUrl` 异步加载 buffer 后没有切换到 buffer 播放。

**修改：**
```typescript
// 后台加载修复后的音频 buffer
if (audioFile && taskIdRef.current) {
  loadAudioFromUrl(previewUrl, processingOptions.sampleRate).then(repairedBuffer => {
    writeLog(`[applySettings] buffer加载完成: duration=${repairedBuffer.duration.toFixed(3)}`);
    setBackendProcessedBuffer(repairedBuffer);
    
    // 如果当前正在播放streaming，切换到buffer播放
    if (isPlayingRef.current && streamingAudioRef.current) {
      writeLog(`[applySettings] 正在播放streaming，切换到buffer播放`);
      const currentPos = streamingAudioRef.current.currentTime;
      stopPlaying();
      pausedAtRef.current = currentPos;
      
      // 使用新的buffer播放
      const context = getAudioContext();
      const newSource = context.createBufferSource();
      const newGain = context.createGain();
      newSource.buffer = repairedBuffer;
      newSource.connect(newGain);
      newGain.connect(analyserRef.current!);
      analyserRef.current!.connect(context.destination);
      newGain.gain.setValueAtTime(0, context.currentTime);
      newGain.gain.linearRampToValueAtTime(1.0, context.currentTime + 0.015);
      
      newSource.onended = () => {
        if (isPlayingRef.current) {
          stopPlaying();
          setCurrentTime(0);
          pausedAtRef.current = 0;
        }
      };
      
      modeNodesRef.current['backend'] = { source: newSource, gain: newGain };
      sourceNodeRef.current = newSource;
      gainNodeRef.current = newGain;
      activeModeRef.current = 'backend';
      
      startTimeRef.current = context.currentTime - currentPos;
      newSource.start(0, currentPos);
      playStartTimeRef.current = performance.now();
      
      const updateTime = () => {
        if (isPlayingRef.current) {
          const elapsed = (performance.now() - playStartTimeRef.current) / 1000;
          const current = currentPos + elapsed;
          if (current >= repairedBuffer.duration) {
            stopPlaying();
            setCurrentTime(0);
            pausedAtRef.current = 0;
          } else {
            setCurrentTime(current);
            animationFrameRef.current = requestAnimationFrame(updateTime);
          }
        }
      };
      updateTime();
    }
  }).catch(err => {
    console.warn('[applySettings] 后台下载修复后音频失败:', err);
  });
}
```

---

### 阶段2：v2.2a电流声修复（中优先级）

#### 2.1 分析电流声来源

**文件：** `backend/services/repair/repair_v2_2a/core.py`

**可能原因及修复：**

1. **makeup gain 过于保守**
   - 当前：最大 +0.35dB
   - 修复：根据实际压缩量计算 makeup gain

2. **loudness normalize 过度放大噪声**
   - 当前：目标 -16 LUFS，最大增益 +12dB
   - 修复：降低目标响度或限制最大增益

3. **depop 线性插值引入高频**
   - 当前：用线性插值替换爆音样本
   - 修复：使用更平滑的插值（如余弦插值）

4. **低通滤波不够低**
   - 当前：17kHz
   - 修复：降低到 16kHz 或根据采样率动态调整

5. **declip 软限幅引入谐波**
   - 当前：sigmoid 曲线
   - 修复：使用更平滑的过渡或降低阈值

#### 2.2 具体修改

**修改 `_smooth_compress`：**
```python
# 更合理的 makeup gain
compressed_rms = np.sqrt(np.mean(out ** 2))
input_rms = np.sqrt(np.mean(y ** 2))
if compressed_rms > 1e-10 and input_rms > 1e-10:
    makeup_gain = min(input_rms / compressed_rms, 1.5)  # 最大 +3.5dB
    out = out * makeup_gain
```

**修改 `_loudness_normalize`：**
```python
# 限制最大增益为 +6dB（避免过度放大噪声底）
gain = min(gain, 2.0)  # 原来是 4.0 (+12dB)
```

**修改 `_simple_depop`：**
```python
# 使用余弦插值代替线性插值
y_out[left:right] = y[left] + (y[right-1] - y[left]) * 0.5 * (1 - np.cos(np.linspace(0, np.pi, right - left)))
```

**修改 `_lowpass_final`：**
```python
# 根据采样率动态调整截止频率
cutoff_hz = min(16000, sr * 0.4)  # 不超过16kHz，不超过采样率的40%
```

---

## 验证步骤

### A/B切换验证
1. 上传音频
2. 点击播放原始音频
3. 点击修复
4. 修复完成后自动播放修复后音频
5. 点击"原始"按钮切换回原始音频
6. 观察波形颜色和label是否正确变化
7. 观察是否有两个音频同时播放（通过耳朵听或看频谱）

### v2.2a电流声验证
1. 上传有明显电流声的音频
2. 选择v2.2a算法
3. 修复后播放
4. 对比修复前后的电流声

---

## 文件修改清单

| 文件 | 修改内容 |
|------|---------|
| `src/hooks/useAudioProcessor.ts` | 修复switchPlayMode、stopAllModeNodes、play、applySettings |
| `backend/services/repair/repair_v2_2a/core.py` | 修复电流声参数 |

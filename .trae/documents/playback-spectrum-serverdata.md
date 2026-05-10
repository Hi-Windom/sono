# 播放即时就绪 + 频谱性能优化 + 服务器数据重连获取

## 问题分析

### 问题1：播放没有立即就绪
- **现象**：加载新音频后，WAV header 解析完成即释放 UI，但 `play()` 在 `audioBuffer` 为 null 时静默返回（L1782-1786）
- **根因**：WAV header 解析只设置了 `duration`/`wavInfo`，`audioBuffer` 要等后台解码完成才可用。用户点击播放时 buffer 为 null，直接 return
- **方案**：新增 `pendingPlayRef`，play 时若 buffer 为 null 但 duration > 0 则标记 pending，解码完成后自动播放

### 问题2：频谱卡顿感明显（1小时 FLAC）
- **现象**：SpectrumVisualizer 在长音频播放时明显卡顿
- **根因**（[SpectrumVisualizer.tsx](file:///workspace/src/components/SpectrumVisualizer.tsx)）：
  1. **每帧重设 canvas 尺寸**（L38-42）：`canvas.width = ...` 会清空 canvas 并重置上下文状态，触发昂贵的 GPU 操作
  2. **每个 bar 每帧创建渐变**（L53-55）：`ctx.createLinearGradient()` + `addColorStop()` 在循环内调用，128 个 bar × 60fps = 7680 次/秒
  3. **无帧率节流**：requestAnimationFrame 以 60fps 运行，频谱 30fps 足够
- **方案**：
  1. 缓存 canvas 尺寸，仅在容器尺寸变化时重设
  2. 预创建渐变对象并缓存，仅颜色变化时重建
  3. 添加 30fps 帧率节流
  4. 用 `clearRect` 替代 canvas 尺寸重设来清屏

### 问题3：服务器数据没有恢复连接后获取
- **现象**：后端断开后重连，AIRepairPanel 的内存/存储数据不刷新
- **根因**（[AIRepairPanel.tsx](file:///workspace/src/components/AIRepairPanel.tsx) L117-139）：
  1. fetch effect 依赖列表中没有 `backendAvailable`，后端恢复时不会重新触发
  2. `duration <= 0` 时清除服务器数据（L118-121, L130-133），但 duration 可能还没设置
- **方案**：
  1. AIRepairPanel 新增 `backendAvailable` prop
  2. fetch effect 依赖列表加入 `backendAvailable`
  3. 服务器数据（memoryInfo/storageEstimate）不因 `duration <= 0` 清除，仅因 `backendAvailable=false` 清除
  4. Home.tsx 和 RepairPage.tsx 传递 `backendAvailable`

## 实现步骤

### 步骤1：播放即时就绪 — pendingPlayRef

**文件**：`/workspace/src/hooks/useAudioProcessor.ts`

1. 在 ref 声明区域新增：
   ```typescript
   const pendingPlayRef = useRef(false);
   ```

2. 修改 `play()` 函数（约 L1782-1786）：
   ```typescript
   const buffer = getCurrentBuffer() ?? audioBufferRef.current;
   if (!buffer) {
     if (durationRef.current > 0) {
       writeLog(`[play] buffer未就绪，标记pendingPlay`);
       pendingPlayRef.current = true;
     }
     return;
   }
   ```

3. 在 `loadAudioFile` 解码完成后（约 L715-717），添加自动播放：
   ```typescript
   audioBufferRef.current = buffer;
   setAudioBuffer(buffer);
   setDuration(buffer.duration);

   // 如果用户已点击播放但buffer未就绪，自动播放
   if (pendingPlayRef.current) {
     pendingPlayRef.current = false;
     writeLog(`[loadAudioFile] 执行pendingPlay`);
     play();
   }
   ```

4. 在 `stopPlaying` 中重置 pendingPlayRef：
   ```typescript
   pendingPlayRef.current = false;
   ```

### 步骤2：频谱性能优化

**文件**：`/workspace/src/components/SpectrumVisualizer.tsx`

重写组件，关键优化：
1. **缓存 canvas 尺寸**：用 `lastWidthRef`/`lastHeightRef` 记录，仅在变化时重设 canvas 尺寸
2. **缓存渐变对象**：预创建渐变，仅在颜色变化时重建
3. **30fps 帧率节流**：用时间戳判断，跳过不足 33ms 的帧
4. **用 clearRect 替代 canvas 尺寸重设**：清屏用 `ctx.clearRect(0, 0, width, height)` 而非重设 `canvas.width`

```typescript
export function SpectrumVisualizer({ analyser, label, color = '#00D9FF' }: SpectrumVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationFrameRef = useRef<number>();
  const containerRef = useRef<HTMLDivElement>(null);
  const lastSizeRef = useRef({ width: 0, height: 0 });
  const gradientRef = useRef<CanvasGradient | null>(null);
  const lastColorRef = useRef<string>('');
  const lastFrameTimeRef = useRef(0);

  useEffect(() => {
    if (!analyser || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    analyser.fftSize = 256;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const ensureCanvasSize = () => {
      const container = containerRef.current;
      const actualWidth = container ? container.clientWidth : 400;
      const actualHeight = 120;
      if (lastSizeRef.current.width !== actualWidth || lastSizeRef.current.height !== actualHeight) {
        canvas.width = actualWidth * window.devicePixelRatio;
        canvas.height = actualHeight * window.devicePixelRatio;
        canvas.style.width = actualWidth + 'px';
        canvas.style.height = actualHeight + 'px';
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
        lastSizeRef.current = { width: actualWidth, height: actualHeight };
        // 尺寸变化时重建渐变
        gradientRef.current = null;
      }
      return { width: actualWidth, height: actualHeight };
    };

    const ensureGradient = (actualHeight: number) => {
      if (gradientRef.current && lastColorRef.current === color) return gradientRef.current;
      const gradient = ctx.createLinearGradient(0, 0, 0, actualHeight);
      gradient.addColorStop(0, color + '80');
      gradient.addColorStop(1, color);
      gradientRef.current = gradient;
      lastColorRef.current = color;
      return gradient;
    };

    const draw = (timestamp: number) => {
      animationFrameRef.current = requestAnimationFrame(draw);
      // 30fps 节流
      if (timestamp - lastFrameTimeRef.current < 33) return;
      lastFrameTimeRef.current = timestamp;

      analyser.getByteFrequencyData(dataArray);
      const { width, height } = ensureCanvasSize();
      const gradient = ensureGradient(height);

      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = '#0A1A2F';
      ctx.fillRect(0, 0, width, height);

      const barWidth = (width / bufferLength) * 2.5;
      let x = 0;
      for (let i = 0; i < bufferLength; i++) {
        const barHeight = (dataArray[i] / 255) * height;
        ctx.fillStyle = gradient;
        ctx.fillRect(x, height - barHeight, barWidth - 2, barHeight);
        x += barWidth;
      }
    };

    draw(0);
    return () => { if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current); };
  }, [analyser, color]);

  // ... JSX 不变
}
```

**渐变方向说明**：原代码每个 bar 创建从 `actualHeight - barHeight` 到 `actualHeight` 的渐变（底部浅色），但每帧每 bar 创建渐变是性能瓶颈。改为预创建一个从顶部到底部的固定渐变（顶部浅色 `color+'80'`，底部深色 `color`），效果接近但只需创建一次。

### 步骤3：服务器数据重连获取

**文件1**：`/workspace/src/components/AIRepairPanel.tsx`

1. Props 接口新增：
   ```typescript
   backendAvailable?: boolean;
   ```

2. 解构新增：
   ```typescript
   backendAvailable = false,
   ```

3. 修改内存 fetch effect（L117-127）：
   ```typescript
   useEffect(() => {
     if (!backendAvailable) {
       setMemoryInfo(null);
       return;
     }
     if (duration <= 0) return; // 不清除，只是不请求
     if (memoryFetchRef.current) clearTimeout(memoryFetchRef.current);
     memoryFetchRef.current = setTimeout(() => {
       fetchMemoryInfo(duration, channels, processingOptions.sampleRate, algorithmVersion).then(setMemoryInfo);
     }, 300);
     return () => { if (memoryFetchRef.current) clearTimeout(memoryFetchRef.current); };
   }, [duration, channels, processingOptions.sampleRate, algorithmVersion, backendAvailable]);
   ```

4. 修改存储 fetch effect（L129-139）：同理，`!backendAvailable` 时清除，`duration <= 0` 时仅不请求但不清除，依赖加 `backendAvailable`

**文件2**：`/workspace/src/pages/Home.tsx`

AIRepairPanel 调用处新增 prop：
```tsx
<AIRepairPanel
  ...
  backendAvailable={backendAvailable}
/>
```

**文件3**：`/workspace/src/pages/RepairPage.tsx`

同上，新增 `backendAvailable` prop。

### 步骤4：波形峰值缓存优化（附加）

**文件**：`/workspace/src/components/WaveformVisualizer.tsx`

当前问题：每帧扫描整个 Float32Array 计算归一化峰值（L67-68），1小时音频的 Float32Array 有 ~1.7 亿个采样点。

1. 新增 `peakNormRef` 缓存归一化系数：
   ```typescript
   const peakNormRef = useRef<number>(0);
   const lastBufferKeyRef = useRef<string>('');
   ```

2. 在 `drawWaveform` 中，仅在 audioBuffer 变化时重新计算 peak：
   ```typescript
   const bufferKey = data ? `${data.length}_${audioBufferRef.current?.duration}` : '';
   if (bufferKey !== lastBufferKeyRef.current) {
     let peak = 0;
     for (let i = 0; i < data.length; i += (isLongAudio ? 8 : 1)) peak = Math.max(peak, Math.abs(data[i]));
     peakNormRef.current = peak > 0.05 ? 1 / peak : 20;
     lastBufferKeyRef.current = bufferKey;
   }
   const norm = peakNormRef.current;
   ```

## 验证步骤

1. 加载音频后立即点击播放 → 应在解码完成后自动开始播放
2. 播放1小时 FLAC → 频谱应流畅无卡顿
3. 断开后端 → 重连后内存/存储数据应自动刷新
4. `npm run build` 无报错
5. `bash scripts/build_android_release.sh` 打包成功

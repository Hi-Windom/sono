/**
 * 智能高频细节补充模块 - 优化版
 * 使用 Web Audio API 原生滤波器进行高效处理，避免 O(n²) FFT 计算
 */

export async function enhanceHighFrequencies(
  buffer: AudioBuffer,
  progressCallback?: (progress: number) => void
): Promise<AudioBuffer> {
  try {
    if (progressCallback) progressCallback(0);

    // 第一步：使用原生 OfflineAudioContext 重采样到 96kHz
    const targetSampleRate = 96000;
    const ratio = targetSampleRate / buffer.sampleRate;
    const newLength = Math.floor(buffer.length * ratio);

    if (progressCallback) progressCallback(0.1);

    const offlineContext = new OfflineAudioContext(
      buffer.numberOfChannels,
      newLength,
      targetSampleRate
    );

    // 创建源节点
    const source = offlineContext.createBufferSource();
    source.buffer = buffer;

    // 创建音频链：源 -> 高频激励 -> 空气感增强 -> 低通滤波 -> 输出

    // 1. 高频激励器：轻微提升超高频区域 (15-20kHz)
    const highShelf1 = offlineContext.createBiquadFilter();
    highShelf1.type = 'highshelf';
    highShelf1.frequency.value = 15000;
    highShelf1.gain.value = 1.5;
    highShelf1.Q.value = 0.5;

    // 2. 空气感增强：极高频提升 (20-30kHz)
    const highShelf2 = offlineContext.createBiquadFilter();
    highShelf2.type = 'highshelf';
    highShelf2.frequency.value = 22000;
    highShelf2.gain.value = 1.0;
    highShelf2.Q.value = 0.3;

    // 3. 超高频空气感 (30-40kHz)
    const peaking1 = offlineContext.createBiquadFilter();
    peaking1.type = 'peaking';
    peaking1.frequency.value = 32000;
    peaking1.Q.value = 1.5;
    peaking1.gain.value = 0.8;

    // 4. 极高空气感 (40-48kHz)
    const peaking2 = offlineContext.createBiquadFilter();
    peaking2.type = 'peaking';
    peaking2.frequency.value = 42000;
    peaking2.Q.value = 2;
    peaking2.gain.value = 0.5;

    // 5. 低通滤波器：防止超过奈奎斯特频率的混叠
    const lowPass = offlineContext.createBiquadFilter();
    lowPass.type = 'lowpass';
    lowPass.frequency.value = 48000;
    lowPass.Q.value = 0.7;

    // 连接音频链
    source.connect(highShelf1);
    highShelf1.connect(highShelf2);
    highShelf2.connect(peaking1);
    peaking1.connect(peaking2);
    peaking2.connect(lowPass);
    lowPass.connect(offlineContext.destination);

    source.start();

    if (progressCallback) progressCallback(0.5);

    // 渲染音频
    const enhanced = await offlineContext.startRendering();

    if (progressCallback) progressCallback(1);

    return enhanced;

  } catch (error) {
    console.error('High frequency enhancement failed:', error);

    // 降级方案：使用简单重采样
    const targetSampleRate = 96000;
    const ratio = targetSampleRate / buffer.sampleRate;
    const newLength = Math.floor(buffer.length * ratio);

    const fallbackContext = new OfflineAudioContext(
      buffer.numberOfChannels,
      newLength,
      targetSampleRate
    );

    const source = fallbackContext.createBufferSource();
    source.buffer = buffer;
    source.connect(fallbackContext.destination);
    source.start();

    return fallbackContext.startRendering();
  }
}
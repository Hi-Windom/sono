export interface DecodedWavResult {
  channelData: Float32Array[];
  sampleRate: number;
  channels: number;
  bitDepth: number;
  totalFrames: number;
  decodeTimeMs?: number;
}

export interface AudioIssue {
  type: 'clip' | 'crackle' | 'pop' | 'ess' | 'noise';
  start: number;
  end: number;
  severity: number;
}

export interface AudioAnalysisResult {
  spectralFlatness: number;
  dynamicRange: number;
  stereoBalance: number;
  peakLevel: number;
  issues: string[];
  clippingCount: number;
  crackleRegions: number[];
  popRegions: number[];
  detailedIssues: AudioIssue[];
  analysisTimeMs?: number;
}

type WorkerRequest =
  | { type: 'decode-wav'; id: number; buffer: ArrayBuffer }
  | { type: 'analyze-audio'; id: number; channelData: Float32Array[]; sampleRate: number; channels: number }
  | { type: 'decode-and-analyze'; id: number; buffer: ArrayBuffer };

type WorkerResponse =
  | { type: 'decode-wav'; id: number; result: DecodedWavResult | null }
  | { type: 'analyze-audio'; id: number; result: AudioAnalysisResult }
  | { type: 'decode-and-analyze'; id: number; decode: DecodedWavResult | null; analysis: AudioAnalysisResult | null };

interface WavParseResult {
  sampleRate: number;
  bitDepth: number;
  channels: number;
  duration: number;
  dataOffset: number;
  dataSize: number;
}

function parseWavHeaderFull(buffer: ArrayBuffer): WavParseResult | null {
  try {
    const view = new DataView(buffer);
    const riff = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
    if (riff !== 'RIFF') return null;
    const wave = String.fromCharCode(view.getUint8(8), view.getUint8(9), view.getUint8(10), view.getUint8(11));
    if (wave !== 'WAVE') return null;

    let offset = 12;
    let sampleRate = 0;
    let bitDepth = 0;
    let channels = 0;
    let dataSize = 0;
    let dataOffset = 0;
    let audioFormat = 0;

    while (offset < buffer.byteLength - 8) {
      const chunkId = String.fromCharCode(
        view.getUint8(offset), view.getUint8(offset + 1),
        view.getUint8(offset + 2), view.getUint8(offset + 3),
      );
      const chunkSize = view.getUint32(offset + 4, true);
      if (chunkId === 'fmt ') {
        audioFormat = view.getUint16(offset + 8, true);
        channels = view.getUint16(offset + 10, true);
        sampleRate = view.getUint32(offset + 12, true);
        bitDepth = view.getUint16(offset + 22, true);
      } else if (chunkId === 'data') {
        dataSize = chunkSize;
        dataOffset = offset + 8;
        break;
      }
      offset += 8 + chunkSize;
      if (chunkSize % 2 !== 0) offset += 1;
    }

    if (sampleRate === 0 || bitDepth === 0 || dataOffset === 0) return null;
    if (audioFormat !== 1) return null;
    return { sampleRate, bitDepth, channels, duration: 0, dataOffset, dataSize };
  } catch {
    return null;
  }
}

function deinterleaveInt16(src: Int16Array, channels: number): Float32Array[] {
  const totalFrames = src.length / channels;
  const outputs: Float32Array[] = new Array(channels);
  for (let ch = 0; ch < channels; ch++) {
    outputs[ch] = new Float32Array(totalFrames);
  }
  const invMax = 1 / 32768;
  let idx = 0;
  for (let i = 0; i < totalFrames; i++) {
    for (let ch = 0; ch < channels; ch++) {
      outputs[ch][i] = src[idx++] * invMax;
    }
  }
  return outputs;
}

function deinterleaveInt32(src: Int32Array, channels: number): Float32Array[] {
  const totalFrames = src.length / channels;
  const outputs: Float32Array[] = new Array(channels);
  for (let ch = 0; ch < channels; ch++) {
    outputs[ch] = new Float32Array(totalFrames);
  }
  const invMax = 1 / 2147483648;
  let idx = 0;
  for (let i = 0; i < totalFrames; i++) {
    for (let ch = 0; ch < channels; ch++) {
      outputs[ch][i] = src[idx++] * invMax;
    }
  }
  return outputs;
}

function deinterleaveUint8(src: Uint8Array, channels: number): Float32Array[] {
  const totalFrames = src.length / channels;
  const outputs: Float32Array[] = new Array(channels);
  for (let ch = 0; ch < channels; ch++) {
    outputs[ch] = new Float32Array(totalFrames);
  }
  const invMax = 1 / 128;
  let idx = 0;
  for (let i = 0; i < totalFrames; i++) {
    for (let ch = 0; ch < channels; ch++) {
      outputs[ch][i] = (src[idx++] - 128) * invMax;
    }
  }
  return outputs;
}

function deinterleaveInt24(src: Uint8Array, channels: number): Float32Array[] {
  const bytesPerFrame = channels * 3;
  const totalFrames = Math.floor(src.length / bytesPerFrame);
  const outputs: Float32Array[] = new Array(channels);
  for (let ch = 0; ch < channels; ch++) {
    outputs[ch] = new Float32Array(totalFrames);
  }
  const invMax = 1 / 8388608;
  for (let i = 0; i < totalFrames; i++) {
    let byteOffset = i * bytesPerFrame;
    for (let ch = 0; ch < channels; ch++) {
      const b0 = src[byteOffset];
      const b1 = src[byteOffset + 1];
      const b2 = src[byteOffset + 2];
      let raw = b0 | (b1 << 8) | (b2 << 16);
      if (raw & 0x800000) raw |= ~0xFFFFFF;
      outputs[ch][i] = raw * invMax;
      byteOffset += 3;
    }
  }
  return outputs;
}

function decodeWavPcm(buffer: ArrayBuffer): DecodedWavResult | null {
  const startTime = performance.now();
  const parseResult = parseWavHeaderFull(buffer);
  if (!parseResult) return null;

  const { sampleRate, bitDepth, channels, dataOffset, dataSize } = parseResult;
  const bytesPerSample = bitDepth / 8;
  const totalFrames = Math.floor(dataSize / (channels * bytesPerSample));
  const actualDataSize = totalFrames * channels * bytesPerSample;

  let channelData: Float32Array[];
  const dataBytes = new Uint8Array(buffer, dataOffset, actualDataSize);

  if (bitDepth === 16) {
    const int16 = new Int16Array(dataBytes.buffer, dataBytes.byteOffset, actualDataSize / 2);
    channelData = deinterleaveInt16(int16, channels);
  } else if (bitDepth === 24) {
    channelData = deinterleaveInt24(dataBytes, channels);
  } else if (bitDepth === 32) {
    const int32 = new Int32Array(dataBytes.buffer, dataBytes.byteOffset, actualDataSize / 4);
    channelData = deinterleaveInt32(int32, channels);
  } else if (bitDepth === 8) {
    channelData = deinterleaveUint8(dataBytes, channels);
  } else {
    return null;
  }

  const decodeTimeMs = performance.now() - startTime;
  return { channelData, sampleRate, channels, bitDepth, totalFrames, decodeTimeMs };
}

function calculateSpectralFlatness(signal: Float32Array, fftSize: number): number {
  const numFrames = Math.min(3, Math.floor(signal.length / fftSize));
  let totalFlatness = 0;

  for (let frame = 0; frame < numFrames; frame++) {
    const start = frame * fftSize;
    const frameData = signal.slice(start, start + fftSize);
    let sum = 0;
    let logSum = 0;
    let count = 0;

    for (let i = 0; i < fftSize / 2; i++) {
      const magnitude = Math.abs(frameData[i]);
      if (magnitude > 0.00001) {
        sum += magnitude;
        logSum += Math.log(magnitude);
        count++;
      }
    }

    if (count > 0 && sum > 0) {
      const geometricMean = Math.exp(logSum / count);
      const arithmeticMean = sum / count;
      totalFlatness += geometricMean / (arithmeticMean + 0.0001);
    }
  }

  return totalFlatness / numFrames;
}

function detectAudioIssues(channelData: Float32Array, sampleRate: number, channels: number, allChannelData: Float32Array[]): AudioAnalysisResult {
  const startTime = performance.now();
  const issues: string[] = [];
  const detailedIssues: AudioIssue[] = [];
  let sumSquares = 0;
  let maxSample = 0;
  let clippingCount = 0;
  const crackleRegions: number[] = [];
  const popRegions: number[] = [];

  const blockSize = Math.floor(sampleRate * 0.001);
  let prevBlockRMS = 0;
  let prevSample = 0;
  let blockSum = 0;
  let blockIdx = 0;

  const len = channelData.length;
  for (let i = 0; i < len; i++) {
    const sample = channelData[i];
    const absSample = Math.abs(sample);
    sumSquares += absSample * absSample;
    if (absSample > maxSample) maxSample = absSample;

    if (absSample > 0.95) {
      clippingCount++;
      const last = detailedIssues[detailedIssues.length - 1];
      if (!last || last.type !== 'clip') {
        detailedIssues.push({ type: 'clip', start: i, end: i, severity: absSample - 0.95 });
      } else {
        last.end = i;
        if (absSample - 0.95 > last.severity) last.severity = absSample - 0.95;
      }
    }

    blockSum += sample * sample;
    blockIdx++;

    if (blockIdx >= blockSize && i > 0) {
      const blockRMS = Math.sqrt(blockSum / blockSize);
      blockSum = 0;
      blockIdx = 0;

      const diff = Math.abs(blockRMS - prevBlockRMS);
      if (diff > 0.35) {
        if (blockRMS > prevBlockRMS * 2.5) {
          popRegions.push(i);
          detailedIssues.push({ type: 'pop', start: i, end: i + blockSize, severity: diff });
        }
        if (diff > 0.5 && blockRMS > 0.1) {
          crackleRegions.push(i);
          detailedIssues.push({ type: 'crackle', start: i, end: i + blockSize, severity: diff });
        }
      }
      prevBlockRMS = blockRMS;
    }

    const diffFromPrev = Math.abs(sample - prevSample);
    if (diffFromPrev > 0.4 && absSample > 0.05) {
      detailedIssues.push({ type: 'crackle', start: i, end: i + 1, severity: diffFromPrev });
    }
    prevSample = sample;
  }

  const rms = Math.sqrt(sumSquares / len);
  const dynamicRangeDb = 20 * Math.log10(maxSample / (rms + 0.0001));
  const fftSize = 1024;
  const spectralFlatness = calculateSpectralFlatness(channelData, fftSize);

  let stereoBalance = 0.5;
  if (channels > 1 && allChannelData.length > 1) {
    const rightChannel = allChannelData[1];
    let leftEnergy = 0;
    let rightEnergy = 0;
    for (let i = 0; i < len; i++) {
      leftEnergy += channelData[i] * channelData[i];
      rightEnergy += rightChannel[i] * rightChannel[i];
    }
    stereoBalance = leftEnergy / (leftEnergy + rightEnergy + 0.0001);
  }

  if (spectralFlatness > 0.6) issues.push('频谱异常');
  if (dynamicRangeDb < 6) issues.push('动态范围过小');
  if (clippingCount > len * 0.0005) issues.push('削波失真');
  if (crackleRegions.length > 3) issues.push('毛刺/撕裂');
  if (popRegions.length > 5) issues.push('爆音');
  if (stereoBalance < 0.4 || stereoBalance > 0.6) issues.push('立体声平衡偏移');

  const analysisTimeMs = performance.now() - startTime;
  return {
    spectralFlatness,
    dynamicRange: dynamicRangeDb,
    stereoBalance,
    peakLevel: maxSample,
    issues,
    clippingCount,
    crackleRegions,
    popRegions,
    detailedIssues,
    analysisTimeMs,
  };
}

self.onmessage = (e: MessageEvent<WorkerRequest>) => {
  const msg = e.data;
  console.log(`[audioWorker] 收到消息: type=${msg.type}, id=${msg.id}`);

  try {
  if (msg.type === 'decode-wav') {
    const result = decodeWavPcm(msg.buffer);
    const transfer: ArrayBuffer[] = [];
    if (result) {
      for (const ch of result.channelData) {
        transfer.push(ch.buffer);
      }
    }
    console.log(`[audioWorker] decode-wav完成: result=${result ? 'success' : 'null'}`);
    const response: WorkerResponse = { type: 'decode-wav', id: msg.id, result };
    (self as unknown as { postMessage: (message: unknown, transfer: Transferable[]) => void }).postMessage(response, transfer);
  } else if (msg.type === 'analyze-audio') {
    const result = detectAudioIssues(msg.channelData[0], msg.sampleRate, msg.channels, msg.channelData);
    const response: WorkerResponse = { type: 'analyze-audio', id: msg.id, result };
    self.postMessage(response);
  } else if (msg.type === 'decode-and-analyze') {
    const decode = decodeWavPcm(msg.buffer);
    let analysis: AudioAnalysisResult | null = null;
    const transfer: ArrayBuffer[] = [];
    if (decode) {
      analysis = detectAudioIssues(decode.channelData[0], decode.sampleRate, decode.channels, decode.channelData);
      for (const ch of decode.channelData) {
        transfer.push(ch.buffer);
      }
    }
    const response: WorkerResponse = { type: 'decode-and-analyze', id: msg.id, decode, analysis };
    (self as unknown as { postMessage: (message: unknown, transfer: Transferable[]) => void }).postMessage(response, transfer);
  }
  } catch (err) {
    console.error('[audioWorker] 处理消息出错:', err);
    (self as unknown as { postMessage: (message: unknown) => void }).postMessage({
      type: 'error',
      id: msg.id,
      error: err instanceof Error ? err.message : String(err),
    });
  }
};

export interface DecodedWavResult {
  channelData: Float32Array[];
  sampleRate: number;
  channels: number;
  bitDepth: number;
  totalFrames: number;
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
  const outputs: Float32Array[] = [];
  for (let ch = 0; ch < channels; ch++) {
    const out = new Float32Array(totalFrames);
    for (let i = 0; i < totalFrames; i++) {
      out[i] = src[i * channels + ch] / 32768;
    }
    outputs.push(out);
  }
  return outputs;
}

function deinterleaveInt32(src: Int32Array, channels: number): Float32Array[] {
  const totalFrames = src.length / channels;
  const outputs: Float32Array[] = [];
  for (let ch = 0; ch < channels; ch++) {
    const out = new Float32Array(totalFrames);
    for (let i = 0; i < totalFrames; i++) {
      out[i] = src[i * channels + ch] / 2147483648;
    }
    outputs.push(out);
  }
  return outputs;
}

function deinterleaveUint8(src: Uint8Array, channels: number): Float32Array[] {
  const totalFrames = src.length / channels;
  const outputs: Float32Array[] = [];
  for (let ch = 0; ch < channels; ch++) {
    const out = new Float32Array(totalFrames);
    for (let i = 0; i < totalFrames; i++) {
      out[i] = (src[i * channels + ch] - 128) / 128;
    }
    outputs.push(out);
  }
  return outputs;
}

function deinterleaveInt24(src: Uint8Array, channels: number): Float32Array[] {
  const bytesPerFrame = channels * 3;
  const totalFrames = Math.floor(src.length / bytesPerFrame);
  const outputs: Float32Array[] = [];
  for (let ch = 0; ch < channels; ch++) {
    const out = new Float32Array(totalFrames);
    for (let i = 0; i < totalFrames; i++) {
      const byteOffset = i * bytesPerFrame + ch * 3;
      const b0 = src[byteOffset];
      const b1 = src[byteOffset + 1];
      const b2 = src[byteOffset + 2];
      let raw = b0 | (b1 << 8) | (b2 << 16);
      if (raw & 0x800000) raw |= ~0xFFFFFF;
      out[i] = raw / 8388608;
    }
    outputs.push(out);
  }
  return outputs;
}

function decodeWavPcm(buffer: ArrayBuffer): DecodedWavResult | null {
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

  return { channelData, sampleRate, channels, bitDepth, totalFrames };
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

  for (let i = 0; i < channelData.length; i++) {
    const sample = Math.abs(channelData[i]);
    sumSquares += sample * sample;
    maxSample = Math.max(maxSample, sample);

    if (sample > 0.95) {
      clippingCount++;
      if (detailedIssues.length === 0 || detailedIssues[detailedIssues.length - 1].type !== 'clip') {
        detailedIssues.push({ type: 'clip', start: i, end: i, severity: sample - 0.95 });
      } else {
        detailedIssues[detailedIssues.length - 1].end = i;
        detailedIssues[detailedIssues.length - 1].severity = Math.max(
          detailedIssues[detailedIssues.length - 1].severity,
          sample - 0.95,
        );
      }
    }

    if (i % blockSize === 0 && i > 0) {
      let blockRMS = 0;
      const end = Math.min(i + blockSize, channelData.length);
      for (let j = i; j < end; j++) {
        blockRMS += channelData[j] * channelData[j];
      }
      blockRMS = Math.sqrt(blockRMS / blockSize);

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

    const diffFromPrev = Math.abs(channelData[i] - prevSample);
    if (diffFromPrev > 0.4 && Math.abs(channelData[i]) > 0.05) {
      detailedIssues.push({ type: 'crackle', start: i, end: i + 1, severity: diffFromPrev });
    }
    prevSample = channelData[i];
  }

  const rms = Math.sqrt(sumSquares / channelData.length);
  const dynamicRangeDb = 20 * Math.log10(maxSample / (rms + 0.0001));
  const fftSize = 1024;
  const spectralFlatness = calculateSpectralFlatness(channelData, fftSize);

  let stereoBalance = 0.5;
  if (channels > 1 && allChannelData.length > 1) {
    const rightChannel = allChannelData[1];
    let leftEnergy = 0;
    let rightEnergy = 0;
    for (let i = 0; i < channelData.length; i++) {
      leftEnergy += channelData[i] * channelData[i];
      rightEnergy += rightChannel[i] * rightChannel[i];
    }
    stereoBalance = leftEnergy / (leftEnergy + rightEnergy + 0.0001);
  }

  if (spectralFlatness > 0.6) issues.push('频谱异常');
  if (dynamicRangeDb < 6) issues.push('动态范围过小');
  if (clippingCount > channelData.length * 0.0005) issues.push('削波失真');
  if (crackleRegions.length > 3) issues.push('毛刺/撕裂');
  if (popRegions.length > 5) issues.push('爆音');
  if (stereoBalance < 0.4 || stereoBalance > 0.6) issues.push('立体声平衡偏移');

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
  };
}

self.onmessage = (e: MessageEvent<WorkerRequest>) => {
  const msg = e.data;

  if (msg.type === 'decode-wav') {
    const result = decodeWavPcm(msg.buffer);
    const transfer: ArrayBuffer[] = [];
    if (result) {
      for (const ch of result.channelData) {
        transfer.push(ch.buffer);
      }
    }
    const response: WorkerResponse = { type: 'decode-wav', id: msg.id, result };
    (self as any).postMessage(response, transfer);
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
    (self as any).postMessage(response, transfer);
  }
};

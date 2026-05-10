export interface WavInfo {
  sampleRate: number;
  bitDepth: number;
  channels: number;
  duration: number;
}

export interface WavParseResult {
  info: WavInfo;
  dataOffset: number;
  dataSize: number;
}

export function parseWavHeaderFull(buffer: ArrayBuffer): WavParseResult | null {
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

    const bytesPerSample = bitDepth / 8;
    const numSamples = dataSize / (channels * bytesPerSample);
    const duration = numSamples / sampleRate;

    return {
      info: { sampleRate, bitDepth, channels, duration },
      dataOffset,
      dataSize,
    };
  } catch {
    return null;
  }
}

export function parseWavHeader(buffer: ArrayBuffer): WavInfo | null {
  const result = parseWavHeaderFull(buffer);
  return result ? result.info : null;
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

export function decodeWavPcm(audioContext: BaseAudioContext, buffer: ArrayBuffer): AudioBuffer | null {
  const parseResult = parseWavHeaderFull(buffer);
  if (!parseResult) return null;

  const { info, dataOffset, dataSize } = parseResult;
  const { sampleRate, bitDepth, channels } = info;

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

  const audioBuffer = audioContext.createBuffer(channels, totalFrames, sampleRate);
  for (let ch = 0; ch < channels; ch++) {
    audioBuffer.copyToChannel(channelData[ch], ch);
  }

  return audioBuffer;
}

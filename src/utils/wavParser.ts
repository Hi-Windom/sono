export interface WavInfo {
  sampleRate: number;
  bitDepth: number;
  channels: number;
  duration: number;
}

export function parseWavHeader(buffer: ArrayBuffer): WavInfo | null {
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

    while (offset < buffer.byteLength - 8) {
      const chunkId = String.fromCharCode(
        view.getUint8(offset), view.getUint8(offset + 1),
        view.getUint8(offset + 2), view.getUint8(offset + 3),
      );
      const chunkSize = view.getUint32(offset + 4, true);

      if (chunkId === 'fmt ') {
        channels = view.getUint16(offset + 10, true);
        sampleRate = view.getUint32(offset + 12, true);
        bitDepth = view.getUint16(offset + 22, true);
      } else if (chunkId === 'data') {
        dataSize = chunkSize;
        break;
      }

      offset += 8 + chunkSize;
      if (chunkSize % 2 !== 0) offset += 1;
    }

    if (sampleRate === 0 || bitDepth === 0) return null;

    const bytesPerSample = bitDepth / 8;
    const numSamples = dataSize / (channels * bytesPerSample);
    const duration = numSamples / sampleRate;

    return { sampleRate, bitDepth, channels, duration };
  } catch {
    return null;
  }
}

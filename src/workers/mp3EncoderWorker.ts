import lamejs from 'lamejs';

interface EncodeRequest {
  type: 'encode';
  audioData: Float32Array;
  sampleRate: number;
  bitRate: number;
  channels: number;
}

interface EncodedResponse {
  type: 'encoded';
  mp3Blob: Blob;
}

interface ErrorResponse {
  type: 'error';
  error: string;
}

type WorkerResponse = EncodedResponse | ErrorResponse;

function convertFloat32ToInt16(float32: Float32Array): Int16Array {
  const len = float32.length;
  const int16 = new Int16Array(len);
  for (let i = 0; i < len; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    int16[i] = s < 0 ? s * 32768 : s * 32767;
  }
  return int16;
}

function encodeMp3(
  audioData: Float32Array,
  sampleRate: number,
  bitRate: number,
  channels: number,
): Blob {
  const samplesPerChunk = 1152;
  const totalSamples = audioData.length / channels;

  let left: Int16Array;
  let right: Int16Array | null = null;

  if (channels === 1) {
    left = convertFloat32ToInt16(audioData);
  } else {
    const leftFloat = new Float32Array(totalSamples);
    const rightFloat = new Float32Array(totalSamples);
    for (let i = 0; i < totalSamples; i++) {
      leftFloat[i] = audioData[i * 2];
      rightFloat[i] = audioData[i * 2 + 1];
    }
    left = convertFloat32ToInt16(leftFloat);
    right = convertFloat32ToInt16(rightFloat);
  }

  const mp3Encoder = new lamejs.Mp3Encoder(channels, sampleRate, bitRate);
  const mp3Data: Int8Array[] = [];

  for (let i = 0; i < totalSamples; i += samplesPerChunk) {
    const chunkSize = Math.min(samplesPerChunk, totalSamples - i);
    const leftChunk = left.subarray(i, i + chunkSize);

    let mp3buf: Int8Array;
    if (channels === 1) {
      mp3buf = mp3Encoder.encodeBuffer(leftChunk);
    } else {
      const rightChunk = right!.subarray(i, i + chunkSize);
      mp3buf = mp3Encoder.encodeBuffer(leftChunk, rightChunk);
    }

    if (mp3buf.length > 0) {
      mp3Data.push(mp3buf);
    }
  }

  const end = mp3Encoder.flush();
  if (end.length > 0) {
    mp3Data.push(end);
  }

  const totalLength = mp3Data.reduce((sum, buf) => sum + buf.length, 0);
  const combined = new Int8Array(totalLength);
  let offset = 0;
  for (const buf of mp3Data) {
    combined.set(buf, offset);
    offset += buf.length;
  }

  return new Blob([combined.buffer], { type: 'audio/mp3' });
}

self.onmessage = (e: MessageEvent<EncodeRequest>) => {
  const { type, audioData, sampleRate, bitRate, channels } = e.data;

  if (type === 'encode') {
    try {
      const mp3Blob = encodeMp3(audioData, sampleRate, bitRate, channels);
      const response: WorkerResponse = { type: 'encoded', mp3Blob };
      self.postMessage(response);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      const response: WorkerResponse = { type: 'error', error: errorMsg };
      self.postMessage(response);
    }
  }
};
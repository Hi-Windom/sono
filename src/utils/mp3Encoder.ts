let worker: Worker | null = null;

function getWorker(): Worker {
  if (!worker) {
    worker = new Worker(
      new URL('../workers/mp3EncoderWorker.ts', import.meta.url),
    );
  }
  return worker;
}

export function encodeMp3(
  audioData: Float32Array,
  sampleRate: number,
  channels: number,
  bitRate: number = 128,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const w = getWorker();
    const handler = (e: MessageEvent) => {
      w.removeEventListener('message', handler);
      w.removeEventListener('error', handler);
      if (e.data.type === 'encoded') {
        resolve(e.data.mp3Blob);
      } else {
        reject(new Error(e.data.error || 'MP3 encoding failed'));
      }
    };
    w.addEventListener('message', handler);
    w.addEventListener('error', handler);
    w.postMessage({ type: 'encode', audioData, sampleRate, bitRate, channels });
  });
}

export function terminateMp3Encoder(): void {
  if (worker) {
    worker.terminate();
    worker = null;
  }
}
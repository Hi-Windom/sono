class FrequencyBand {
  minFreq: number;
  maxFreq: number;
  harmonicRelation: number;
  intensity: number;

  constructor(min: number, max: number, harmonic: number, intensity: number) {
    this.minFreq = min;
    this.maxFreq = max;
    this.harmonicRelation = harmonic;
    this.intensity = intensity;
  }
}

const ENHANCEMENT_BANDS: FrequencyBand[] = [
  new FrequencyBand(20000, 28000, 2, 0.15),
  new FrequencyBand(28000, 36000, 2, 0.12),
  new FrequencyBand(36000, 44000, 3, 0.08),
  new FrequencyBand(44000, 48000, 4, 0.05),
];

function applyHannWindow(data: Float32Array): Float32Array {
  const result = new Float32Array(data.length);
  for (let i = 0; i < data.length; i++) {
    const window = 0.5 * (1 - Math.cos(2 * Math.PI * i / (data.length - 1)));
    result[i] = data[i] * window;
  }
  return result;
}

function computeFFT(data: Float32Array): { real: Float32Array; imag: Float32Array } {
  const n = data.length;
  const real = new Float32Array(n);
  const imag = new Float32Array(n);

  for (let k = 0; k < n; k++) {
    let sumRe = 0;
    let sumIm = 0;
    for (let t = 0; t < n; t++) {
      const angle = 2 * Math.PI * k * t / n;
      sumRe += data[t] * Math.cos(angle);
      sumIm -= data[t] * Math.sin(angle);
    }
    real[k] = sumRe;
    imag[k] = sumIm;
  }

  return { real, imag };
}

function computeIFFT(real: Float32Array, imag: Float32Array): Float32Array {
  const n = real.length;
  const output = new Float32Array(n);

  for (let t = 0; t < n; t++) {
    let sumRe = 0;
    for (let k = 0; k < n; k++) {
      const angle = 2 * Math.PI * k * t / n;
      sumRe += real[k] * Math.cos(angle) - imag[k] * Math.sin(angle);
    }
    output[t] = sumRe / n;
  }

  return output;
}

function freqToIndex(freq: number, frameSize: number, sampleRate: number): number {
  return Math.round(freq * frameSize / sampleRate);
}

function generateHarmonicSpectrum(
  real: Float32Array,
  imag: Float32Array,
  frameSize: number,
  sampleRate: number,
  bands: FrequencyBand[]
): { real: Float32Array; imag: Float32Array } {
  const newReal = new Float32Array(real);
  const newImag = new Float32Array(imag);

  for (const band of bands) {
    const minIdx = freqToIndex(band.minFreq, frameSize, sampleRate);
    const maxIdx = freqToIndex(band.maxFreq, frameSize, sampleRate);
    const sourceMinIdx = Math.floor(minIdx / band.harmonicRelation);
    const sourceMaxIdx = Math.floor(maxIdx / band.harmonicRelation);

    if (sourceMaxIdx >= 0 && sourceMaxIdx < frameSize / 2) {
      for (let k = minIdx; k <= maxIdx && k < frameSize / 2; k++) {
        const sourceIdx = Math.floor(k / band.harmonicRelation);
        if (sourceIdx < sourceMinIdx || sourceIdx > sourceMaxIdx) continue;
        if (sourceIdx < 0 || sourceIdx >= frameSize / 2) continue;

        const sourceMag = Math.sqrt(real[sourceIdx] ** 2 + imag[sourceIdx] ** 2);
        const sourcePhase = Math.atan2(imag[sourceIdx], real[sourceIdx]);

        const phaseShift = Math.random() * 0.2 - 0.1;
        const newMag = sourceMag * band.intensity * (0.9 + Math.random() * 0.2);
        const newPhase = sourcePhase * band.harmonicRelation + phaseShift;

        newReal[k] += newMag * Math.cos(newPhase);
        newImag[k] += newMag * Math.sin(newPhase);
      }
    }
  }

  for (let k = 1; k < frameSize / 2; k++) {
    newReal[frameSize - k] = newReal[k];
    newImag[frameSize - k] = -newImag[k];
  }

  return { real: newReal, imag: newImag };
}

self.onmessage = async (e) => {
  const { type, data } = e.data;

  if (type === 'enhance') {
    const { channelData, frameSize, hopSize, sampleRate } = data;
    const numFrames = Math.floor((channelData.length - frameSize) / hopSize) + 1;
    const targetSampleRate = 96000;
    const lengthFactor = targetSampleRate / sampleRate;
    const newHopSize = Math.floor(hopSize * lengthFactor);
    const newLength = Math.floor(frameSize + (numFrames - 1) * newHopSize);

    const outputBuffer = new Float32Array(newLength);
    const conservativeBands = ENHANCEMENT_BANDS.map(b =>
      new FrequencyBand(b.minFreq, b.maxFreq, b.harmonicRelation, b.intensity * 0.5)
    );

    for (let i = 0; i < numFrames; i++) {
      const start = i * hopSize;
      const end = Math.min(start + frameSize, channelData.length);
      const frame = new Float32Array(frameSize);
      
      for (let j = 0; j < frameSize && start + j < channelData.length; j++) {
        frame[j] = channelData[start + j];
      }

      const windowed = applyHannWindow(frame);
      const { real, imag } = computeFFT(windowed);
      const enhanced = generateHarmonicSpectrum(real, imag, frameSize, targetSampleRate, conservativeBands);
      const timeDomain = computeIFFT(enhanced.real, enhanced.imag);
      const overlap = applyHannWindow(timeDomain);

      const outputStart = i * newHopSize;
      for (let j = 0; j < Math.min(overlap.length, newLength - outputStart); j++) {
        outputBuffer[outputStart + j] += overlap[j] / (frameSize / (frameSize * lengthFactor));
      }

      if ((i + 1) % Math.max(1, Math.floor(numFrames / 10)) === 0) {
        self.postMessage({ type: 'progress', progress: (i + 1) / numFrames });
      }
    }

    let maxSample = 0;
    for (let i = 0; i < newLength; i++) {
      maxSample = Math.max(maxSample, Math.abs(outputBuffer[i]));
    }

    if (maxSample > 1) {
      const norm = 0.95 / maxSample;
      for (let i = 0; i < newLength; i++) {
        outputBuffer[i] *= norm;
      }
    }

    self.postMessage({ type: 'complete', data: outputBuffer });
  }
};
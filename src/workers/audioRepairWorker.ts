interface RepairParams {
  deClipping: number;
  noiseReduction: number;
  deCrackle: number;
  dePop: number;
  harmonicEnhance: number;
  dynamicRange: number;
  spatialEnhance: number;
  transientRepair: number;
  softness: number;
  deEssing: number;
  presenceBoost: number;
  bassEnhance: number;
  warmth: number;
  clarity: number;
}

let aborted = false;

function cubicSplineInterpolate(knotsX: number[], knotsY: number[], evalX: number[]): number[] {
  const n = knotsX.length;
  if (n < 2) return evalX.map(() => knotsY[0] || 0);

  const h: number[] = new Array(n - 1);
  for (let i = 0; i < n - 1; i++) {
    h[i] = knotsX[i + 1] - knotsX[i];
  }

  const alpha: number[] = new Array(n).fill(0);
  for (let i = 1; i < n - 1; i++) {
    alpha[i] = (3 / h[i]) * (knotsY[i + 1] - knotsY[i]) - (3 / h[i - 1]) * (knotsY[i] - knotsY[i - 1]);
  }

  const l: number[] = new Array(n);
  const mu: number[] = new Array(n);
  const z: number[] = new Array(n);
  const c: number[] = new Array(n);
  const b: number[] = new Array(n - 1);
  const d: number[] = new Array(n - 1);

  l[0] = 1;
  mu[0] = 0;
  z[0] = 0;

  for (let i = 1; i < n - 1; i++) {
    l[i] = 2 * (knotsX[i + 1] - knotsX[i - 1]) - h[i - 1] * mu[i - 1];
    mu[i] = h[i] / l[i];
    z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / l[i];
  }

  l[n - 1] = 1;
  z[n - 1] = 0;
  c[n - 1] = 0;

  for (let j = n - 2; j >= 0; j--) {
    c[j] = z[j] - mu[j] * c[j + 1];
    b[j] = (knotsY[j + 1] - knotsY[j]) / h[j] - h[j] * (c[j + 1] + 2 * c[j]) / 3;
    d[j] = (c[j + 1] - c[j]) / (3 * h[j]);
  }

  const result: number[] = [];
  for (const xi of evalX) {
    let idx = n - 2;
    for (let j = 0; j < n - 1; j++) {
      if (xi < knotsX[j + 1]) {
        idx = j;
        break;
      }
    }
    const dx = xi - knotsX[idx];
    result.push(knotsY[idx] + b[idx] * dx + c[idx] * dx * dx + d[idx] * dx * dx * dx);
  }

  return result;
}

function fft(real: number[], imag: number[]): void {
  const n = real.length;
  if (n <= 1) return;

  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    while (j & bit) {
      j ^= bit;
      bit >>= 1;
    }
    j ^= bit;
    if (i < j) {
      const tmpR = real[i]; real[i] = real[j]; real[j] = tmpR;
      const tmpI = imag[i]; imag[i] = imag[j]; imag[j] = tmpI;
    }
  }

  for (let len = 2; len <= n; len <<= 1) {
    const halfLen = len >> 1;
    const angle = -2 * Math.PI / len;
    const wReal = Math.cos(angle);
    const wImag = Math.sin(angle);

    for (let i = 0; i < n; i += len) {
      let curReal = 1, curImag = 0;
      for (let j = 0; j < halfLen; j++) {
        const tReal = curReal * real[i + j + halfLen] - curImag * imag[i + j + halfLen];
        const tImag = curReal * imag[i + j + halfLen] + curImag * real[i + j + halfLen];
        real[i + j + halfLen] = real[i + j] - tReal;
        imag[i + j + halfLen] = imag[i + j] - tImag;
        real[i + j] += tReal;
        imag[i + j] += tImag;
        const newCurReal = curReal * wReal - curImag * wImag;
        curImag = curReal * wImag + curImag * wReal;
        curReal = newCurReal;
      }
    }
  }
}

function ifft(real: number[], imag: number[]): void {
  const n = real.length;
  for (let i = 0; i < n; i++) imag[i] = -imag[i];
  fft(real, imag);
  for (let i = 0; i < n; i++) {
    real[i] /= n;
    imag[i] = -imag[i] / n;
  }
}

function applyDeClipping(data: Float32Array, intensity: number): Float32Array {
  const output = new Float32Array(data);

  const clippedRegions: { start: number; end: number }[] = [];
  let i = 0;
  while (i < data.length) {
    if (Math.abs(data[i]) > 0.95) {
      const start = i;
      while (i < data.length && Math.abs(data[i]) > 0.95) {
        i++;
      }
      clippedRegions.push({ start, end: i });
    } else {
      i++;
    }
  }

  for (const region of clippedRegions) {
    const margin = 8;
    const knotX: number[] = [];
    const knotY: number[] = [];

    for (let k = Math.max(0, region.start - margin); k < region.start; k++) {
      knotX.push(k);
      knotY.push(data[k]);
    }

    for (let k = region.end; k < Math.min(data.length, region.end + margin); k++) {
      knotX.push(k);
      knotY.push(data[k]);
    }

    if (knotX.length >= 2) {
      const evalX: number[] = [];
      for (let k = region.start; k < region.end; k++) {
        evalX.push(k);
      }

      const interpolated = cubicSplineInterpolate(knotX, knotY, evalX);

      for (let k = 0; k < interpolated.length; k++) {
        const idx = region.start + k;
        if (idx < data.length) {
          output[idx] = data[idx] * (1 - intensity) + interpolated[k] * intensity;
        }
      }
    }
  }

  return output;
}

function applyDeCrackle(data: Float32Array, intensity: number): Float32Array {
  const output = new Float32Array(data);

  for (let i = 2; i < data.length - 2; i++) {
    let sample = data[i];

    const neighbors = [
      data[i - 2], data[i - 1], sample, data[i + 1], data[i + 2]
    ].sort((a, b) => a - b);

    const median = neighbors[2];

    if (Math.abs(sample - median) > 0.1 * intensity) {
      sample = median + (sample - median) * (1 - intensity);
    }

    output[i] = sample;
  }

  return output;
}

function applyDePop(data: Float32Array, intensity: number): Float32Array {
  const output = new Float32Array(data);

  for (let i = 1; i < data.length - 2; i++) {
    let sample = data[i];

    const deltaPrev = Math.abs(sample - data[i - 1]);
    const deltaNext = Math.abs(data[i + 1] - sample);

    if (deltaPrev > 0.05 * intensity && deltaNext > 0.05 * intensity) {
      sample = (data[i - 1] + data[i + 1]) / 2;
    }

    output[i] = sample;
  }

  return output;
}

function applyNoiseReductionChannel(data: Float32Array, sampleRate: number, intensity: number): Float32Array {
  const output = new Float32Array(data.length);
  const fftSize = 2048;
  const hopSize = fftSize >> 1;

  const windowArr = new Array(fftSize);
  for (let i = 0; i < fftSize; i++) {
    windowArr[i] = 0.5 * (1 - Math.cos(2 * Math.PI * i / (fftSize - 1)));
  }

  const noiseEstimateFrames = Math.min(8, Math.floor(data.length / fftSize));
  const noiseMag = new Array(fftSize / 2 + 1).fill(0);

  for (let frame = 0; frame < noiseEstimateFrames; frame++) {
    const offset = frame * fftSize;
    const real = new Array(fftSize).fill(0);
    const imag = new Array(fftSize).fill(0);

    for (let i = 0; i < fftSize && offset + i < data.length; i++) {
      real[i] = data[offset + i] * windowArr[i];
    }

    fft(real, imag);

    for (let i = 0; i <= fftSize / 2; i++) {
      noiseMag[i] += Math.sqrt(real[i] * real[i] + imag[i] * imag[i]);
    }
  }

  for (let i = 0; i <= fftSize / 2; i++) {
    noiseMag[i] /= Math.max(1, noiseEstimateFrames);
  }

  for (let i = 0; i < data.length; i++) {
    output[i] = 0;
  }

  const windowSum = new Float64Array(data.length);

  let frameIdx = 0;
  while (frameIdx * hopSize < data.length) {
    const offset = frameIdx * hopSize;
    const real = new Array(fftSize).fill(0);
    const imag = new Array(fftSize).fill(0);

    for (let i = 0; i < fftSize && offset + i < data.length; i++) {
      real[i] = data[offset + i] * windowArr[i];
    }

    fft(real, imag);

    for (let i = 0; i <= fftSize / 2; i++) {
      const mag = Math.sqrt(real[i] * real[i] + imag[i] * imag[i]);
      const phase = Math.atan2(imag[i], real[i]);
      const threshold = noiseMag[i] * (1 + (1 - intensity) * 8);

      let newMag: number;
      if (mag < threshold) {
        const gateFactor = mag / threshold;
        newMag = mag * (1 - intensity * (1 - gateFactor) * 0.6);
      } else {
        newMag = mag;
      }

      real[i] = newMag * Math.cos(phase);
      imag[i] = newMag * Math.sin(phase);

      if (i > 0 && i < fftSize / 2) {
        real[fftSize - i] = real[i];
        imag[fftSize - i] = -imag[i];
      }
    }

    ifft(real, imag);

    for (let i = 0; i < fftSize && offset + i < data.length; i++) {
      output[offset + i] += real[i] * windowArr[i];
      windowSum[offset + i] += windowArr[i] * windowArr[i];
    }

    frameIdx++;
  }

  for (let i = 0; i < data.length; i++) {
    if (windowSum[i] > 1e-10) {
      output[i] /= windowSum[i];
    } else {
      output[i] = data[i];
    }
  }

  return output;
}

function applyTransientRepairChannel(data: Float32Array, sampleRate: number, intensity: number): Float32Array {
  const output = new Float32Array(data);

  const attackCoeff = Math.exp(-1 / (0.005 * sampleRate));
  const releaseCoeff = Math.exp(-1 / (0.05 * sampleRate));
  const transientThreshold = 2.5;

  const envelope = new Float64Array(data.length);
  envelope[0] = Math.abs(data[0]);

  for (let i = 1; i < data.length; i++) {
    const absSample = Math.abs(data[i]);
    const coeff = absSample > envelope[i - 1] ? attackCoeff : releaseCoeff;
    envelope[i] = coeff * envelope[i - 1] + (1 - coeff) * absSample;
  }

  const smoothWindow = Math.floor(sampleRate * 0.01);
  const avgEnvelope = new Float64Array(data.length);
  let runningSum = 0;

  for (let i = 0; i < data.length; i++) {
    runningSum += envelope[i];
    if (i >= smoothWindow) {
      runningSum -= envelope[i - smoothWindow];
      avgEnvelope[i] = runningSum / smoothWindow;
    } else {
      avgEnvelope[i] = runningSum / (i + 1);
    }
  }

  const reshapeWindow = Math.max(3, Math.floor(sampleRate * 0.002));

  for (let i = reshapeWindow; i < data.length - reshapeWindow; i++) {
    if (avgEnvelope[i] > 1e-10) {
      const ratio = envelope[i] / avgEnvelope[i];
      if (ratio > transientThreshold) {
        const excess = ratio - transientThreshold;
        const reshapeFactor = 1 / (1 + (excess / transientThreshold) * intensity * 0.5);
        output[i] = data[i] * reshapeFactor;

        for (let j = 1; j <= reshapeWindow; j++) {
          const blend = j / reshapeWindow;
          const leftIdx = i - j;
          const rightIdx = i + j;
          if (leftIdx >= 0 && rightIdx < data.length) {
            const neighborAvg = (data[leftIdx] + data[rightIdx]) / 2;
            output[leftIdx] = data[leftIdx] * (1 - intensity * blend * 0.3) + neighborAvg * intensity * blend * 0.3;
            output[rightIdx] = data[rightIdx] * (1 - intensity * blend * 0.3) + neighborAvg * intensity * blend * 0.3;
          }
        }
      }
    }
  }

  return output;
}

function softClip(x: number): number {
  if (x > 1) return 1;
  if (x < -1) return -1;
  return x;
}

function applyHarmonicEnhanceChannel(data: Float32Array, intensity: number): Float32Array {
  const output = new Float32Array(data.length);
  const drive = 1 + intensity * 0.5;

  for (let i = 0; i < data.length; i++) {
    const sample = data[i] * drive;
    output[i] = Math.tanh(sample) / drive * 0.3 + data[i] * 0.7;
  }

  return output;
}

function applySpatialEnhanceAll(channels: Float32Array[], intensity: number): Float32Array[] {
  const output: Float32Array[] = channels.map(ch => new Float32Array(ch));

  if (channels.length >= 2) {
    const sideGain = 1 + intensity * 0.25;
    const midGain = 1 - intensity * 0.05;

    for (let i = 0; i < channels[0].length; i++) {
      const mid = (channels[0][i] + channels[1][i]) * 0.5;
      const side = (channels[0][i] - channels[1][i]) * 0.5;

      const enhancedMid = mid * midGain;
      const enhancedSide = side * sideGain;

      output[0][i] = enhancedMid + enhancedSide;
      output[1][i] = enhancedMid - enhancedSide;
    }

    for (let ch = 2; ch < channels.length; ch++) {
      for (let i = 0; i < channels[ch].length; i++) {
        output[ch][i] = channels[ch][i];
      }
    }
  } else {
    const delaySamples = Math.round(channels[0].length * 0.00002 * (1 + intensity * 10));
    const sideAmount = intensity * 0.08;

    output.push(new Float32Array(channels[0].length));

    for (let i = 0; i < channels[0].length; i++) {
      const delayed = (i + delaySamples < channels[0].length) ? channels[0][i + delaySamples] : 0;
      output[0][i] = channels[0][i] + delayed * sideAmount;
      output[1][i] = channels[0][i] - delayed * sideAmount;
    }
  }

  return output;
}

function applyDynamicRangeChannel(data: Float32Array, amount: number): Float32Array {
  const output = new Float32Array(data.length);
  const threshold = -18;
  const ratio = 1.15 + amount * 0.2;
  const attack = 0.008;
  const release = 0.15;

  let gain = 1;

  for (let i = 0; i < data.length; i++) {
    const sample = data[i];
    const db = 20 * Math.log10(Math.abs(sample) + 0.0001);

    let desiredGain = 1;
    if (db > threshold) {
      const overDb = db - threshold;
      desiredGain = Math.pow(10, -overDb / (20 * ratio));
    }

    if (desiredGain < gain) {
      gain += (desiredGain - gain) * attack;
    } else {
      gain += (desiredGain - gain) * release;
    }

    output[i] = sample * gain;
  }

  return output;
}

class BiquadFilter {
  private b0: number;
  private b1: number;
  private b2: number;
  private a1: number;
  private a2: number;
  private x1 = 0;
  private x2 = 0;
  private y1 = 0;
  private y2 = 0;

  constructor(type: string, freq: number, Q: number, gainDb: number, sampleRate: number) {
    const w0 = 2 * Math.PI * freq / sampleRate;
    const sinW0 = Math.sin(w0);
    const cosW0 = Math.cos(w0);
    const alpha = sinW0 / (2 * Q);
    const A = Math.pow(10, gainDb / 40);

    let b0: number, b1: number, b2: number, a0: number, a1: number, a2: number;

    if (type === 'lowpass') {
      b0 = (1 - cosW0) / 2;
      b1 = 1 - cosW0;
      b2 = (1 - cosW0) / 2;
      a0 = 1 + alpha;
      a1 = -2 * cosW0;
      a2 = 1 - alpha;
    } else if (type === 'bandpass') {
      b0 = alpha;
      b1 = 0;
      b2 = -alpha;
      a0 = 1 + alpha;
      a1 = -2 * cosW0;
      a2 = 1 - alpha;
    } else if (type === 'peaking') {
      b0 = 1 + alpha * A;
      b1 = -2 * cosW0;
      b2 = 1 - alpha * A;
      a0 = 1 + alpha / A;
      a1 = -2 * cosW0;
      a2 = 1 - alpha / A;
    } else {
      b0 = 1;
      b1 = 0;
      b2 = 0;
      a0 = 1;
      a1 = 0;
      a2 = 0;
    }

    this.b0 = b0 / a0;
    this.b1 = b1 / a0;
    this.b2 = b2 / a0;
    this.a1 = a1 / a0;
    this.a2 = a2 / a0;
  }

  processBuffer(data: Float32Array): Float32Array {
    const output = new Float32Array(data.length);
    for (let i = 0; i < data.length; i++) {
      const sample = data[i];
      const y = this.b0 * sample + this.b1 * this.x1 + this.b2 * this.x2
                - this.a1 * this.y1 - this.a2 * this.y2;
      this.x2 = this.x1;
      this.x1 = sample;
      this.y2 = this.y1;
      this.y1 = y;
      output[i] = y;
    }
    return output;
  }
}

function applySoftnessChannel(data: Float32Array, sampleRate: number, amount: number): Float32Array {
  const lowpassFreq = Math.max(15000, 19000 - amount * 3000);
  const filter = new BiquadFilter('lowpass', lowpassFreq, 0.7, 0, sampleRate);
  return filter.processBuffer(data);
}

function applyDeEssingChannel(data: Float32Array, sampleRate: number, intensity: number): Float32Array {
  const output = new Float32Array(data.length);
  const bandFreq = 6000;
  const bandQ = 2.0;
  const bandFilter = new BiquadFilter('bandpass', bandFreq, bandQ, 0, sampleRate);

  const sibilant = bandFilter.processBuffer(data);

  const attackCoeff = Math.exp(-1 / (0.001 * sampleRate));
  const releaseCoeff = Math.exp(-1 / (0.05 * sampleRate));
  const threshold = 0.02 + (1 - intensity) * 0.08;
  const maxReduction = intensity * 0.6;

  let env = 0;
  for (let i = 0; i < data.length; i++) {
    const absSib = Math.abs(sibilant[i]);
    const coeff = absSib > env ? attackCoeff : releaseCoeff;
    env = coeff * env + (1 - coeff) * absSib;

    let gain = 1;
    if (env > threshold) {
      const overRatio = env / threshold;
      gain = 1 - maxReduction * (1 - 1 / overRatio);
      gain = Math.max(1 - maxReduction, Math.min(1, gain));
    }

    output[i] = data[i] * gain;
  }

  return output;
}

function applyPresenceBoostChannel(data: Float32Array, sampleRate: number, intensity: number): Float32Array {
  const eq2500 = new BiquadFilter('peaking', 2500, 1.2, intensity * 0.8, sampleRate);
  const eq3500 = new BiquadFilter('peaking', 3500, 1.0, intensity * 1.0, sampleRate);
  const eq5000 = new BiquadFilter('peaking', 5000, 1.4, intensity * 0.6, sampleRate);

  let result = eq2500.processBuffer(data);
  result = eq3500.processBuffer(result);
  result = eq5000.processBuffer(result);
  return result;
}

function applyBassEnhanceChannel(data: Float32Array, sampleRate: number, intensity: number): Float32Array {
  const subBass = new BiquadFilter('peaking', 60, 0.8, intensity * 1.0, sampleRate);
  const bassWarmth = new BiquadFilter('peaking', 150, 0.7, intensity * 0.8, sampleRate);

  let result = subBass.processBuffer(data);
  result = bassWarmth.processBuffer(result);
  return result;
}

function applyWarmthChannel(data: Float32Array, sampleRate: number, intensity: number): Float32Array {
  const lowFilter = new BiquadFilter('lowpass', 500, 0.707, 0, sampleRate);
  const lowSignal = lowFilter.processBuffer(data);
  const rectFilter = new BiquadFilter('lowpass', 1000, 0.707, 0, sampleRate);

  const result = new Float32Array(data.length);
  for (let i = 0; i < data.length; i++) {
    const rectified = Math.abs(lowSignal[i]);
    result[i] = data[i];
    lowSignal[i] = rectified;
  }

  const evenHarmonics = rectFilter.processBuffer(lowSignal);
  const gain = intensity * 0.15;
  for (let i = 0; i < data.length; i++) {
    result[i] += evenHarmonics[i] * gain;
  }
  return result;
}

function applyClarityChannel(data: Float32Array, sampleRate: number, intensity: number): Float32Array {
  const boostDb = intensity * 3.0;
  const gain = Math.pow(10, boostDb / 20) - 1;
  const highFilter = new BiquadFilter('highpass', 4000, 0.707, 0, sampleRate);
  const highFreq = highFilter.processBuffer(data);

  const result = new Float32Array(data.length);
  for (let i = 0; i < data.length; i++) {
    result[i] = data[i] + highFreq[i] * gain;
  }
  return result;
}

function encodeWav(channels: Float32Array[], sampleRate: number, bitDepth: number): ArrayBuffer {
  const numChannels = channels.length;
  const bytesPerSample = bitDepth / 8;
  const blockAlign = numChannels * bytesPerSample;
  const dataLength = channels[0].length * blockAlign;
  const bufferLength = 44 + dataLength;

  const arrayBuffer = new ArrayBuffer(bufferLength);
  const view = new DataView(arrayBuffer);

  const writeStr = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + dataLength, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitDepth, true);
  writeStr(36, 'data');
  view.setUint32(40, dataLength, true);

  let offset = 44;
  for (let i = 0; i < channels[0].length; i++) {
    for (let ch = 0; ch < numChannels; ch++) {
      const sample = Math.max(-1, Math.min(1, channels[ch][i]));

      if (bitDepth === 16) {
        view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
        offset += 2;
      } else if (bitDepth === 24) {
        const intSample = sample < 0 ? sample * 0x800000 : sample * 0x7fffff;
        const d = intSample & 0x00ffffff;
        view.setUint8(offset, d & 0xff);
        view.setUint8(offset + 1, (d >> 8) & 0xff);
        view.setUint8(offset + 2, (d >> 16) & 0xff);
        offset += 3;
      } else if (bitDepth === 32) {
        view.setInt32(offset, sample < 0 ? sample * 0x80000000 : sample * 0x7fffffff, true);
        offset += 4;
      }
    }
  }

  return arrayBuffer;
}

function handleRepair(channels: Float32Array[], sampleRate: number, params: RepairParams, id: string) {
  try {
    let processedChannels: Float32Array[] = channels.map(ch => new Float32Array(ch));
    const numChannels = processedChannels.length;
    const activeSteps: string[] = [];

    if (params.deClipping > 0) activeSteps.push('deClipping');
    if (params.deCrackle > 0) activeSteps.push('deCrackle');
    if (params.dePop > 0) activeSteps.push('dePop');
    if (params.noiseReduction > 0) activeSteps.push('noiseReduction');
    if (params.transientRepair > 0) activeSteps.push('transientRepair');
    if (params.harmonicEnhance > 0) activeSteps.push('harmonicEnhance');
    if (params.spatialEnhance > 0) activeSteps.push('spatialEnhance');
    if (params.dynamicRange > 0) activeSteps.push('dynamicRange');
    if (params.softness > 0) activeSteps.push('softness');
    if (params.deEssing > 0) activeSteps.push('deEssing');
    if (params.presenceBoost > 0) activeSteps.push('presenceBoost');
    if (params.bassEnhance > 0) activeSteps.push('bassEnhance');
    if (params.warmth > 0) activeSteps.push('warmth');
    if (params.clarity > 0) activeSteps.push('clarity');

    const totalSteps = activeSteps.length || 1;
    let currentStep = 0;

    const stepLabels: Record<string, string> = {
      deClipping: '去削波(三次样条插值)...',
      deCrackle: '去毛刺处理...',
      dePop: '去爆音处理...',
      noiseReduction: '频谱门限降噪...',
      transientRepair: '瞬态修复...',
      harmonicEnhance: '谐波增强...',
      spatialEnhance: '空间感增强...',
      dynamicRange: '动态范围优化...',
      softness: '柔化处理...',
      deEssing: '去齿音...',
      presenceBoost: '临场感增强...',
      bassEnhance: '低音增强...',
      warmth: '温暖度...',
      clarity: '清晰度...',
    };

    const updateProgress = (stepName: string) => {
      currentStep++;
      (self as unknown as Worker).postMessage({
        type: 'progress',
        progress: currentStep / totalSteps,
        step: stepLabels[stepName] || stepName,
        id,
      });
    };

    for (const stepName of activeSteps) {
      if (aborted) return;

      switch (stepName) {
        case 'deClipping':
          for (let ch = 0; ch < numChannels; ch++) {
            processedChannels[ch] = applyDeClipping(processedChannels[ch], params.deClipping);
          }
          break;

        case 'deCrackle':
          for (let ch = 0; ch < numChannels; ch++) {
            processedChannels[ch] = applyDeCrackle(processedChannels[ch], params.deCrackle);
          }
          break;

        case 'dePop':
          for (let ch = 0; ch < numChannels; ch++) {
            processedChannels[ch] = applyDePop(processedChannels[ch], params.dePop);
          }
          break;

        case 'noiseReduction':
          for (let ch = 0; ch < numChannels; ch++) {
            processedChannels[ch] = applyNoiseReductionChannel(processedChannels[ch], sampleRate, params.noiseReduction);
          }
          break;

        case 'transientRepair':
          for (let ch = 0; ch < numChannels; ch++) {
            processedChannels[ch] = applyTransientRepairChannel(processedChannels[ch], sampleRate, params.transientRepair);
          }
          break;

        case 'harmonicEnhance':
          for (let ch = 0; ch < numChannels; ch++) {
            processedChannels[ch] = applyHarmonicEnhanceChannel(processedChannels[ch], params.harmonicEnhance);
          }
          break;

        case 'spatialEnhance':
          processedChannels = applySpatialEnhanceAll(processedChannels, params.spatialEnhance);
          break;

        case 'dynamicRange':
          for (let ch = 0; ch < processedChannels.length; ch++) {
            processedChannels[ch] = applyDynamicRangeChannel(processedChannels[ch], params.dynamicRange);
          }
          break;

        case 'softness':
          for (let ch = 0; ch < processedChannels.length; ch++) {
            processedChannels[ch] = applySoftnessChannel(processedChannels[ch], sampleRate, params.softness);
          }
          break;

        case 'deEssing':
          for (let ch = 0; ch < processedChannels.length; ch++) {
            processedChannels[ch] = applyDeEssingChannel(processedChannels[ch], sampleRate, params.deEssing);
          }
          break;

        case 'presenceBoost':
          for (let ch = 0; ch < processedChannels.length; ch++) {
            processedChannels[ch] = applyPresenceBoostChannel(processedChannels[ch], sampleRate, params.presenceBoost);
          }
          break;

        case 'bassEnhance':
          for (let ch = 0; ch < processedChannels.length; ch++) {
            processedChannels[ch] = applyBassEnhanceChannel(processedChannels[ch], sampleRate, params.bassEnhance);
          }
          break;

        case 'warmth':
          for (let ch = 0; ch < processedChannels.length; ch++) {
            processedChannels[ch] = applyWarmthChannel(processedChannels[ch], sampleRate, params.warmth);
          }
          break;

        case 'clarity':
          for (let ch = 0; ch < processedChannels.length; ch++) {
            processedChannels[ch] = applyClarityChannel(processedChannels[ch], sampleRate, params.clarity);
          }
          break;
      }

      updateProgress(stepName);
    }

    if (aborted) return;

    let peak = 0;
    for (const ch of processedChannels) {
      for (let i = 0; i < ch.length; i++) {
        const abs = Math.abs(ch[i]);
        if (abs > peak) peak = abs;
      }
    }

    if (peak > 0.95) {
      const scale = 0.95 / peak;
      for (const ch of processedChannels) {
        for (let i = 0; i < ch.length; i++) {
          ch[i] = Math.tanh(ch[i] * 1.2) / 1.2;
        }
      }
    }

    const transferList: ArrayBuffer[] = [];
    for (const ch of processedChannels) {
      transferList.push(ch.buffer);
    }

    (self as unknown as Worker).postMessage({
      type: 'repair_complete',
      channels: processedChannels,
      sampleRate,
      id,
    }, transferList);
  } catch (error) {
    (self as unknown as Worker).postMessage({
      type: 'error',
      error: error instanceof Error ? error.message : String(error),
      id,
    });
  }
}

function handleEncodeWav(channels: Float32Array[], sampleRate: number, bitDepth: number, id: string) {
  try {
    const wavData = encodeWav(channels, sampleRate, bitDepth);

    (self as unknown as Worker).postMessage({
      type: 'encode_wav_complete',
      wavData,
      id,
    }, [wavData]);
  } catch (error) {
    (self as unknown as Worker).postMessage({
      type: 'error',
      error: error instanceof Error ? error.message : String(error),
      id,
    });
  }
}

self.onmessage = (e) => {
  const { type, data } = e.data;

  if (type === 'repair') {
    aborted = false;
    const { channels, sampleRate, params, id } = data;
    handleRepair(channels, sampleRate, params, id);
  } else if (type === 'encode_wav') {
    const { channels, sampleRate, bitDepth, id } = data;
    handleEncodeWav(channels, sampleRate, bitDepth, id);
  } else if (type === 'abort') {
    aborted = true;
  }
};

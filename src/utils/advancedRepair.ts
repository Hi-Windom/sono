export interface AdvancedRepairParams {
  deClipping: number;
  noiseReduction: number;
  deEssing: number;
  deCrackle: number;
  dePop: number;
  harmonicEnhance: number;
  dynamicRange: number;
  softness: number;
  presenceBoost: number;
  bassEnhance: number;
  spatialEnhance: number;
  transientRepair: number;
}

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

function applyDeClipping(buffer: AudioBuffer, intensity: number): AudioBuffer {
  const ctx = new OfflineAudioContext(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  const newBuffer = ctx.createBuffer(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
    const sourceData = buffer.getChannelData(ch);
    const destData = newBuffer.getChannelData(ch);

    const clippedRegions: { start: number; end: number }[] = [];
    let i = 0;
    while (i < sourceData.length) {
      if (Math.abs(sourceData[i]) > 0.95) {
        const start = i;
        while (i < sourceData.length && Math.abs(sourceData[i]) > 0.95) {
          i++;
        }
        clippedRegions.push({ start, end: i });
      } else {
        i++;
      }
    }

    for (let j = 0; j < sourceData.length; j++) {
      destData[j] = sourceData[j];
    }

    for (const region of clippedRegions) {
      const margin = 8;
      const knotX: number[] = [];
      const knotY: number[] = [];

      for (let k = Math.max(0, region.start - margin); k < region.start; k++) {
        knotX.push(k);
        knotY.push(sourceData[k]);
      }

      for (let k = region.end; k < Math.min(sourceData.length, region.end + margin); k++) {
        knotX.push(k);
        knotY.push(sourceData[k]);
      }

      if (knotX.length >= 2) {
        const evalX: number[] = [];
        for (let k = region.start; k < region.end; k++) {
          evalX.push(k);
        }

        const interpolated = cubicSplineInterpolate(knotX, knotY, evalX);

        for (let k = 0; k < interpolated.length; k++) {
          const idx = region.start + k;
          if (idx < sourceData.length) {
            destData[idx] = sourceData[idx] * (1 - intensity) + interpolated[k] * intensity;
          }
        }
      }
    }
  }

  return newBuffer;
}

function applyDeCrackle(buffer: AudioBuffer, intensity: number): AudioBuffer {
  const ctx = new OfflineAudioContext(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  const newBuffer = ctx.createBuffer(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
    const sourceData = buffer.getChannelData(ch);
    const destData = newBuffer.getChannelData(ch);

    for (let i = 0; i < sourceData.length; i++) {
      let sample = sourceData[i];

      if (i > 2 && i < sourceData.length - 3) {
        const neighbors = [
          sourceData[i - 2],
          sourceData[i - 1],
          sample,
          sourceData[i + 1],
          sourceData[i + 2]
        ].sort((a, b) => a - b);

        const median = neighbors[2];

        if (Math.abs(sample - median) > 0.1 * intensity) {
          sample = median + (sample - median) * (1 - intensity);
        }
      }

      destData[i] = sample;
    }
  }

  return newBuffer;
}

function applyDePop(buffer: AudioBuffer, intensity: number): AudioBuffer {
  const ctx = new OfflineAudioContext(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  const newBuffer = ctx.createBuffer(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
    const sourceData = buffer.getChannelData(ch);
    const destData = newBuffer.getChannelData(ch);

    for (let i = 0; i < sourceData.length; i++) {
      let sample = sourceData[i];

      if (i > 1 && i < sourceData.length - 2) {
        const deltaPrev = Math.abs(sample - sourceData[i - 1]);
        const deltaNext = Math.abs(sourceData[i + 1] - sample);

        if (deltaPrev > 0.05 * intensity && deltaNext > 0.05 * intensity) {
          sample = (sourceData[i - 1] + sourceData[i + 1]) / 2;
        }
      }

      destData[i] = sample;
    }
  }

  return newBuffer;
}

async function applyDeEssing(buffer: AudioBuffer, intensity: number): Promise<AudioBuffer> {
  const ctx = new OfflineAudioContext(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  const source = ctx.createBufferSource();
  source.buffer = buffer;

  const band4k = ctx.createBiquadFilter();
  band4k.type = 'bandpass';
  band4k.frequency.value = 4000;
  band4k.Q.value = 2;

  const band6k = ctx.createBiquadFilter();
  band6k.type = 'bandpass';
  band6k.frequency.value = 6000;
  band6k.Q.value = 2;

  const band8k = ctx.createBiquadFilter();
  band8k.type = 'bandpass';
  band8k.frequency.value = 8000;
  band8k.Q.value = 2;

  const comp4k = ctx.createDynamicsCompressor();
  comp4k.threshold.value = -35 + intensity * 10;
  comp4k.knee.value = 30;
  comp4k.ratio.value = 2 + intensity * 4;
  comp4k.attack.value = 0.001;
  comp4k.release.value = 0.05;

  const comp6k = ctx.createDynamicsCompressor();
  comp6k.threshold.value = -35 + intensity * 10;
  comp6k.knee.value = 30;
  comp6k.ratio.value = 2 + intensity * 4;
  comp6k.attack.value = 0.001;
  comp6k.release.value = 0.05;

  const comp8k = ctx.createDynamicsCompressor();
  comp8k.threshold.value = -35 + intensity * 10;
  comp8k.knee.value = 30;
  comp8k.ratio.value = 2 + intensity * 4;
  comp8k.attack.value = 0.001;
  comp8k.release.value = 0.05;

  const mergeGain4k = ctx.createGain();
  mergeGain4k.gain.value = 0.3 * intensity;

  const mergeGain6k = ctx.createGain();
  mergeGain6k.gain.value = 0.4 * intensity;

  const mergeGain8k = ctx.createGain();
  mergeGain8k.gain.value = 0.3 * intensity;

  const dryGain = ctx.createGain();
  dryGain.gain.value = 1;

  source.connect(dryGain);
  dryGain.connect(ctx.destination);

  source.connect(band4k);
  band4k.connect(comp4k);
  comp4k.connect(mergeGain4k);
  mergeGain4k.connect(ctx.destination);

  source.connect(band6k);
  band6k.connect(comp6k);
  comp6k.connect(mergeGain6k);
  mergeGain6k.connect(ctx.destination);

  source.connect(band8k);
  band8k.connect(comp8k);
  comp8k.connect(mergeGain8k);
  mergeGain8k.connect(ctx.destination);

  source.start();

  return ctx.startRendering();
}

function applyNoiseReduction(buffer: AudioBuffer, intensity: number): AudioBuffer {
  const ctx = new OfflineAudioContext(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  const newBuffer = ctx.createBuffer(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  const fftSize = 2048;
  const hopSize = fftSize >> 1;

  for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
    const sourceData = buffer.getChannelData(ch);
    const destData = newBuffer.getChannelData(ch);

    const window = new Array(fftSize);
    for (let i = 0; i < fftSize; i++) {
      window[i] = 0.5 * (1 - Math.cos(2 * Math.PI * i / (fftSize - 1)));
    }

    const noiseEstimateFrames = Math.min(8, Math.floor(sourceData.length / fftSize));
    const noiseMag = new Array(fftSize / 2 + 1).fill(0);

    for (let frame = 0; frame < noiseEstimateFrames; frame++) {
      const offset = frame * fftSize;
      const real = new Array(fftSize).fill(0);
      const imag = new Array(fftSize).fill(0);

      for (let i = 0; i < fftSize && offset + i < sourceData.length; i++) {
        real[i] = sourceData[offset + i] * window[i];
      }

      fft(real, imag);

      for (let i = 0; i <= fftSize / 2; i++) {
        noiseMag[i] += Math.sqrt(real[i] * real[i] + imag[i] * imag[i]);
      }
    }

    for (let i = 0; i <= fftSize / 2; i++) {
      noiseMag[i] /= Math.max(1, noiseEstimateFrames);
    }

    for (let i = 0; i < sourceData.length; i++) {
      destData[i] = 0;
    }

    const windowSum = new Array(sourceData.length).fill(0);

    let frameIdx = 0;
    while (frameIdx * hopSize < sourceData.length) {
      const offset = frameIdx * hopSize;
      const real = new Array(fftSize).fill(0);
      const imag = new Array(fftSize).fill(0);

      for (let i = 0; i < fftSize && offset + i < sourceData.length; i++) {
        real[i] = sourceData[offset + i] * window[i];
      }

      fft(real, imag);

      for (let i = 0; i <= fftSize / 2; i++) {
        const mag = Math.sqrt(real[i] * real[i] + imag[i] * imag[i]);
        const phase = Math.atan2(imag[i], real[i]);
        const threshold = noiseMag[i] * (1 + (1 - intensity) * 4);

        let newMag: number;
        if (mag < threshold) {
          const gateFactor = mag / threshold;
          newMag = mag * gateFactor * intensity;
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

      for (let i = 0; i < fftSize && offset + i < sourceData.length; i++) {
        destData[offset + i] += real[i] * window[i];
        windowSum[offset + i] += window[i] * window[i];
      }

      frameIdx++;
    }

    for (let i = 0; i < sourceData.length; i++) {
      if (windowSum[i] > 1e-10) {
        destData[i] /= windowSum[i];
      } else {
        destData[i] = sourceData[i];
      }
    }
  }

  return newBuffer;
}

function applyTransientRepair(buffer: AudioBuffer, intensity: number): AudioBuffer {
  const ctx = new OfflineAudioContext(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  const newBuffer = ctx.createBuffer(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  const attackCoeff = Math.exp(-1 / (0.005 * buffer.sampleRate));
  const releaseCoeff = Math.exp(-1 / (0.05 * buffer.sampleRate));
  const transientThreshold = 2.5;

  for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
    const sourceData = buffer.getChannelData(ch);
    const destData = newBuffer.getChannelData(ch);

    const envelope = new Array(sourceData.length);
    envelope[0] = Math.abs(sourceData[0]);

    for (let i = 1; i < sourceData.length; i++) {
      const absSample = Math.abs(sourceData[i]);
      const coeff = absSample > envelope[i - 1] ? attackCoeff : releaseCoeff;
      envelope[i] = coeff * envelope[i - 1] + (1 - coeff) * absSample;
    }

    const avgEnvelope = new Array(sourceData.length);
    const smoothWindow = Math.floor(buffer.sampleRate * 0.01);
    let runningSum = 0;

    for (let i = 0; i < sourceData.length; i++) {
      runningSum += envelope[i];
      if (i >= smoothWindow) {
        runningSum -= envelope[i - smoothWindow];
        avgEnvelope[i] = runningSum / smoothWindow;
      } else {
        avgEnvelope[i] = runningSum / (i + 1);
      }
    }

    for (let i = 0; i < sourceData.length; i++) {
      destData[i] = sourceData[i];
    }

    const reshapeWindow = Math.max(3, Math.floor(buffer.sampleRate * 0.002));

    for (let i = reshapeWindow; i < sourceData.length - reshapeWindow; i++) {
      if (avgEnvelope[i] > 1e-10) {
        const ratio = envelope[i] / avgEnvelope[i];
        if (ratio > transientThreshold) {
          const excess = ratio - transientThreshold;
          const reshapeFactor = 1 / (1 + (excess / transientThreshold) * intensity * 0.5);
          const reshaped = sourceData[i] * reshapeFactor;

          for (let j = 1; j <= reshapeWindow; j++) {
            const blend = j / reshapeWindow;
            const leftIdx = i - j;
            const rightIdx = i + j;
            if (leftIdx >= 0 && rightIdx < sourceData.length) {
              const neighborAvg = (sourceData[leftIdx] + sourceData[rightIdx]) / 2;
              destData[leftIdx] = sourceData[leftIdx] * (1 - intensity * blend * 0.3) + neighborAvg * intensity * blend * 0.3;
              destData[rightIdx] = sourceData[rightIdx] * (1 - intensity * blend * 0.3) + neighborAvg * intensity * blend * 0.3;
            }
          }

          destData[i] = reshaped;
        }
      }
    }
  }

  return newBuffer;
}

function applyHarmonicEnhance(buffer: AudioBuffer, intensity: number): AudioBuffer {
  const ctx = new OfflineAudioContext(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  const newBuffer = ctx.createBuffer(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  const evenHarmonicGain = 0.06 * intensity;
  const oddHarmonicGain = 0.03 * intensity;

  for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
    const sourceData = buffer.getChannelData(ch);
    const destData = newBuffer.getChannelData(ch);

    for (let i = 0; i < sourceData.length; i++) {
      const sample = sourceData[i];
      const h2 = sample * Math.abs(sample);
      const h4 = sample * sample * sample * Math.abs(sample);
      const evenHarmonic = h2 * 0.7 + h4 * 0.3;
      const h3 = sample * sample * sample;
      const h5 = h3 * sample * sample;
      const oddHarmonic = h3 * 0.8 + h5 * 0.2;

      destData[i] = sample + evenHarmonic * evenHarmonicGain + oddHarmonic * oddHarmonicGain;
      destData[i] = Math.max(-0.98, Math.min(0.98, destData[i]));
    }
  }

  return newBuffer;
}

function applySpatialEnhance(buffer: AudioBuffer, intensity: number): AudioBuffer {
  const ctx = new OfflineAudioContext(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  const channels = Math.max(buffer.numberOfChannels, 2);
  const newBuffer = ctx.createBuffer(
    channels,
    buffer.length,
    buffer.sampleRate
  );

  if (buffer.numberOfChannels >= 2) {
    const leftData = buffer.getChannelData(0);
    const rightData = buffer.getChannelData(1);
    const newLeft = newBuffer.getChannelData(0);
    const newRight = newBuffer.getChannelData(1);

    const sideGain = 1 + intensity * 0.4;
    const midGain = 1 - intensity * 0.1;

    for (let i = 0; i < buffer.length; i++) {
      const mid = (leftData[i] + rightData[i]) * 0.5;
      const side = (leftData[i] - rightData[i]) * 0.5;

      const enhancedMid = mid * midGain;
      const enhancedSide = side * sideGain;

      newLeft[i] = Math.max(-0.98, Math.min(0.98, enhancedMid + enhancedSide));
      newRight[i] = Math.max(-0.98, Math.min(0.98, enhancedMid - enhancedSide));
    }

    for (let ch = 2; ch < buffer.numberOfChannels; ch++) {
      const srcData = buffer.getChannelData(ch);
      const dstData = newBuffer.getChannelData(ch);
      for (let i = 0; i < buffer.length; i++) {
        dstData[i] = srcData[i];
      }
    }
  } else {
    const sourceData = buffer.getChannelData(0);
    const newLeft = newBuffer.getChannelData(0);
    const newRight = newBuffer.getChannelData(1);

    const delaySamples = Math.round(buffer.sampleRate * 0.00002 * (1 + intensity * 20));
    const sideAmount = intensity * 0.15;

    for (let i = 0; i < buffer.length; i++) {
      newLeft[i] = Math.max(-0.98, Math.min(0.98, sourceData[i] + (i + delaySamples < buffer.length ? sourceData[i + delaySamples] : 0) * sideAmount));
      newRight[i] = Math.max(-0.98, Math.min(0.98, sourceData[i] - (i + delaySamples < buffer.length ? sourceData[i + delaySamples] : 0) * sideAmount));
    }
  }

  return newBuffer;
}

async function applyPresenceBoost(buffer: AudioBuffer, intensity: number): Promise<AudioBuffer> {
  const ctx = new OfflineAudioContext(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  const source = ctx.createBufferSource();
  source.buffer = buffer;

  const eq2500 = ctx.createBiquadFilter();
  eq2500.type = 'peaking';
  eq2500.frequency.value = 2500;
  eq2500.Q.value = 1.2;
  eq2500.gain.value = intensity * 2.5;

  const eq3500 = ctx.createBiquadFilter();
  eq3500.type = 'peaking';
  eq3500.frequency.value = 3500;
  eq3500.Q.value = 1.0;
  eq3500.gain.value = intensity * 4;

  const eq5000 = ctx.createBiquadFilter();
  eq5000.type = 'peaking';
  eq5000.frequency.value = 5000;
  eq5000.Q.value = 1.4;
  eq5000.gain.value = intensity * 2;

  source.connect(eq2500);
  eq2500.connect(eq3500);
  eq3500.connect(eq5000);
  eq5000.connect(ctx.destination);

  source.start();

  return ctx.startRendering();
}

async function applyBassEnhance(buffer: AudioBuffer, intensity: number): Promise<AudioBuffer> {
  const ctx = new OfflineAudioContext(
    buffer.numberOfChannels,
    buffer.length,
    buffer.sampleRate
  );

  const source = ctx.createBufferSource();
  source.buffer = buffer;

  const subBass = ctx.createBiquadFilter();
  subBass.type = 'peaking';
  subBass.frequency.value = 60;
  subBass.Q.value = 0.8;
  subBass.gain.value = intensity * 4;

  const bassWarmth = ctx.createBiquadFilter();
  bassWarmth.type = 'peaking';
  bassWarmth.frequency.value = 150;
  bassWarmth.Q.value = 0.7;
  bassWarmth.gain.value = intensity * 3;

  source.connect(subBass);
  subBass.connect(bassWarmth);
  bassWarmth.connect(ctx.destination);

  source.start();

  return ctx.startRendering();
}

export async function applyAdvancedRepair(
  buffer: AudioBuffer,
  params: AdvancedRepairParams,
  progressCallback?: (progress: number) => void
): Promise<AudioBuffer> {
  let result = buffer;

  if (params.deClipping > 0) {
    result = applyDeClipping(result, params.deClipping);
    progressCallback?.(0.1);
  }

  if (params.deCrackle > 0) {
    result = applyDeCrackle(result, params.deCrackle);
    progressCallback?.(0.2);
  }

  if (params.dePop > 0) {
    result = applyDePop(result, params.dePop);
    progressCallback?.(0.3);
  }

  if (params.deEssing > 0) {
    result = await applyDeEssing(result, params.deEssing);
    progressCallback?.(0.4);
  }

  if (params.noiseReduction > 0) {
    result = applyNoiseReduction(result, params.noiseReduction);
    progressCallback?.(0.5);
  }

  if (params.transientRepair > 0) {
    result = applyTransientRepair(result, params.transientRepair);
    progressCallback?.(0.6);
  }

  if (params.harmonicEnhance > 0) {
    result = applyHarmonicEnhance(result, params.harmonicEnhance);
    progressCallback?.(0.7);
  }

  if (params.spatialEnhance > 0) {
    result = applySpatialEnhance(result, params.spatialEnhance);
    progressCallback?.(0.8);
  }

  if (params.presenceBoost > 0) {
    result = await applyPresenceBoost(result, params.presenceBoost);
    progressCallback?.(0.9);
  }

  if (params.bassEnhance > 0) {
    result = await applyBassEnhance(result, params.bassEnhance);
    progressCallback?.(0.95);
  }

  progressCallback?.(1);

  return result;
}

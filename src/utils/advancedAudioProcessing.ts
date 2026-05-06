export interface AIRepairParams {
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

export const defaultAIRepairParams: AIRepairParams = {
  deClipping: 0.25,
  noiseReduction: 0.18,
  deEssing: 0.22,
  deCrackle: 0.2,
  dePop: 0.15,
  harmonicEnhance: 0.12,
  dynamicRange: 0.08,
  softness: 0.06,
  presenceBoost: 0.05,
  bassEnhance: 0.08,
  spatialEnhance: 0.1,
  transientRepair: 0.1,
};

export interface RepairMode {
  name: string;
  description: string;
  icon: string;
  params: AIRepairParams;
}

export const repairModes: RepairMode[] = [
  {
    name: 'AI人声修复',
    description: '精准修复AI人声的毛刺、撕裂和数字伪影',
    icon: '🎤',
    params: {
      deClipping: 0.2,
      noiseReduction: 0.12,
      deEssing: 0.18,
      deCrackle: 0.15,
      dePop: 0.12,
      harmonicEnhance: 0.08,
      dynamicRange: 0.05,
      softness: 0.05,
      presenceBoost: 0.08,
      bassEnhance: 0.05,
      spatialEnhance: 0.08,
      transientRepair: 0.1,
    },
  },
  {
    name: '降噪修复',
    description: '去除背景噪音和数字伪影',
    icon: '🔇',
    params: {
      deClipping: 0.12,
      noiseReduction: 0.25,
      deEssing: 0.12,
      deCrackle: 0.12,
      dePop: 0.08,
      harmonicEnhance: 0.03,
      dynamicRange: 0.03,
      softness: 0.08,
      presenceBoost: 0.02,
      bassEnhance: 0.03,
      spatialEnhance: 0.05,
      transientRepair: 0.06,
    },
  },
  {
    name: '温和修复',
    description: '轻微处理，保留原始音质',
    icon: '🌿',
    params: {
      deClipping: 0.08,
      noiseReduction: 0.06,
      deEssing: 0.08,
      deCrackle: 0.06,
      dePop: 0.04,
      harmonicEnhance: 0.03,
      dynamicRange: 0.02,
      softness: 0.02,
      presenceBoost: 0.01,
      bassEnhance: 0.02,
      spatialEnhance: 0.02,
      transientRepair: 0.03,
    },
  },
  {
    name: '全面修复',
    description: '综合修复所有常见问题',
    icon: '🎵',
    params: {
      deClipping: 0.25,
      noiseReduction: 0.18,
      deEssing: 0.22,
      deCrackle: 0.18,
      dePop: 0.15,
      harmonicEnhance: 0.1,
      dynamicRange: 0.06,
      softness: 0.06,
      presenceBoost: 0.08,
      bassEnhance: 0.1,
      spatialEnhance: 0.12,
      transientRepair: 0.15,
    },
  },
];

export interface AudioIssue {
  type: 'clip' | 'crackle' | 'pop' | 'ess' | 'noise';
  start: number;
  end: number;
  severity: number;
}

export function detectAudioIssues(buffer: AudioBuffer): {
  spectralFlatness: number;
  dynamicRange: number;
  stereoBalance: number;
  peakLevel: number;
  issues: string[];
  clippingCount: number;
  crackleRegions: number[];
  popRegions: number[];
  detailedIssues: AudioIssue[];
} {
  const issues: string[] = [];
  const detailedIssues: AudioIssue[] = [];
  const channelData = buffer.getChannelData(0);
  const sampleRate = buffer.sampleRate;

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
          sample - 0.95
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
  if (buffer.numberOfChannels > 1) {
    const rightChannel = buffer.getChannelData(1);
    let leftEnergy = 0;
    let rightEnergy = 0;
    for (let i = 0; i < channelData.length; i++) {
      leftEnergy += channelData[i] * channelData[i];
      rightEnergy += rightChannel[i] * rightChannel[i];
    }
    stereoBalance = leftEnergy / (leftEnergy + rightEnergy + 0.0001);
  }

  if (spectralFlatness > 0.6) {
    issues.push('频谱异常');
  }
  if (dynamicRangeDb < 6) {
    issues.push('动态范围过小');
  }
  if (clippingCount > channelData.length * 0.0005) {
    issues.push('削波失真');
  }
  if (crackleRegions.length > 3) {
    issues.push('毛刺/撕裂');
  }
  if (popRegions.length > 5) {
    issues.push('爆音');
  }
  if (stereoBalance < 0.4 || stereoBalance > 0.6) {
    issues.push('立体声平衡偏移');
  }

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

function yieldToEventLoop(): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, 0));
}

export async function processWithAIRepair(
  buffer: AudioBuffer,
  params: AIRepairParams,
  onProgress?: (progress: number) => void
): Promise<AudioBuffer> {
  onProgress?.(0.1);

  const numChannels = buffer.numberOfChannels;
  const length = buffer.length;
  const sampleRate = buffer.sampleRate;
  
  const outputChannels: Float32Array[] = [];
  for (let ch = 0; ch < numChannels; ch++) {
    outputChannels.push(new Float32Array(buffer.getChannelData(ch)));
  }

  await yieldToEventLoop();
  onProgress?.(0.2);

  const analysis = detectAudioIssues(buffer);

  for (let ch = 0; ch < numChannels; ch++) {
    let processedChannel = outputChannels[ch];

    if (params.deClipping > 0 && analysis.clippingCount > 0) {
      processedChannel = applyDeClipping(processedChannel, params.deClipping);
    }

    if (params.deCrackle > 0 && analysis.detailedIssues.some(i => i.type === 'crackle')) {
      processedChannel = applyDeCrackle(processedChannel, sampleRate, params.deCrackle, analysis.detailedIssues);
    }

    if (params.dePop > 0 && analysis.detailedIssues.some(i => i.type === 'pop')) {
      processedChannel = applyDePop(processedChannel, params.dePop, analysis.detailedIssues);
    }

    outputChannels[ch] = processedChannel;
  }

  await yieldToEventLoop();
  onProgress?.(0.5);

  for (let ch = 0; ch < numChannels; ch++) {
    if (params.deEssing > 0) {
      outputChannels[ch] = applyDeEssing(outputChannels[ch], sampleRate, params.deEssing);
    }

    if (params.noiseReduction > 0) {
      outputChannels[ch] = applyNoiseReduction(outputChannels[ch], sampleRate, params.noiseReduction);
    }

    if (params.softness > 0) {
      outputChannels[ch] = applySoftness(outputChannels[ch], sampleRate, params.softness);
    }
  }

  await yieldToEventLoop();
  onProgress?.(0.75);

  for (let ch = 0; ch < numChannels; ch++) {
    if (params.harmonicEnhance > 0) {
      outputChannels[ch] = applyHarmonicEnhancement(outputChannels[ch], sampleRate, params.harmonicEnhance);
    }

    if (params.dynamicRange > 0) {
      outputChannels[ch] = applyDynamicRange(outputChannels[ch], params.dynamicRange);
    }
  }

  await yieldToEventLoop();
  onProgress?.(0.9);

  const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
  const outputBuffer = audioContext.createBuffer(numChannels, length, sampleRate);
  
  for (let ch = 0; ch < numChannels; ch++) {
    outputBuffer.copyToChannel(outputChannels[ch], ch);
  }

  onProgress?.(1);
  return outputBuffer;
}

function applyDeClipping(signal: Float32Array, amount: number): Float32Array {
  const output = new Float32Array(signal.length);
  const threshold = 0.95;
  const knee = 0.03;
  
  for (let i = 0; i < signal.length; i++) {
    const sample = signal[i];
    const absSample = Math.abs(sample);
    
    if (absSample > threshold + knee) {
      const excess = absSample - (threshold + knee);
      const scaledExcess = excess * (1 - amount);
      output[i] = Math.sign(sample) * (threshold + knee + scaledExcess * 0.3);
    } else if (absSample > threshold) {
      const t = (absSample - threshold) / knee;
      const eased = t * t * (3 - 2 * t);
      output[i] = Math.sign(sample) * (threshold + eased * knee);
    } else {
      output[i] = sample;
    }
  }
  
  return output;
}

function applyDeCrackle(signal: Float32Array, sampleRate: number, amount: number, issues: AudioIssue[]): Float32Array {
  const output = new Float32Array(signal);
  
  const crackleIssues = issues.filter(i => i.type === 'crackle');
  
  for (const issue of crackleIssues) {
    const start = Math.max(0, issue.start - Math.floor(sampleRate * 0.0005));
    const end = Math.min(signal.length, issue.end + Math.floor(sampleRate * 0.0005));
    const width = end - start;
    
    if (width < 2) continue;
    
    const before = signal[start > 0 ? start - 1 : 0];
    const after = signal[end < signal.length ? end : end - 1];
    
    const fadeLength = Math.min(Math.floor(width * 0.3), Math.floor(sampleRate * 0.0003));
    
    for (let i = start; i < end; i++) {
      const localIdx = i - start;
      let weight = 1;
      
      if (localIdx < fadeLength) {
        weight = localIdx / fadeLength;
      } else if (localIdx > width - fadeLength) {
        weight = 1 - (localIdx - (width - fadeLength)) / fadeLength;
      }
      
      const interpolated = before + (after - before) * ((i - start) / width);
      const smoothFactor = issue.severity > 0.5 ? amount * 0.8 : amount * 0.4;
      
      output[i] = output[i] * (1 - smoothFactor * weight) + interpolated * smoothFactor * weight;
    }
  }
  
  return output;
}

function applyDePop(signal: Float32Array, amount: number, issues: AudioIssue[]): Float32Array {
  const output = new Float32Array(signal);
  
  const popIssues = issues.filter(i => i.type === 'pop');
  
  for (const issue of popIssues) {
    const center = Math.floor((issue.start + issue.end) / 2);
    const radius = Math.min(5, Math.floor((issue.end - issue.start) / 2));
    
    const leftIdx = Math.max(0, center - radius - 1);
    const rightIdx = Math.min(signal.length - 1, center + radius + 1);
    
    const leftSample = signal[leftIdx];
    const rightSample = signal[rightIdx];
    
    for (let i = leftIdx; i <= rightIdx; i++) {
      const dist = Math.abs(i - center);
      const weight = Math.max(0, 1 - dist / (radius + 1));
      
      const interpolated = leftSample + (rightSample - leftSample) * ((i - leftIdx) / (rightIdx - leftIdx));
      
      output[i] = output[i] * (1 - amount * weight) + interpolated * amount * weight;
    }
  }
  
  return output;
}

function applyDeEssing(signal: Float32Array, sampleRate: number, amount: number): Float32Array {
  const output = new Float32Array(signal.length);
  
  const essThreshold = 0.08;
  const highFreqThreshold = 5000;
  const attackTime = Math.floor(sampleRate * 0.0005);
  const releaseTime = Math.floor(sampleRate * 0.02);
  
  let gain = 1;
  let attackCounter = 0;
  let releaseCounter = 0;
  
  const hpFilter = createHighPassFilter(sampleRate, highFreqThreshold);
  
  for (let i = 0; i < signal.length; i++) {
    const filtered = hpFilter(signal[i]);
    const absFiltered = Math.abs(filtered);
    
    if (absFiltered > essThreshold) {
      attackCounter++;
      releaseCounter = 0;
      
      if (attackCounter >= attackTime) {
        const overshoot = (absFiltered - essThreshold) / essThreshold;
        const targetGain = Math.max(0.7, 1 - overshoot * amount * 0.4);
        gain = Math.min(gain, targetGain);
      }
    } else {
      releaseCounter++;
      attackCounter = 0;
      
      if (releaseCounter >= releaseTime) {
        gain = Math.min(1, gain + 0.002);
      }
    }
    
    output[i] = signal[i] * gain;
  }
  
  return output;
}

function createHighPassFilter(sampleRate: number, cutoffFreq: number): (input: number) => number {
  const RC = 1 / (2 * Math.PI * cutoffFreq);
  const dt = 1 / sampleRate;
  const alpha = RC / (RC + dt);
  
  let prevInput = 0;
  let prevOutput = 0;
  
  return (input: number) => {
    const output = alpha * (prevOutput + input - prevInput);
    prevInput = input;
    prevOutput = output;
    return output;
  };
}

function applyNoiseReduction(signal: Float32Array, sampleRate: number, amount: number): Float32Array {
  const output = new Float32Array(signal.length);
  
  const lowpassFreq = 17000 + amount * 2000;
  const RC = 1 / (2 * Math.PI * lowpassFreq);
  const dt = 1 / sampleRate;
  const alpha = dt / (RC + dt);
  
  let prevOutput = signal[0];
  output[0] = signal[0];
  
  for (let i = 1; i < signal.length; i++) {
    prevOutput = output[i] = prevOutput + alpha * (signal[i] - prevOutput);
  }
  
  const noiseGateThreshold = 0.008 * amount;
  for (let i = 0; i < signal.length; i++) {
    if (Math.abs(output[i]) < noiseGateThreshold) {
      output[i] *= 0.3;
    }
  }
  
  return output;
}

function applySoftness(signal: Float32Array, sampleRate: number, amount: number): Float32Array {
  const output = new Float32Array(signal.length);
  
  const lowpassFreq = Math.max(15000, 19000 - amount * 3000);
  const RC = 1 / (2 * Math.PI * lowpassFreq);
  const dt = 1 / sampleRate;
  const alpha = dt / (RC + dt);
  
  let prevOutput = signal[0];
  output[0] = signal[0];
  
  for (let i = 1; i < signal.length; i++) {
    prevOutput = output[i] = prevOutput + alpha * (signal[i] - prevOutput);
  }
  
  return output;
}

function applyHarmonicEnhancement(signal: Float32Array, sampleRate: number, amount: number): Float32Array {
  const output = new Float32Array(signal.length);
  
  const centerFreq = 3000;
  const Q = 1.5;
  const boost = amount * 0.4;
  
  const w0 = 2 * Math.PI * centerFreq / sampleRate;
  const alpha = Math.sin(w0) / (2 * Q);
  const cosW0 = Math.cos(w0);
  
  const b0 = 1 + alpha * boost;
  const b1 = -2 * cosW0;
  const b2 = 1 - alpha * boost;
  const a0 = 1 + alpha / boost;
  const a1 = -2 * cosW0;
  const a2 = 1 - alpha / boost;
  
  let x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  
  for (let i = 0; i < signal.length; i++) {
    const x0 = signal[i];
    const y0 = (b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2) / a0;
    
    output[i] = y0 * amount + x0 * (1 - amount);
    
    x2 = x1;
    x1 = x0;
    y2 = y1;
    y1 = y0;
  }
  
  return output;
}

function applyDynamicRange(signal: Float32Array, amount: number): Float32Array {
  const output = new Float32Array(signal.length);
  
  const threshold = -18;
  const ratio = 1.15 + amount * 0.2;
  const attack = 0.008;
  const release = 0.15;
  
  let gain = 1;
  
  for (let i = 0; i < signal.length; i++) {
    const sample = signal[i];
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
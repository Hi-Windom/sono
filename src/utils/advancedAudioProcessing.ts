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
  warmth: number;
  clarity: number;
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
  warmth: 0,
  clarity: 0,
};

export interface RepairMode {
  name: string;
  description: string;
  icon: string;
  params: AIRepairParams;
}

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
export interface AISongDetectionResult {
  isAI: boolean;
  aiProbability: number;
  humanProbability: number;
  confidence: number;
  features: {
    spectralFlatness: number;
    spectralCentroid: number;
    spectralBandwidth: number;
    spectralRolloff: number;
    zeroCrossingRate: number;
    energy: number;
    energyEntropy: number;
    harmonicSpectralCentroid: number;
    onsetRate: number;
    pitchVariability: number;
    vibratoRate: number;
    vibratoDepth: number;
    formantStability: number;
    noiseFloor: number;
    dynamicRange: number;
    temporalCentroid: number;
    spectralFlux: number;
    spectralEntropy: number;
    mfccSimilarity: number;
    microRhythmConsistency: number;
    harmonicRatio: number;
    highFreqAttenuation: number;
    temporalRegularity: number;
  };
  reasons: string[];
  signature: 'human' | 'ai' | 'mixed' | 'uncertain';
}

export class AISongChecker {
  private buffer: AudioBuffer;
  private sampleRate: number;
  private channelData: Float32Array;
  private analysisLength: number;

  constructor(buffer: AudioBuffer) {
    this.buffer = buffer;
    this.sampleRate = buffer.sampleRate;
    this.channelData = buffer.getChannelData(0);
    this.analysisLength = Math.min(this.channelData.length, Math.floor(this.sampleRate * 45));
  }

  analyze(): AISongDetectionResult {
    const features = this.extractAdvancedFeatures();
    const { aiProbability, humanProbability, confidence, reasons, signature } = this.calculateProbability(features);

    return {
      isAI: aiProbability > 0.5,
      aiProbability,
      humanProbability,
      confidence,
      features,
      reasons,
      signature,
    };
  }

  private extractAdvancedFeatures() {
    const data = this.channelData.slice(0, this.analysisLength);
    
    const spectralFeatures = this.calculateSpectralFeatures(data);
    const temporalFeatures = this.calculateTemporalFeatures(data);
    const pitchFeatures = this.calculatePitchFeatures(data);
    const vocalFeatures = this.calculateVocalFeatures(data);
    const dynamicFeatures = this.calculateDynamicFeatures(data);
    const nextGenFeatures = this.calculateNextGenFeatures(data);

    return {
      ...spectralFeatures,
      ...temporalFeatures,
      ...pitchFeatures,
      ...vocalFeatures,
      ...dynamicFeatures,
      ...nextGenFeatures,
    };
  }

  private calculateSpectralFeatures(data: Float32Array) {
    const fftSize = 4096;
    const numFrames = Math.min(8, Math.floor(data.length / fftSize));
    
    let spectralFlatnessSum = 0;
    let spectralCentroidSum = 0;
    let spectralBandwidthSum = 0;
    let spectralRolloffSum = 0;
    let spectralFluxSum = 0;
    let prevSpectrum: Float32Array | null = null;

    for (let frame = 0; frame < numFrames; frame++) {
      const start = frame * fftSize;
      const frameData = data.slice(start, start + fftSize);
      const spectrum = this.calculateSpectrum(frameData, fftSize);

      spectralFlatnessSum += this.calculateSpectralFlatness(spectrum);
      spectralCentroidSum += this.calculateSpectralCentroid(spectrum);
      spectralBandwidthSum += this.calculateSpectralBandwidth(spectrum);
      spectralRolloffSum += this.calculateSpectralRolloff(spectrum);

      if (prevSpectrum) {
        spectralFluxSum += this.calculateSpectralFlux(spectrum, prevSpectrum);
      }
      prevSpectrum = spectrum;
    }

    return {
      spectralFlatness: spectralFlatnessSum / numFrames,
      spectralCentroid: spectralCentroidSum / numFrames,
      spectralBandwidth: spectralBandwidthSum / numFrames,
      spectralRolloff: spectralRolloffSum / numFrames,
      spectralFlux: spectralFluxSum / Math.max(1, numFrames - 1),
    };
  }

  private calculateSpectrum(data: Float32Array, fftSize: number): Float32Array {
    const spectrum = new Float32Array(fftSize / 2);
    
    for (let k = 0; k < fftSize / 2; k++) {
      let real = 0;
      let imag = 0;

      for (let n = 0; n < fftSize && n < data.length; n++) {
        const angle = (2 * Math.PI * k * n) / fftSize;
        real += data[n] * Math.cos(angle);
        imag -= data[n] * Math.sin(angle);
      }

      spectrum[k] = Math.sqrt(real * real + imag * imag);
    }

    return spectrum;
  }

  private calculateSpectralFlatness(spectrum: Float32Array): number {
    let sum = 0;
    let logSum = 0;
    let count = 0;

    for (let i = 0; i < spectrum.length; i++) {
      const mag = spectrum[i];
      if (mag > 0.00001) {
        sum += mag;
        logSum += Math.log(mag);
        count++;
      }
    }

    if (count === 0 || sum === 0) return 0;

    const geometricMean = Math.exp(logSum / count);
    const arithmeticMean = sum / count;

    return geometricMean / arithmeticMean;
  }

  private calculateSpectralCentroid(spectrum: Float32Array): number {
    let weightedSum = 0;
    let sum = 0;

    for (let i = 0; i < spectrum.length; i++) {
      const freq = (i * this.sampleRate) / spectrum.length;
      weightedSum += freq * spectrum[i];
      sum += spectrum[i];
    }

    return sum > 0 ? weightedSum / sum : 0;
  }

  private calculateSpectralBandwidth(spectrum: Float32Array): number {
    const centroid = this.calculateSpectralCentroid(spectrum);
    let weightedSum = 0;
    let sum = 0;

    for (let i = 0; i < spectrum.length; i++) {
      const freq = (i * this.sampleRate) / spectrum.length;
      weightedSum += Math.pow(freq - centroid, 2) * spectrum[i];
      sum += spectrum[i];
    }

    return sum > 0 ? Math.sqrt(weightedSum / sum) : 0;
  }

  private calculateSpectralRolloff(spectrum: Float32Array): number {
    const totalEnergy = spectrum.reduce((sum, val) => sum + val, 0);
    let cumulativeEnergy = 0;
    const targetEnergy = totalEnergy * 0.85;

    for (let i = 0; i < spectrum.length; i++) {
      cumulativeEnergy += spectrum[i];
      if (cumulativeEnergy >= targetEnergy) {
        return (i * this.sampleRate) / spectrum.length;
      }
    }

    return (spectrum.length * this.sampleRate) / spectrum.length;
  }

  private calculateSpectralFlux(spectrum: Float32Array, prevSpectrum: Float32Array): number {
    let flux = 0;
    const minLen = Math.min(spectrum.length, prevSpectrum.length);
    
    for (let i = 0; i < minLen; i++) {
      const diff = spectrum[i] - prevSpectrum[i];
      flux += Math.max(0, diff);
    }

    return flux / minLen;
  }

  private calculateTemporalFeatures(data: Float32Array) {
    const zeroCrossings = this.calculateZeroCrossingRate(data);
    const energy = this.calculateEnergy(data);
    const entropy = this.calculateEnergyEntropy(data);
    const temporalCentroid = this.calculateTemporalCentroid(data);
    const onsetRate = this.calculateOnsetRate(data);

    return {
      zeroCrossingRate: zeroCrossings,
      energy,
      energyEntropy: entropy,
      temporalCentroid,
      onsetRate,
    };
  }

  private calculateZeroCrossingRate(data: Float32Array): number {
    let crossings = 0;
    for (let i = 1; i < data.length; i++) {
      if (data[i] * data[i - 1] < 0) {
        crossings++;
      }
    }
    return crossings / (data.length - 1);
  }

  private calculateEnergy(data: Float32Array): number {
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      sum += data[i] * data[i];
    }
    return sum / data.length;
  }

  private calculateEnergyEntropy(data: Float32Array): number {
    const blockSize = 512;
    const numBlocks = Math.floor(data.length / blockSize);
    const energies: number[] = [];

    for (let i = 0; i < numBlocks; i++) {
      let energy = 0;
      for (let j = 0; j < blockSize; j++) {
        energy += data[i * blockSize + j] * data[i * blockSize + j];
      }
      energies.push(energy);
    }

    const totalEnergy = energies.reduce((sum, e) => sum + e, 0);
    if (totalEnergy === 0) return 0;

    let entropy = 0;
    for (const e of energies) {
      const prob = e / totalEnergy;
      if (prob > 0) {
        entropy -= prob * Math.log2(prob);
      }
    }

    return entropy / Math.log2(numBlocks);
  }

  private calculateTemporalCentroid(data: Float32Array): number {
    let weightedSum = 0;
    let sum = 0;

    for (let i = 0; i < data.length; i++) {
      const weight = Math.abs(data[i]);
      weightedSum += i * weight;
      sum += weight;
    }

    return sum > 0 ? weightedSum / sum / data.length : 0;
  }

  private calculateOnsetRate(data: Float32Array): number {
    const blockSize = 256;
    const numBlocks = Math.floor(data.length / blockSize);
    const energies: number[] = [];

    for (let i = 0; i < numBlocks; i++) {
      let energy = 0;
      for (let j = 0; j < blockSize; j++) {
        energy += Math.abs(data[i * blockSize + j]);
      }
      energies.push(energy / blockSize);
    }

    let onsets = 0;
    for (let i = 1; i < energies.length; i++) {
      const diff = energies[i] - energies[i - 1];
      if (diff > 0.05 && energies[i] > 0.02) {
        onsets++;
      }
    }

    return onsets / (numBlocks - 1);
  }

  private calculatePitchFeatures(data: Float32Array) {
    const pitchStability = this.calculatePitchStability(data);
    const pitchVariability = 1 - pitchStability;

    return {
      pitchVariability,
    };
  }

  private calculatePitchStability(data: Float32Array): number {
    const windowSize = Math.floor(this.sampleRate * 0.1);
    const numWindows = Math.min(20, Math.floor((data.length - windowSize) / windowSize));
    
    const pitches: number[] = [];

    for (let i = 0; i < numWindows; i++) {
      const start = i * windowSize;
      const windowData = data.slice(start, start + windowSize);
      const pitch = this.estimatePitch(windowData);
      if (pitch > 50 && pitch < 2000) {
        pitches.push(pitch);
      }
    }

    if (pitches.length < 3) return 0.5;

    const mean = pitches.reduce((a, b) => a + b, 0) / pitches.length;
    const variance = pitches.reduce((sum, p) => sum + Math.pow(p - mean, 2), 0) / pitches.length;
    const stdDev = Math.sqrt(variance);
    const cv = stdDev / mean;

    return Math.max(0, Math.min(1, 1 - cv * 2));
  }

  private estimatePitch(data: Float32Array): number {
    let maxCorr = 0;
    let bestLag = 0;
    const minLag = Math.floor(this.sampleRate / 2000);
    const maxLag = Math.floor(this.sampleRate / 50);

    for (let lag = minLag; lag < maxLag; lag += 2) {
      let corr = 0;
      for (let j = 0; j < data.length - lag; j++) {
        corr += data[j] * data[j + lag];
      }
      if (corr > maxCorr) {
        maxCorr = corr;
        bestLag = lag;
      }
    }

    return bestLag > 0 ? this.sampleRate / bestLag : 0;
  }

  private calculateVocalFeatures(data: Float32Array) {
    const vibratoStats = this.analyzeVibrato(data);
    const formantStability = this.calculateFormantStability(data);
    const harmonicCentroid = this.calculateHarmonicSpectralCentroid(data);

    return {
      vibratoRate: vibratoStats.rate,
      vibratoDepth: vibratoStats.depth,
      formantStability,
      harmonicSpectralCentroid: harmonicCentroid,
    };
  }

  private analyzeVibrato(data: Float32Array) {
    const windowSize = Math.floor(this.sampleRate * 0.2);
    const numWindows = Math.min(5, Math.floor((data.length - windowSize) / windowSize));
    
    const frequencies: number[] = [];

    for (let i = 0; i < numWindows; i++) {
      const start = Math.floor(i * windowSize);
      const windowData = data.slice(start, start + windowSize);
      const freq = this.estimatePitch(windowData);
      if (freq > 80 && freq < 1000) {
        frequencies.push(freq);
      }
    }

    if (frequencies.length < 3) {
      return { rate: 0, depth: 0 };
    }

    const diffs: number[] = [];
    for (let i = 1; i < frequencies.length; i++) {
      diffs.push(Math.abs(frequencies[i] - frequencies[i - 1]));
    }

    const avgDiff = diffs.reduce((a, b) => a + b, 0) / diffs.length;
    const variance = diffs.reduce((sum, d) => sum + Math.pow(d - avgDiff, 2), 0) / diffs.length;
    const _stdDev = Math.sqrt(variance);

    const vibratoRate = numWindows / (windowSize * numWindows / this.sampleRate);
    const vibratoDepth = avgDiff / frequencies[0];

    return {
      rate: Math.min(10, vibratoRate),
      depth: Math.min(0.05, vibratoDepth),
    };
  }

  private calculateFormantStability(data: Float32Array): number {
    const fftSize = 2048;
    const numFrames = Math.min(4, Math.floor(data.length / fftSize));
    
    const formantPositions: number[][] = [];

    for (let frame = 0; frame < numFrames; frame++) {
      const start = frame * fftSize;
      const frameData = data.slice(start, start + fftSize);
      const spectrum = this.calculateSpectrum(frameData, fftSize);

      const formants: number[] = [];
      for (let i = 1; i < spectrum.length - 1; i++) {
        if (spectrum[i] > spectrum[i - 1] && spectrum[i] > spectrum[i + 1]) {
          formants.push(i);
        }
      }
      formantPositions.push(formants.slice(0, 4));
    }

    if (formantPositions.length < 2) return 0.5;

    let totalDiff = 0;
    let count = 0;

    for (let i = 1; i < formantPositions.length; i++) {
      const prev = formantPositions[i - 1];
      const curr = formantPositions[i];
      const minLen = Math.min(prev.length, curr.length);
      
      for (let j = 0; j < minLen; j++) {
        totalDiff += Math.abs(prev[j] - curr[j]);
        count++;
      }
    }

    const avgDiff = count > 0 ? totalDiff / count : 0;
    return Math.max(0, Math.min(1, 1 - avgDiff / 20));
  }

  private calculateHarmonicSpectralCentroid(data: Float32Array): number {
    const spectrum = this.calculateSpectrum(data.slice(0, 4096), 4096);
    
    let totalSum = 0;
    let weightedSum = 0;

    for (let i = 0; i < spectrum.length; i++) {
      const freq = (i * this.sampleRate) / spectrum.length;
      totalSum += spectrum[i];
      weightedSum += freq * spectrum[i];
    }

    const centroid = totalSum > 0 ? weightedSum / totalSum : 0;
    return centroid / 5000;
  }

  private calculateDynamicFeatures(data: Float32Array) {
    const noiseFloor = this.calculateNoiseFloor(data);
    const dynamicRange = this.calculateDynamicRange(data);

    return {
      noiseFloor,
      dynamicRange,
    };
  }

  private calculateNoiseFloor(data: Float32Array): number {
    const spectrum = this.calculateSpectrum(data.slice(0, 4096), 4096);
    
    let lowFreqEnergy = 0;
    let highFreqEnergy = 0;

    for (let i = 0; i < spectrum.length; i++) {
      const freq = (i * this.sampleRate) / spectrum.length;
      if (freq < 100) {
        lowFreqEnergy += spectrum[i] * spectrum[i];
      } else if (freq > 15000) {
        highFreqEnergy += spectrum[i] * spectrum[i];
      }
    }

    const totalEnergy = spectrum.reduce((sum, s) => sum + s * s, 0);
    
    if (totalEnergy === 0) return 0;
    
    const noiseRatio = highFreqEnergy / (lowFreqEnergy + 0.0001);
    
    return Math.max(0, Math.min(1, noiseRatio / 50));
  }

  private calculateDynamicRange(data: Float32Array): number {
    const blockSize = 1024;
    const numBlocks = Math.floor(data.length / blockSize);
    
    if (numBlocks < 2) return 0;
    
    const blockRMS: number[] = [];
    let maxRMS = 0;
    let minRMS = Infinity;

    for (let i = 0; i < numBlocks; i++) {
      let energy = 0;
      for (let j = 0; j < blockSize; j++) {
        const idx = i * blockSize + j;
        if (idx < data.length) {
          energy += data[idx] * data[idx];
        }
      }
      const rms = Math.sqrt(energy / blockSize);
      blockRMS.push(rms);
      maxRMS = Math.max(maxRMS, rms);
      minRMS = Math.min(minRMS, rms);
    }

    if (minRMS === 0) return 0;
    
    return 20 * Math.log10(maxRMS / minRMS);
  }

  private calculateNextGenFeatures(data: Float32Array) {
    const spectralEntropy = this.calculateSpectralEntropy(data);
    const mfccSimilarity = this.calculateMFCCSimilarity(data);
    const microRhythmConsistency = this.calculateMicroRhythmConsistency(data);
    const harmonicRatio = this.calculateHarmonicRatio(data);
    const highFreqAttenuation = this.calculateHighFreqAttenuation(data);
    const temporalRegularity = this.calculateTemporalRegularity(data);

    return {
      spectralEntropy,
      mfccSimilarity,
      microRhythmConsistency,
      harmonicRatio,
      highFreqAttenuation,
      temporalRegularity,
    };
  }

  private calculateSpectralEntropy(data: Float32Array): number {
    const fftSize = 4096;
    const spectrum = this.calculateSpectrum(data.slice(0, fftSize), fftSize);
    const totalEnergy = spectrum.reduce((sum, val) => sum + val * val, 0);

    if (totalEnergy === 0) return 0;

    let entropy = 0;
    for (let i = 0; i < spectrum.length; i++) {
      const prob = (spectrum[i] * spectrum[i]) / totalEnergy;
      if (prob > 0) {
        entropy -= prob * Math.log2(prob);
      }
    }

    const maxEntropy = Math.log2(spectrum.length);
    return maxEntropy > 0 ? entropy / maxEntropy : 0;
  }

  private calculateMFCCSimilarity(data: Float32Array): number {
    const fftSize = 2048;
    const hopSize = Math.floor(fftSize / 4);
    const numFrames = Math.min(10, Math.floor((data.length - fftSize) / hopSize));

    if (numFrames < 2) return 0.5;

    const mfccFrames: number[][] = [];
    const numMelBins = 13;
    const melFilters = this.createMelFilterBank(numMelBins, fftSize);

    for (let frame = 0; frame < numFrames; frame++) {
      const start = frame * hopSize;
      const frameData = data.slice(start, start + fftSize);
      const spectrum = this.calculateSpectrum(frameData, fftSize);

      const melEnergies: number[] = [];
      for (let m = 0; m < numMelBins; m++) {
        let energy = 0;
        for (let k = 0; k < spectrum.length; k++) {
          energy += spectrum[k] * spectrum[k] * melFilters[m][k];
        }
        melEnergies.push(Math.log(energy + 1e-10));
      }

      const dctCoeffs: number[] = [];
      for (let c = 0; c < Math.min(13, numMelBins); c++) {
        let coeff = 0;
        for (let n = 0; n < numMelBins; n++) {
          coeff += melEnergies[n] * Math.cos(Math.PI * c * (2 * n + 1) / (2 * numMelBins));
        }
        dctCoeffs.push(coeff);
      }

      mfccFrames.push(dctCoeffs);
    }

    let totalSimilarity = 0;
    let pairCount = 0;

    for (let i = 1; i < mfccFrames.length; i++) {
      const sim = this.cosineSimilarity(mfccFrames[i - 1], mfccFrames[i]);
      totalSimilarity += sim;
      pairCount++;
    }

    return pairCount > 0 ? totalSimilarity / pairCount : 0.5;
  }

  private createMelFilterBank(numBins: number, fftSize: number): number[][] {
    const filters: number[][] = [];
    const numSpectrumBins = fftSize / 2;
    const lowMel = this.hzToMel(0);
    const highMel = this.hzToMel(this.sampleRate / 2);
    const melPoints: number[] = [];

    for (let i = 0; i <= numBins + 1; i++) {
      melPoints.push(lowMel + (i * (highMel - lowMel)) / (numBins + 1));
    }

    const binPoints = melPoints.map(mel => Math.floor(this.melToHz(mel) / this.sampleRate * fftSize));

    for (let m = 0; m < numBins; m++) {
      const filter = new Array(numSpectrumBins).fill(0);
      const start = binPoints[m];
      const center = binPoints[m + 1];
      const end = binPoints[m + 2];

      for (let k = start; k < center && k < numSpectrumBins; k++) {
        if (k >= 0) filter[k] = (k - start) / (center - start + 1e-10);
      }
      for (let k = center; k < end && k < numSpectrumBins; k++) {
        if (k >= 0) filter[k] = (end - k) / (end - center + 1e-10);
      }

      filters.push(filter);
    }

    return filters;
  }

  private hzToMel(hz: number): number {
    return 2595 * Math.log10(1 + hz / 700);
  }

  private melToHz(mel: number): number {
    return 700 * (Math.pow(10, mel / 2595) - 1);
  }

  private cosineSimilarity(a: number[], b: number[]): number {
    let dotProduct = 0;
    let normA = 0;
    let normB = 0;

    const len = Math.min(a.length, b.length);
    for (let i = 0; i < len; i++) {
      dotProduct += a[i] * b[i];
      normA += a[i] * a[i];
      normB += b[i] * b[i];
    }

    const denominator = Math.sqrt(normA) * Math.sqrt(normB);
    return denominator > 0 ? dotProduct / denominator : 0;
  }

  private calculateMicroRhythmConsistency(data: Float32Array): number {
    const blockSize = 512;
    const numBlocks = Math.floor(data.length / blockSize);

    if (numBlocks < 4) return 0.5;

    const blockEnergies: number[] = [];
    for (let i = 0; i < numBlocks; i++) {
      let energy = 0;
      for (let j = 0; j < blockSize; j++) {
        energy += Math.abs(data[i * blockSize + j]);
      }
      blockEnergies.push(energy / blockSize);
    }

    const onsets: number[] = [];
    for (let i = 1; i < blockEnergies.length; i++) {
      if (blockEnergies[i] - blockEnergies[i - 1] > 0.03 && blockEnergies[i] > 0.02) {
        onsets.push(i);
      }
    }

    if (onsets.length < 3) return 0.5;

    const intervals: number[] = [];
    for (let i = 1; i < onsets.length; i++) {
      intervals.push(onsets[i] - onsets[i - 1]);
    }

    const meanInterval = intervals.reduce((a, b) => a + b, 0) / intervals.length;
    const variance = intervals.reduce((sum, iv) => sum + Math.pow(iv - meanInterval, 2), 0) / intervals.length;
    const cv = Math.sqrt(variance) / (meanInterval + 1e-10);

    return Math.max(0, Math.min(1, 1 - cv * 3));
  }

  private calculateHarmonicRatio(data: Float32Array): number {
    const fftSize = 4096;
    const spectrum = this.calculateSpectrum(data.slice(0, fftSize), fftSize);
    const totalEnergy = spectrum.reduce((sum, val) => sum + val * val, 0);

    if (totalEnergy === 0) return 0;

    const peakIndices: number[] = [];
    for (let i = 1; i < spectrum.length - 1; i++) {
      if (spectrum[i] > spectrum[i - 1] && spectrum[i] > spectrum[i + 1] && spectrum[i] > 0.001) {
        peakIndices.push(i);
      }
    }

    if (peakIndices.length < 2) return 0;

    const fundamentalIdx = peakIndices[0];
    let harmonicEnergy = 0;

    for (let h = 1; h <= 8; h++) {
      const targetIdx = fundamentalIdx * h;
      if (targetIdx >= spectrum.length) break;

      const searchRadius = Math.max(2, Math.floor(fundamentalIdx * 0.1));
      let maxEnergy = 0;
      for (let k = Math.max(0, targetIdx - searchRadius); k <= Math.min(spectrum.length - 1, targetIdx + searchRadius); k++) {
        maxEnergy = Math.max(maxEnergy, spectrum[k] * spectrum[k]);
      }
      harmonicEnergy += maxEnergy;
    }

    return Math.min(1, harmonicEnergy / totalEnergy);
  }

  private calculateHighFreqAttenuation(data: Float32Array): number {
    const fftSize = 4096;
    const numFrames = Math.min(6, Math.floor(data.length / fftSize));
    const spectrum = this.calculateSpectrum(data.slice(0, fftSize), fftSize);

    const highFreqStart = Math.floor(8000 * spectrum.length / this.sampleRate);
    const veryHighFreqStart = Math.floor(12000 * spectrum.length / this.sampleRate);

    let midHighEnergy = 0;
    let veryHighEnergy = 0;

    for (let i = highFreqStart; i < veryHighFreqStart && i < spectrum.length; i++) {
      midHighEnergy += spectrum[i] * spectrum[i];
    }
    for (let i = veryHighFreqStart; i < spectrum.length; i++) {
      veryHighEnergy += spectrum[i] * spectrum[i];
    }

    if (midHighEnergy === 0) return 0;

    const attenuationRatio = veryHighEnergy / midHighEnergy;

    let unnaturalScore = 0;
    if (numFrames > 1) {
      const attenuationRatios: number[] = [attenuationRatio];
      for (let frame = 1; frame < numFrames; frame++) {
        const start = frame * fftSize;
        if (start + fftSize > data.length) break;
        const frameSpectrum = this.calculateSpectrum(data.slice(start, start + fftSize), fftSize);

        let mhe = 0;
        let vhe = 0;
        for (let i = highFreqStart; i < veryHighFreqStart && i < frameSpectrum.length; i++) {
          mhe += frameSpectrum[i] * frameSpectrum[i];
        }
        for (let i = veryHighFreqStart; i < frameSpectrum.length; i++) {
          vhe += frameSpectrum[i] * frameSpectrum[i];
        }
        attenuationRatios.push(mhe > 0 ? vhe / mhe : 0);
      }

      const meanRatio = attenuationRatios.reduce((a, b) => a + b, 0) / attenuationRatios.length;
      const variance = attenuationRatios.reduce((sum, r) => sum + Math.pow(r - meanRatio, 2), 0) / attenuationRatios.length;
      const cv = Math.sqrt(variance) / (meanRatio + 1e-10);

      unnaturalScore = Math.max(0, 1 - cv * 5);
    }

    const steepDrop = attenuationRatio < 0.01 ? 0.3 : 0;
    return Math.max(0, Math.min(1, unnaturalScore * 0.7 + steepDrop));
  }

  private calculateTemporalRegularity(data: Float32Array): number {
    const blockSize = 1024;
    const numBlocks = Math.floor(data.length / blockSize);

    if (numBlocks < 4) return 0.5;

    const envelope: number[] = [];
    for (let i = 0; i < numBlocks; i++) {
      let energy = 0;
      for (let j = 0; j < blockSize; j++) {
        const idx = i * blockSize + j;
        if (idx < data.length) {
          energy += data[idx] * data[idx];
        }
      }
      envelope.push(Math.sqrt(energy / blockSize));
    }

    const diffs: number[] = [];
    for (let i = 1; i < envelope.length; i++) {
      diffs.push(Math.abs(envelope[i] - envelope[i - 1]));
    }

    const meanDiff = diffs.reduce((a, b) => a + b, 0) / diffs.length;
    const variance = diffs.reduce((sum, d) => sum + Math.pow(d - meanDiff, 2), 0) / diffs.length;
    const cv = Math.sqrt(variance) / (meanDiff + 1e-10);

    const secondDiffs: number[] = [];
    for (let i = 1; i < diffs.length; i++) {
      secondDiffs.push(Math.abs(diffs[i] - diffs[i - 1]));
    }
    const meanSecondDiff = secondDiffs.reduce((a, b) => a + b, 0) / secondDiffs.length;
    const smoothness = 1 / (1 + meanSecondDiff * 100);

    const regularityScore = Math.max(0, Math.min(1, 1 - cv * 2));
    return regularityScore * 0.6 + smoothness * 0.4;
  }

  private calculateProbability(features: AISongDetectionResult['features']) {
    const reasons: string[] = [];
    let aiScore = 0;
    let humanScore = 0;
    let weightSum = 0;

    const checkFeature = (
      value: number, 
      aiThreshold: number, 
      humanThreshold: number, 
      aiReason: string, 
      humanReason: string, 
      weight: number, 
      higherIsAI: boolean
    ) => {
      const range = Math.abs(aiThreshold - humanThreshold);
      
      if (higherIsAI) {
        if (value > aiThreshold) {
          const excess = (value - aiThreshold) / range;
          aiScore += weight * Math.min(2, excess * 2);
          reasons.push(aiReason);
          weightSum += weight;
        } else if (value < humanThreshold) {
          const deficit = (humanThreshold - value) / range;
          humanScore += weight * Math.min(2, deficit * 2);
          reasons.push(humanReason);
          weightSum += weight;
        } else {
          const midPoint = (aiThreshold + humanThreshold) / 2;
          if (value > midPoint) {
            aiScore += weight * 0.3;
          } else {
            humanScore += weight * 0.3;
          }
        }
      } else {
        if (value < aiThreshold) {
          const deficit = (aiThreshold - value) / range;
          aiScore += weight * Math.min(2, deficit * 2);
          reasons.push(aiReason);
          weightSum += weight;
        } else if (value > humanThreshold) {
          const excess = (value - humanThreshold) / range;
          humanScore += weight * Math.min(2, excess * 2);
          reasons.push(humanReason);
          weightSum += weight;
        } else {
          const midPoint = (aiThreshold + humanThreshold) / 2;
          if (value < midPoint) {
            aiScore += weight * 0.3;
          } else {
            humanScore += weight * 0.3;
          }
        }
      }
    };

    checkFeature(features.spectralFlatness, 0.55, 0.35, '频谱过于均匀', '频谱有自然变化', 0.12, true);
    checkFeature(features.spectralFlux, 0.06, 0.02, '频谱变化异常', '频谱变化自然', 0.08, true);
    checkFeature(features.zeroCrossingRate, 0.12, 0.04, '波形变化频率异常', '波形变化自然', 0.07, true);
    checkFeature(features.energyEntropy, 0.55, 0.75, '能量分布过于均匀', '能量分布有变化', 0.07, false);
    checkFeature(features.pitchVariability, 0.15, 0.35, '音高过于稳定', '音高有自然变化', 0.09, false);
    checkFeature(features.formantStability, 0.85, 0.55, '共振峰过于稳定', '共振峰有变化', 0.07, true);
    checkFeature(features.dynamicRange, 12, 22, '动态范围偏小', '动态范围良好', 0.06, false);
    checkFeature(features.noiseFloor, 0.003, 0.015, '底噪过低', '有自然底噪', 0.04, false);
    checkFeature(features.spectralEntropy, 0.7, 0.5, '频谱熵过高能量分布太均匀', '频谱熵正常能量分布自然', 0.10, true);
    checkFeature(features.mfccSimilarity, 0.85, 0.6, 'MFCC帧间过于相似', 'MFCC帧间变化自然', 0.10, true);
    checkFeature(features.microRhythmConsistency, 0.8, 0.5, '微节奏过于一致', '微节奏有自然波动', 0.07, true);
    checkFeature(features.harmonicRatio, 0.7, 0.45, '谐波比率过高过于规则', '谐波结构自然', 0.07, true);
    checkFeature(features.highFreqAttenuation, 0.5, 0.25, '高频衰减不自然', '高频衰减自然', 0.05, true);
    checkFeature(features.temporalRegularity, 0.75, 0.5, '时域包络过于规律', '时域包络有自然变化', 0.08, true);

    let aiProbability = 0.5;
    let humanProbability = 0.5;
    let confidence = 0.3;

    const totalScore = aiScore + humanScore;
    if (totalScore > 0.05) {
      const ratio = aiScore / totalScore;
      
      if (ratio > 0.65) {
        aiProbability = 0.35 + ratio * 0.55;
        humanProbability = 1 - aiProbability;
      } else if (ratio < 0.35) {
        humanProbability = 0.35 + (1 - ratio) * 0.55;
        aiProbability = 1 - humanProbability;
      } else {
        aiProbability = 0.4 + ratio * 0.2;
        humanProbability = 1 - aiProbability;
      }
      
      confidence = Math.min(0.9, weightSum / 2.0);
    }

    let signature: 'human' | 'ai' | 'mixed' | 'uncertain' = 'uncertain';
    if (aiProbability > 0.7 && confidence > 0.4) {
      signature = 'ai';
    } else if (humanProbability > 0.7 && confidence > 0.4) {
      signature = 'human';
    } else if (weightSum > 0.3) {
      signature = 'mixed';
    }

    return {
      aiProbability,
      humanProbability,
      confidence,
      reasons: reasons.slice(0, 6),
      signature,
    };
  }
}

export function checkAISong(buffer: AudioBuffer): AISongDetectionResult {
  const checker = new AISongChecker(buffer);
  return checker.analyze();
}

import { API_BASE, log } from './_shared';
import type { DetectAudioResponse, BackendDetectionResult, AudioFileInfo } from './types';
import { AISongDetectionResult } from '../../utils/aiSongChecker';

export function mapDetectionResult(backend: BackendDetectionResult): AISongDetectionResult {
  const aiProbability = backend.ai_probability;
  const humanProbability = backend.human_probability ?? (1 - aiProbability);
  const isAI = aiProbability > humanProbability;

  let signature: AISongDetectionResult['signature'];
  if (backend.signature) {
    signature = backend.signature;
  } else {
    signature = 'uncertain';
    if (aiProbability > 0.7 && backend.confidence > 0.4) {
      signature = 'ai';
    } else if (humanProbability > 0.7 && backend.confidence > 0.4) {
      signature = 'human';
    } else if (backend.confidence > 0.3) {
      signature = 'mixed';
    }
  }

  const f = backend.features || {};

  return {
    isAI,
    aiProbability,
    humanProbability,
    confidence: backend.confidence,
    features: {
      spectralFlatness: f.spectral_flatness ?? 0,
      spectralCentroid: f.spectral_centroid_mean ?? 0,
      spectralBandwidth: 0,
      spectralRolloff: 0,
      zeroCrossingRate: 0,
      energy: 0,
      energyEntropy: 0,
      harmonicSpectralCentroid: 0,
      onsetRate: 0,
      pitchVariability: f.pitch_variability ?? 0,
      vibratoRate: 0,
      vibratoDepth: 0,
      formantStability: 0,
      noiseFloor: 0,
      dynamicRange: f.dynamic_range ?? 0,
      temporalCentroid: 0,
      spectralFlux: 0,
      spectralEntropy: f.spectral_entropy ?? 0,
      mfccSimilarity: f.mfcc_variability ?? 0,
      microRhythmConsistency: f.micro_rhythm_consistency ?? 0,
      harmonicRatio: 0,
      highFreqAttenuation: f.high_freq_attenuation ?? 0,
      temporalRegularity: f.temporal_regularity ?? 0,
    },
    reasons: backend.reasons || [],
    signature,
  };
}

export async function detectAudio(taskId: string, type: 'original' | 'repaired' = 'original', detectorVersion?: string, skipCache: boolean = false): Promise<DetectAudioResponse> {
  const url = `${API_BASE}/detect`;
  const versionToSend = detectorVersion || 'v1.0';
  log('detect', `POST ${url} task_id=${taskId} type=${type} detector_version=${versionToSend} skipCache=${skipCache}`);

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, type, detector_version: versionToSend, skip_cache: skipCache }),
    });

    log('detect', `response status=${res.status} ok=${res.ok}`);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '检测请求失败' }));
      log('detect', `ERROR: ${err.detail}`);
      throw new Error(err.detail || '检测请求失败');
    }

    const data: DetectAudioResponse = await res.json();
    log('detect', `success: status=${data.status} cached=${!!data.cached}`);
    return data;
  } catch (e) {
    log('detect', `FETCH ERROR: ${e instanceof Error ? e.message : String(e)}`);
    throw e;
  }
}

export async function detectFile(file: File, detectorVersion: string = 'v1.1'): Promise<{ task_id: string; status: string }> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('detector_version', detectorVersion);

  const res = await fetch(`${API_BASE}/detect-file`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '检测请求失败' }));
    throw new Error(err.detail || '检测请求失败');
  }

  return res.json();
}

export async function getAudioFiles(): Promise<{ files: AudioFileInfo[]; count: number }> {
  const res = await fetch(`${API_BASE}/audio-files`);
  if (!res.ok) throw new Error('获取音频文件列表失败');
  return res.json();
}

export async function detectByPath(fileId: string, detectorVersion: string = 'v1.1'): Promise<{ task_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/detect-path`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_id: fileId, detector_version: detectorVersion }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '检测请求失败' }));
    throw new Error(err.detail || '检测请求失败');
  }

  return res.json();
}

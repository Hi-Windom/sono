import { ProcessingOptions, AlgorithmVersion, QueueStatus, SignalProfile } from '../../services/backendApi';
import { AIRepairParams, RepairMode } from '../../utils/advancedAudioProcessing';
import { WavInfo } from '../../utils/wavParser';
import { CacheHitInfo } from '../../components/RepairCacheModal';

export { defaultAIRepairParams } from '../../utils/advancedAudioProcessing';

export interface AudioAnalysis {
  spectralFlatness: number;
  dynamicRange: number;
  stereoBalance: number;
  peakLevel: number;
  issues: string[];
}

export type PlayMode = 'original' | 'backend';

export type { ProcessingOptions };

export const defaultProcessingOptions: ProcessingOptions = {
  sampleRate: 48000,
  bitDepth: 24,
  masteringStyle: 'standard',
  qualityMode: 'standard',
};

export interface RepairResult {
  issues_found: string[];
  original_sample_rate: number;
  output_sample_rate: number;
  output_bit_depth: number;
  duration: number;
  channels: number;
  algorithm_version?: string;
  waveform_peaks?: number[][];
  processing_mode?: string;
  signal_profile?: SignalProfile;
  completed_at?: string;
}

export interface StuckInfo {
  taskId: string;
  lastProgress: number;
  lastStep: string;
  duration: number;
}

export interface AutoRenderInfo {
  output_sample_rate: number;
  output_bit_depth: number;
  duration: number;
  channels: number;
}

export type {
  AIRepairParams,
  RepairMode,
  WavInfo,
  AlgorithmVersion,
  QueueStatus,
  CacheHitInfo,
  SignalProfile,
};

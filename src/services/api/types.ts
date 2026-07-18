import { AIRepairParams } from '../../utils/advancedAudioProcessing';
import { AISongDetectionResult } from '../../utils/aiSongChecker';

export interface VocalRepairParams {
  deClipping: number;
  dePop: number;
  formantRepair: number;
  deEssing: number;
  breathEnhance: number;
  aiRepair: number;
  bassEnhance: number;
  airTexture: number;
  loudness: number;
  exciter?: number;
  compressor?: number;
  spatial?: number;
  warmth?: number;
  smartCompressor?: number;
  transientAware?: number;
  resonanceSuppress?: number;
  aiRepairAdaptive?: number;
  exciterImproved?: number;
  deEsserImproved?: number;
  speed?: number;
}

export interface InstrumentRepairParams {
  deClipping: number;
  dePop: number;
  timbreProtect: number;
  dynamicRange: number;
  noiseReduction: number;
  spatialEnhance: number;
  warmth: number;
  loudness: number;
  stereo_enhance?: number;
  exciter?: number;
  transient?: number;
  resonance?: number;
  bassEnhance?: number;
  airTexture?: number;
  speed?: number;
}

export const defaultVocalRepairParams: VocalRepairParams = {
  deClipping: 0.30,
  dePop: 0.18,
  formantRepair: 0.5,
  deEssing: 0.25,
  breathEnhance: 0.3,
  aiRepair: 0.2,
  bassEnhance: 0.1,
  airTexture: 0.2,
  loudness: 0.5,
  exciter: 0.5,
  compressor: 0.5,
  spatial: 0.5,
  warmth: 0.5,
  smartCompressor: 0.5,
  transientAware: 0.3,
  resonanceSuppress: 0.3,
  aiRepairAdaptive: 0.5,
  exciterImproved: 0.5,
  deEsserImproved: 0.5,
  speed: 1.0,
};

export const defaultInstrumentRepairParams: InstrumentRepairParams = {
  deClipping: 0.30,
  dePop: 0.18,
  timbreProtect: 0.5,
  dynamicRange: 0.2,
  noiseReduction: 0.15,
  spatialEnhance: 0.15,
  warmth: 0.25,
  loudness: 0.5,
  stereo_enhance: 0.5,
  exciter: 0,
  transient: 0,
  resonance: 0,
  bassEnhance: 0,
  airTexture: 0,
  speed: 1.0,
};

export interface ProcessingOptions {
  sampleRate: number;
  bitDepth: 16 | 24 | 32;
  masteringStyle?: 'standard' | 'powerful' | 'warm' | 'adaptive';
  qualityMode?: 'standard' | 'fine';
  outputVolume?: number;
}

export interface AudioInfo {
  sample_rate: number;
  channels: number;
  duration: number;
  num_frames: number;
  format: string;
  sample_width: number;
}

export interface UploadResponse {
  task_id: string;
  filename: string;
  size: number;
  message: string;
  cached?: boolean;
  audio_info?: AudioInfo | null;
}

export interface TaskStatus {
  task_id: string;
  status: string;
  progress: number;
  step: string;
  detection_result?: BackendDetectionResult;
  repaired_detection_result?: BackendDetectionResult;
  repair_result?: BackendRepairResult;
  error?: string;
}

export interface BackendDetectionResult {
  is_ai_generated: boolean;
  confidence: number;
  ai_probability: number;
  human_probability?: number;
  signature?: 'human' | 'ai' | 'mixed' | 'uncertain';
  reasons: string[];
  features: Record<string, number>;
  sample_rate: number;
  duration: number;
  detect_type?: string;
}

export interface SignalProfile {
  clip_density_pct: number;
  peak_db: number;
  rms_db: number;
  crest_factor_db: number;
  noise_floor_db: number;
  snr_db: number;
  sibilance_pct: number;
  transient_density: number;
  spectral_flatness: number;
  spectral_centroid_hz: number;
  lufs: number;
  dynamic_range_db: number;
  stereo_width: number;
  detected_issues: string[];
}

export interface BackendRepairResult {
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
}

export interface ProgressEvent {
  task_id: string;
  status: string;
  progress: number;
  step: string;
  detection_result?: BackendDetectionResult;
  repaired_detection_result?: BackendDetectionResult;
  repair_result?: BackendRepairResult;
  render_filename?: string;
  render_result?: {
    original_sample_rate: number;
    output_sample_rate: number;
    output_bit_depth: number;
    duration: number;
    channels: number;
  };
  error?: string;
}

export interface AlgorithmVersion {
  name: string;
  label: string;
  description: string;
  tags?: string[];
  supportsDualTrack?: boolean;
  defaultParams: Record<string, number>;
  paramRanges: Record<string, {
    min: number;
    max: number;
    step: number;
    label: string;
  }>;
  modes: {
    name: string;
    description: string;
    icon: string;
    params: Record<string, number>;
  }[];
}

export interface DetectorVersion {
  name: string;
  label: string;
  description: string;
}

export type ProgressCallback = (loaded: number, total: number, speed: number) => void;

export interface DualUploadResponse {
  task_id: string;
  vocal_task_id: string;
  accompaniment_task_id: string;
  vocal_filename: string;
  accompaniment_filename: string;
  vocal_size: number;
  accompaniment_size: number;
  vocal_info?: AudioInfo | null;
  accompaniment_info?: AudioInfo | null;
  message?: string;
}

export interface DetectAudioResponse {
  task_id: string;
  status: string;
  cached?: boolean;
  detection_result?: BackendDetectionResult;
}

export interface DualRepairResponse {
  task_id: string;
  status: string;
}

export interface DualRepairFromHashResponse {
  task_id: string;
  vocal_task_id: string;
  accompaniment_task_id: string;
  status: string;
}

export interface QueueStatus {
  total_tasks: number;
  pending: number;
  detecting: number;
  repairing: number;
  completed: number;
  error: number;
  timeout: number;
  running_tasks: Array<{
    task_id: string;
    status: string;
    step: string;
    progress: number;
    elapsed_seconds: number;
  }>;
}

export interface RepairCacheLookupResult {
  found: boolean;
  task_id?: string;
  output_path?: string;
  output_size?: number;
  repair_result?: BackendRepairResult;
  detection_result?: BackendDetectionResult;
  repaired_detection_result?: BackendDetectionResult;
}

export interface DualRepairCacheLookupResult {
  found: boolean;
  task_id?: string;
  output_path?: string;
  output_size?: number;
  repair_result?: BackendRepairResult;
  detection_result?: BackendDetectionResult;
  repaired_detection_result?: BackendDetectionResult;
}

export interface PollCallbacks {
  onProgress: (event: ProgressEvent) => void;
  onError?: (error: Error) => void;
  onComplete?: (event: ProgressEvent) => void;
  onStuck?: (info: { taskId: string; lastProgress: number; lastStep: string; duration: number }) => void;
  onUnstuck?: () => void;
  onQueueUpdate?: (queueStatus: QueueStatus) => void;
}

export interface RenderCacheEntry {
  sample_rate: number;
  bit_depth: number;
  filename: string;
  size: number;
  mtime: string;
  algorithm_version: string;
  is_merged?: boolean;
  track_type?: string;
}

export interface WSProgressControl {
  close: () => void;
}

export interface CacheUpdateEvent {
  type: 'render_cache_updated';
  task_id: string;
  files: Array<{
    filename: string;
    sample_rate: number;
    bit_depth: number;
    track_type: string;
  }>;
}

export interface MemoryInfoResult {
  available_memory_bytes: number | null;
  total_memory_bytes: number | null;
  used_memory_bytes: number | null;
  estimated_memory_bytes: number;
  is_sufficient: boolean;
  working_sr: number;
  use_float32: boolean;
  has_streaming: boolean;
  memory_saving: number;
}

export interface FileInfoResult {
  sample_rate: number;
  channels: number;
  duration: number;
}

export interface StorageEstimateResult {
  estimated_output_bytes: number;
  estimated_output_mb: number;
  available_disk_bytes: number | null;
  total_disk_bytes: number | null;
  used_disk_bytes: number | null;
  is_sufficient: boolean;
}

export interface RenderResult {
  task_id: string;
  status: string;
  render_filename?: string;
  render_result?: {
    original_sample_rate: number;
    output_sample_rate: number;
    output_bit_depth: number;
    duration: number;
    channels: number;
  };
}

export interface AudioFileInfo {
  file_id: string;
  filename: string;
  size: number;
  type: string;
  modified_at: number;
}

export interface DeliveryFile {
  filename: string;
  size: number;
  mtime: string;
  task_id?: string;
  track_type?: string;
  is_parent: boolean;
  parent_filename?: string;
  children?: DeliveryFile[];
}

export interface DeliveryFilesResponse {
  files: DeliveryFile[];
}

export const ALGORITHM_VERSIONS = [
  { id: 'v3.1', label: 'v3.1 (桌面增强)', description: 'AI人声修复增强 + 人声效果器' },
  { id: 'v3.1a', label: 'v3.1a (移动增强)', description: '精简版人声效果器' },
  { id: 'v3.2', label: 'v3.2 (桌面智能)', description: '智能压缩+自适应AI修复+瞬态感知+共振抑制+自适应母带' },
  { id: 'v3.2+', label: 'v3.2+ (精修)', description: '前视压缩+双分辨率AI修复+增强空间感+两遍处理' },
  { id: 'v3.2a', label: 'v3.2a (移动)', description: '移动版智能压缩+自适应AI修复+瞬态感知+共振抑制' },
  { id: 'v3.2a+', label: 'v3.2a+ (增强)', description: '移动增强版前视压缩+全分辨率AI修复+两遍处理' },
];

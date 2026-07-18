import { ProcessingOptions } from '../../services/backendApi';

export interface DualTrackAudioInfo {
  sample_rate: number;
  channels: number;
  duration: number;
}

export const sampleRateOptions = [
  { value: 44100, label: '44.1k', recommended: false },
  { value: 48000, label: '48k', recommended: true },
  { value: 96000, label: '96k', recommended: false },
];

export const bitDepthOptions: { value: 16 | 24 | 32; label: string; recommended?: boolean }[] = [
  { value: 16, label: '16bit', recommended: false },
  { value: 24, label: '24bit', recommended: true },
  { value: 32, label: '32bit', recommended: false },
];

export const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

export const WARNING_THRESHOLD_MB = 186;

export function estimateFileSize(
  duration: number,
  sampleRate: number,
  bitDepth: number,
  channels: number
): { size: number; sizeMiB: number; sizeMB: number } {
  const bytes = sampleRate * duration * (bitDepth / 8) * channels;
  const totalBytes = bytes + 44;
  const sizeMiB = totalBytes / (1024 * 1024);
  const sizeMB = totalBytes / (1000 * 1000);
  const size = isMobile ? sizeMB : sizeMiB;
  return { size, sizeMiB, sizeMB };
}

export function isRecommendedCombo(sampleRate: number, bitDepth: number): boolean {
  return sampleRate === 48000 && bitDepth === 24;
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024 / 1024).toFixed(2)} TB`;
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

export function getEffectiveMasteringStyle(style: ProcessingOptions['masteringStyle']): 'standard' | 'powerful' | 'warm' {
  if (style === 'adaptive') return 'standard';
  return (style || 'standard') as 'standard' | 'powerful' | 'warm';
}

export const masteringStyleOptions = [
  { value: 'standard' as const, label: '标准母带', recommended: true },
  { value: 'powerful' as const, label: '强力母带' },
  { value: 'warm' as const, label: '温暖母带' },
];

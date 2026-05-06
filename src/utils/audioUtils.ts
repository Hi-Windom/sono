export interface AudioEffectParams {
  noiseReduction: number;
  bass: number;
  mid: number;
  treble: number;
  compression: number;
  normalize: number;
}

export const defaultEffectParams: AudioEffectParams = {
  noiseReduction: 0,
  bass: 0,
  mid: 0,
  treble: 0,
  compression: 0,
  normalize: 0,
};

export function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

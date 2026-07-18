import { describe, it, expect } from 'vitest';
import { formatTime, formatFileSize, defaultEffectParams } from '../utils/audioUtils';

describe('audioUtils', () => {
  describe('formatTime', () => {
    it('should format 0 seconds correctly', () => {
      expect(formatTime(0)).toBe('00:00');
    });

    it('should format less than 60 seconds correctly', () => {
      expect(formatTime(5)).toBe('00:05');
      expect(formatTime(30)).toBe('00:30');
      expect(formatTime(59)).toBe('00:59');
    });

    it('should format minutes and seconds correctly', () => {
      expect(formatTime(60)).toBe('01:00');
      expect(formatTime(90)).toBe('01:30');
      expect(formatTime(125)).toBe('02:05');
    });

    it('should pad single digit numbers with leading zero', () => {
      expect(formatTime(3)).toBe('00:03');
      expect(formatTime(62)).toBe('01:02');
    });

    it('should handle large values correctly', () => {
      expect(formatTime(3600)).toBe('60:00');
      expect(formatTime(3661)).toBe('61:01');
    });

    it('should floor the seconds', () => {
      expect(formatTime(1.5)).toBe('00:01');
      expect(formatTime(60.9)).toBe('01:00');
    });
  });

  describe('formatFileSize', () => {
    it('should format bytes correctly', () => {
      expect(formatFileSize(0)).toBe('0 B');
      expect(formatFileSize(500)).toBe('500 B');
      expect(formatFileSize(1023)).toBe('1023 B');
    });

    it('should format kilobytes correctly', () => {
      expect(formatFileSize(1024)).toBe('1.0 KB');
      expect(formatFileSize(1536)).toBe('1.5 KB');
      expect(formatFileSize(1024 * 100)).toBe('100.0 KB');
    });

    it('should format megabytes correctly', () => {
      expect(formatFileSize(1024 * 1024)).toBe('1.0 MB');
      expect(formatFileSize(1024 * 1024 * 5.5)).toBe('5.5 MB');
      expect(formatFileSize(1024 * 1024 * 100)).toBe('100.0 MB');
    });

    it('should have one decimal place for KB and MB', () => {
      expect(formatFileSize(1500)).toBe('1.5 KB');
      expect(formatFileSize(1024 * 1024 * 2.2)).toMatch(/^2\.2 MB$/);
    });
  });

  describe('defaultEffectParams', () => {
    it('should have all required fields with zero values', () => {
      expect(defaultEffectParams.noiseReduction).toBe(0);
      expect(defaultEffectParams.bass).toBe(0);
      expect(defaultEffectParams.mid).toBe(0);
      expect(defaultEffectParams.treble).toBe(0);
      expect(defaultEffectParams.compression).toBe(0);
      expect(defaultEffectParams.normalize).toBe(0);
    });
  });
});

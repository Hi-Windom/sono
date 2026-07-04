// @vitest-environment node
import { describe, it, expect } from 'vitest';
import { stripAudioExtension, deriveExportFilename } from '../components/DownloadModal';

describe('DownloadModal 文件名统一（Bug1 回归）', () => {
  describe('stripAudioExtension', () => {
    it('去除 .wav 后缀', () => {
      expect(stripAudioExtension('song_repaired.wav')).toBe('song_repaired');
    });

    it('去除任意单一后缀（.mp3/.m4a）', () => {
      expect(stripAudioExtension('song.mp3')).toBe('song');
      expect(stripAudioExtension('song.m4a')).toBe('song');
    });

    it('仅去除最后一个后缀，保留中间点', () => {
      expect(stripAudioExtension('v1.2_song.wav')).toBe('v1.2_song');
    });

    it('处理双轨带前缀的文件名', () => {
      expect(stripAudioExtension('【合并_】song_repaired.wav')).toBe('【合并_】song_repaired');
      expect(stripAudioExtension('song_人声.wav')).toBe('song_人声');
      expect(stripAudioExtension('song_伴奏.wav')).toBe('song_伴奏');
    });

    it('无后缀时原样返回', () => {
      expect(stripAudioExtension('audio')).toBe('audio');
    });

    it('空值/未定义回退为 audio', () => {
      expect(stripAudioExtension('')).toBe('audio');
      expect(stripAudioExtension(null)).toBe('audio');
      expect(stripAudioExtension(undefined)).toBe('audio');
    });
  });

  describe('deriveExportFilename', () => {
    it('MP3 使用展示名（不含后缀）+ .mp3', () => {
      expect(deriveExportFilename('song_repaired.wav', 'mp3')).toBe('song_repaired.mp3');
    });

    it('M4A 使用展示名（不含后缀）+ .m4a', () => {
      expect(deriveExportFilename('song_repaired.wav', 'm4a')).toBe('song_repaired.m4a');
    });

    it('与 WAV 展示名保持一致的基础名（不含后缀）', () => {
      const wavName = 'song_repaired.wav';
      expect(stripAudioExtension(wavName)).toBe(stripAudioExtension(wavName));
      expect(deriveExportFilename(wavName, 'mp3')).toBe(`${stripAudioExtension(wavName)}.mp3`);
      expect(deriveExportFilename(wavName, 'm4a')).toBe(`${stripAudioExtension(wavName)}.m4a`);
    });

    it('双轨合并轨命名一致', () => {
      const merged = '【合并_】song_repaired.wav';
      expect(deriveExportFilename(merged, 'mp3')).toBe('【合并_】song_repaired.mp3');
      expect(deriveExportFilename(merged, 'm4a')).toBe('【合并_】song_repaired.m4a');
    });

    it('空展示名回退为 audio.<ext>', () => {
      expect(deriveExportFilename('', 'mp3')).toBe('audio.mp3');
      expect(deriveExportFilename(undefined, 'm4a')).toBe('audio.m4a');
    });
  });
});

import { describe, it, expect } from 'vitest';
import { parseWavHeader, parseWavHeaderFull, decodeWavPcm, WavInfo } from '../utils/wavParser';

function createWavBuffer(
  sampleRate: number = 44100,
  bitDepth: number = 16,
  channels: number = 1,
  duration: number = 0.1
): ArrayBuffer {
  const numSamples = Math.floor(sampleRate * duration);
  const bytesPerSample = bitDepth / 8;
  const dataSize = numSamples * channels * bytesPerSample;
  const bufferSize = 44 + dataSize;
  const buffer = new ArrayBuffer(bufferSize);
  const view = new DataView(buffer);

  view.setUint8(0, 0x52); view.setUint8(1, 0x49); view.setUint8(2, 0x46); view.setUint8(3, 0x46);
  view.setUint32(4, 36 + dataSize, true);
  view.setUint8(8, 0x57); view.setUint8(9, 0x41); view.setUint8(10, 0x56); view.setUint8(11, 0x45);

  view.setUint8(12, 0x66); view.setUint8(13, 0x6d); view.setUint8(14, 0x74); view.setUint8(15, 0x20);
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * channels * bytesPerSample, true);
  view.setUint16(32, channels * bytesPerSample, true);
  view.setUint16(34, bitDepth, true);

  view.setUint8(36, 0x64); view.setUint8(37, 0x61); view.setUint8(38, 0x74); view.setUint8(39, 0x61);
  view.setUint32(40, dataSize, true);

  return buffer;
}

function createInvalidWavBuffer(): ArrayBuffer {
  return new ArrayBuffer(10);
}

describe('wavParser', () => {
  describe('parseWavHeader', () => {
    it('should parse valid 16-bit mono WAV header', () => {
      const buffer = createWavBuffer(44100, 16, 1, 0.1);
      const result = parseWavHeader(buffer);
      expect(result).not.toBeNull();
      expect(result?.sampleRate).toBe(44100);
      expect(result?.bitDepth).toBe(16);
      expect(result?.channels).toBe(1);
      expect(result?.duration).toBeCloseTo(0.1, 2);
    });

    it('should parse valid 24-bit stereo WAV header', () => {
      const buffer = createWavBuffer(48000, 24, 2, 0.5);
      const result = parseWavHeader(buffer);
      expect(result).not.toBeNull();
      expect(result?.sampleRate).toBe(48000);
      expect(result?.bitDepth).toBe(24);
      expect(result?.channels).toBe(2);
      expect(result?.duration).toBeCloseTo(0.5, 2);
    });

    it('should parse valid 32-bit WAV header', () => {
      const buffer = createWavBuffer(96000, 32, 1, 0.2);
      const result = parseWavHeader(buffer);
      expect(result).not.toBeNull();
      expect(result?.sampleRate).toBe(96000);
      expect(result?.bitDepth).toBe(32);
      expect(result?.channels).toBe(1);
    });

    it('should parse valid 8-bit WAV header', () => {
      const buffer = createWavBuffer(22050, 8, 1, 0.3);
      const result = parseWavHeader(buffer);
      expect(result).not.toBeNull();
      expect(result?.sampleRate).toBe(22050);
      expect(result?.bitDepth).toBe(8);
    });

    it('should return null for invalid buffer', () => {
      const buffer = createInvalidWavBuffer();
      const result = parseWavHeader(buffer);
      expect(result).toBeNull();
    });

    it('should return null for non-WAV buffer', () => {
      const buffer = new ArrayBuffer(100);
      const view = new Uint8Array(buffer);
      view[0] = 0x41; view[1] = 0x42; view[2] = 0x43; view[3] = 0x44;
      const result = parseWavHeader(buffer);
      expect(result).toBeNull();
    });
  });

  describe('parseWavHeaderFull', () => {
    it('should return full parse result with data offset and size', () => {
      const buffer = createWavBuffer(44100, 16, 1, 0.1);
      const result = parseWavHeaderFull(buffer);
      expect(result).not.toBeNull();
      expect(result?.info).toBeDefined();
      expect(result?.dataOffset).toBeGreaterThan(0);
      expect(result?.dataSize).toBeGreaterThan(0);
    });

    it('should have data offset pointing to actual data', () => {
      const buffer = createWavBuffer(44100, 16, 1, 0.1);
      const result = parseWavHeaderFull(buffer);
      expect(result).not.toBeNull();
      expect(result?.dataOffset).toBe(44);
    });
  });

  describe('decodeWavPcm', () => {
    it('should decode 16-bit mono WAV to AudioBuffer', () => {
      const buffer = createWavBuffer(44100, 16, 1, 0.01);
      const mockAudioContext = {
        createBuffer: (channels: number, length: number, sampleRate: number) => {
          const buf = {
            numberOfChannels: channels,
            length,
            sampleRate,
            copyToChannel: (data: Float32Array, channel: number) => {},
            getChannelData: (channel: number) => new Float32Array(length),
          };
          return buf as unknown as AudioBuffer;
        },
      } as unknown as BaseAudioContext;

      const result = decodeWavPcm(mockAudioContext, buffer);
      expect(result).not.toBeNull();
      expect(result?.sampleRate).toBe(44100);
      expect(result?.numberOfChannels).toBe(1);
    });

    it('should decode 16-bit stereo WAV', () => {
      const buffer = createWavBuffer(48000, 16, 2, 0.01);
      const mockAudioContext = {
        createBuffer: (channels: number, length: number, sampleRate: number) => {
          const channelData: Float32Array[] = [];
          const buf = {
            numberOfChannels: channels,
            length,
            sampleRate,
            copyToChannel: (data: Float32Array, channel: number) => {
              channelData[channel] = data;
            },
            getChannelData: (channel: number) => channelData[channel] || new Float32Array(length),
          };
          return buf as unknown as AudioBuffer;
        },
      } as unknown as BaseAudioContext;

      const result = decodeWavPcm(mockAudioContext, buffer);
      expect(result).not.toBeNull();
      expect(result?.numberOfChannels).toBe(2);
    });

    it('should return null for invalid WAV', () => {
      const buffer = createInvalidWavBuffer();
      const mockAudioContext = {} as unknown as BaseAudioContext;
      const result = decodeWavPcm(mockAudioContext, buffer);
      expect(result).toBeNull();
    });
  });
});

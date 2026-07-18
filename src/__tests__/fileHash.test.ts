import { describe, it, expect, beforeEach } from 'vitest';
import { computeFileHash } from '../utils/fileHash';

let digestCalls: { algorithm: string; data: Uint8Array }[] = [];

Object.defineProperty(globalThis, 'crypto', {
  value: {
    subtle: {
      digest: async (algorithm: string, data: BufferSource) => {
        const buffer = data as ArrayBuffer;
        const view = new Uint8Array(buffer);
        digestCalls.push({ algorithm, data: new Uint8Array(view) });
        const hash = new Uint8Array(32);
        for (let i = 0; i < 32; i++) {
          hash[i] = view[i % view.length] ^ (i * 7);
        }
        return hash.buffer;
      },
    },
  },
  writable: true,
});

describe('fileHash', () => {
  beforeEach(() => {
    digestCalls = [];
  });

  it('should compute hash for small file (less than 2MB)', async () => {
    const smallData = new Uint8Array(1024 * 500);
    for (let i = 0; i < smallData.length; i++) {
      smallData[i] = i % 256;
    }
    const file = new File([smallData], 'small.wav', { type: 'audio/wav' });
    
    const hash = await computeFileHash(file);
    
    expect(typeof hash).toBe('string');
    expect(hash.length).toBe(64);
    expect(/^[a-f0-9]+$/.test(hash)).toBe(true);
    expect(digestCalls.length).toBe(1);
  });

  it('should compute hash for large file (more than 2MB)', async () => {
    const largeSize = 1024 * 1024 * 5;
    const largeData = new Uint8Array(largeSize);
    for (let i = 0; i < largeData.length; i++) {
      largeData[i] = i % 256;
    }
    const file = new File([largeData], 'large.wav', { type: 'audio/wav' });
    
    const hash = await computeFileHash(file);
    
    expect(typeof hash).toBe('string');
    expect(hash.length).toBe(64);
    expect(/^[a-f0-9]+$/.test(hash)).toBe(true);
    expect(digestCalls.length).toBe(1);
  });

  it('should return consistent hash for same file content', async () => {
    const data = new Uint8Array(1024 * 100);
    for (let i = 0; i < data.length; i++) {
      data[i] = i % 256;
    }
    const file1 = new File([data], 'test1.wav', { type: 'audio/wav' });
    const file2 = new File([data], 'test2.wav', { type: 'audio/wav' });
    
    const hash1 = await computeFileHash(file1);
    const hash2 = await computeFileHash(file2);
    
    expect(hash1).toBe(hash2);
  });

  it('should return different hash for different file content', async () => {
    const data1 = new Uint8Array(1024 * 100);
    const data2 = new Uint8Array(1024 * 100);
    for (let i = 0; i < data1.length; i++) {
      data1[i] = i % 256;
      data2[i] = (i + 1) % 256;
    }
    const file1 = new File([data1], 'file1.wav', { type: 'audio/wav' });
    const file2 = new File([data2], 'file2.wav', { type: 'audio/wav' });
    
    const hash1 = await computeFileHash(file1);
    const hash2 = await computeFileHash(file2);
    
    expect(hash1).not.toBe(hash2);
  });

  it('should use head+tail+size for large files', async () => {
    const CHUNK_SIZE = 1024 * 1024;
    const largeSize = CHUNK_SIZE * 3;
    const data = new Uint8Array(largeSize);
    for (let i = 0; i < data.length; i++) {
      data[i] = i % 256;
    }
    
    const file = new File([data], 'large.wav', { type: 'audio/wav' });
    await computeFileHash(file);
    
    expect(digestCalls.length).toBe(1);
    const hashedData = digestCalls[0].data;
    expect(hashedData.length).toBe(CHUNK_SIZE * 2 + 8);
  });

  it('should use full file for small files', async () => {
    const smallSize = 1024 * 500;
    const data = new Uint8Array(smallSize);
    for (let i = 0; i < data.length; i++) {
      data[i] = i % 256;
    }
    
    const file = new File([data], 'small.wav', { type: 'audio/wav' });
    await computeFileHash(file);
    
    expect(digestCalls.length).toBe(1);
    const hashedData = digestCalls[0].data;
    expect(hashedData.length).toBe(smallSize);
  });
});

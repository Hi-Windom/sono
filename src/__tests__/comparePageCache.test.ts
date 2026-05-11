import { describe, it, expect, beforeEach } from 'vitest';
import { audioBufferCache, getCachedBuffer, setCachedBuffer } from '../pages/ComparePage';

describe('ComparePage audioBufferCache', () => {
  beforeEach(() => {
    audioBufferCache.clear();
  });

  it('getCachedBuffer returns null for uncached key', () => {
    expect(getCachedBuffer('task-1', 'original')).toBeNull();
    expect(getCachedBuffer('task-1', 'repaired')).toBeNull();
  });

  it('setCachedBuffer + getCachedBuffer round-trip', () => {
    const mockBuffer = { duration: 10, sampleRate: 44100, numberOfChannels: 2 } as unknown as AudioBuffer;
    setCachedBuffer('task-1', 'original', mockBuffer);

    const result = getCachedBuffer('task-1', 'original');
    expect(result).toBe(mockBuffer);
  });

  it('different types are cached independently', () => {
    const buf1 = { duration: 10 } as unknown as AudioBuffer;
    const buf2 = { duration: 20 } as unknown as AudioBuffer;
    setCachedBuffer('task-1', 'original', buf1);
    setCachedBuffer('task-1', 'repaired', buf2);

    expect(getCachedBuffer('task-1', 'original')).toBe(buf1);
    expect(getCachedBuffer('task-1', 'repaired')).toBe(buf2);
  });

  it('different taskIds are cached independently', () => {
    const buf1 = { duration: 10 } as unknown as AudioBuffer;
    const buf2 = { duration: 20 } as unknown as AudioBuffer;
    setCachedBuffer('task-1', 'original', buf1);
    setCachedBuffer('task-2', 'original', buf2);

    expect(getCachedBuffer('task-1', 'original')).toBe(buf1);
    expect(getCachedBuffer('task-2', 'original')).toBe(buf2);
  });

  it('expired cache entries return null', () => {
    const mockBuffer = { duration: 10 } as unknown as AudioBuffer;
    setCachedBuffer('task-1', 'original', mockBuffer);

    const key = 'task-1:original';
    const entry = audioBufferCache.get(key);
    expect(entry).not.toBeNull();
    if (entry) {
      entry.timestamp = Date.now() - 31 * 60 * 1000;
    }

    expect(getCachedBuffer('task-1', 'original')).toBeNull();
  });

  it('cache entry is removed after TTL expiry', () => {
    const mockBuffer = { duration: 10 } as unknown as AudioBuffer;
    setCachedBuffer('task-1', 'original', mockBuffer);

    const key = 'task-1:original';
    const entry = audioBufferCache.get(key);
    if (entry) {
      entry.timestamp = Date.now() - 31 * 60 * 1000;
    }

    getCachedBuffer('task-1', 'original');
    expect(audioBufferCache.has(key)).toBe(false);
  });

  it('re-setting a cache entry updates timestamp', () => {
    const buf1 = { duration: 10 } as unknown as AudioBuffer;
    const buf2 = { duration: 20 } as unknown as AudioBuffer;
    setCachedBuffer('task-1', 'original', buf1);

    const key = 'task-1:original';
    const ts1 = audioBufferCache.get(key)!.timestamp;

    setCachedBuffer('task-1', 'original', buf2);
    const ts2 = audioBufferCache.get(key)!.timestamp;

    expect(ts2).toBeGreaterThanOrEqual(ts1);
    expect(getCachedBuffer('task-1', 'original')).toBe(buf2);
  });

  it('clearing cache removes all entries', () => {
    setCachedBuffer('task-1', 'original', { duration: 10 } as unknown as AudioBuffer);
    setCachedBuffer('task-1', 'repaired', { duration: 10 } as unknown as AudioBuffer);
    setCachedBuffer('task-2', 'original', { duration: 10 } as unknown as AudioBuffer);

    audioBufferCache.clear();

    expect(getCachedBuffer('task-1', 'original')).toBeNull();
    expect(getCachedBuffer('task-1', 'repaired')).toBeNull();
    expect(getCachedBuffer('task-2', 'original')).toBeNull();
  });
});

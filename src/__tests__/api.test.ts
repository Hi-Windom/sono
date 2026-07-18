// @vitest-environment node
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { checkBackendHealth, fetchAlgorithmVersions, fetchMemoryInfo } from '../services/api/system';
import { checkFileHash } from '../services/api/upload';

vi.mock('../services/api/_shared', () => ({
  API_BASE: '/api/v1',
  HEALTH_URL: '/health',
  CHUNK_SIZE: 1024 * 1024,
  log: vi.fn(),
}));

describe('API System Functions', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('checkBackendHealth', () => {
    it('should return true when health endpoint returns 200', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
      });

      const result = await checkBackendHealth();
      expect(result).toBe(true);
      expect(fetch).toHaveBeenCalledWith('/health', expect.any(Object));
    });

    it('should return false when health endpoint returns 500', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
      });

      const result = await checkBackendHealth();
      expect(result).toBe(false);
    });

    it('should return false when fetch throws', async () => {
      global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

      const result = await checkBackendHealth();
      expect(result).toBe(false);
    });
  });

  describe('fetchAlgorithmVersions', () => {
    it('should return algorithm versions on success', async () => {
      const mockVersions = [
        { version: 'v2.4a', name: 'v2.4a' },
        { version: 'v3.1a', name: 'v3.1a' },
      ];
      
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ versions: mockVersions }),
      });

      const result = await fetchAlgorithmVersions();
      expect(result).toEqual(mockVersions);
    });

    it('should return empty array on HTTP error', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
      });

      const result = await fetchAlgorithmVersions();
      expect(result).toEqual([]);
    });

    it('should return empty array on fetch error', async () => {
      global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

      const result = await fetchAlgorithmVersions();
      expect(result).toEqual([]);
    });

    it('should return empty array when versions field is missing', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({}),
      });

      const result = await fetchAlgorithmVersions();
      expect(result).toEqual([]);
    });
  });

  describe('fetchMemoryInfo', () => {
    it('should return memory info on success', async () => {
      const mockInfo = {
        estimated_memory_bytes: 1024 * 1024 * 100,
        is_sufficient: true,
        working_sr: 48000,
        use_float32: false,
        has_streaming: true,
      };
      
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockInfo,
      });

      const result = await fetchMemoryInfo(60, 2, 44100, 'v2.4a');
      expect(result).toEqual(mockInfo);
      expect(fetch).toHaveBeenCalledWith(
        '/api/v1/memory/info',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        })
      );
    });

    it('should return null on HTTP error', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
      });

      const result = await fetchMemoryInfo(60, 2, 44100, 'v2.4a');
      expect(result).toBeNull();
    });

    it('should return null on fetch error', async () => {
      global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

      const result = await fetchMemoryInfo(60, 2, 44100, 'v2.4a');
      expect(result).toBeNull();
    });
  });
});

describe('API Upload Functions', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('checkFileHash', () => {
    it('should return exists=true when hash exists', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ exists: true, task_id: 'task-123', filename: 'test.wav' }),
      });

      const result = await checkFileHash('abc123');
      expect(result.exists).toBe(true);
      expect(result.task_id).toBe('task-123');
      expect(result.filename).toBe('test.wav');
    });

    it('should return exists=false when hash does not exist', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ exists: false }),
      });

      const result = await checkFileHash('nonexistent');
      expect(result.exists).toBe(false);
    });

    it('should return exists=false on HTTP error', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
      });

      const result = await checkFileHash('abc123');
      expect(result.exists).toBe(false);
    });

    it('should return exists=false on fetch error', async () => {
      global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

      const result = await checkFileHash('abc123');
      expect(result.exists).toBe(false);
    });
  });
});

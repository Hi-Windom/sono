// @vitest-environment node
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { uploadAudio, uploadDualAudio } from '../services/api/upload';

vi.mock('../services/api/_shared', () => ({
  API_BASE: '/api/v1',
  CHUNK_SIZE: 1024 * 1024,
  log: vi.fn(),
}));

class MockXHR {
  static instances: MockXHR[] = [];
  upload: { onprogress: ((e: any) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  status = 200;
  responseText = '';
  timeout = 0;

  constructor() {
    MockXHR.instances.push(this);
  }

  open(_method: string, _url: string) {}
  send(_data: any) {}
}

describe('Upload Progress Tests', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    MockXHR.instances = [];
    (global as any).XMLHttpRequest = MockXHR;
  });

  describe('uploadAudio - simple upload (small file)', () => {
    it('should call onProgress with speed parameter', async () => {
      const mockFile = new File(['x'.repeat(100 * 1024)], 'test.wav', { type: 'audio/wav' });
      const progressCalls: Array<{ loaded: number; total: number; speed: number }> = [];

      const promise = uploadAudio(
        mockFile,
        (loaded, total, speed) => {
          progressCalls.push({ loaded, total, speed });
        }
      );

      await new Promise(r => setTimeout(r, 10));
      expect(MockXHR.instances.length).toBe(1);

      const xhr = MockXHR.instances[0];
      xhr.upload.onprogress?.({
        lengthComputable: true,
        loaded: 50 * 1024,
        total: 100 * 1024,
      });

      xhr.responseText = JSON.stringify({ task_id: 'task-123', filename: 'test.wav', size: 102400 });
      xhr.onload?.();

      await promise;

      expect(progressCalls.length).toBeGreaterThan(0);
      const lastCall = progressCalls[progressCalls.length - 1];
      expect(lastCall.loaded).toBe(50 * 1024);
      expect(lastCall.total).toBe(100 * 1024);
      expect(typeof lastCall.speed).toBe('number');
      expect(lastCall.speed).toBeGreaterThanOrEqual(0);
    });

    it('should return cached result when file hash exists', async () => {
      const mockFile = new File(['x'.repeat(100 * 1024)], 'test.wav', { type: 'audio/wav' });
      const onProgress = vi.fn();

      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => ({ exists: true, task_id: 'cached-task-456', filename: 'test.wav' }),
      });

      const result = await uploadAudio(mockFile, onProgress, 'hash123');

      expect(result.cached).toBe(true);
      expect(result.task_id).toBe('cached-task-456');
      expect(onProgress).not.toHaveBeenCalled();
    });
  });

  describe('uploadAudio - chunked upload (large file)', () => {
    it('should report progress incrementally per chunk with real speed', async () => {
      const chunkSize = 1024 * 1024;
      const totalSize = chunkSize * 3;
      const mockFile = new File(['x'.repeat(totalSize)], 'large.wav', { type: 'audio/wav' });
      const progressCalls: Array<{ loaded: number; total: number; speed: number }> = [];

      global.fetch = vi.fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ session_id: 'sess-123' }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ uploaded_chunks: [] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ success: true, task_id: 'chunked-task-789' }),
        });

      const promise = uploadAudio(
        mockFile,
        (loaded, total, speed) => {
          progressCalls.push({ loaded, total, speed });
        }
      );

      await new Promise(r => setTimeout(r, 50));

      for (let i = 0; i < 3; i++) {
        const xhr = MockXHR.instances[i];
        if (!xhr) break;

        xhr.upload.onprogress?.({
          lengthComputable: true,
          loaded: chunkSize * 0.5,
          total: chunkSize,
        });
        xhr.upload.onprogress?.({
          lengthComputable: true,
          loaded: chunkSize,
          total: chunkSize,
        });

        xhr.responseText = JSON.stringify({ success: true });
        xhr.onload?.();

        await new Promise(r => setTimeout(r, 20));
      }

      const allCalls = (global.fetch as any).mock.calls;
      const finalizeCall = allCalls.find((c: any) => c[0].includes('upload-finalize'));
      expect(finalizeCall).toBeDefined();

      expect(progressCalls.length).toBeGreaterThan(3);

      const speeds = progressCalls.map(c => c.speed);
      const nonZeroSpeeds = speeds.filter(s => s > 0);
      expect(nonZeroSpeeds.length).toBeGreaterThan(0);

      progressCalls.forEach((call, idx) => {
        expect(call.total).toBe(totalSize);
        expect(call.loaded).toBeGreaterThanOrEqual(0);
        expect(call.loaded).toBeLessThanOrEqual(totalSize);
        expect(typeof call.speed).toBe('number');
        if (idx > 0) {
          expect(call.loaded).toBeGreaterThanOrEqual(progressCalls[idx - 1].loaded);
        }
      });
    });
  });

  describe('uploadDualAudio - total progress calculation', () => {
    it('should report combined progress for both files', async () => {
      const vocalFile = new File(['v'.repeat(50 * 1024)], 'vocal.wav', { type: 'audio/wav' });
      const accFile = new File(['a'.repeat(50 * 1024)], 'acc.wav', { type: 'audio/wav' });
      const totalSize = 100 * 1024;
      const progressCalls: Array<{ loaded: number; total: number; speed: number; type: string }> = [];

      const promise = uploadDualAudio(
        vocalFile,
        accFile,
        (loaded, total, speed, type) => {
          progressCalls.push({ loaded, total, speed, type });
        }
      );

      await new Promise(r => setTimeout(r, 20));
      expect(MockXHR.instances.length).toBeGreaterThanOrEqual(1);

      if (MockXHR.instances[0]) {
        MockXHR.instances[0].upload.onprogress?.({
          lengthComputable: true,
          loaded: 25 * 1024,
          total: 50 * 1024,
        });
        MockXHR.instances[0].responseText = JSON.stringify({ task_id: 'vocal-task', filename: 'vocal.wav', size: 51200 });
        MockXHR.instances[0].onload?.();
      }

      await new Promise(r => setTimeout(r, 20));

      if (MockXHR.instances[1]) {
        MockXHR.instances[1].upload.onprogress?.({
          lengthComputable: true,
          loaded: 25 * 1024,
          total: 50 * 1024,
        });
        MockXHR.instances[1].responseText = JSON.stringify({ task_id: 'acc-task', filename: 'acc.wav', size: 51200 });
        MockXHR.instances[1].onload?.();
      }

      await promise;

      expect(progressCalls.length).toBeGreaterThanOrEqual(2);

      progressCalls.forEach(call => {
        expect(call.total).toBe(totalSize);
        expect(call.loaded).toBeGreaterThanOrEqual(0);
        expect(call.loaded).toBeLessThanOrEqual(totalSize);
        expect(typeof call.speed).toBe('number');
        expect(call.type === 'vocal' || call.type === 'accompaniment').toBe(true);
      });

      const vocalCalls = progressCalls.filter(c => c.type === 'vocal');
      const accCalls = progressCalls.filter(c => c.type === 'accompaniment');
      expect(vocalCalls.length).toBeGreaterThan(0);
      expect(accCalls.length).toBeGreaterThan(0);

      const firstVocalCall = vocalCalls[0];
      expect(firstVocalCall.loaded).toBe(25 * 1024);

      const firstAccCall = accCalls[0];
      expect(firstAccCall.loaded).toBe(75 * 1024);
    });
  });
});

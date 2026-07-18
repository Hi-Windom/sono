import { API_BASE, HEALTH_URL, log } from './_shared';
import type {
  AlgorithmVersion,
  DetectorVersion,
  MemoryInfoResult,
  FileInfoResult,
  StorageEstimateResult,
  QueueStatus,
  TaskStatus,
} from './types';

export async function checkBackendHealth(): Promise<boolean> {
  log('health', `GET ${HEALTH_URL}`);
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    const res = await fetch(HEALTH_URL, { signal: controller.signal });
    clearTimeout(timeoutId);
    log('health', `response status=${res.status} ok=${res.ok}`);
    return res.ok;
  } catch (e) {
    log('health', `FAILED: ${e instanceof Error ? e.message : String(e)}`);
    return false;
  }
}

export async function fetchAlgorithmVersions(): Promise<AlgorithmVersion[]> {
  try {
    const res = await fetch(`${API_BASE}/algorithm-versions`, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) {
      console.warn(`[fetchAlgorithmVersions] HTTP ${res.status}`);
      return [];
    }
    const data = await res.json();
    return data.versions || [];
  } catch (e) {
    console.warn('[fetchAlgorithmVersions] failed:', e);
    return [];
  }
}

export async function fetchDetectorVersions(): Promise<DetectorVersion[]> {
  try {
    const res = await fetch(`${API_BASE}/detector-versions`, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) {
      console.warn(`[fetchDetectorVersions] HTTP ${res.status}`);
      return [];
    }
    const data = await res.json();
    return data.versions || [];
  } catch (e) {
    console.warn('[fetchDetectorVersions] failed:', e);
    return [];
  }
}

export async function fetchMemoryInfo(
  duration: number,
  channels: number,
  sampleRate: number,
  algorithmVersion: string,
): Promise<MemoryInfoResult | null> {
  try {
    const res = await fetch(`${API_BASE}/memory/info`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        duration,
        channels,
        sample_rate: sampleRate,
        algorithm_version: algorithmVersion,
      }),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function fetchStorageEstimate(
  duration: number,
  channels: number,
  sampleRate: number,
  bitDepth: number,
): Promise<StorageEstimateResult | null> {
  try {
    const res = await fetch(`${API_BASE}/storage/estimate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        duration,
        channels,
        sample_rate: sampleRate,
        bit_depth: bitDepth,
      }),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function fetchFileInfoByHash(fileHashes: string[]): Promise<Record<string, FileInfoResult>> {
  const url = `${API_BASE}/file-info-by-hash`;
  log('file-info-by-hash', `POST ${url} hashes=${fileHashes.map(h => h.slice(0, 12)).join(',')}`);
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_hashes: fileHashes }),
    });
    if (!res.ok) {
      log('file-info-by-hash', `ERROR HTTP ${res.status}`);
      return {};
    }
    const data = await res.json();
    log('file-info-by-hash', `result: ${JSON.stringify(data)}`);
    return data;
  } catch (e) {
    log('file-info-by-hash', `FAILED: ${e instanceof Error ? e.message : String(e)}`);
    return {};
  }
}

export async function getQueueStatus(): Promise<QueueStatus | null> {
  try {
    const res = await fetch(`${API_BASE}/queue-status`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function getTrackStatus(taskId: string): Promise<{
  task_id: string;
  status: string;
  progress: number;
  step: string;
  vocal?: { task_id: string; status: string; progress: number };
  accompaniment?: { task_id: string; status: string; progress: number };
}> {
  const url = `${API_BASE}/tracks/${taskId}`;

  try {
    const res = await fetch(url);

    if (!res.ok) {
      let detail = `获取轨道状态失败 (HTTP ${res.status})`;
      try {
        const body = await res.json();
        if (body.detail) detail = body.detail;
      } catch {}
      log('track-status', `ERROR: ${detail} url=${url}`);
      throw new Error(detail);
    }

    const data = await res.json();
    log('track-status', `task_id=${taskId} status=${data.status}`);
    return data;
  } catch (e) {
    if (!(e instanceof Error && e.message.includes('HTTP'))) {
      log('track-status', `ERROR: ${e instanceof Error ? e.message : String(e)}`);
    }
    throw e;
  }
}

export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  const url = `${API_BASE}/status/${taskId}`;

  try {
    const res = await fetch(url);

    if (!res.ok) {
      let detail = `获取任务状态失败 (HTTP ${res.status})`;
      try {
        const body = await res.json();
        if (body.detail) detail = body.detail;
      } catch {}
      log('status', `ERROR: ${detail} url=${url}`);
      throw new Error(detail);
    }

    const data = await res.json();
    log('status', `task_id=${taskId} status=${data.status} progress=${data.progress} step=${data.step}`);
    return data;
  } catch (e) {
    if (!(e instanceof Error && e.message.includes('HTTP'))) {
      log('status', `FETCH ERROR: ${e instanceof Error ? e.message : String(e)} url=${url}`);
    }
    throw e;
  }
}

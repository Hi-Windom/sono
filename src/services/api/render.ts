import { API_BASE, log } from './_shared';
import type { RenderResult, RenderCacheEntry, PollCallbacks } from './types';
import { connectProgressWS } from './repair';

export async function renderAudio(
  taskId: string,
  sampleRate: number,
  bitDepth: number,
  masteringStyle?: string,
  algorithmVersion?: string,
  qualityMode?: string,
): Promise<RenderResult> {
  const url = `${API_BASE}/render`;
  log('render', `POST ${url} task_id=${taskId} sr=${sampleRate} bd=${bitDepth} style=${masteringStyle || 'standard'} ver=${algorithmVersion || 'unknown'} quality=${qualityMode || 'standard'}`);
  const body: Record<string, unknown> = {
    task_id: taskId,
    sample_rate: sampleRate,
    bit_depth: bitDepth,
  };
  if (masteringStyle) {
    body.mastering_style = masteringStyle;
  }
  if (algorithmVersion) {
    body.algorithm_version = algorithmVersion;
  }
  if (qualityMode) {
    body.quality_mode = qualityMode;
  }
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `渲染失败 (${res.status})`);
  }
  return await res.json();
}

export async function fetchRenderCache(taskId: string): Promise<RenderCacheEntry[]> {
  try {
    const res = await fetch(`${API_BASE}/render-cache/${taskId}`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) return [];
    const data = await res.json();
    return data.caches || [];
  } catch {
    return [];
  }
}

export function waitRenderWithWS(
  taskId: string,
  onProgress?: (progress: number, step: string) => void,
): { promise: Promise<RenderResult>; close: () => void } {
  let closeFn = () => {};
  const terminals = new Set(['render_completed', 'error', 'completed']);

  const promise = new Promise<RenderResult>((resolve, reject) => {
    const wsControl = connectProgressWS(
      taskId,
      {
        onProgress: (data) => {
          if (onProgress) onProgress(data.progress, data.step || '');
        },
        onComplete: (data) => {
          if (data.status === 'render_completed' || data.status === 'completed') {
            resolve({
              task_id: taskId,
              status: data.status,
              render_filename: data.render_filename,
              render_result: data.render_result,
            });
          } else {
            reject(new Error(data.error || data.step || '渲染失败'));
          }
        },
        onError: (err) => reject(err),
        onStuck: undefined,
        onUnstuck: undefined,
      },
      terminals,
    );
    closeFn = wsControl.close;
  });

  return { promise, close: closeFn };
}

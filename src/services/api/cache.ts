import { API_BASE, log } from './_shared';
import type {
  RepairCacheLookupResult,
  DualRepairCacheLookupResult,
  WSProgressControl,
  CacheUpdateEvent,
} from './types';

export async function lookupRepairCache(fileHash: string, params: Record<string, unknown>): Promise<RepairCacheLookupResult> {
  const url = `${API_BASE}/cache/lookup`;
  log('cache-lookup', `POST ${url} hash=${fileHash}`);
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_hash: fileHash, params }),
    });
    if (!res.ok) {
      log('cache-lookup', `ERROR HTTP ${res.status}`);
      return { found: false };
    }
    const data = await res.json();
    log('cache-lookup', `result: found=${data.found} output_size=${data.output_size || 0}`);
    return data;
  } catch (e) {
    log('cache-lookup', `FAILED: ${e instanceof Error ? e.message : String(e)}`);
    return { found: false };
  }
}

export async function lookupDualRepairCache(
  vocalFileHash: string,
  accompanimentFileHash: string,
  params: Record<string, unknown>,
  vocalParams?: Record<string, unknown>,
  accompanimentParams?: Record<string, unknown>,
  mixRatio?: number
): Promise<DualRepairCacheLookupResult> {
  const url = `${API_BASE}/cache/lookup-dual`;
  log('cache-lookup-dual', `POST ${url} vocal_hash=${vocalFileHash.slice(0, 12)} acc_hash=${accompanimentFileHash.slice(0, 12)}`);
  try {
    const body: Record<string, unknown> = {
      vocal_file_hash: vocalFileHash,
      accompaniment_file_hash: accompanimentFileHash,
      params,
    };
    if (vocalParams !== undefined) body.vocal_params = vocalParams;
    if (accompanimentParams !== undefined) body.accompaniment_params = accompanimentParams;
    if (mixRatio !== undefined) body.mix_ratio = mixRatio;
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      log('cache-lookup-dual', `ERROR HTTP ${res.status}`);
      return { found: false };
    }
    const data = await res.json();
    log('cache-lookup-dual', `result: found=${data.found} output_size=${data.output_size || 0}`);
    return data;
  } catch (e) {
    log('cache-lookup-dual', `FAILED: ${e instanceof Error ? e.message : String(e)}`);
    return { found: false };
  }
}

export function connectCacheWS(
  onCacheUpdate?: (event: CacheUpdateEvent) => void,
): WSProgressControl {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  let wsHost: string;
  const viteApiUrl = import.meta.env.VITE_API_URL;
  if (viteApiUrl && import.meta.env.DEV) {
    try {
      const backendUrl = new URL(viteApiUrl);
      wsHost = backendUrl.host;
    } catch {
      wsHost = window.location.host;
    }
  } else {
    wsHost = window.location.host;
  }
  const wsUrl = `${protocol}//${wsHost}/api/v1/ws/cache-events`;

  let ws: WebSocket | null = null;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 5;
  let closed = false;

  const connect = () => {
    if (closed) return;

    try {
      ws = new WebSocket(wsUrl);
    } catch (e) {
      console.warn(`[CacheWS] 创建连接失败:`, e);
      return;
    }

    const connectTimeout = setTimeout(() => {
      if (ws && ws.readyState === WebSocket.CONNECTING) {
        console.warn(`[CacheWS] 连接超时`);
        ws.close();
      }
    }, 5000);

    ws.onopen = () => {
      clearTimeout(connectTimeout);
      reconnectAttempts = 0;
      console.log(`[CacheWS] 连接成功`);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'render_cache_updated') {
          onCacheUpdate?.(data as CacheUpdateEvent);
        }
      } catch (e) {
        console.warn(`[CacheWS] 消息解析失败:`, e);
      }
    };

    ws.onerror = (e) => {
      clearTimeout(connectTimeout);
      console.warn(`[CacheWS] 连接错误`, e);
    };

    ws.onclose = () => {
      clearTimeout(connectTimeout);
      if (closed) return;

      if (reconnectAttempts < maxReconnectAttempts) {
        reconnectAttempts++;
        const delay = Math.pow(2, reconnectAttempts - 1) * 1000;
        console.log(`[CacheWS] 重连 #${reconnectAttempts} 延迟=${delay}ms`);
        setTimeout(connect, delay);
      } else {
        console.warn(`[CacheWS] 重连耗尽`);
      }
    };
  };

  connect();

  return {
    close: () => {
      closed = true;
      if (ws) {
        ws.close();
        ws = null;
      }
    },
  };
}

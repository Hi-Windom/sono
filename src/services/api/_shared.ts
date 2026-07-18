export const API_BASE = '/api/v1';
export const HEALTH_URL = '/health';
export const CHUNK_SIZE = 5 * 1024 * 1024;

const LOG_ENABLED = true;

export function log(tag: string, ...args: unknown[]) {
  if (!LOG_ENABLED) return;
  const ts = new Date().toISOString().substr(11, 12);
  const msg = `[${ts}][backendApi][${tag}] ${args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ')}`;
  console.log(msg);
}

export const DEFAULT_TERMINAL_STATES = new Set(['completed', 'detected', 'error', 'timeout']);

export interface ApiError {
  code: string;
  message: string;
  detail: string;
  request_id?: string;
}

async function recordPerf(endpoint: string, durationMs: number, success: boolean) {
  try {
    const { perfMonitor } = await import('../../utils/perfMonitor');
    perfMonitor.recordApiCall(endpoint, durationMs, success);
  } catch {
    // ignore
  }
}

export async function apiRequest<T>(
  url: string,
  options: RequestInit = {},
  tag: string = 'request'
): Promise<T> {
  const startTime = performance.now();
  log(tag, `>>> ${options.method || 'GET'} ${url}`);

  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    const elapsed = performance.now() - startTime;
    log(tag, `<<< ${res.status} ${url} (${elapsed.toFixed(1)}ms)`);

    const endpoint = url.replace(API_BASE, '').split('?')[0];
    void recordPerf(endpoint, elapsed, res.ok);

    const requestId = res.headers.get('X-Request-ID');

    if (!res.ok) {
      let errorData: ApiError | null = null;
      try {
        const data = await res.json();
        if (data.error && typeof data.error === 'object') {
          errorData = data.error as ApiError;
        } else if (data.detail) {
          errorData = {
            code: `http_${res.status}`,
            message: typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail),
            detail: '',
            request_id: requestId || undefined,
          };
        }
      } catch {
        // 无法解析 JSON 响应
      }

      const errorMessage = errorData?.message || `HTTP ${res.status}: ${res.statusText}`;
      const errorDetail = errorData?.detail || '';
      const fullMessage = errorDetail ? `${errorMessage} (${errorDetail})` : errorMessage;

      log(tag, `ERROR: ${fullMessage} request_id=${requestId || 'unknown'}`);
      console.error(`[API Error] ${url}:`, {
        status: res.status,
        statusText: res.statusText,
        error: errorData,
        requestId,
      });

      const error = new Error(fullMessage) as Error & { apiError?: ApiError; statusCode?: number };
      error.apiError = errorData || undefined;
      error.statusCode = res.status;
      throw error;
    }

    const data = await res.json();
    return data as T;
  } catch (e) {
    if (e instanceof Error && (e as Error & { statusCode?: number }).statusCode) {
      throw e;
    }

    const elapsed = performance.now() - startTime;
    const errorMessage = e instanceof Error ? e.message : String(e);
    log(tag, `NETWORK ERROR: ${errorMessage} (${elapsed.toFixed(1)}ms)`);
    console.error(`[API Network Error] ${url}:`, e);

    const endpoint = url.replace(API_BASE, '').split('?')[0];
    void recordPerf(endpoint, elapsed, false);

    const isTimeout = errorMessage.includes('timeout') || errorMessage.includes('Timeout');
    const isNetwork = !errorMessage.includes('HTTP');

    const userMessage = isTimeout
      ? '请求超时，请检查网络连接后重试'
      : isNetwork
        ? '网络连接失败，请检查网络设置'
        : errorMessage;

    const error = new Error(userMessage) as Error & { isNetworkError?: boolean; isTimeout?: boolean };
    error.isNetworkError = isNetwork;
    error.isTimeout = isTimeout;
    throw error;
  }
}

import { AIRepairParams } from '../../utils/advancedAudioProcessing';
import { API_BASE, DEFAULT_TERMINAL_STATES, log } from './_shared';
import type {
  VocalRepairParams,
  InstrumentRepairParams,
  ProcessingOptions,
  DualRepairResponse,
  DualRepairFromHashResponse,
  PollCallbacks,
  ProgressEvent,
  WSProgressControl,
  QueueStatus,
} from './types';
import { getTaskStatus, getQueueStatus } from './system';

export function mapParamsToBackend(params: AIRepairParams, _options?: ProcessingOptions, algorithmVersion?: string): Record<string, unknown> {
  const out: Record<string, unknown> = {
    de_clipping: params.deClipping,
    noise_reduction: params.noiseReduction,
    de_essing: params.deEssing,
    de_crackle: params.deCrackle,
    de_pop: params.dePop,
    harmonic_enhance: params.harmonicEnhance,
    dynamic_range: params.dynamicRange,
    softness: params.softness,
    presence_boost: params.presenceBoost,
    bass_enhance: params.bassEnhance,
    spatial_enhance: params.spatialEnhance,
    transient_repair: params.transientRepair,
    warmth: params.warmth,
    clarity: params.clarity,
    algorithm_version: algorithmVersion || 'v2.0',
  };
  if (params.airTexture !== undefined) out.air_texture = params.airTexture;
  if (params.exciter !== undefined) out.exciter = params.exciter;
  if (params.compressor !== undefined) out.compressor = params.compressor;
  if (params.smartCompressor !== undefined) out.smart_compressor = params.smartCompressor;
  if (params.transientAware !== undefined) out.transient_aware = params.transientAware;
  if (params.resonanceSuppress !== undefined) out.resonance_suppress = params.resonanceSuppress;
  if (params.aiRepairAdaptive !== undefined) out.ai_repair_adaptive = params.aiRepairAdaptive;
  if (params.loudnessOptimize !== undefined) out.loudness_optimize = params.loudnessOptimize;
  if (_options?.masteringStyle) out.mastering_style = _options.masteringStyle;
  if (_options?.outputVolume !== undefined) out.output_volume = _options.outputVolume;
  return out;
}

export function mapVocalParamsToBackend(params: VocalRepairParams, _options?: ProcessingOptions, algorithmVersion?: string): Record<string, unknown> {
  const out: Record<string, unknown> = {
    de_clipping: params.deClipping,
    de_pop: params.dePop,
    formant_repair: params.formantRepair,
    de_essing: params.deEssing,
    breath_enhance: params.breathEnhance,
    ai_repair: params.aiRepair,
    bass_enhance: params.bassEnhance,
    air_texture: params.airTexture,
    loudness_optimize: params.loudness,
    speed: params.speed ?? 1.0,
    algorithm_version: algorithmVersion || 'v3.0',
    ...(_options?.outputVolume !== undefined ? { output_volume: _options.outputVolume } : {}),
  };
  if (params.exciter !== undefined) out.exciter = params.exciter;
  if (params.compressor !== undefined) out.compressor = params.compressor;
  if (params.spatial !== undefined) out.spatial = params.spatial;
  if (params.warmth !== undefined) out.warmth = params.warmth;
  if (params.smartCompressor !== undefined) out.smart_compressor = params.smartCompressor;
  if (params.transientAware !== undefined) out.transient_aware = params.transientAware;
  if (params.resonanceSuppress !== undefined) out.resonance_suppress = params.resonanceSuppress;
  if (params.aiRepairAdaptive !== undefined) out.ai_repair_adaptive = params.aiRepairAdaptive;
  if (params.exciterImproved !== undefined) out.exciter_improved = params.exciterImproved;
  if (params.deEsserImproved !== undefined) out.de_esser_improved = params.deEsserImproved;
  return out;
}

export function mapInstrumentParamsToBackend(params: InstrumentRepairParams, _options?: ProcessingOptions, algorithmVersion?: string): Record<string, unknown> {
  const out: Record<string, unknown> = {
    de_clipping: params.deClipping,
    de_pop: params.dePop,
    timbre_protect: params.timbreProtect,
    dynamic_range: params.dynamicRange,
    noise_reduction: params.noiseReduction,
    spatial_enhance: params.spatialEnhance,
    warmth: params.warmth,
    loudness_optimize: params.loudness,
    speed: params.speed ?? 1.0,
    algorithm_version: algorithmVersion || 'v3.0',
  };
  if (params.stereo_enhance !== undefined) out.stereo_enhance = params.stereo_enhance;
  if (params.exciter !== undefined) out.inst_exciter = params.exciter;
  if (params.transient !== undefined) out.inst_transient = params.transient;
  if (params.resonance !== undefined) out.inst_resonance = params.resonance;
  if (params.bassEnhance !== undefined) out.inst_bass_enhance = params.bassEnhance;
  if (params.airTexture !== undefined) out.inst_air_texture = params.airTexture;
  if (_options?.outputVolume !== undefined) out.output_volume = _options.outputVolume;
  return out;
}

export async function repairAudio(taskId: string, params: AIRepairParams, options: ProcessingOptions, algorithmVersion?: string): Promise<{ task_id: string; message: string }> {
  const url = `${API_BASE}/repair`;
  const backendParams = mapParamsToBackend(params, options, algorithmVersion);
  log('repair', `POST ${url} task_id=${taskId}`);

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, params: backendParams }),
    });

    log('repair', `response status=${res.status} ok=${res.ok}`);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '修复请求失败' }));
      const detail = Array.isArray(err.detail)
        ? err.detail.map((e: { msg?: string }) => e.msg || String(e)).join('; ')
        : (err.detail || '修复请求失败');
      log('repair', `ERROR: ${detail}`);
      throw new Error(detail);
    }

    const data = await res.json();
    log('repair', `success: ${data.message}`);
    return data;
  } catch (e) {
    log('repair', `FETCH ERROR: ${e instanceof Error ? e.message : String(e)}`);
    throw e;
  }
}

export async function repairDualAudio(
  mainTaskId: string,
  vocalTaskId: string,
  accompanimentTaskId: string,
  params: AIRepairParams,
  options: ProcessingOptions,
  algorithmVersion?: string,
  vocalParams?: VocalRepairParams,
  accompanimentParams?: InstrumentRepairParams,
  mixRatio?: number
): Promise<DualRepairResponse> {
  const url = `${API_BASE}/repair-dual`;
  const backendParams = mapParamsToBackend(params, options, algorithmVersion);
  log('repair-dual', `POST ${url} task_id=${mainTaskId}`);

  const body: Record<string, unknown> = {
    task_id: mainTaskId,
    vocal_task_id: vocalTaskId,
    accompaniment_task_id: accompanimentTaskId,
    params: backendParams,
  };

  if (vocalParams) {
    body.vocal_params = mapVocalParamsToBackend(vocalParams, options, algorithmVersion);
  }
  if (accompanimentParams) {
    body.accompaniment_params = mapInstrumentParamsToBackend(accompanimentParams, options, algorithmVersion);
  }
  if (mixRatio !== undefined) {
    body.mix_ratio = mixRatio;
  }

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    log('repair-dual', `response status=${res.status} ok=${res.ok}`);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '双轨修复请求失败' }));
      const detail = Array.isArray(err.detail)
        ? err.detail.map((e: { msg?: string }) => e.msg || String(e)).join('; ')
        : (err.detail || '双轨修复请求失败');
      log('repair-dual', `ERROR: ${detail}`);
      throw new Error(detail);
    }

    const data = await res.json();
    log('repair-dual', `success: task_id=${data.task_id}`);
    return data;
  } catch (e) {
    log('repair-dual', `FETCH ERROR: ${e instanceof Error ? e.message : String(e)}`);
    throw e;
  }
}

export async function repairDualFromHash(
  vocalFileHash: string,
  accompanimentFileHash: string,
  vocalFileName: string,
  accompanimentFileName: string,
  params: AIRepairParams,
  options: ProcessingOptions,
  algorithmVersion?: string,
  vocalParams?: VocalRepairParams,
  accompanimentParams?: InstrumentRepairParams,
  mixRatio?: number
): Promise<DualRepairFromHashResponse> {
  const url = `${API_BASE}/repair-dual-from-hash`;
  const backendParams = mapParamsToBackend(params, options, algorithmVersion);
  log('repair-dual-from-hash', `POST ${url} vocal_hash=${vocalFileHash.slice(0, 12)} acc_hash=${accompanimentFileHash.slice(0, 12)}`);

  const body: Record<string, unknown> = {
    vocal_file_hash: vocalFileHash,
    accompaniment_file_hash: accompanimentFileHash,
    vocal_filename: vocalFileName,
    accompaniment_filename: accompanimentFileName,
    params: backendParams,
  };

  if (vocalParams) {
    body.vocal_params = mapVocalParamsToBackend(vocalParams, options, algorithmVersion);
  }
  if (accompanimentParams) {
    body.accompaniment_params = mapInstrumentParamsToBackend(accompanimentParams, options, algorithmVersion);
  }
  if (mixRatio !== undefined) {
    body.mix_ratio = mixRatio;
  }

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    log('repair-dual-from-hash', `response status=${res.status} ok=${res.ok}`);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '双轨修复请求失败' }));
      const detail = Array.isArray(err.detail)
        ? err.detail.map((e: { msg?: string }) => e.msg || String(e)).join('; ')
        : (err.detail || '双轨修复请求失败');
      log('repair-dual-from-hash', `ERROR: ${detail}`);
      throw new Error(detail);
    }

    const data = await res.json();
    log('repair-dual-from-hash', `success: task_id=${data.task_id} vocal=${data.vocal_task_id} acc=${data.accompaniment_task_id}`);
    return data;
  } catch (e) {
    log('repair-dual-from-hash', `FETCH ERROR: ${e instanceof Error ? e.message : String(e)}`);
    throw e;
  }
}

interface PollConfig {
  initialInterval: number;
  fastInterval: number;
  normalInterval: number;
  slowInterval: number;
  stuckThresholdSeconds: number;
  maxErrors: number;
}

const DEFAULT_POLL_CONFIG: PollConfig = {
  initialInterval: 500,
  fastInterval: 800,
  normalInterval: 1500,
  slowInterval: 3000,
  stuckThresholdSeconds: 30,
  maxErrors: 5,
};

export function pollProgress(
  taskId: string,
  callbacks: PollCallbacks,
  terminalStates?: Set<string>,
  config: Partial<PollConfig> = {},
): AbortController {
  const cfg = { ...DEFAULT_POLL_CONFIG, ...config };
  const controller = new AbortController();
  let stopped = false;
  let consecutiveErrors = 0;
  const terminals = terminalStates || DEFAULT_TERMINAL_STATES;

  let lastProgress = -1;
  let lastProgressTime = Date.now();
  let lastStep = '';
  const pollStartTime = Date.now();
  let isStuck = false;
  let queueCheckInterval: number | null = null;

  log('poll', `START task_id=${taskId} terminals=[${[...terminals].join(',')}]`);

  const getPollInterval = (): number => {
    const elapsed = (Date.now() - pollStartTime) / 1000;
    if (elapsed < 10) return cfg.fastInterval;
    if (elapsed < 30) return cfg.normalInterval;
    return cfg.slowInterval;
  };

  const checkStuck = (currentProgress: number, currentStep: string): boolean => {
    const now = Date.now();
    const timeSinceProgress = (now - lastProgressTime) / 1000;

    if (currentProgress !== lastProgress || currentStep !== lastStep) {
      if (isStuck) {
        isStuck = false;
        log('poll', `UNSTUCK task_id=${taskId} progress=${currentProgress} step="${currentStep}"`);
        callbacks.onUnstuck?.();
      }
      lastProgress = currentProgress;
      lastStep = currentStep;
      lastProgressTime = now;
      return false;
    }

    if (timeSinceProgress > cfg.stuckThresholdSeconds && !isStuck) {
      isStuck = true;
      log('poll', `STUCK DETECTED task_id=${taskId} progress=${currentProgress} step="${currentStep}" duration=${timeSinceProgress.toFixed(1)}s`);
      callbacks.onStuck?.({
        taskId,
        lastProgress: currentProgress,
        lastStep: currentStep,
        duration: timeSinceProgress,
      });
      return true;
    }

    return isStuck;
  };

  const startQueueCheck = () => {
    if (queueCheckInterval) return;
    queueCheckInterval = window.setInterval(async () => {
      if (stopped) return;
      const queueStatus = await getQueueStatus();
      if (queueStatus && callbacks.onQueueUpdate) {
        callbacks.onQueueUpdate(queueStatus);
      }
    }, 5000);
  };

  const stopQueueCheck = () => {
    if (queueCheckInterval) {
      clearInterval(queueCheckInterval);
      queueCheckInterval = null;
    }
  };

  const poll = async () => {
    startQueueCheck();

    while (!stopped) {
      try {
        const status = await getTaskStatus(taskId);
        consecutiveErrors = 0;

        checkStuck(status.progress, status.step);

        callbacks.onProgress(status);

        if (terminals.has(status.status)) {
          log('poll', `COMPLETE task_id=${taskId} status=${status.status}`);
          stopQueueCheck();
          if (status.status === 'error' || status.status === 'timeout') {
            callbacks.onError?.(new Error(status.error || status.step || `任务失败(status=${status.status})`));
          } else {
            callbacks.onComplete?.(status);
          }
          return;
        }
      } catch (err) {
        if (stopped) return;
        consecutiveErrors++;
        log('poll', `ERROR #${consecutiveErrors} task_id=${taskId}: ${err instanceof Error ? err.message : String(err)}`);
        if (consecutiveErrors >= cfg.maxErrors) {
          log('poll', `GIVING UP after ${cfg.maxErrors} errors`);
          stopQueueCheck();
          callbacks.onError?.(err instanceof Error ? err : new Error(String(err)));
          return;
        }
      }

      const interval = getPollInterval();
      await new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, interval);
        controller.signal.addEventListener('abort', () => {
          clearTimeout(timer);
          stopped = true;
          resolve();
        }, { once: true });
      });

      if (stopped) {
        stopQueueCheck();
        return;
      }
    }
  };

  poll();

  return controller;
}

export function pollProgressLegacy(
  taskId: string,
  onProgress: (event: ProgressEvent) => void,
  onError?: (error: Error) => void,
  onComplete?: (event: ProgressEvent) => void,
  terminalStates?: Set<string>,
): AbortController {
  return pollProgress(
    taskId,
    { onProgress, onError, onComplete },
    terminalStates
  );
}

export async function cancelTask(taskId: string): Promise<{ task_id: string; status: string; message: string }> {
  const url = `${API_BASE}/cancel/${taskId}`;
  log('cancel', `POST ${url}`);

  try {
    const res = await fetch(url, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '取消请求失败' }));
      throw new Error(err.detail || '取消请求失败');
    }
    const data = await res.json();
    log('cancel', `success: ${data.message}`);
    return data;
  } catch (e) {
    log('cancel', `ERROR: ${e instanceof Error ? e.message : String(e)}`);
    throw e;
  }
}

export function connectProgressWS(
  taskId: string,
  callbacks: PollCallbacks,
  terminalStates?: Set<string>,
): WSProgressControl {
  const terminals = terminalStates || DEFAULT_TERMINAL_STATES;
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
  const wsUrl = `${protocol}//${wsHost}/api/v1/ws/${taskId}`;

  let ws: WebSocket | null = null;
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 3;
  let closed = false;
  let stuckDetected = false;
  let lastProgress = -1;
  let lastStep = '';
  let lastProgressTime = Date.now();

  const checkStuck = (progress: number, step: string) => {
    const now = Date.now();
    if (progress !== lastProgress || step !== lastStep) {
      if (stuckDetected) {
        stuckDetected = false;
        callbacks.onUnstuck?.();
      }
      lastProgress = progress;
      lastStep = step;
      lastProgressTime = now;
    } else {
      const timeSinceProgress = (now - lastProgressTime) / 1000;
      if (timeSinceProgress > 30 && !stuckDetected) {
        stuckDetected = true;
        callbacks.onStuck?.({
          taskId,
          lastProgress: progress,
          lastStep: step,
          duration: timeSinceProgress,
        });
      }
    }
  };

  const fallbackToPolling = () => {
    console.warn(`[WS] 降级到 HTTP 轮询 task_id=${taskId}`);
    pollProgress(taskId, callbacks, terminals);
  };

  const connect = () => {
    if (closed) return;

    try {
      ws = new WebSocket(wsUrl);
    } catch (e) {
      console.warn(`[WS] 创建连接失败:`, e);
      fallbackToPolling();
      return;
    }

    const connectTimeout = setTimeout(() => {
      if (ws && ws.readyState === WebSocket.CONNECTING) {
        console.warn(`[WS] 连接超时 task_id=${taskId}`);
        ws.close();
      }
    }, 5000);

    ws.onopen = () => {
      clearTimeout(connectTimeout);
      reconnectAttempts = 0;
      console.log(`[WS] 连接成功 task_id=${taskId}`);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.error && !data.task_id) {
          callbacks.onError?.(new Error(data.error));
          return;
        }
        checkStuck(data.progress, data.step);
        callbacks.onProgress(data);
        if (terminals.has(data.status)) {
          console.log(`[WS] 任务终态 task_id=${taskId} status=${data.status}`);
          if (data.status === 'error') {
            callbacks.onError?.(new Error(data.error || data.step || '任务失败'));
          } else {
            callbacks.onComplete?.(data);
          }
          closed = true;
          ws?.close();
        }
      } catch (e) {
        console.warn(`[WS] 消息解析失败:`, e);
      }
    };

    ws.onerror = (e) => {
      clearTimeout(connectTimeout);
      console.warn(`[WS] 连接错误 task_id=${taskId}`, e);
    };

    ws.onclose = (_event) => {
      clearTimeout(connectTimeout);
      if (closed) return;

      if (reconnectAttempts < maxReconnectAttempts) {
        reconnectAttempts++;
        const delay = Math.pow(2, reconnectAttempts - 1) * 1000;
        console.log(`[WS] 重连 #${reconnectAttempts} task_id=${taskId} 延迟=${delay}ms`);
        setTimeout(connect, delay);
      } else {
        console.warn(`[WS] 重连耗尽 task_id=${taskId}`);
        fallbackToPolling();
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

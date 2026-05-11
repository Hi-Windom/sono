import { AIRepairParams } from '../utils/advancedAudioProcessing';
import { AISongDetectionResult } from '../utils/aiSongChecker';

export interface ProcessingOptions {
  sampleRate: number;
  bitDepth: 16 | 24 | 32;
}

const API_BASE = '/api/v1';
const HEALTH_URL = '/health';

const LOG_ENABLED = true;
function log(tag: string, ...args: unknown[]) {
  if (!LOG_ENABLED) return;
  const ts = new Date().toISOString().substr(11, 12);
  const msg = `[${ts}][backendApi][${tag}] ${args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ')}`;
  console.log(msg);
}

interface AudioInfo {
  sample_rate: number;
  channels: number;
  duration: number;
  num_frames: number;
  format: string;
  sample_width: number;
}

interface UploadResponse {
  task_id: string;
  filename: string;
  size: number;
  message: string;
  cached?: boolean;
  audio_info?: AudioInfo | null;
}

interface TaskStatus {
  task_id: string;
  status: string;
  progress: number;
  step: string;
  detection_result?: BackendDetectionResult;
  repaired_detection_result?: BackendDetectionResult;
  repair_result?: BackendRepairResult;
  error?: string;
}

interface BackendDetectionResult {
  is_ai_generated: boolean;
  confidence: number;
  ai_probability: number;
  human_probability?: number;
  signature?: 'human' | 'ai' | 'mixed' | 'uncertain';
  reasons: string[];
  features: Record<string, number>;
  sample_rate: number;
  duration: number;
  detect_type?: string;
}

interface BackendRepairResult {
  issues_found: string[];
  original_sample_rate: number;
  output_sample_rate: number;
  output_bit_depth: number;
  duration: number;
  channels: number;
  algorithm_version?: string;
  waveform_peaks?: number[][];
}

interface ProgressEvent {
  task_id: string;
  status: string;
  progress: number;
  step: string;
  detection_result?: BackendDetectionResult;
  repaired_detection_result?: BackendDetectionResult;
  repair_result?: BackendRepairResult;
  render_filename?: string;
  render_result?: {
    original_sample_rate: number;
    output_sample_rate: number;
    output_bit_depth: number;
    duration: number;
    channels: number;
  };
  error?: string;
}

export interface AlgorithmVersion {
  name: string;
  label: string;
  description: string;
  defaultParams: Record<string, number>;
  paramRanges: Record<string, {
    min: number;
    max: number;
    step: number;
    label: string;
  }>;
  modes: {
    name: string;
    description: string;
    icon: string;
    params: Record<string, number>;
  }[];
}

export interface DetectorVersion {
  name: string;
  label: string;
  description: string;
}

export function mapParamsToBackend(params: AIRepairParams, _options?: ProcessingOptions, algorithmVersion?: string): Record<string, unknown> {
  return {
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
}

function mapDetectionResult(backend: BackendDetectionResult): AISongDetectionResult {
  const aiProbability = backend.ai_probability;
  const humanProbability = backend.human_probability ?? (1 - aiProbability);
  const isAI = aiProbability > humanProbability;

  let signature: AISongDetectionResult['signature'];
  if (backend.signature) {
    signature = backend.signature;
  } else {
    signature = 'uncertain';
    if (aiProbability > 0.7 && backend.confidence > 0.4) {
      signature = 'ai';
    } else if (humanProbability > 0.7 && backend.confidence > 0.4) {
      signature = 'human';
    } else if (backend.confidence > 0.3) {
      signature = 'mixed';
    }
  }

  const f = backend.features || {};

  return {
    isAI,
    aiProbability,
    humanProbability,
    confidence: backend.confidence,
    features: {
      spectralFlatness: f.spectral_flatness ?? 0,
      spectralCentroid: f.spectral_centroid_mean ?? 0,
      spectralBandwidth: 0,
      spectralRolloff: 0,
      zeroCrossingRate: 0,
      energy: 0,
      energyEntropy: 0,
      harmonicSpectralCentroid: 0,
      onsetRate: 0,
      pitchVariability: f.pitch_variability ?? 0,
      vibratoRate: 0,
      vibratoDepth: 0,
      formantStability: 0,
      noiseFloor: 0,
      dynamicRange: f.dynamic_range ?? 0,
      temporalCentroid: 0,
      spectralFlux: 0,
      spectralEntropy: f.spectral_entropy ?? 0,
      mfccSimilarity: f.mfcc_variability ?? 0,
      microRhythmConsistency: f.micro_rhythm_consistency ?? 0,
      harmonicRatio: 0,
      highFreqAttenuation: f.high_freq_attenuation ?? 0,
      temporalRegularity: f.temporal_regularity ?? 0,
    },
    reasons: backend.reasons || [],
    signature,
  };
}

export type ProgressCallback = (loaded: number, total: number, speed: number) => void;

export async function checkFileHash(fileHash: string): Promise<{ exists: boolean; task_id?: string; filename?: string }> {
  const url = `${API_BASE}/check-hash`;
  log('check-hash', `POST ${url} hash=${fileHash}`);
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_hash: fileHash }),
    });
    if (!res.ok) return { exists: false };
    const data = await res.json();
    log('check-hash', `result: exists=${data.exists} task_id=${data.task_id || 'none'}`);
    return data;
  } catch {
    log('check-hash', 'FAILED');
    return { exists: false };
  }
}

export async function uploadAudio(file: File, onProgress?: ProgressCallback, fileHash?: string): Promise<UploadResponse> {
  if (fileHash) {
    const checkResult = await checkFileHash(fileHash);
    if (checkResult.exists && checkResult.task_id) {
      log('upload', `CACHE HIT hash=${fileHash} task_id=${checkResult.task_id}`);
      return {
        task_id: checkResult.task_id,
        filename: checkResult.filename || file.name,
        size: file.size,
        message: '文件已缓存，跳过上传',
        cached: true,
      };
    }
  }

  const url = `${API_BASE}/upload`;
  log('upload', `POST ${url} file=${file.name} size=${file.size} hash=${fileHash || 'none'}`);

  const formData = new FormData();
  formData.append('file', file);
  if (fileHash) {
    formData.append('file_hash', fileHash);
  }

  return new Promise<UploadResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.timeout = 120000;

    const startTime = Date.now();

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        const elapsed = (Date.now() - startTime) / 1000;
        const speed = elapsed > 0 ? e.loaded / elapsed : 0;
        onProgress(e.loaded, e.total, speed);
      }
    };

    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          log('upload', `success task_id=${data.task_id} cached=${data.cached}`);
          resolve(data);
        } else {
          const detail = data.detail || '上传失败';
          log('upload', `ERROR: ${detail}`);
          reject(new Error(detail));
        }
      } catch {
        log('upload', `PARSE ERROR`);
        reject(new Error('上传响应解析失败'));
      }
    };

    xhr.onerror = () => {
      log('upload', `XHR ERROR`);
      reject(new Error('上传网络错误'));
    };

    xhr.ontimeout = () => {
      log('upload', 'TIMEOUT');
      reject(new Error('上传超时(120s)，请检查网络或后端是否正常运行'));
    };

    xhr.send(formData);
  });
}

export interface DetectAudioResponse {
  task_id: string;
  status: string;
  cached?: boolean;
  detection_result?: BackendDetectionResult;
}

export async function detectAudio(taskId: string, type: 'original' | 'repaired' = 'original', detectorVersion?: string, skipCache: boolean = false): Promise<DetectAudioResponse> {
  const url = `${API_BASE}/detect`;
  const versionToSend = detectorVersion || 'v1.0';
  log('detect', `POST ${url} task_id=${taskId} type=${type} detector_version=${versionToSend} skipCache=${skipCache}`);

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, type, detector_version: versionToSend, skip_cache: skipCache }),
    });

    log('detect', `response status=${res.status} ok=${res.ok}`);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: '检测请求失败' }));
      log('detect', `ERROR: ${err.detail}`);
      throw new Error(err.detail || '检测请求失败');
    }

    const data: DetectAudioResponse = await res.json();
    log('detect', `success: status=${data.status} cached=${!!data.cached}`);
    return data;
  } catch (e) {
    log('detect', `FETCH ERROR: ${e instanceof Error ? e.message : String(e)}`);
    throw e;
  }
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
      log('repair', `ERROR: ${err.detail}`);
      throw new Error(err.detail || '修复请求失败');
    }

    const data = await res.json();
    log('repair', `success: ${data.message}`);
    return data;
  } catch (e) {
    log('repair', `FETCH ERROR: ${e instanceof Error ? e.message : String(e)}`);
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

// 队列状态接口
export interface QueueStatus {
  total_tasks: number;
  pending: number;
  detecting: number;
  repairing: number;
  completed: number;
  error: number;
  timeout: number;
  running_tasks: Array<{
    task_id: string;
    status: string;
    step: string;
    progress: number;
    elapsed_seconds: number;
  }>;
}

// 获取队列状态
export async function getQueueStatus(): Promise<QueueStatus | null> {
  try {
    const res = await fetch(`${API_BASE}/queue-status`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export interface RepairCacheLookupResult {
  found: boolean;
  task_id?: string;
  output_path?: string;
  output_size?: number;
  repair_result?: BackendRepairResult;
  detection_result?: BackendDetectionResult;
  repaired_detection_result?: BackendDetectionResult;
}

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

const DEFAULT_TERMINAL_STATES = new Set(['completed', 'detected', 'error', 'timeout']);

// 轮询配置
interface PollConfig {
  // 动态间隔配置 (ms)
  initialInterval: number;      // 初始间隔
  fastInterval: number;         // 快速模式 (<10s)
  normalInterval: number;       // 正常模式 (10-30s)
  slowInterval: number;         // 慢速模式 (>30s)
  // 卡住检测配置
  stuckThresholdSeconds: number; // 多少秒无进度视为卡住
  // 错误配置
  maxErrors: number;
}

const DEFAULT_POLL_CONFIG: PollConfig = {
  initialInterval: 500,         // 0.5s 初始快速轮询
  fastInterval: 800,            // 0.8s 前10秒
  normalInterval: 1500,         // 1.5s 10-30秒
  slowInterval: 3000,           // 3s 30秒后
  stuckThresholdSeconds: 30,    // 30秒无进度视为卡住
  maxErrors: 5,
};

export interface PollCallbacks {
  onProgress: (event: ProgressEvent) => void;
  onError?: (error: Error) => void;
  onComplete?: (event: ProgressEvent) => void;
  onStuck?: (info: { taskId: string; lastProgress: number; lastStep: string; duration: number }) => void;
  onUnstuck?: () => void;  // 进度恢复时触发
  onQueueUpdate?: (queueStatus: QueueStatus) => void;
}

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

  // 状态追踪
  let lastProgress = -1;
  let lastProgressTime = Date.now();
  let lastStep = '';
  let pollStartTime = Date.now();
  let isStuck = false;
  let queueCheckInterval: number | null = null;

  log('poll', `START task_id=${taskId} terminals=[${[...terminals].join(',')}]`);

  // 计算当前轮询间隔
  const getPollInterval = (): number => {
    const elapsed = (Date.now() - pollStartTime) / 1000;
    if (elapsed < 10) return cfg.fastInterval;
    if (elapsed < 30) return cfg.normalInterval;
    return cfg.slowInterval;
  };

  // 检查是否卡住
  const checkStuck = (currentProgress: number, currentStep: string): boolean => {
    const now = Date.now();
    const timeSinceProgress = (now - lastProgressTime) / 1000;

    // 如果进度变化或步骤变化，重置计时
    if (currentProgress !== lastProgress || currentStep !== lastStep) {
      // 如果之前是卡住状态，现在恢复了，触发 onUnstuck
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

    // 检查是否超过阈值
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

  // 定期检查队列状态
  const startQueueCheck = () => {
    if (queueCheckInterval) return;
    queueCheckInterval = window.setInterval(async () => {
      if (stopped) return;
      const queueStatus = await getQueueStatus();
      if (queueStatus && callbacks.onQueueUpdate) {
        callbacks.onQueueUpdate(queueStatus);
      }
    }, 5000); // 每5秒检查一次队列状态
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

        // 检查是否卡住
        checkStuck(status.progress, status.step);

        callbacks.onProgress(status);

        if (terminals.has(status.status)) {
          log('poll', `COMPLETE task_id=${taskId} status=${status.status}`);
          stopQueueCheck();
          callbacks.onComplete?.(status);
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

// 兼容旧版调用方式
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

export function getDownloadUrl(taskId: string): string {
  return `${API_BASE}/download/${taskId}`;
}

export function getPreviewUrl(taskId: string, type: 'original' | 'repaired'): string {
  return `${API_BASE}/preview/${taskId}?type=${type}`;
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

export async function downloadWithProgress(url: string, onProgress?: ProgressCallback, maxRetries: number = 3): Promise<ArrayBuffer> {
  let lastError: Error | null = null;
  let savedChunks: Uint8Array[] = [];
  let savedBytes = 0;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const startByte = savedBytes;
      const result = await new Promise<ArrayBuffer>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('GET', url);
        xhr.responseType = 'arraybuffer';

        if (startByte > 0) {
          xhr.setRequestHeader('Range', `bytes=${startByte}-`);
          log('download', `retry #${attempt + 1} resume from byte ${startByte}`);
        } else if (attempt > 0) {
          log('download', `retry #${attempt + 1}`);
        }

        const startTime = Date.now();
        let lastSpeedLoaded = 0;

        xhr.onprogress = (e) => {
          if (e.lengthComputable && onProgress) {
            const currentLoaded = startByte + e.loaded;
            const total = startByte + e.total;
            const elapsed = (Date.now() - startTime) / 1000;
            const speed = elapsed > 0 ? (e.loaded - lastSpeedLoaded) / elapsed : 0;
            lastSpeedLoaded = e.loaded;
            onProgress(currentLoaded, total, speed);
          }
        };

        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            savedChunks = [];
            savedBytes = 0;
            resolve(xhr.response);
          } else if (xhr.status === 206) {
            resolve(xhr.response);
          } else {
            reject(new Error(`下载失败 (HTTP ${xhr.status})`));
          }
        };

        xhr.onerror = () => {
          reject(new Error('下载网络错误'));
        };

        xhr.ontimeout = () => {
          reject(new Error('下载超时'));
        };

        xhr.timeout = 60000;
        xhr.send();
      });

      if (savedChunks.length > 0) {
        const newData = new Uint8Array(result);
        savedChunks.push(newData);
        const totalLen = savedChunks.reduce((s, c) => s + c.length, 0);
        const combined = new Uint8Array(totalLen);
        let off = 0;
        for (const chunk of savedChunks) {
          combined.set(chunk, off);
          off += chunk.length;
        }
        savedChunks = [];
        savedBytes = 0;
        return combined.buffer;
      }

      return result;
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      log('download', `attempt ${attempt + 1} failed: ${lastError.message}`);

      if (attempt < maxRetries - 1) {
        await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
      }
    }
  }

  throw lastError || new Error('下载失败');
}

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

// 渲染缓存查询
export interface RenderCacheEntry {
  sample_rate: number;
  bit_depth: number;
  filename: string;
  size: number;
  mtime: string;
  algorithm_version: string;
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

// 训练素材哈希检查
export async function checkTrainingHash(fileHash: string): Promise<{ exists: boolean; filename?: string; size?: number }> {
  const url = `${API_BASE}/training/check-hash`;
  log('training-check-hash', `POST ${url} hash=${fileHash}`);
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_hash: fileHash }),
    });
    if (!res.ok) return { exists: false };
    const data = await res.json();
    log('training-check-hash', `result: exists=${data.exists}`);
    return data;
  } catch {
    log('training-check-hash', 'FAILED');
    return { exists: false };
  }
}

// 训练素材上传接口（支持进度回调和哈希检测）
export async function uploadTrainingAudio(
  file: File,
  onProgress?: (loaded: number, total: number) => void,
  fileHash?: string
): Promise<{ filename: string; size: number; message: string; cached?: boolean }> {
  const url = `${API_BASE}/training/upload`;
  
  // 如果有哈希，先检查是否已存在
  if (fileHash) {
    const checkResult = await checkTrainingHash(fileHash);
    if (checkResult.exists) {
      log('trainingUpload', `CACHE HIT hash=${fileHash} filename=${checkResult.filename}`);
      return {
        filename: checkResult.filename || file.name,
        size: checkResult.size || file.size,
        message: '文件已缓存，跳过上传',
        cached: true,
      };
    }
  }
  
  log('trainingUpload', `POST ${url} file=${file.name} size=${file.size} hash=${fileHash || 'none'}`);

  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append('file', file);
    if (fileHash) {
      formData.append('file_hash', fileHash);
    }

    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(e.loaded, e.total);
      }
    };

    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          log('trainingUpload', `success: ${data.message} cached=${data.cached}`);
          resolve(data);
        } else {
          const detail = data.detail || '上传失败';
          log('trainingUpload', `ERROR: ${detail}`);
          reject(new Error(detail));
        }
      } catch {
        log('trainingUpload', `PARSE ERROR`);
        reject(new Error('上传响应解析失败'));
      }
    };

    xhr.onerror = () => {
      log('trainingUpload', `XHR ERROR`);
      reject(new Error('上传网络错误'));
    };

    xhr.send(formData);
  });
}

export interface WSProgressControl {
  close: () => void;
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
  const wsUrl = `${protocol}//${wsHost}/api/v1/ws/progress/${taskId}`;

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

    ws.onclose = (event) => {
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

export interface MemoryInfoResult {
  available_memory_bytes: number | null;
  total_memory_bytes: number | null;
  used_memory_bytes: number | null;
  estimated_memory_bytes: number;
  is_sufficient: boolean;
  working_sr: number;
  use_float32: boolean;
  has_streaming: boolean;
  memory_saving: number;
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

export interface StorageEstimateResult {
  estimated_output_bytes: number;
  estimated_output_mb: number;
  available_disk_bytes: number | null;
  total_disk_bytes: number | null;
  used_disk_bytes: number | null;
  is_sufficient: boolean;
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

export interface RenderResult {
  task_id: string;
  status: string;
  render_filename?: string;
  render_result?: {
    original_sample_rate: number;
    output_sample_rate: number;
    output_bit_depth: number;
    duration: number;
    channels: number;
  };
}

export async function renderAudio(
  taskId: string,
  sampleRate: number,
  bitDepth: number,
): Promise<RenderResult> {
  const url = `${API_BASE}/render`;
  log('render', `POST ${url} task_id=${taskId} sr=${sampleRate} bd=${bitDepth}`);
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      task_id: taskId,
      sample_rate: sampleRate,
      bit_depth: bitDepth,
    }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `渲染失败 (${res.status})`);
  }
  return await res.json();
}

/** 通过 WebSocket 等待渲染完成，替代轮询 */
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

export { mapDetectionResult, type BackendDetectionResult, type BackendRepairResult, type ProgressEvent, type TaskStatus };

/**
 * 从 Content-Disposition 头解析文件名
 * 支持 RFC 5987 (filename*=UTF-8''xxx) 和普通格式 (filename="xxx")
 */
export function parseFilenameFromDisposition(disposition: string | null): string | null {
  if (!disposition) return null;
  // 优先匹配 RFC 5987: filename*=UTF-8''xxx（URL编码，支持中文）
  const utf8 = disposition.match(/filename\*=UTF-8''(.+?)(?:;|$)/i);
  if (utf8?.[1]) return decodeURIComponent(utf8[1]);
  // 其次匹配 filename="xxx" 或 filename=xxx
  const plain = disposition.match(/filename=["']?([^"';\n]+)["']?/i);
  if (plain?.[1]) return plain[1].trim();
  return null;
}

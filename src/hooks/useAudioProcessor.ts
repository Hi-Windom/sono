import { useRef, useState, useCallback, useEffect } from 'react';
import { AIRepairParams, defaultAIRepairParams, RepairMode } from '../utils/advancedAudioProcessing';
import { loadSettings, saveSettings, resetSettings as resetStoredSettings, saveProfileToStorage } from '../utils/settingsStorage';
import { parseWavHeader, WavInfo } from '../utils/wavParser';
import { saveSession, loadSession, clearSession, saveAnalysisCache } from '../utils/sessionDB';
import { computeFileHash } from '../utils/fileHash';
import { useAudioWorker } from '../workers/useAudioWorker';
import { useRepairSessionStore } from '../store/repairSessionStore';
import {
  uploadAudio,
  repairAudio,
  pollProgress,
  pollProgressLegacy,
  connectProgressWS,
  WSProgressControl,
  getPreviewUrl,
  getDownloadUrl,
  cancelTask,
  downloadWithProgress,
  mapParamsToBackend,
  lookupRepairCache,
  RepairCacheLookupResult,
  ProcessingOptions,
  fetchAlgorithmVersions,
  AlgorithmVersion,
  QueueStatus,
  renderAudio,
  waitRenderWithWS,
  fetchRenderCache,
  RenderCacheEntry,
  parseFilenameFromDisposition,
} from '../services/backendApi';
import { CacheHitInfo } from '../components/RepairCacheModal';

function writeLog(message: string) {
  // eslint-disable-next-line no-console
  console.log(message);
}


export interface AudioAnalysis {
  spectralFlatness: number;
  dynamicRange: number;
  stereoBalance: number;
  peakLevel: number;
  issues: string[];
}

export type PlayMode = 'original' | 'backend';

export type { ProcessingOptions };

export const defaultProcessingOptions: ProcessingOptions = {
  sampleRate: 48000,
  bitDepth: 24,
};

function formatSpeed(bytesPerSec: number): string {
  if (bytesPerSec < 1024) return `${bytesPerSec.toFixed(0)} B/s`;
  if (bytesPerSec < 1024 * 1024) return `${(bytesPerSec / 1024).toFixed(1)} KB/s`;
  return `${(bytesPerSec / 1024 / 1024).toFixed(1)} MB/s`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function downloadBlob(blob: Blob, fileName: string) {
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = fileName;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  // 立即移除 a 元素，避免阻塞页面交互
  document.body.removeChild(a);
  setTimeout(() => {
    URL.revokeObjectURL(blobUrl);
  }, 30000);
}

function downloadUrl(url: string, fileName: string) {
  // 使用 fetch+blob 下载，避免 <a href> 直接触发页面导航（用户取消时可能导致页面卡死）
  // 后备：如果 fetch 失败，回退到 <a> 方式
  fetch(url)
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.blob();
    })
    .then(blob => {
      downloadBlob(blob, fileName);
    })
    .catch(() => {
      // 回退到直接链接（支持 Range 请求和下载器）
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { document.body.removeChild(a); }, 5000);
    });
}

export function generateExportFilename(
  audioFileName: string | undefined,
  algorithmVersion: string,
  sampleRate: number,
  bitDepth: number,
  suffix?: string,
): string {
  const baseName = audioFileName ? audioFileName.replace(/\.[^/.]+$/, '') : 'audio';
  const ts = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 15);
  const parts = [baseName];
  if (suffix) parts.push(suffix);
  parts.push(algorithmVersion, `${sampleRate / 1000}k`, `${bitDepth}bit`, ts);
  return `${parts.join('_')}.wav`;
}

export function useAudioProcessor() {
  const savedSettings = loadSettings();
  const audioWorker = useAudioWorker();

  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioBuffer, setAudioBuffer] = useState<AudioBuffer | null>(null);
  const [backendProcessedBuffer, setBackendProcessedBuffer] = useState<AudioBuffer | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isDecodingAudio, setIsDecodingAudio] = useState(false);
  const [processingProgress, setProcessingProgress] = useState(0);
  const [processingStep, setProcessingStep] = useState('');
  const [processingSource, setProcessingSource] = useState<'backend' | null>(null);
  const [isRenderLoading, setIsRenderLoading] = useState(false);
  const [fileHash, setFileHash] = useState<string | null>(null);
  const [params, setParams] = useState<AIRepairParams>(savedSettings.aiRepairParams);
  const [audioAnalysis, setAudioAnalysis] = useState<AudioAnalysis | null>(null);
  const [selectedMode, setSelectedMode] = useState<string>(savedSettings.selectedMode);
  const [playMode, setPlayMode] = useState<PlayMode>('original');
  const [processingOptions, setProcessingOptionsState] = useState<ProcessingOptions>(savedSettings.exportOptions);
  const [hasBeenProcessed, setHasBeenProcessed] = useState(false);
  const [backendAvailable, setBackendAvailable] = useState(false);
  const [backendDiag, setBackendDiag] = useState<string>('未检测');
  const [taskId, setTaskIdState] = useState<string | null>(null);
  const setTaskId = useCallback((id: string | null) => {
    setTaskIdState(id);
    taskIdRef.current = id;
  }, []);
  const [algorithmVersion, setAlgorithmVersionState] = useState<string>(savedSettings.algorithmVersion);
  const [availableAlgorithms, setAvailableAlgorithms] = useState<AlgorithmVersion[]>([]);
  const [repairModes, setRepairModes] = useState<RepairMode[]>([]);
  const versionInitializedRef = useRef(false);
  const taskIdRef = useRef<string | null>(null);
  const wsControlRef = useRef<WSProgressControl | null>(null);
  const [wavInfo, setWavInfoState] = useState<WavInfo | null>(null);
  const wavInfoRef = useRef<WavInfo | null>(null);
  const setWavInfo = useCallback((info: WavInfo | null) => {
    wavInfoRef.current = info;
    setWavInfoState(info);
  }, []);
  const [repairResult, setRepairResult] = useState<{
    issues_found: string[];
    original_sample_rate: number;
    output_sample_rate: number;
    output_bit_depth: number;
    duration: number;
    channels: number;
    algorithm_version?: string;
    waveform_peaks?: number[][];
    completed_at?: string;
  } | null>(null);

  const [backendWaveformPeaks, setBackendWaveformPeaks] = useState<number[][] | null>(null);
  const [originalWaveformPeaks, setOriginalWaveformPeaks] = useState<number[][] | null>(null);
  const pendingObjectURLRef = useRef<string | null>(null);
  const pendingPlayRef = useRef(false);
  const durationRef = useRef(0);
  const loadAudioSeqRef = useRef(0);
  // 任务卡住状态
  const [isTaskStuck, setIsTaskStuck] = useState(false);
  const [stuckInfo, setStuckInfo] = useState<{ taskId: string; lastProgress: number; lastStep: string; duration: number } | null>(null);
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [backendPreviewUrl, setBackendPreviewUrl] = useState<string | null>(null);
  const [renderDownloadUrl, setRenderDownloadUrl] = useState<string | null>(null);
  const [showDownloadModal, setShowDownloadModal] = useState(false);
  const [cacheHitInfo, setCacheHitInfo] = useState<CacheHitInfo | null>(null);
  const [showRepairCacheModal, setShowRepairCacheModal] = useState(false);
  const [autoRenderInfo, setAutoRenderInfo] = useState<{
    output_sample_rate: number;
    output_bit_depth: number;
    duration: number;
    channels: number;
  } | null>(null);

  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<AudioBufferSourceNode | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const startTimeRef = useRef(0);
  const playStartTimeRef = useRef(0);
  const pausedAtRef = useRef(0);
  const animationFrameRef = useRef<number>();
  const isPlayingRef = useRef(false);
  const fileHashRef = useRef<string | null>(null);
  const sessionRestoredRef = useRef(false);
  const restoreSeqRef = useRef(0);
  const forceReRepairRef = useRef(false);
  const forceRenderRef = useRef(false); // 全新修复后强制重新渲染，跳过旧渲染缓存
  const streamingAudioRef = useRef<HTMLAudioElement | null>(null);
  const mediaSourceRef = useRef<MediaElementAudioSourceNode | null>(null);
  const playRef = useRef<(() => void) | null>(null);
  const audioBufferRef = useRef<AudioBuffer | null>(null);
  const backendProcessedBufferRef = useRef<AudioBuffer | null>(null);
  const seekInProgressRef = useRef(false);
  const processingOptionsRef = useRef<ProcessingOptions>(processingOptions);
  const algorithmVersionRef = useRef(algorithmVersion);

  useEffect(() => { processingOptionsRef.current = processingOptions; }, [processingOptions]);
  useEffect(() => { algorithmVersionRef.current = algorithmVersion; }, [algorithmVersion]);
  // 静音策略：为每种播放模式维护独立的 source + gain，通过 gain 切换实现无缝 A/B 对比
  const modeNodesRef = useRef<Record<PlayMode, { source: AudioBufferSourceNode; gain: GainNode } | null>>({
    original: null,
    backend: null,
  });
  const activeModeRef = useRef<PlayMode>('original');

  // 同步 audioBufferRef 与 audioBuffer state
  useEffect(() => {
    audioBufferRef.current = audioBuffer;
  }, [audioBuffer]);

  useEffect(() => {
    backendProcessedBufferRef.current = backendProcessedBuffer;
  }, [backendProcessedBuffer]);

  const applyAlgorithmVersion = useCallback((version: string) => {
    setAlgorithmVersionState(version);
    const algoInfo = availableAlgorithms.find(a => a.name === version);
    if (!algoInfo) return;

    if (algoInfo.defaultParams) {
      setParams(prev => ({ ...prev, ...algoInfo.defaultParams }));
    }
    if (algoInfo.modes && algoInfo.modes.length > 0) {
      const modes: RepairMode[] = algoInfo.modes.map(m => ({
        name: m.name,
        description: m.description,
        icon: m.icon,
        params: { ...defaultAIRepairParams, ...m.params } as AIRepairParams,
      }));
      setRepairModes(modes);
      setSelectedMode(modes[0].name);
    }
  }, [availableAlgorithms]);

  useEffect(() => {
    fetch('/health', { signal: AbortSignal.timeout(5000) })
      .then(res => {
        setBackendAvailable(res.ok);
        writeLog(`[useAudioProcessor] 初始健康检查: ${res.ok ? '后端可用' : '后端不可用'}`);
        if (res.ok) {
          fetchAlgorithmVersions().then(versions => {
            if (versions.length > 0) {
              setAvailableAlgorithms(versions);
              const current = versions.find(v => v.name === algorithmVersion);
              if (current && algorithmVersion) {
                if (current.modes && current.modes.length > 0) {
                  const modes: RepairMode[] = current.modes.map(m => ({
                    name: m.name,
                    description: m.description,
                    icon: m.icon,
                    params: { ...defaultAIRepairParams, ...m.params } as AIRepairParams,
                  }));
                  setRepairModes(modes);
                  setSelectedMode(modes[0].name);
                }
                versionInitializedRef.current = true;
                writeLog(`[useAudioProcessor] 版本 ${current.name} 可用，已加载模式`);
              } else {
                const latestVersion = versions[0];
                writeLog(`[useAudioProcessor] 当前版本 '${algorithmVersion}' 无效或未设置，自动选择最新: ${latestVersion.name}`);
                setAlgorithmVersionState(latestVersion.name);
                saveSettings({ algorithmVersion: latestVersion.name });
                if (latestVersion.modes && latestVersion.modes.length > 0) {
                  const modes: RepairMode[] = latestVersion.modes.map(m => ({
                    name: m.name,
                    description: m.description,
                    icon: m.icon,
                    params: { ...defaultAIRepairParams, ...m.params } as AIRepairParams,
                  }));
                  setRepairModes(modes);
                  setSelectedMode(modes[0].name);
                }
                versionInitializedRef.current = true;
              }
            }
          });
        }
      })
      .catch(() => {
        setBackendAvailable(false);
        writeLog('[useAudioProcessor] 初始健康检查: 后端不可用(请求失败)');
      });
  }, []);

  useEffect(() => {
    saveSettings({
      aiRepairParams: params,
      exportOptions: processingOptions,
      stemSettings: {
        vocalGain: 0,
        instrumentalGain: 0,
        vocalBalance: 0,
      },
      selectedMode,
      algorithmVersion,
    });
  }, [params, processingOptions, selectedMode, algorithmVersion]);

  useEffect(() => {
    if (availableAlgorithms.length > 0 && !versionInitializedRef.current) {
      const current = availableAlgorithms.find(v => v.name === algorithmVersion);
      if (current) {
        if (current.modes && current.modes.length > 0) {
          const modes: RepairMode[] = current.modes.map(m => ({
            name: m.name,
            description: m.description,
            icon: m.icon,
            params: { ...defaultAIRepairParams, ...m.params } as AIRepairParams,
          }));
          setRepairModes(modes);
          setSelectedMode(modes[0].name);
        }
        versionInitializedRef.current = true;
        writeLog(`[useAudioProcessor] 版本 ${current.name} 可用，已加载模式`);
      } else {
        const defaultVersion = availableAlgorithms[0];
        writeLog(`[useAudioProcessor] 当前版本 ${algorithmVersion} 不可用，自动切换到 ${defaultVersion.name}`);
        setAlgorithmVersionState(defaultVersion.name);
        if (defaultVersion.modes && defaultVersion.modes.length > 0) {
          const modes: RepairMode[] = defaultVersion.modes.map(m => ({
            name: m.name,
            description: m.description,
            icon: m.icon,
            params: { ...defaultAIRepairParams, ...m.params } as AIRepairParams,
          }));
          setRepairModes(modes);
          setSelectedMode(modes[0].name);
        }
        versionInitializedRef.current = true;
      }
    }
  }, [availableAlgorithms, algorithmVersion]);

  // 定期健康检查（每10秒）- 使用 ref 避免依赖项变化导致重新创建定时器
  const backendAvailableRef = useRef(backendAvailable);
  backendAvailableRef.current = backendAvailable;
  const healthFailCountRef = useRef(0);

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch('/health', { signal: AbortSignal.timeout(15000) });
        const wasAvailable = backendAvailableRef.current;
        const isAvailable = res.ok;

        if (isAvailable) {
          healthFailCountRef.current = 0;
          setBackendAvailable(true);
          if (!wasAvailable) {
            writeLog('[useAudioProcessor] 后端恢复可用');
            fetchAlgorithmVersions().then(versions => {
              if (versions.length > 0) {
                setAvailableAlgorithms(versions);
                const current = versions.find(v => v.name === algorithmVersion) || versions[0];
                if (current.modes && current.modes.length > 0) {
                  const modes: RepairMode[] = current.modes.map(m => ({
                    name: m.name,
                    description: m.description,
                    icon: m.icon,
                    params: { ...defaultAIRepairParams, ...m.params } as AIRepairParams,
                  }));
                  setRepairModes(modes);
                  setSelectedMode(modes[0].name);
                }
              }
            });
          }
        } else {
          healthFailCountRef.current++;
          if (backendAvailableRef.current && healthFailCountRef.current >= 3) {
            console.warn('[useAudioProcessor] 后端健康检查连续3次失败，标记为不可用');
            setBackendAvailable(false);
            healthFailCountRef.current = 0;
          }
        }
      } catch {
        healthFailCountRef.current++;
        if (backendAvailableRef.current && healthFailCountRef.current >= 3) {
          console.warn('[useAudioProcessor] 后端健康检查连续3次失败，标记为不可用');
          setBackendAvailable(false);
          healthFailCountRef.current = 0;
        }
      }
    };

    // 立即检查一次
    checkHealth();

    // 每10秒检查一次
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    return () => {
      closeWS();
      audioWorker.terminate();
    };
  }, []);

  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
      analyserRef.current = audioContextRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
      analyserRef.current.connect(audioContextRef.current.destination);
    }
    return audioContextRef.current;
  }, []);

  const pendingSessionRef = useRef<{
    file: File;
    fileName: string;
    fileHash: string;
    taskId: string;
    hasBeenProcessed: boolean;
    wavInfo?: string;
    repairResult?: string;
    processingOptions?: string;
  } | null>(null);

  useEffect(() => {
    if (sessionRestoredRef.current || !backendAvailable) return;

    if (!useRepairSessionStore.persist.hasHydrated()) {
      writeLog('[useAudioProcessor] 等待 session store 水合...');
      return;
    }

    const sessionStore = useRepairSessionStore.getState();
    if (sessionStore.isDualTrackMode) {
      writeLog('[useAudioProcessor] 双轨模式，跳过单轨会话恢复');
      sessionRestoredRef.current = true;
      return;
    }

    const seq = ++restoreSeqRef.current;

    (async () => {
      try {
        if (!pendingSessionRef.current) {
          const session = await loadSession();
          if (seq !== restoreSeqRef.current) return;

          if (!session || !session.taskId) {
            sessionRestoredRef.current = true;
            return;
          }

          writeLog(`[useAudioProcessor] 发现保存的会话: file=${session.fileName} taskId=${session.taskId} hasFile=${!!session.file} fileSize=${session.file?.size ?? 0}`);

          pendingSessionRef.current = {
            file: session.file,
            fileName: session.fileName,
            fileHash: session.fileHash || '',
            taskId: session.taskId,
            hasBeenProcessed: session.hasBeenProcessed,
            wavInfo: session.wavInfo,
            repairResult: session.repairResult,
            processingOptions: session.processingOptions,
          };
        }

        const session = pendingSessionRef.current;

        if (audioFile) {
          writeLog(`[useAudioProcessor] 用户已加载文件 ${audioFile.name}，跳过旧会话恢复`);
          pendingSessionRef.current = null;
          sessionRestoredRef.current = true;
          return;
        }

        let taskExists = true;
        let taskStatus: { status: string; [k: string]: unknown } | null = null;
        try {
          const statusRes = await fetch(`/api/v1/status/${session.taskId}`);
          if (seq !== restoreSeqRef.current) return;

          if (!statusRes.ok) {
            writeLog(`[useAudioProcessor] 任务不存在 taskId=${session.taskId} (HTTP ${statusRes.status})，清除会话`);
            taskExists = false;
          } else {
            taskStatus = await statusRes.json();
            if (seq !== restoreSeqRef.current) return;
            if (taskStatus.status === 'error') {
              writeLog(`[useAudioProcessor] 任务已出错，清除会话`);
              taskExists = false;
            }
          }
        } catch (netErr) {
          if (seq !== restoreSeqRef.current) return;
          writeLog(`[useAudioProcessor] 任务状态检查网络错误: ${netErr instanceof Error ? netErr.message : String(netErr)}，跳过恢复（不清除会话）`);
          pendingSessionRef.current = null;
          sessionRestoredRef.current = true;
          return;
        }

        if (!taskExists) {
          await clearSession();
          pendingSessionRef.current = null;
          sessionRestoredRef.current = true;
          return;
        }

        writeLog(`[useAudioProcessor] 恢复会话: taskId=${session.taskId} status=${taskStatus!.status}`);

        let arrayBuf: ArrayBuffer | null = null;
        let restoredFile: File | null = null;

        try {
          const originalUrl = getPreviewUrl(session.taskId, 'original');
          arrayBuf = await downloadWithProgress(originalUrl);
          if (seq !== restoreSeqRef.current) return;
          if (arrayBuf.byteLength === 0) throw new Error('下载的原始音频为空');
          restoredFile = new File([arrayBuf], session.fileName || 'audio.wav', { type: 'audio/wav' });
          writeLog(`[useAudioProcessor] 从后端下载原始音频成功: ${arrayBuf.byteLength} bytes`);
        } catch (dlErr) {
          if (seq !== restoreSeqRef.current) return;
          writeLog(`[useAudioProcessor] 后端下载失败: ${dlErr instanceof Error ? dlErr.message : String(dlErr)}，尝试 IndexedDB File 回退`);
          arrayBuf = null;
        }

        if (!arrayBuf && session.file && session.file.size > 0) {
          try {
            arrayBuf = await session.file.arrayBuffer();
            if (seq !== restoreSeqRef.current) return;
            if (arrayBuf.byteLength === 0) throw new Error('arrayBuffer 为空');
            restoredFile = session.file instanceof File
              ? session.file
              : new File([arrayBuf], session.fileName || 'audio.wav', { type: 'audio/wav' });
            writeLog(`[useAudioProcessor] IndexedDB File 回退成功: ${arrayBuf.byteLength} bytes`);
          } catch (fileErr) {
            if (seq !== restoreSeqRef.current) return;
            writeLog(`[useAudioProcessor] IndexedDB File 也失败: ${fileErr instanceof Error ? fileErr.message : String(fileErr)}`);
            arrayBuf = null;
          }
        }

        if (!arrayBuf) {
          writeLog(`[useAudioProcessor] 无法获取音频数据，跳过恢复（不清除会话，下次刷新可重试）`);
          pendingSessionRef.current = null;
          sessionRestoredRef.current = true;
          return;
        }

        setAudioFile(restoredFile);
        fileHashRef.current = session.fileHash;

        const context = getAudioContext();
        const wavHeaderInfo = parseWavHeader(arrayBuf.slice(0, 44 + 4096));
        setWavInfo(wavHeaderInfo);
        if (!wavHeaderInfo && session.fileHash) {
          try {
            const infoRes = await fetch(`/api/v1/audio-info/${session.fileHash}`);
            if (seq !== restoreSeqRef.current) return;
            if (infoRes.ok) {
              const ai = await infoRes.json();
              if (seq !== restoreSeqRef.current) return;
              const infoFromApi: WavInfo = {
                sampleRate: ai.sample_rate,
                channels: ai.channels,
                duration: ai.duration,
                bitDepth: ai.sample_width * 8,
              };
              setWavInfo(infoFromApi);
            }
          } catch {}
        }
        const { audioBuffer: workerBuffer, analysis: workerAnalysis } = await audioWorker.decodeAndAnalyze(context, arrayBuf);
        if (seq !== restoreSeqRef.current) return;
        const buffer = workerBuffer || await context.decodeAudioData(arrayBuf);
        if (seq !== restoreSeqRef.current) return;

        setAudioBuffer(buffer);
        setDuration(buffer.duration);
        durationRef.current = buffer.duration;
        setCurrentTime(0);
        pausedAtRef.current = 0;

        if (workerAnalysis) setAudioAnalysis(workerAnalysis);

        setTaskId(session.taskId);
        taskIdRef.current = session.taskId;

        if (session.hasBeenProcessed && taskStatus!.status === 'completed') {
          try {
            const previewUrl = getPreviewUrl(session.taskId, 'repaired');
            const repairedBuffer = await downloadWithProgress(previewUrl);
            if (seq !== restoreSeqRef.current) return;
            const tempContext = new OfflineAudioContext(1, 1, processingOptions.sampleRate);
            const decoded = await tempContext.decodeAudioData(repairedBuffer);
            backendProcessedBufferRef.current = decoded;
            setBackendProcessedBuffer(decoded);
            setHasBeenProcessed(true);
            setPlayMode('backend');
          } catch (e) {
            console.warn('[useAudioProcessor] 恢复修复后音频失败:', e);
          }
        }

        if (session.repairResult) {
          try { setRepairResult(JSON.parse(session.repairResult)); } catch {}
        }
        if (session.processingOptions) {
          try {
            const restoredOpts = JSON.parse(session.processingOptions);
            if (restoredOpts.sampleRate && restoredOpts.bitDepth) {
              setProcessingOptionsState(prev => ({ ...prev, ...restoredOpts }));
            }
          } catch {}
        }

        if (restoredFile) {
          saveSession({
            file: restoredFile,
            fileName: session.fileName,
            fileSize: restoredFile.size,
            fileHash: session.fileHash,
            taskId: session.taskId,
            backendAvailable: true,
            hasBeenProcessed: session.hasBeenProcessed,
            wavInfo: wavInfoRef.current ? JSON.stringify(wavInfoRef.current) : '',
            repairResult: session.repairResult || '',
            processingOptions: session.processingOptions || JSON.stringify(processingOptionsRef.current),
          });
        }

        sessionRestoredRef.current = true;
        pendingSessionRef.current = null;
        writeLog(`[useAudioProcessor] 会话恢复完成 seq=${seq}`);
      } catch (e) {
        if (seq !== restoreSeqRef.current) return;
        console.warn('[useAudioProcessor] 会话恢复失败（不清除会话，下次刷新可重试）:', e);
        pendingSessionRef.current = null;
        sessionRestoredRef.current = true;
      }
    })();
  }, [backendAvailable, getAudioContext, useRepairSessionStore.persist.hasHydrated()]);

  const stopAllModeNodes = useCallback((immediate = true) => {
    const context = audioContextRef.current;
    (Object.keys(modeNodesRef.current) as PlayMode[]).forEach((mode) => {
      const node = modeNodesRef.current[mode];
      if (!node) return;
      try {
        // 清除 onended 回调，防止它调用 stopPlaying 影响新音频
        node.source.onended = null;
        if (!immediate && context) {
          // 使用 Web Audio API 调度淡出，不依赖 setTimeout
          const now = context.currentTime;
          node.gain.gain.setValueAtTime(node.gain.gain.value, now);
          node.gain.gain.linearRampToValueAtTime(0.0001, now + 0.03);
          node.source.stop(now + 0.03);
        } else {
          try { node.source.stop(); } catch {}
          try { node.source.disconnect(); } catch {}
          try { node.gain.disconnect(); } catch {}
        }
      } catch {}
      modeNodesRef.current[mode] = null;
    });
    sourceNodeRef.current = null;
    gainNodeRef.current = null;
  }, []);

  const stopPlaying = useCallback((immediate = true) => {
    stopAllModeNodes(immediate);
    pendingPlayRef.current = false;
    pendingObjectURLRef.current = null;

    if (mediaSourceRef.current) {
      try { mediaSourceRef.current.disconnect(); } catch {}
      mediaSourceRef.current = null;
    }
    if (streamingAudioRef.current) {
      streamingAudioRef.current.pause();
      streamingAudioRef.current.src = '';
      streamingAudioRef.current = null;
    }
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }
    isPlayingRef.current = false;
    setIsPlaying(false);
  }, [stopAllModeNodes]);

  const closeWS = useCallback(() => {
    if (wsControlRef.current) {
      wsControlRef.current.close();
      wsControlRef.current = null;
    }
  }, []);

  const startStreamingPlayback = useCallback((url: string, mode: PlayMode = 'backend') => {
    stopPlaying();

    const context = getAudioContext();
    if (context.state === 'suspended') {
      context.resume();
    }

    const audio = new Audio();
    audio.crossOrigin = 'anonymous';
    audio.src = url;

    const source = context.createMediaElementSource(audio);
    source.connect(analyserRef.current!);

    streamingAudioRef.current = audio;
    mediaSourceRef.current = source;

    audio.play().catch(err => {
      console.warn('[startStreamingPlayback] 播放失败:', err);
    });

    isPlayingRef.current = true;
    setIsPlaying(true);
    activeModeRef.current = mode;
    setPlayMode(mode);
    startTimeRef.current = context.currentTime;
    pausedAtRef.current = 0;
    setCurrentTime(0);

    const lastUiUpdateRef = { current: 0 };
    const updateTime = () => {
      if (isPlayingRef.current && streamingAudioRef.current) {
        const current = streamingAudioRef.current.currentTime;
        const now = performance.now();
        if (now - lastUiUpdateRef.current >= 100) {
          setCurrentTime(current);
          lastUiUpdateRef.current = now;
        }
        if (streamingAudioRef.current.ended) {
          stopPlaying();
          setCurrentTime(0);
          pausedAtRef.current = 0;
        } else {
          animationFrameRef.current = requestAnimationFrame(updateTime);
        }
      }
    };
    audio.addEventListener('playing', () => {
      updateTime();
    });

    audio.onended = () => {
      if (isPlayingRef.current) {
        stopPlaying();
        setCurrentTime(0);
        pausedAtRef.current = 0;
      }
    };
  }, [getAudioContext, stopPlaying]);

  const loadAudioFile = useCallback(async (file: File) => {
    const seq = ++loadAudioSeqRef.current;
    stopPlaying();
    closeWS();
    setBackendError(null);
    setAudioFile(file);

    audioBufferRef.current = null;
    setAudioBuffer(null);
    backendProcessedBufferRef.current = null;
    setBackendProcessedBuffer(null);
    setCurrentTime(0);
    pausedAtRef.current = 0;
    setHasBeenProcessed(false);
    setPlayMode('original');
    useRepairSessionStore.getState().clearSingleTrack();
    setTaskId(null);
    taskIdRef.current = null;
    setRepairResult(null);
    setBackendWaveformPeaks(null);
    setOriginalWaveformPeaks(null);
    setBackendPreviewUrl(null);
    setAudioAnalysis(null);
    setDuration(0);
    durationRef.current = 0;
    setWavInfo(null);

    setProcessingStep('读取音频信息...');
    setIsProcessing(true);
    setIsDecodingAudio(true);
    setProcessingProgress(0.02);
    const headerBuf = await file.slice(0, 44 + 4096).arrayBuffer();
    if (seq !== loadAudioSeqRef.current) return;
    const wavHeaderInfo = parseWavHeader(headerBuf);
    setWavInfo(wavHeaderInfo);

    if (wavHeaderInfo) {
      setDuration(wavHeaderInfo.duration);
      durationRef.current = wavHeaderInfo.duration;
    }

    if (pendingObjectURLRef.current) {
      URL.revokeObjectURL(pendingObjectURLRef.current);
    }
    pendingObjectURLRef.current = URL.createObjectURL(file);

    setIsProcessing(false);
    setProcessingStep('');
    setProcessingProgress(0);

    const [arrayBuf, hash] = await Promise.all([
      file.arrayBuffer(),
      computeFileHash(file),
    ]);
    if (seq !== loadAudioSeqRef.current) return;
    fileHashRef.current = hash;
    setFileHash(hash);
    writeLog(`[loadAudioFile] fileHash=${hash.slice(0, 16)}`);

    let cachedAnalysis: AudioAnalysis | null = null;
    let cachedWavInfo: WavInfo | null = null;
    try {
      const cacheRes = await fetch(`/api/v1/analysis-cache/${hash}`);
      if (cacheRes.ok) {
        const cacheData = await cacheRes.json();
        if (cacheData.found && cacheData.data) {
          const d = cacheData.data;
          if (d.wav_info) cachedWavInfo = JSON.parse(d.wav_info);
          if (d.analysis) cachedAnalysis = JSON.parse(d.analysis);
          writeLog(`[loadAudioFile] 后端分析缓存命中: fileHash=${hash.slice(0, 16)}`);
          if (cachedWavInfo) setWavInfo(cachedWavInfo);
          if (cachedAnalysis) setAudioAnalysis(cachedAnalysis);
        }
      }
    } catch { /* 缓存读取失败，继续正常流程 */ }

    const context = getAudioContext();
    let buffer: AudioBuffer;
    const workerDecoded = await audioWorker.decodeWav(context, arrayBuf);
    const isNonWavFile = !workerDecoded;
    if (workerDecoded) {
      buffer = workerDecoded;
      writeLog(`[loadAudioFile] WAV PCM Worker解码完成`);
    } else {
      const decodedWavUrl = `/api/v1/decoded-wav/${hash}`;
      let usedDecodedCache = false;
      try {
        const headRes = await fetch(decodedWavUrl, { method: 'HEAD' });
        if (headRes.ok && headRes.headers.get('Content-Length')) {
          writeLog(`[loadAudioFile] 发现后端解码WAV缓存，下载快速解码`);
          const wavBuf = await downloadWithProgress(decodedWavUrl);
          const cachedBuf = await audioWorker.decodeWav(context, wavBuf);
          if (cachedBuf) {
            buffer = cachedBuf;
            usedDecodedCache = true;
            writeLog(`[loadAudioFile] 后端解码WAV缓存Worker解码完成`);
          }
        }
      } catch { /* 解码缓存不可用，继续正常流程 */ }

      if (!usedDecodedCache) {
        buffer = await context.decodeAudioData(arrayBuf);
        writeLog(`[loadAudioFile] 浏览器解码完成`);
      }
    }
    if (seq !== loadAudioSeqRef.current) return;

    audioBufferRef.current = buffer;
    setAudioBuffer(buffer);
    setDuration(buffer.duration);
    durationRef.current = buffer.duration;
    setIsDecodingAudio(false);

    if (pendingPlayRef.current && streamingAudioRef.current) {
      const resumeTime = streamingAudioRef.current.currentTime;
      pausedAtRef.current = resumeTime;
      streamingAudioRef.current.pause();
      streamingAudioRef.current.src = '';
      streamingAudioRef.current = null;
      if (mediaSourceRef.current) {
        try { mediaSourceRef.current.disconnect(); } catch {}
        mediaSourceRef.current = null;
      }
      pendingPlayRef.current = false;
      pendingObjectURLRef.current = null;
      writeLog(`[loadAudioFile] 从streaming切换到BufferSource播放 offset=${resumeTime.toFixed(3)}`);
      play();
    } else if (pendingPlayRef.current) {
      pendingPlayRef.current = false;
      pendingObjectURLRef.current = null;
      writeLog(`[loadAudioFile] 执行pendingPlay`);
      play();
    }

    let analysis = cachedAnalysis;
    if (!analysis) {
      const channelData: Float32Array[] = [];
      for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
        channelData.push(buffer.getChannelData(ch));
      }
      analysis = await audioWorker.analyzeAudio(channelData, buffer.sampleRate, buffer.numberOfChannels);
    }
    setAudioAnalysis(analysis);

    if (!cachedAnalysis) {
      fetch('/api/v1/analysis-cache', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          quick_hash: hash,
          file_name: file.name,
          file_size: file.size,
          wav_info: JSON.stringify(wavHeaderInfo || cachedWavInfo),
          analysis: JSON.stringify(analysis),
        }),
      }).catch(() => { /* 忽略缓存写入失败 */ });
      saveAnalysisCache({
        fileHash: hash,
        fileName: file.name,
        fileSize: file.size,
        wavInfo: JSON.stringify(wavHeaderInfo || cachedWavInfo),
        analysis: JSON.stringify(analysis),
      }).catch(() => {});
    }

    (async () => {
      try {
        writeLog(`[loadAudioFile] 后台上传开始...`);
        const uploadRes = await uploadAudio(file, undefined, hash);
        if (seq !== loadAudioSeqRef.current) return;

        const newTaskId = uploadRes.task_id;
        setTaskId(newTaskId);
        taskIdRef.current = newTaskId;
        setBackendAvailable(true);
        useRepairSessionStore.getState().setSingleTrackFile(hash, file.name);
        if (uploadRes.cached) {
          writeLog(`[loadAudioFile] 文件已缓存，跳过上传 taskId=${newTaskId}`);
        } else {
          writeLog(`[loadAudioFile] 上传成功 taskId=${newTaskId}`);
        }

        if (uploadRes.audio_info && !wavHeaderInfo) {
          const ai = uploadRes.audio_info;
          const infoFromApi: WavInfo = {
            sampleRate: ai.sample_rate,
            channels: ai.channels,
            duration: ai.duration,
            bitDepth: ai.sample_width * 8,
          };
          setWavInfo(infoFromApi);
          setDuration(ai.duration);
          durationRef.current = ai.duration;
          writeLog(`[loadAudioFile] 从audio_info获取规格: sr=${ai.sample_rate} ch=${ai.channels} dur=${ai.duration.toFixed(1)}`);
        }

        saveSession({
          file,
          fileName: file.name,
          fileSize: file.size,
          fileHash: hash,
          taskId: newTaskId,
          backendAvailable: true,
          hasBeenProcessed: false,
          wavInfo: wavInfoRef.current ? JSON.stringify(wavInfoRef.current) : '',
          repairResult: '',
          processingOptions: JSON.stringify(processingOptionsRef.current),
        });

        if (isNonWavFile) {
          fetch(`/api/v1/decoded-wav/${hash}`, { method: 'POST' }).catch(() => {});
          writeLog(`[loadAudioFile] 触发后端解码WAV缓存创建`);
        }

        fetch(`/api/v1/waveform/${hash}`)
          .then(res => res.ok ? res.json() : null)
          .then(data => {
            if (data?.peaks && seq === loadAudioSeqRef.current) {
              setOriginalWaveformPeaks(data.peaks);
              writeLog(`[loadAudioFile] 原始波形缓存已加载`);
            }
          })
          .catch(() => {});

        pendingSessionRef.current = null;
        sessionRestoredRef.current = true;
        writeLog(`[loadAudioFile] 新文件上传完成，阻止旧会话恢复`);
      } catch (err) {
        console.warn('[loadAudioFile] 上传失败:', err);
        setBackendAvailable(false);
      }
    })();
  }, [getAudioContext, stopPlaying]);

  const applyRepairMode = useCallback((mode: RepairMode) => {
    setSelectedMode(mode.name);
    setParams(mode.params);
  }, []);

  // 标记：用户手动编辑参数（区别于 applyRepairMode / 初始化设置 params）
  const userEditingParamRef = useRef(false);

  const updateParam = useCallback((key: keyof AIRepairParams, value: number) => {
    userEditingParamRef.current = true;
    setParams(prev => ({ ...prev, [key]: value }));
  }, []);

  // 当用户手动修改参数时，检查是否仍命中某个预设模式，自动联动 selectedMode
  useEffect(() => {
    if (!userEditingParamRef.current) return;
    userEditingParamRef.current = false;
    if (repairModes.length === 0) return;
    const matched = repairModes.find(m => {
      return (Object.keys(m.params) as (keyof AIRepairParams)[]).every(
        k => m.params[k] === params[k]
      );
    });
    setSelectedMode(matched ? matched.name : '');
  }, [params, repairModes]);

  const updateProcessingOptions = useCallback((options: Partial<ProcessingOptions>) => {
    setProcessingOptionsState(prev => ({ ...prev, ...options }));
  }, []);

  const loadAudioFromUrl = useCallback(async (url: string, targetSampleRate?: number, silent?: boolean): Promise<AudioBuffer> => {
    const arrayBuffer = await downloadWithProgress(url, (loaded, total, speed) => {
      if (silent) return;
      const pct = total > 0 ? loaded / total : 0;
      setProcessingStep(`下载中 ${formatBytes(loaded)}/${formatBytes(total)} ${formatSpeed(speed)}`);
      setProcessingProgress(0.96 + pct * 0.03);
    });

    if (targetSampleRate && targetSampleRate !== getAudioContext().sampleRate) {
      const tempContext = new OfflineAudioContext(1, 1, targetSampleRate);
      const tempBuffer = await tempContext.decodeAudioData(arrayBuffer);
      if (tempBuffer.sampleRate === targetSampleRate) {
        return tempBuffer;
      }
      const resampleLength = Math.ceil(tempBuffer.length * targetSampleRate / tempBuffer.sampleRate);
      const offlineCtx = new OfflineAudioContext(
        tempBuffer.numberOfChannels,
        resampleLength,
        targetSampleRate,
      );
      const source = offlineCtx.createBufferSource();
      source.buffer = tempBuffer;
      source.connect(offlineCtx.destination);
      source.start();
      return offlineCtx.startRendering();
    }

    const context = getAudioContext();
    if (context.state === 'suspended') {
      await context.resume();
    }
    return context.decodeAudioData(arrayBuffer);
  }, [getAudioContext]);

  const applySettings = useCallback(async () => {
    if (!audioBuffer) return;

    setIsProcessing(true);
    setProcessingProgress(0);
    const REPAIR_TERMINALS = new Set(['completed', 'error']);
    let currentTaskId = taskIdRef.current;
    const backendProg = { value: 0 };

    writeLog(`[applySettings] ===== 开始修复流程 =====`);
    writeLog(`[applySettings] 初始状态: currentTaskId=${currentTaskId}, fileHash=${fileHashRef.current || 'none'}`);

    let effectiveAlgorithmVersion = algorithmVersion;
    if (availableAlgorithms.length > 0) {
      const current = availableAlgorithms.find(v => v.name === algorithmVersion);
      if (!current) {
        effectiveAlgorithmVersion = availableAlgorithms[0].name;
        writeLog(`[applySettings] 当前版本 ${algorithmVersion} 不可用，使用有效版本 ${effectiveAlgorithmVersion}`);
        setAlgorithmVersionState(effectiveAlgorithmVersion);
      }
    }

    const currentParamsForCache = mapParamsToBackend(params, processingOptions, effectiveAlgorithmVersion);

    // ===== 路径A：纯数据驱动缓存查询（不依赖任务状态）=====
    if (fileHashRef.current && !forceReRepairRef.current) {
      writeLog(`[applySettings] 查询缓存: hash=${fileHashRef.current}`);
      try {
        const cacheResult = await lookupRepairCache(fileHashRef.current, currentParamsForCache);
        if (cacheResult.found) {
          writeLog(`[applySettings] ✅ 修复缓存命中 taskId=${cacheResult.task_id}`);
          setIsProcessing(false);
          setCacheHitInfo({
            repair: {
              task_id: cacheResult.task_id || '',
              output_size: cacheResult.output_size || 0,
              repair_result: cacheResult.repair_result || undefined,
              detection_result: cacheResult.detection_result,
              repaired_detection_result: cacheResult.repaired_detection_result,
            },
            renderCaches: [],
          });
          let renderCaches: RenderCacheEntry[] = [];
          const cachedTaskId = cacheResult.task_id;
          if (cachedTaskId) {
            try {
              renderCaches = await fetchRenderCache(cachedTaskId);
              writeLog(`[applySettings] 渲染缓存: ${renderCaches.length} 个命中`);
            } catch {
              writeLog(`[applySettings] 渲染缓存查询失败`);
            }
          }
          setCacheHitInfo(prev => prev ? { ...prev, renderCaches } : null);
          setShowRepairCacheModal(true);
          return;
        } else {
          writeLog(`[applySettings] 缓存未命中`);
        }
      } catch (cacheErr) {
        writeLog(`[applySettings] 缓存查询失败: ${cacheErr instanceof Error ? cacheErr.message : String(cacheErr)}`);
      }
    }
    if (forceReRepairRef.current) {
      forceReRepairRef.current = false;
    }

    // ===== 路径B：正常修复流程（上传 + Promise链）=====
    writeLog(`[applySettings] 进入正常修复流程`);

    if (!currentTaskId) {
      if (!audioFile) {
        writeLog(`[applySettings] 没有音频文件，无法创建任务`);
        setIsProcessing(false);
        return;
      }

      setProcessingStep('上传到后端...');
      setProcessingProgress(0.01);
      let uploadRes;
      try {
        uploadRes = await uploadAudio(audioFile, undefined, fileHashRef.current || undefined);
      } catch (uploadErr) {
        const msg = uploadErr instanceof Error ? uploadErr.message : String(uploadErr);
        console.warn('[applySettings] 上传失败:', msg);
        writeLog(`[applySettings] 上传失败: ${msg}`);
        setBackendError('上传失败: ' + msg);
        setProcessingStep('[上传失败] ' + msg);
        setIsProcessing(false);
        return;
      }
      currentTaskId = uploadRes.task_id;
      setTaskId(currentTaskId);
      taskIdRef.current = currentTaskId;
      setBackendAvailable(true);
      writeLog(`[applySettings] 上传完成: taskId=${currentTaskId}, cached=${uploadRes.cached}`);
    } else {
      writeLog(`[applySettings] 跳过上传: currentTaskId=${currentTaskId}, audioFile=${!!audioFile}`);
    }
    
    writeLog(`[applySettings] 创建 Promise 前: taskIdRef=${taskIdRef.current}`);

    const updateCombinedProgress = (source: string) => {
      writeLog(`[progress][${source}] taskId=${taskIdRef.current}, backend=${backendProg.value.toFixed(2)}`);
      setProcessingProgress(backendProg.value);
    };

    const backendRepairPromise = taskIdRef.current ? (async () => {
      try {
        setBackendAvailable(true);
        const taskId = taskIdRef.current!;
        writeLog(`[backend] 开始修复 taskId=${taskId}`);

        // 先建立 WebSocket 连接，再提交任务
        const repairResultData = await new Promise<import('../services/backendApi').ProgressEvent>((resolve, reject) => {
          wsControlRef.current = connectProgressWS(
            taskId,
            {
              onProgress: (event) => {
                backendProg.value = 0.1 + event.progress * 0.8;
                updateCombinedProgress('backend-ws');
                setProcessingSource('backend');
                setProcessingStep(event.step);
              },
              onError: reject,
              onComplete: resolve,
              onStuck: (info) => {
                setIsTaskStuck(true);
                setStuckInfo(info);
              },
              onUnstuck: () => {
                setIsTaskStuck(false);
              },
              onQueueUpdate: (queue) => {
                setQueueStatus(queue);
              },
            },
            REPAIR_TERMINALS,
          );
          // WebSocket 连接已建立，现在提交任务
          repairAudio(taskId, params, processingOptions, effectiveAlgorithmVersion).catch(reject);
        });
        writeLog(`[backend] WebSocket 连接完成, status=${repairResultData.status}`);

        writeLog(`[applySettings] 后端轮询结束 status=${repairResultData.status}`);

        if (repairResultData.status !== 'completed') {
          throw new Error(repairResultData.error || `修复失败(status=${repairResultData.status})`);
        }

        const previewUrl = getPreviewUrl(taskId, 'repaired');
        setBackendPreviewUrl(previewUrl);

        return { previewUrl, repairResult: repairResultData.repair_result };
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.warn(`[applySettings] 后端修复失败: ${msg}`);
        setBackendError(msg);
        setProcessingSource('backend');
        setProcessingStep('修复失败: ' + msg);
        setBackendAvailable(false);
        return null;
      }
    })() : Promise.resolve(null);

    writeLog(`[applySettings] 开始后端修复`);
    const startTime = Date.now();
    const backendResult = await backendRepairPromise;
    writeLog(`[applySettings] 修复完成, 耗时=${Date.now() - startTime}ms`);

    let anySuccess = false;

    if (backendResult) {
      if (backendResult.repairResult) {
        setRepairResult({
          ...backendResult.repairResult,
          completed_at: new Date().toISOString(),
        });
        if (backendResult.repairResult.waveform_peaks) {
          setBackendWaveformPeaks(backendResult.repairResult.waveform_peaks);
        }
      }
      anySuccess = true;

      const previewUrl = backendResult.previewUrl;
      if (previewUrl) {
        writeLog(`[applySettings] 修复完成，预览URL已就绪: ${previewUrl}`);
      }

      if (audioFile && taskIdRef.current) {
        loadAudioFromUrl(previewUrl, processingOptionsRef.current.sampleRate, true).then(repairedBuffer => {
          writeLog(`[applySettings] buffer加载完成: duration=${repairedBuffer.duration.toFixed(3)}`);
          backendProcessedBufferRef.current = repairedBuffer;
          setBackendProcessedBuffer(repairedBuffer);
        }).catch(err => {
          console.warn('[applySettings] 后台下载修复后音频失败:', err);
        });
      }
    }

    if (anySuccess) {
      setHasBeenProcessed(true);
      useRepairSessionStore.getState().setSingleTrackProcessed(true);

      if (audioFile && taskIdRef.current) {
        saveSession({
          file: audioFile,
          fileName: audioFile.name,
          fileSize: audioFile.size,
          fileHash: fileHashRef.current || '',
          taskId: taskIdRef.current,
          backendAvailable: !!backendResult,
          hasBeenProcessed: true,
          wavInfo: wavInfoRef.current ? JSON.stringify(wavInfoRef.current) : '',
          repairResult: backendResult?.repairResult
            ? JSON.stringify(backendResult.repairResult)
            : '',
          processingOptions: JSON.stringify(processingOptionsRef.current),
        });
      }

      if (backendResult && taskIdRef.current) {
        forceRenderRef.current = true;
        const currentOpts = { ...processingOptions };
        renderAndDownload(currentOpts).then(result => {
          if (result?.downloadUrl) {
            setRenderDownloadUrl(result.downloadUrl);
          }
          setShowDownloadModal(true);
        }).catch(err => {
          writeLog(`[applySettings] 自动渲染失败: ${err}`);
          setShowDownloadModal(true);
        });
      }
    }

    if (backendResult) {
      setProcessingStep('完成!');
    }
    setProcessingProgress(1);

    if (!backendResult) {
      setIsProcessing(false);
      setTimeout(() => {
        setProcessingStep('');
        setProcessingSource(null);
        setProcessingProgress(0);
      }, 2000);
    }
  }, [audioBuffer, audioFile, params, processingOptions, loadAudioFromUrl, wavInfo]);

  const resetParams = useCallback(() => {
    setParams(defaultAIRepairParams);
    setSelectedMode('全面修复');
    resetStoredSettings();
  }, []);

  // ========== 修复参数配置管理 ==========

  const getSavedProfiles = useCallback((): import('../utils/settingsStorage').ProfileConfig[] => {
    const settings = loadSettings();
    return settings.savedProfiles || [];
  }, []);

  const saveProfile = useCallback((name: string) => {
    saveProfileToStorage(name, params, algorithmVersion);
  }, [params, algorithmVersion]);

  const applyProfile = useCallback((id: string) => {
    const settings = loadSettings();
    const profile = (settings.savedProfiles || []).find(p => p.id === id);
    if (!profile) return;
    setParams(profile.params);
    setAlgorithmVersionState(profile.algorithmVersion);
    setSelectedMode('');
  }, []);

  const deleteProfile = useCallback((id: string) => {
    const settings = loadSettings();
    const updated = (settings.savedProfiles || []).filter(p => p.id !== id);
    saveSettings({ savedProfiles: updated });
  }, []);

  const renameProfile = useCallback((id: string, newName: string) => {
    const settings = loadSettings();
    const updated = (settings.savedProfiles || []).map(p =>
      p.id === id ? { ...p, name: newName } : p
    );
    saveSettings({ savedProfiles: updated });
  }, []);

  // 重置卡住状态
  const resetStuckState = useCallback(() => {
    setIsTaskStuck(false);
    setStuckInfo(null);
  }, []);

  const clearBackendError = useCallback(() => setBackendError(null), []);

  const cancelCurrentTask = useCallback(async () => {
    const currentTaskId = taskIdRef.current;
    if (currentTaskId) {
      try {
        await cancelTask(currentTaskId);
      } catch (e) {
        console.warn('[cancelCurrentTask] 后端取消失败:', e);
      }
    }
    closeWS();
    resetStuckState();
    setIsProcessing(false);
    setProcessingStep('');
    setProcessingProgress(0);
  }, [taskIdRef, resetStuckState]);

  const runBackendDiag = useCallback(async () => {
    const lines: string[] = [];
    lines.push(`时间: ${new Date().toLocaleTimeString()}`);
    lines.push(`页面URL: ${window.location.href}`);
    lines.push(`hostname: ${window.location.hostname}`);
    lines.push(`protocol: ${window.location.protocol}`);

    lines.push('');
    lines.push('--- /health 测试 ---');
    try {
      const t0 = performance.now();
      const res = await fetch('/health', { signal: AbortSignal.timeout(5000) });
      const t1 = performance.now();
      const text = await res.text();
      lines.push(`状态: ${res.status} ${res.statusText}`);
      lines.push(`耗时: ${Math.round(t1 - t0)}ms`);
      lines.push(`响应: ${text.substring(0, 200)}`);
    } catch (e: any) {
      lines.push(`失败: ${e?.message || e}`);
    }

    lines.push('');
    lines.push('--- /api/v1/upload 测试(有效WAV) ---');
    try {
      const wavBlob = createValidWavBlob(1, 44100, 0.5);
      const file = new File([wavBlob], 'diag.wav', { type: 'audio/wav' });
      const form = new FormData();
      form.append('file', file);
      const t0 = performance.now();
      const res = await fetch('/api/v1/upload', { method: 'POST', body: form, signal: AbortSignal.timeout(5000) });
      const t1 = performance.now();
      const text = await res.text();
      lines.push(`状态: ${res.status} ${res.statusText}`);
      lines.push(`耗时: ${Math.round(t1 - t0)}ms`);
      lines.push(`响应: ${text.substring(0, 200)}`);
    } catch (e: any) {
      lines.push(`失败: ${e?.message || e}`);
    }

    lines.push('');
    lines.push('--- 完整流程测试: 上传→检测→轮询(有效WAV) ---');
    try {
      const wavBlob = createValidWavBlob(1, 44100, 0.5);
      const file = new File([wavBlob], 'diag.wav', { type: 'audio/wav' });
      const form = new FormData();
      form.append('file', file);
      const uploadRes = await fetch('/api/v1/upload', { method: 'POST', body: form, signal: AbortSignal.timeout(10000) });
      const uploadData = await uploadRes.json();
      lines.push(`上传: status=${uploadRes.status} task_id=${uploadData.task_id}`);

      if (uploadData.task_id) {
        const detectRes = await fetch('/api/v1/detect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_id: uploadData.task_id, type: 'original' }),
          signal: AbortSignal.timeout(5000),
        });
        const detectData = await detectRes.json();
        lines.push(`检测提交: status=${detectRes.status} msg=${detectData.message || detectData.detail}`);

        lines.push('轮询状态(最多30次, 每2秒):');
        for (let i = 0; i < 30; i++) {
          await new Promise(r => setTimeout(r, 2000));
          try {
            const statusRes = await fetch(`/api/v1/status/${uploadData.task_id}`, { signal: AbortSignal.timeout(5000) });
            const statusData = await statusRes.json();
            lines.push(`  [${i+1}] status=${statusData.status} progress=${statusData.progress?.toFixed?.(2) ?? statusData.progress} step=${statusData.step} err=${statusData.error || 'none'}`);
            if (['completed', 'detected', 'error'].includes(statusData.status)) break;
          } catch (e: any) {
            lines.push(`  [${i+1}] 轮询失败: ${e?.message || e}`);
            break;
          }
        }
      }
    } catch (e: any) {
      lines.push(`完整流程失败: ${e?.message || e}`);
    }

    const diagText = lines.join('\n');
    setBackendDiag(diagText);
    writeLog('[BackendDiag]\n' + diagText);

    const hasHealthOk = lines.some(l => l.includes('"status":"ok"'));
    const has200 = lines.some(l => l.includes('状态: 200'));
    setBackendAvailable(hasHealthOk && has200);
    return diagText;
  }, []);

  const getCurrentBuffer = useCallback(() => {
    if (playMode === 'backend') return backendProcessedBufferRef.current;
    return audioBufferRef.current;
  }, [playMode]);

  const play = useCallback(async () => {
    writeLog(`[play] 开始播放: playMode=${playMode}, isPlaying=${isPlayingRef.current}, activeMode=${activeModeRef.current}`);

    if (playMode === 'backend' && streamingAudioRef.current && !backendProcessedBufferRef.current) {
      writeLog(`[play] 使用streaming播放`);
      streamingAudioRef.current.play().catch(() => {});
      isPlayingRef.current = true;
      setIsPlaying(true);
      activeModeRef.current = 'backend';
      const lastUiUpdateRef = { current: 0 };
      const updateTime = () => {
        if (isPlayingRef.current && streamingAudioRef.current) {
          const current = streamingAudioRef.current.currentTime;
          const now = performance.now();
          if (now - lastUiUpdateRef.current >= 100) {
            setCurrentTime(current);
            lastUiUpdateRef.current = now;
          }
          if (streamingAudioRef.current.ended) {
            stopPlaying();
            setCurrentTime(0);
            pausedAtRef.current = 0;
          } else {
            animationFrameRef.current = requestAnimationFrame(updateTime);
          }
        }
      };
      updateTime();
      return;
    }

    if (streamingAudioRef.current) {
      writeLog(`[play] 停止streaming，切换到buffer播放`);
      const resumeTime = streamingAudioRef.current.currentTime;
      streamingAudioRef.current.pause();
      streamingAudioRef.current = null;
      if (mediaSourceRef.current) {
        try { mediaSourceRef.current.disconnect(); } catch {}
        mediaSourceRef.current = null;
      }
      if (resumeTime > 0) {
        pausedAtRef.current = resumeTime;
      }
    }

    const buffer = getCurrentBuffer() ?? audioBufferRef.current;
    if (!buffer) {
      if (durationRef.current > 0 && pendingObjectURLRef.current) {
        writeLog(`[play] buffer未就绪，使用streaming播放`);
        startStreamingPlayback(pendingObjectURLRef.current, 'original');
        pendingPlayRef.current = true;
        return;
      }
      if (durationRef.current > 0) {
        writeLog(`[play] buffer未就绪，标记pendingPlay`);
        pendingPlayRef.current = true;
      }
      return;
    }

    const context = getAudioContext();
    if (context.state === 'suspended') {
      await context.resume();
      await new Promise(resolve => setTimeout(resolve, 50));
    }

    // seek 时停止所有模式节点，重新创建
    if (seekInProgressRef.current) {
      writeLog(`[play] seek模式，停止所有节点`);
      stopAllModeNodes();
      seekInProgressRef.current = false;
    }

    // 检查是否已有节点在运行（保护逻辑）
    if (modeNodesRef.current[playMode]) {
      writeLog(`[play] 警告: 当前模式已有节点，先停止`);
      try {
        const node = modeNodesRef.current[playMode]!;
        node.source.onended = null;
        node.source.stop();
        node.source.disconnect();
        node.gain.disconnect();
      } catch {}
      modeNodesRef.current[playMode] = null;
    }

    // 创建当前模式的音频节点
    writeLog(`[play] 创建新节点: mode=${playMode}, bufferDuration=${buffer.duration.toFixed(3)}`);
    const source = context.createBufferSource();
    const gain = context.createGain();

    source.buffer = buffer;
    source.connect(gain);
    gain.connect(analyserRef.current!);

    // 使用淡入避免爆音
    const fadeInDuration = 0.015; // 15ms 淡入
    gain.gain.setValueAtTime(0, context.currentTime);
    gain.gain.linearRampToValueAtTime(1.0, context.currentTime + fadeInDuration);

    let playOffset = pausedAtRef.current;
    if (playOffset >= buffer.duration) {
      pausedAtRef.current = 0;
      playOffset = 0;
    }

    source.onended = () => {
      writeLog(`[play] 节点播放结束`);
      if (isPlayingRef.current) {
        stopPlaying();
        setCurrentTime(0);
        pausedAtRef.current = 0;
      }
    };

    modeNodesRef.current[playMode] = { source, gain };
    sourceNodeRef.current = source;
    gainNodeRef.current = gain;
    activeModeRef.current = playMode;

    playStartTimeRef.current = performance.now();
    startTimeRef.current = context.currentTime - playOffset;
    source.start(0, playOffset);
    writeLog(`[play] 节点已启动: offset=${playOffset.toFixed(3)}`);

    isPlayingRef.current = true;
    setIsPlaying(true);

    const lastUiUpdateRef = { current: 0 };
    const updateTime = () => {
      if (isPlayingRef.current) {
        const elapsed = (performance.now() - playStartTimeRef.current) / 1000;
        const current = playOffset + elapsed;
        if (current >= buffer.duration) {
          stopPlaying();
          setCurrentTime(0);
          pausedAtRef.current = 0;
        } else {
          const now = performance.now();
          if (now - lastUiUpdateRef.current >= 100) {
            setCurrentTime(current);
            lastUiUpdateRef.current = now;
          }
          animationFrameRef.current = requestAnimationFrame(updateTime);
        }
      }
    };
    updateTime();
  }, [playMode, getCurrentBuffer, getAudioContext, stopPlaying, stopAllModeNodes, startStreamingPlayback]);

  // 更新 playRef
  useEffect(() => {
    playRef.current = play;
  }, [play]);

  const pause = useCallback(() => {
    if (streamingAudioRef.current) {
      pausedAtRef.current = streamingAudioRef.current.currentTime;
      streamingAudioRef.current.pause();
      isPlayingRef.current = false;
      setIsPlaying(false);
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      return;
    }
    pausedAtRef.current = currentTime;
    stopPlaying();
  }, [currentTime, stopPlaying]);

  const seek = useCallback((time: number) => {
    if (streamingAudioRef.current) {
      streamingAudioRef.current.currentTime = time;
      pausedAtRef.current = time;
      setCurrentTime(time);
      return;
    }
    const wasPlaying = isPlayingRef.current;
    if (isPlayingRef.current) {
      stopPlaying();
    }
    pausedAtRef.current = time;
    setCurrentTime(time);
    if (wasPlaying && playRef.current) {
      seekInProgressRef.current = true;
      playRef.current();
    }
  }, [stopPlaying, playMode, audioBuffer]);

  const switchPlayMode = useCallback(async (mode: PlayMode) => {
    writeLog(`[switchPlayMode] 开始切换: target=${mode}, current=${activeModeRef.current}, isPlaying=${isPlayingRef.current}`);

    const targetBuffer = mode === 'backend' ? backendProcessedBufferRef.current
      : audioBufferRef.current;
    if (!targetBuffer) {
      writeLog(`[switchPlayMode] 目标buffer为空，只切换状态`);
      setPlayMode(mode);
      return;
    }

    if (!isPlayingRef.current) {
      writeLog(`[switchPlayMode] 未在播放，直接切换状态`);
      setPlayMode(mode);
      return;
    }

    if (activeModeRef.current === mode) {
      writeLog(`[switchPlayMode] 已是目标模式，无需操作`);
      setPlayMode(mode);
      return;
    }

    const context = getAudioContext();
    if (context.state === 'suspended') {
      await context.resume();
    }

    const now = context.currentTime;
    const currentElapsed = now - startTimeRef.current;
    const startPosition = Math.min(currentElapsed, targetBuffer.duration - 0.01);

    writeLog(`[switchPlayMode] 停止当前节点: mode=${activeModeRef.current}, position=${startPosition.toFixed(3)}`);

    if (streamingAudioRef.current) {
      writeLog(`[switchPlayMode] 停止streaming音频`);
      try {
        streamingAudioRef.current.pause();
        streamingAudioRef.current.src = '';
      } catch {}
      streamingAudioRef.current = null;
      if (mediaSourceRef.current) {
        try { mediaSourceRef.current.disconnect(); } catch {}
        mediaSourceRef.current = null;
      }
    }

    const currentNode = modeNodesRef.current[activeModeRef.current];
    if (currentNode) {
      try {
        currentNode.source.onended = null;
        currentNode.source.stop(now);
        currentNode.source.disconnect();
        currentNode.gain.disconnect();
        writeLog(`[switchPlayMode] 旧节点已停止并断开`);
      } catch (e) {
        writeLog(`[switchPlayMode] 停止旧节点出错: ${e}`);
      }
    }

    (Object.keys(modeNodesRef.current) as PlayMode[]).forEach((m) => {
      modeNodesRef.current[m] = null;
    });

    writeLog(`[switchPlayMode] 创建新节点: mode=${mode}, bufferDuration=${targetBuffer.duration.toFixed(3)}`);
    const newSource = context.createBufferSource();
    const newGain = context.createGain();
    newSource.buffer = targetBuffer;
    newSource.connect(newGain);
    newGain.connect(analyserRef.current!);

    newGain.gain.setValueAtTime(0, now);
    newGain.gain.linearRampToValueAtTime(1.0, now + 0.01);

    newSource.onended = () => {
      writeLog(`[switchPlayMode] 新节点播放结束`);
      if (isPlayingRef.current) {
        stopPlaying();
        setCurrentTime(0);
        pausedAtRef.current = 0;
      }
    };

    modeNodesRef.current[mode] = { source: newSource, gain: newGain };
    sourceNodeRef.current = newSource;
    gainNodeRef.current = newGain;
    activeModeRef.current = mode;

    startTimeRef.current = now - startPosition;
    newSource.start(now, startPosition);
    writeLog(`[switchPlayMode] 新节点已启动: startTime=${startTimeRef.current.toFixed(3)}, offset=${startPosition.toFixed(3)}`);

    setPlayMode(mode);

    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }

    const updateTime = () => {
      if (isPlayingRef.current) {
        const elapsed = context.currentTime - startTimeRef.current;
        if (elapsed >= targetBuffer.duration) {
          stopPlaying();
          setCurrentTime(0);
          pausedAtRef.current = 0;
        } else {
          setCurrentTime(elapsed);
          animationFrameRef.current = requestAnimationFrame(updateTime);
        }
      }
    };
    updateTime();
  }, [stopPlaying, getAudioContext]);

  const renderAndDownload = useCallback(async (overrideOptions?: ProcessingOptions) => {
    const opts = overrideOptions || processingOptionsRef.current;
    const algoVer = algorithmVersionRef.current;
    const fileName = generateExportFilename(audioFile?.name, algoVer, opts.sampleRate, opts.bitDepth);

    if (!taskIdRef.current) return null;

    try {
      if (!forceRenderRef.current) {
        const caches = await fetchRenderCache(taskIdRef.current);
        const hit = caches.find(c => c.sample_rate === opts.sampleRate && c.bit_depth === opts.bitDepth && c.algorithm_version === algoVer);
        if (hit) {
          writeLog(`[renderAndDownload] 渲染缓存命中: ${hit.filename}`);
          const renderInfo = {
            output_sample_rate: hit.sample_rate,
            output_bit_depth: hit.bit_depth,
            duration: durationRef.current,
            channels: 2,
          };
          setAutoRenderInfo(renderInfo);
          return {
            downloadUrl: `/api/v1/download-file/${hit.filename}`,
            fileName,
            renderInfo,
          };
        }
      }
    } catch { /* 忽略缓存查询失败，继续渲染 */ }

    try {
      writeLog(`[renderAndDownload] 开始渲染: sr=${opts.sampleRate} bd=${opts.bitDepth}`);
      setIsProcessing(true);
      setProcessingSource('backend');
      setProcessingStep('渲染交付规格...');
      setProcessingProgress(0);
      setIsRenderLoading(true);
      await renderAudio(taskIdRef.current, opts.sampleRate, opts.bitDepth);
      const { promise, close } = waitRenderWithWS(taskIdRef.current, (progress, step) => {
        writeLog(`[renderAndDownload] 渲染进度: ${progress} step=${step}`);
        setProcessingProgress(progress);
        setProcessingStep(step);
      });
      wsControlRef.current = { close };
      const renderRes = await promise;
      wsControlRef.current = null;
      setIsRenderLoading(false);
      if (!renderRes.render_filename || !renderRes.render_result) {
        throw new Error('渲染结果不完整');
      }
      writeLog(`[renderAndDownload] 渲染完成: sr=${renderRes.render_result.output_sample_rate} bd=${renderRes.render_result.output_bit_depth}`);
      const renderInfo = {
        output_sample_rate: renderRes.render_result!.output_sample_rate,
        output_bit_depth: renderRes.render_result!.output_bit_depth,
        duration: renderRes.render_result!.duration,
        channels: renderRes.render_result!.channels,
      };
      setAutoRenderInfo(renderInfo);
      setRepairResult(prev => prev ? {
        ...prev,
        output_sample_rate: renderInfo.output_sample_rate,
        output_bit_depth: renderInfo.output_bit_depth,
      } : null);
      setProcessingStep('');
      setProcessingSource(null);
      setProcessingProgress(0);
      setIsProcessing(false);
      return {
        downloadUrl: `/api/v1/download-file/${renderRes.render_filename}`,
        fileName,
        renderInfo,
      };
    } catch (renderErr) {
      wsControlRef.current?.close();
      wsControlRef.current = null;
      setIsRenderLoading(false);
      setIsProcessing(false);
      writeLog(`[renderAndDownload] 渲染失败: ${renderErr}`);
      setProcessingStep('');
      setProcessingSource(null);
      setProcessingProgress(0);
      return null;
    }
  }, [audioFile]);

  useEffect(() => {
    return () => {
      stopPlaying();
    };
  }, [stopPlaying]);

  const originalSampleRate = audioBuffer?.sampleRate ?? 0;
  const currentSampleRate = (() => {
    if (playMode === 'backend' && backendProcessedBuffer) return backendProcessedBuffer.sampleRate;
    return originalSampleRate;
  })();

  const handleUseRepairCache = useCallback((taskId: string) => {
    setShowRepairCacheModal(false);
    writeLog(`[handleUseRepairCache] 使用修复缓存 taskId=${taskId}`);

    const cache = cacheHitInfo?.repair;
    if (!cache) return;

    if (taskId && taskId !== taskIdRef.current) {
      setTaskId(taskId);
      taskIdRef.current = taskId;
    }

    setBackendAvailable(true);

    if (cache.repair_result) {
      setRepairResult({
        ...cache.repair_result,
        completed_at: new Date().toISOString(),
      });
      if (cache.repair_result.waveform_peaks) {
        setBackendWaveformPeaks(cache.repair_result.waveform_peaks);
      }
    }

    const previewUrl = getPreviewUrl(taskId, 'repaired');
    setBackendPreviewUrl(previewUrl);
    setHasBeenProcessed(true);

    if (audioFile && taskId) {
      loadAudioFromUrl(previewUrl, processingOptionsRef.current.sampleRate, true).then(repairedBuffer => {
        backendProcessedBufferRef.current = repairedBuffer;
        setBackendProcessedBuffer(repairedBuffer);
      }).catch(err => {
        console.warn('[handleUseRepairCache] 后台下载缓存音频失败:', err);
      });
    }

    saveSession({
      file: audioFile,
      fileName: audioFile.name,
      fileSize: audioFile.size,
      fileHash: fileHashRef.current || '',
      taskId,
      backendAvailable: true,
      hasBeenProcessed: true,
      wavInfo: wavInfoRef.current ? JSON.stringify(wavInfoRef.current) : '',
      repairResult: cache.repair_result ? JSON.stringify(cache.repair_result) : '',
      processingOptions: JSON.stringify(processingOptionsRef.current),
    });

    // 直接开始渲染下载，确保进度条显示
    writeLog(`[handleUseRepairCache] 开始调用 renderAndDownload`);
    forceRenderRef.current = false;
    const currentOpts = { ...processingOptions };
    renderAndDownload(currentOpts).then(result => {
      writeLog(`[handleUseRepairCache] renderAndDownload 完成: ${!!result}`);
      if (result?.downloadUrl) {
        setRenderDownloadUrl(result.downloadUrl);
      }
      setShowDownloadModal(true);
    }).catch((err) => {
      writeLog(`[handleUseRepairCache] renderAndDownload 失败: ${err}`);
      setShowDownloadModal(true);
    });
  }, [cacheHitInfo, loadAudioFromUrl, wavInfo, renderAndDownload]);

  const handleRenderCacheDownload = useCallback((cache: RenderCacheEntry, downloadUrl: string, filename: string) => {
    writeLog(`[handleRenderCacheDownload] 秒下: ${cache.filename}`);
    setRenderDownloadUrl(downloadUrl);
    setAutoRenderInfo({
      output_sample_rate: cache.sample_rate,
      output_bit_depth: cache.bit_depth,
      duration: durationRef.current,
      channels: 2,
    });
    setShowDownloadModal(true);
  }, []);

  const handleReRepair = useCallback(() => {
    writeLog(`[handleReRepair] 用户选择重新修复`);
    setShowRepairCacheModal(false);
    setCacheHitInfo(null);
    setIsProcessing(true);
    forceReRepairRef.current = true;
    applySettings();
  }, [applySettings]);

  const handleCloseRepairCacheModal = useCallback(() => {
    writeLog(`[handleCloseRepairCacheModal] 关闭模态框`);
    setShowRepairCacheModal(false);
    setIsProcessing(false);
  }, []);

  return {
    audioFile,
    fileHash,
    audioBuffer,
    backendProcessedBuffer,
    backendPreviewUrl,
    isPlaying,
    currentTime,
    duration,
    isProcessing,
    isDecodingAudio,
    processingProgress,
    processingStep,
    processingSource,
    setProcessingSource,
    params,
    audioAnalysis,
    selectedMode,
    playMode,
    repairModes,
    processingOptions,
    hasBeenProcessed,
    originalSampleRate,
    currentSampleRate,
    backendAvailable,
    backendDiag,
    runBackendDiag,
    wavInfo,
    repairResult,
    backendWaveformPeaks,
    algorithmVersion,
    availableAlgorithms,
    applyAlgorithmVersion,
    isTaskStuck,
    stuckInfo,
    queueStatus,
    resetStuckState,
    cancelCurrentTask,
    backendError,
    clearBackendError,
    loadAudioFile,
    play,
    pause,
    seek,
    updateParam,
    resetParams,
    applyRepairMode,
    applySettings,
    switchPlayMode,
    setProcessingOptions: updateProcessingOptions,
    getSavedProfiles,
    saveProfile,
    applyProfile,
    deleteProfile,
    renameProfile,
    analyserRef,
    isRenderLoading,
    taskId,
    renderAndDownload,
    renderDownloadUrl,
    setRenderDownloadUrl,
    showDownloadModal,
    setShowDownloadModal,
    autoRenderInfo,
    showRepairCacheModal,
    setShowRepairCacheModal,
    cacheHitInfo,
    handleUseRepairCache,
    handleRenderCacheDownload,
    handleReRepair,
    handleCloseRepairCacheModal,
    originalWaveformPeaks,
    setIsProcessing,
    setProcessingStep,
    setProcessingProgress,
    setBackendError,
    setHasBeenProcessed,
    setRepairResult,
    setBackendProcessedBuffer,
    setBackendWaveformPeaks,
    loadAudioFromUrl,
    setTaskId,
  };
}

function writeString(view: DataView, offset: number, string: string) {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}

function createValidWavBlob(durationSec: number, sampleRate: number, frequency: number): Blob {
  const numChannels = 1;
  const numSamples = Math.floor(sampleRate * durationSec);
  const bytesPerSample = 2;
  const blockAlign = numChannels * bytesPerSample;
  const dataLength = numSamples * blockAlign;
  const bufferLength = 44 + dataLength;

  const arrayBuffer = new ArrayBuffer(bufferLength);
  const view = new DataView(arrayBuffer);

  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + dataLength, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bytesPerSample * 8, true);
  writeString(view, 36, 'data');
  view.setUint32(40, dataLength, true);

  let offset = 44;
  for (let i = 0; i < numSamples; i++) {
    const t = i / sampleRate;
    const sample = Math.sin(2 * Math.PI * frequency * t) * 0.3;
    const intSample = Math.max(-32768, Math.min(32767, Math.round(sample * 32767)));
    view.setInt16(offset, intSample, true);
    offset += 2;
  }

  return new Blob([arrayBuffer], { type: 'audio/wav' });
}



import { useRef, useState, useCallback, useEffect } from 'react';
import { AIRepairParams, defaultAIRepairParams, detectAudioIssues, RepairMode } from '../utils/advancedAudioProcessing';
import { AISongDetectionResult } from '../utils/aiSongChecker';
import { loadSettings, saveSettings, resetSettings as resetStoredSettings } from '../utils/settingsStorage';
import { parseWavHeader, WavInfo } from '../utils/wavParser';
import { saveSession, loadSession, clearSession } from '../utils/sessionDB';
import {
  uploadAudio,
  detectAudio,
  repairAudio,
  pollProgress,
  pollProgressLegacy,
  connectProgressWS,
  WSProgressControl,
  getPreviewUrl,
  getDownloadUrl,
  cancelTask,
  downloadWithProgress,
  mapDetectionResult,
  mapParamsToBackend,
  lookupRepairCache,
  ProcessingOptions,
  fetchAlgorithmVersions,
  fetchDetectorVersions,
  AlgorithmVersion,
  DetectorVersion,
  QueueStatus,
} from '../services/backendApi';

function writeLog(message: string) {
  console.log(message);
  fetch('/api/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message })
  }).catch(() => {});
}

function formatDetectTime(date: Date = new Date()): string {
  const now = date;
  const month = (now.getMonth() + 1).toString().padStart(2, '0');
  const day = now.getDate().toString().padStart(2, '0');
  const hours = now.getHours().toString().padStart(2, '0');
  const minutes = now.getMinutes().toString().padStart(2, '0');
  return `${month}-${day} ${hours}:${minutes}`;
}


export interface AudioAnalysis {
  spectralFlatness: number;
  dynamicRange: number;
  stereoBalance: number;
  peakLevel: number;
  issues: string[];
}

export type PlayMode = 'original' | 'browser' | 'backend';

export type { ProcessingOptions };

export const defaultProcessingOptions: ProcessingOptions = {
  sampleRate: 48000,
  bitDepth: 24,
};

function createRepairWorker(): Worker {
  return new Worker(new URL('../workers/audioRepairWorker.ts', import.meta.url));
}

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
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
  }, 5000);
}

function downloadUrl(url: string, fileName: string) {
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
  }, 5000);
}

async function computeFileHash(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

export function useAudioProcessor() {
  const savedSettings = loadSettings();

  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioBuffer, setAudioBuffer] = useState<AudioBuffer | null>(null);
  const [browserProcessedBuffer, setBrowserProcessedBuffer] = useState<AudioBuffer | null>(null);
  const [backendProcessedBuffer, setBackendProcessedBuffer] = useState<AudioBuffer | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingProgress, setProcessingProgress] = useState(0);
  const [processingStep, setProcessingStep] = useState('');
  const [params, setParams] = useState<AIRepairParams>(savedSettings.aiRepairParams);
  const [audioAnalysis, setAudioAnalysis] = useState<AudioAnalysis | null>(null);
  const [selectedMode, setSelectedMode] = useState<string>(savedSettings.selectedMode);
  const [playMode, setPlayMode] = useState<PlayMode>('original');
  const [processingOptions, setProcessingOptionsState] = useState<ProcessingOptions>(savedSettings.exportOptions);
  const [originalAIDetection, setOriginalAIDetection] = useState<AISongDetectionResult | null>(null);
  const [backendAIDetection, setBackendAIDetection] = useState<AISongDetectionResult | null>(null);
  const [hasBeenProcessed, setHasBeenProcessed] = useState(false);
  const [backendAvailable, setBackendAvailable] = useState(false);
  const [backendDiag, setBackendDiag] = useState<string>('未检测');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [algorithmVersion, setAlgorithmVersionState] = useState<string>(savedSettings.algorithmVersion);
  const [availableAlgorithms, setAvailableAlgorithms] = useState<AlgorithmVersion[]>([]);
  const [repairModes, setRepairModes] = useState<RepairMode[]>([]);
  const [detectorVersion, setDetectorVersion] = useState<string>(savedSettings.detectorVersion);
  const [availableDetectors, setAvailableDetectors] = useState<DetectorVersion[]>([]);
  const versionInitializedRef = useRef(false);
  const taskIdRef = useRef<string | null>(null);
  const wsControlRef = useRef<WSProgressControl | null>(null);
  const [wavInfo, setWavInfo] = useState<WavInfo | null>(null);
  const [repairResult, setRepairResult] = useState<{
    issues_found: string[];
    original_sample_rate: number;
    output_sample_rate: number;
    output_bit_depth: number;
    duration: number;
    channels: number;
    completed_at?: string;
  } | null>(null);
  const [browserRepairInfo, setBrowserRepairInfo] = useState<{
    completedAt: string;
    algorithmVersion: string;
  } | null>(null);
  // 任务卡住状态
  const [isTaskStuck, setIsTaskStuck] = useState(false);
  const [stuckInfo, setStuckInfo] = useState<{ taskId: string; lastProgress: number; lastStep: string; duration: number } | null>(null);
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [backendPreviewUrl, setBackendPreviewUrl] = useState<string | null>(null);
  const [enableBrowserRepair, setEnableBrowserRepair] = useState(true);

  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<AudioBufferSourceNode | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const startTimeRef = useRef(0);
  const playStartTimeRef = useRef(0);
  const pausedAtRef = useRef(0);
  const animationFrameRef = useRef<number>();
  const isPlayingRef = useRef(false);
  const workerRef = useRef<Worker | null>(null);
  const fileHashRef = useRef<string | null>(null);
  const sessionRestoredRef = useRef(false);
  const streamingAudioRef = useRef<HTMLAudioElement | null>(null);
  const mediaSourceRef = useRef<MediaElementAudioSourceNode | null>(null);
  const playRef = useRef<(() => void) | null>(null);
  const audioBufferRef = useRef<AudioBuffer | null>(null);
  const seekInProgressRef = useRef(false);

  // 同步 audioBufferRef 与 audioBuffer state
  useEffect(() => {
    audioBufferRef.current = audioBuffer;
  }, [audioBuffer]);

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
          fetchDetectorVersions().then(detectors => {
            setAvailableDetectors(detectors);
            writeLog(`[useAudioProcessor] 检测器版本: ${JSON.stringify(detectors.map(d => d.name))}`);
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
      detectorVersion,
    });
  }, [params, processingOptions, selectedMode, algorithmVersion, detectorVersion]);

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

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch('/health', { signal: AbortSignal.timeout(5000) });
        const wasAvailable = backendAvailableRef.current;
        const isAvailable = res.ok;
        setBackendAvailable(isAvailable);

        if (!wasAvailable && isAvailable) {
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
          fetchDetectorVersions().then(detectors => {
            setAvailableDetectors(detectors);
          });
        } else if (wasAvailable && !isAvailable) {
          console.warn('[useAudioProcessor] 后端变为不可用');
        }
      } catch {
        if (backendAvailableRef.current) {
          console.warn('[useAudioProcessor] 后端健康检查失败，标记为不可用');
          setBackendAvailable(false);
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
      if (workerRef.current) {
        workerRef.current.terminate();
        workerRef.current = null;
      }
      closeWS();
    };
  }, []);

  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
      analyserRef.current = audioContextRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
    }
    return audioContextRef.current;
  }, []);

  // 会话恢复逻辑 - 监听后端可用性变化来触发恢复
  const pendingSessionRef = useRef<{
    file: File;
    fileName: string;
    fileHash: string;
    taskId: string;
    hasBeenProcessed: boolean;
    wavInfo?: string;
    repairResult?: string;
  } | null>(null);

  useEffect(() => {
    if (sessionRestoredRef.current) return;

    (async () => {
      const session = await loadSession();
      if (!session || !session.file || !session.taskId) {
        sessionRestoredRef.current = true; // 没有会话需要恢复，标记为已完成
        return;
      }

      writeLog(`[useAudioProcessor] 发现保存的会话: file=${session.fileName} taskId=${session.taskId}`);

      // 保存会话数据到 ref，等待后端可用时恢复
      pendingSessionRef.current = {
        file: session.file,
        fileName: session.fileName,
        fileHash: session.fileHash,
        taskId: session.taskId,
        hasBeenProcessed: session.hasBeenProcessed,
        wavInfo: session.wavInfo,
        repairResult: session.repairResult,
      };
    })();
  }, []);

  // 当后端变为可用时，尝试恢复会话
  useEffect(() => {
    if (!backendAvailable || !pendingSessionRef.current || sessionRestoredRef.current) return;

    const session = pendingSessionRef.current;

    (async () => {
      try {
        const statusRes = await fetch(`/api/v1/status/${session.taskId}`);
        if (!statusRes.ok) {
          writeLog(`[useAudioProcessor] 任务不存在 taskId=${session.taskId}，清除会话`);
          await clearSession();
          pendingSessionRef.current = null;
          sessionRestoredRef.current = true;
          return;
        }

        const taskStatus = await statusRes.json();
        if (taskStatus.status === 'error') {
          writeLog(`[useAudioProcessor] 任务已出错，清除会话`);
          await clearSession();
          pendingSessionRef.current = null;
          sessionRestoredRef.current = true;
          return;
        }

        writeLog(`[useAudioProcessor] 恢复会话: taskId=${session.taskId} status=${taskStatus.status}`);

        const file = session.file;
        setAudioFile(file);
        fileHashRef.current = session.fileHash;

        const context = getAudioContext();
        const arrayBuf = await file.arrayBuffer();
        const wavHeaderInfo = parseWavHeader(arrayBuf.slice(0, 44 + 4096));
        setWavInfo(wavHeaderInfo);
        const buffer = await context.decodeAudioData(arrayBuf);

        setAudioBuffer(buffer);
        setDuration(buffer.duration);
        setCurrentTime(0);
        pausedAtRef.current = 0;

        const analysis = detectAudioIssues(buffer);
        setAudioAnalysis(analysis);

        setTaskId(session.taskId);
        taskIdRef.current = session.taskId;

        if (session.hasBeenProcessed && taskStatus.status === 'completed') {
          try {
            const previewUrl = getPreviewUrl(session.taskId, 'repaired');
            const repairedBuffer = await downloadWithProgress(previewUrl);
            const tempContext = new OfflineAudioContext(1, 1, processingOptions.sampleRate);
            const decoded = await tempContext.decodeAudioData(repairedBuffer);
            setBackendProcessedBuffer(decoded);
            setHasBeenProcessed(true);
            setPlayMode('backend');
          } catch (e) {
            console.warn('[useAudioProcessor] 恢复修复后音频失败:', e);
          }
        }

        if (session.wavInfo) {
          try { setWavInfo(JSON.parse(session.wavInfo)); } catch {}
        }
        if (session.repairResult) {
          try { setRepairResult(JSON.parse(session.repairResult)); } catch {}
        }
        if (taskStatus.detection_result) {
          try { setOriginalAIDetection(mapDetectionResult(taskStatus.detection_result as import('../services/backendApi').BackendDetectionResult)); } catch {}
        }
        if (taskStatus.repaired_detection_result) {
          try { setBackendAIDetection(mapDetectionResult(taskStatus.repaired_detection_result as import('../services/backendApi').BackendDetectionResult)); } catch {}
        }

        sessionRestoredRef.current = true;
        pendingSessionRef.current = null;
      } catch (e) {
        console.warn('[useAudioProcessor] 会话恢复失败:', e);
        await clearSession();
        pendingSessionRef.current = null;
        sessionRestoredRef.current = true;
      }
    })();
  }, [backendAvailable, getAudioContext, processingOptions.sampleRate]);

  const stopPlaying = useCallback(() => {
    if (sourceNodeRef.current) {
      try { sourceNodeRef.current.stop(); } catch {}
      sourceNodeRef.current.onended = null;
      sourceNodeRef.current.disconnect();
      sourceNodeRef.current = null;
    }
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
  }, []);

  const closeWS = useCallback(() => {
    if (wsControlRef.current) {
      wsControlRef.current.close();
      wsControlRef.current = null;
    }
  }, []);

  const startStreamingPlayback = useCallback((url: string) => {
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
    analyserRef.current!.connect(context.destination);

    streamingAudioRef.current = audio;
    mediaSourceRef.current = source;

    audio.play().catch(err => {
      console.warn('[startStreamingPlayback] 播放失败:', err);
    });

    isPlayingRef.current = true;
    setIsPlaying(true);
    startTimeRef.current = context.currentTime;
    pausedAtRef.current = 0;
    setCurrentTime(0);

    const updateTime = () => {
      if (isPlayingRef.current && streamingAudioRef.current) {
        const current = streamingAudioRef.current.currentTime;
        setCurrentTime(current);
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
    stopPlaying();
    closeWS();
    setBackendError(null);
    setAudioFile(file);

    setProcessingStep('计算文件哈希...');
    setIsProcessing(true);
    setProcessingProgress(0);

    const fileHash = await computeFileHash(file);
    fileHashRef.current = fileHash;
    writeLog(`[loadAudioFile] fileHash=${fileHash}`);

    const context = getAudioContext();
    const arrayBuf = await file.arrayBuffer();
    const wavHeaderInfo = parseWavHeader(arrayBuf.slice(0, 44 + 4096));
    setWavInfo(wavHeaderInfo);
    const buffer = await context.decodeAudioData(arrayBuf);

    setAudioBuffer(buffer);
    setBrowserProcessedBuffer(null);
    setBackendProcessedBuffer(null);
    setDuration(buffer.duration);
    setCurrentTime(0);
    pausedAtRef.current = 0;
    setOriginalAIDetection(null);
    setBackendAIDetection(null);
    setHasBeenProcessed(false);
    setPlayMode('original');
    setTaskId(null);
    taskIdRef.current = null;
    setRepairResult(null);
    setBackendAvailable(false);
    setBackendPreviewUrl(null);

    const analysis = detectAudioIssues(buffer);
    setAudioAnalysis(analysis);

    try {
      setProcessingStep('上传到后端...');
      setProcessingProgress(0);

      const uploadRes = await uploadAudio(file, (loaded, total, speed) => {
        const pct = total > 0 ? loaded / total : 0;
        setProcessingProgress(pct);
        setProcessingStep(`上传中 ${formatBytes(loaded)}/${formatBytes(total)} ${formatSpeed(speed)}`);
      }, fileHash);

      const newTaskId = uploadRes.task_id;
      setTaskId(newTaskId);
      taskIdRef.current = newTaskId;
      setBackendAvailable(true);
      if (uploadRes.cached) {
        writeLog(`[loadAudioFile] 文件已缓存，跳过上传 taskId=${newTaskId}`);
      } else {
        writeLog(`[loadAudioFile] 上传成功 taskId=${newTaskId}`);
      }

      saveSession({
        file,
        fileName: file.name,
        fileSize: file.size,
        fileHash,
        taskId: newTaskId,
        backendAvailable: true,
        hasBeenProcessed: false,
        wavInfo: wavHeaderInfo ? JSON.stringify(wavHeaderInfo) : '',
        repairResult: '',
      });

      // 阻止旧会话恢复逻辑覆盖新上传的任务
      pendingSessionRef.current = null;
      sessionRestoredRef.current = true;
      writeLog(`[loadAudioFile] 新文件上传完成，阻止旧会话恢复`);
    } catch (err) {
      console.warn('[loadAudioFile] 上传失败:', err);
      setBackendAvailable(false);
    }

    setIsProcessing(false);
    setProcessingStep('');
    setProcessingProgress(0);
  }, [getAudioContext, stopPlaying]);

  const applyRepairMode = useCallback((mode: RepairMode) => {
    setSelectedMode(mode.name);
    setParams(mode.params);
  }, []);

  const updateParam = useCallback((key: keyof AIRepairParams, value: number) => {
    setParams(prev => ({ ...prev, [key]: value }));
  }, []);

  const updateProcessingOptions = useCallback((options: Partial<ProcessingOptions>) => {
    setProcessingOptionsState(prev => ({ ...prev, ...options }));
  }, []);

  const loadAudioFromUrl = useCallback(async (url: string, targetSampleRate?: number): Promise<AudioBuffer> => {
    const arrayBuffer = await downloadWithProgress(url, (loaded, total, speed) => {
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

  const repairWithWorker = useCallback(async (
    buffer: AudioBuffer,
    repairParams: Partial<AIRepairParams>,
    onProgress?: (progress: number, step: string) => void,
  ): Promise<AudioBuffer> => {
    if (workerRef.current) {
      workerRef.current.terminate();
    }

    const worker = createRepairWorker();
    workerRef.current = worker;

    const channelData: Float32Array[] = [];
    for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
      channelData.push(new Float32Array(buffer.getChannelData(ch)));
    }

    const requestId = Date.now().toString();

    const result = await new Promise<Float32Array[]>((resolve, reject) => {
      worker.onmessage = (e: MessageEvent) => {
        const { type, ...data } = e.data;

        if (type === 'progress') {
          if (onProgress) {
            onProgress(data.progress, data.step);
          } else {
            setProcessingProgress(0.1 + data.progress * 0.6);
            setProcessingStep(data.step);
          }
        } else if (type === 'repair_complete') {
          resolve(data.channels);
        } else if (type === 'error') {
          reject(new Error(data.error));
        }
      };

      worker.onerror = (e) => {
        reject(new Error(e.message));
      };

      worker.postMessage({
        type: 'repair',
        data: {
          channels: channelData,
          sampleRate: buffer.sampleRate,
          params: repairParams,
          id: requestId,
        },
      });
    });

    worker.terminate();
    workerRef.current = null;

    const context = getAudioContext();
    const numChannels = result.length;
    const length = result[0].length;
    const repairedBuffer = context.createBuffer(numChannels, length, buffer.sampleRate);

    for (let ch = 0; ch < numChannels; ch++) {
      repairedBuffer.copyToChannel(result[ch], ch);
    }

    return repairedBuffer;
  }, [getAudioContext]);

  const encodeWavWithWorker = useCallback(async (
    buffer: AudioBuffer,
    bitDepth: 16 | 24 | 32,
  ): Promise<ArrayBuffer> => {
    if (workerRef.current) {
      workerRef.current.terminate();
    }

    const worker = createRepairWorker();
    workerRef.current = worker;

    const channelData: Float32Array[] = [];
    for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
      channelData.push(new Float32Array(buffer.getChannelData(ch)));
    }

    const requestId = Date.now().toString();

    const workerPromise = new Promise<ArrayBuffer>((resolve, reject) => {
      worker.onmessage = (e: MessageEvent) => {
        const { type, ...data } = e.data;

        if (type === 'encode_wav_complete') {
          resolve(data.wavData);
        } else if (type === 'error') {
          reject(new Error(data.error));
        }
      };

      worker.onerror = (e) => {
        reject(new Error(e.message));
      };

      worker.postMessage({
        type: 'encode_wav',
        data: {
          channels: channelData,
          sampleRate: buffer.sampleRate,
          bitDepth,
          id: requestId,
        },
      });
    });

    const timeoutPromise = new Promise<never>((_, reject) => {
      setTimeout(() => reject(new Error('Worker编码超时(30s)')), 30000);
    });

    try {
      const wavData = await Promise.race([workerPromise, timeoutPromise]);
      worker.terminate();
      workerRef.current = null;
      return wavData;
    } catch (err) {
      worker.terminate();
      workerRef.current = null;
      throw err;
    }
  }, []);

  const applySettings = useCallback(async () => {
    if (!audioBuffer) return;

    setIsProcessing(true);
    setProcessingProgress(0);
    const REPAIR_TERMINALS = new Set(['completed', 'error']);
    let currentTaskId = taskIdRef.current;
    const backendProg = { value: 0 };
    const browserProg = { value: 0 };

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
    if (fileHashRef.current) {
      writeLog(`[applySettings] 查询缓存: hash=${fileHashRef.current}`);
      try {
        const cacheResult = await lookupRepairCache(fileHashRef.current, currentParamsForCache);
        if (cacheResult.found) {
          setProcessingStep('检测到已有修复记录...');
          setProcessingProgress(0.01);

          const useCache = window.confirm(
            `检测到相同参数的已完成的修复记录。\n\n` +
            `输出文件大小: ${formatBytes(cacheResult.output_size || 0)}\n\n` +
            `点击「确定」直接使用已有结果\n点击「取消」重新执行修复`
          );

          if (useCache) {
            const cachedTaskId = cacheResult.task_id || currentTaskId;
            writeLog(`[applySettings] ✅ 用户选择使用缓存结果(output=${formatBytes(cacheResult.output_size || 0)})，跳过修复`);

            if (cachedTaskId && cachedTaskId !== taskIdRef.current) {
              setTaskId(cachedTaskId);
              taskIdRef.current = cachedTaskId;
            }

            setProcessingStep('使用缓存的修复结果');
            setProcessingProgress(1);
            setBackendAvailable(true);

            if (cacheResult.repair_result) {
              setRepairResult({
                ...cacheResult.repair_result,
                completed_at: new Date().toISOString(),
              });
            }

            if (cacheResult.detection_result) {
              setOriginalAIDetection(mapDetectionResult(cacheResult.detection_result));
            }
            if (cacheResult.repaired_detection_result) {
              setBackendAIDetection(mapDetectionResult(cacheResult.repaired_detection_result));
            }

            const previewUrl = getPreviewUrl(cachedTaskId || currentTaskId, 'repaired');
            setBackendPreviewUrl(previewUrl);
            startStreamingPlayback(previewUrl);
            setPlayMode('backend');
            setHasBeenProcessed(true);

            if (audioFile && (cachedTaskId || currentTaskId)) {
              loadAudioFromUrl(previewUrl, processingOptions.sampleRate).then(repairedBuffer => {
                setBackendProcessedBuffer(repairedBuffer);
              }).catch(err => {
                console.warn('[applySettings] 后台下载缓存音频失败:', err);
              });
            }

            saveSession({
              file: audioFile,
              fileName: audioFile.name,
              fileSize: audioFile.size,
              fileHash: fileHashRef.current || '',
              taskId: cachedTaskId || currentTaskId || '',
              backendAvailable: true,
              hasBeenProcessed: true,
              wavInfo: wavInfo ? JSON.stringify(wavInfo) : '',
              repairResult: cacheResult.repair_result
                ? JSON.stringify(cacheResult.repair_result)
                : '',
            });

            setIsProcessing(false);
            setTimeout(() => {
              setProcessingStep('');
              setProcessingProgress(0);
            }, 2000);
            return;
          } else {
            writeLog(`[applySettings] 用户选择重新修复`);
          }
        } else {
          writeLog(`[applySettings] 缓存未命中`);
        }
      } catch (cacheErr) {
        writeLog(`[applySettings] 缓存查询失败: ${cacheErr instanceof Error ? cacheErr.message : String(cacheErr)}`);
      }
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
      // 使用 taskIdRef.current 而不是闭包中的 currentTaskId
      // 确保即使上传完成后也能正确显示并行进度
      const hasTaskId = !!taskIdRef.current;
      const combinedProgress = hasTaskId
        ? backendProg.value * 0.5 + browserProg.value * 0.5
        : browserProg.value;
      writeLog(`[progress][${source}] taskId=${taskIdRef.current}, hasTaskId=${hasTaskId}, backend=${backendProg.value.toFixed(2)}, browser=${browserProg.value.toFixed(2)}, combined=${combinedProgress.toFixed(2)}`);
      setProcessingProgress(combinedProgress);
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
                setProcessingStep(`[后端] ${event.step}`);
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
        setProcessingStep('[后端] 修复失败: ' + msg);
        setBackendAvailable(false);
        return null;
      }
    })() : Promise.resolve(null);

    const browserRepairPromise = enableBrowserRepair ? (async () => {
      try {
        writeLog(`[browser] 开始修复`);
        setProcessingStep('[浏览器] 准备修复...');
        const { enhanceHighFrequencies } = await import('../utils/highFrequencyEnhancer');

        // 修复流程不自动触发AI检测，由用户手动触发
        browserProg.value = 0.05;
        writeLog(`[browser] 设置初始进度 0.05`);
        updateCombinedProgress('browser-start');

        const workerParams = {
          deClipping: params.deClipping,
          noiseReduction: params.noiseReduction,
          deCrackle: params.deCrackle,
          dePop: params.dePop,
          harmonicEnhance: params.harmonicEnhance,
          dynamicRange: params.dynamicRange,
          softness: params.softness,
          spatialEnhance: params.spatialEnhance,
          transientRepair: params.transientRepair,
          deEssing: params.deEssing,
          presenceBoost: params.presenceBoost,
          bassEnhance: params.bassEnhance,
          warmth: params.warmth,
          clarity: params.clarity,
        };

        const repaired = await repairWithWorker(audioBuffer, workerParams, (progress, step) => {
          browserProg.value = 0.05 + progress * 0.8;
          updateCombinedProgress('browser-worker');
          setProcessingStep(`[浏览器] ${step}`);
        });

        browserProg.value = 0.85;
        updateCombinedProgress('browser-post-worker');

        const targetSampleRate = processingOptions.sampleRate;
        let finalBuffer: AudioBuffer;

        if (repaired.sampleRate !== targetSampleRate) {
          if (targetSampleRate === 96000) {
            setProcessingStep('[浏览器] 96kHz高频增强重采样...');
            finalBuffer = await enhanceHighFrequencies(repaired, (progress) => {
              browserProg.value = 0.85 + progress * 0.08;
              updateCombinedProgress('browser-enhance');
            });
          } else {
            setProcessingStep(`[浏览器] 重采样到 ${targetSampleRate / 1000} kHz...`);
            const targetLength = Math.ceil(repaired.length * (targetSampleRate / repaired.sampleRate));
            const offlineContext = new OfflineAudioContext(
              repaired.numberOfChannels,
              targetLength,
              targetSampleRate,
            );
            const source = offlineContext.createBufferSource();
            source.buffer = repaired;
            source.connect(offlineContext.destination);
            source.start();
            finalBuffer = await offlineContext.startRendering();
          }
        } else {
          finalBuffer = repaired;
        }

        browserProg.value = 0.95;
        updateCombinedProgress('browser-pre-finish');

        setProcessingStep('[浏览器] 完成');
        // 修复后不再自动触发AI检测，由用户手动触发
        // setBrowserAIDetection(checkAISong(finalBuffer));

        browserProg.value = 1.0;
        writeLog(`[browser] 修复完成`);
        updateCombinedProgress('browser-finish');

        // 记录浏览器修复完成信息
        setBrowserRepairInfo({
          completedAt: new Date().toISOString(),
          algorithmVersion: effectiveAlgorithmVersion,
        });

        return finalBuffer;
      } catch (browserErr) {
        console.error('[applySettings] 浏览器修复失败:', browserErr);
        writeLog(`[browser] 修复失败: ${browserErr}`);
        return null;
      }
    })() : (async () => {
      writeLog(`[browser] 浏览器修复已禁用，跳过`);
      browserProg.value = 1.0;
      updateCombinedProgress('browser-skipped');
      return null;
    })();

    writeLog(`[applySettings] 开始并行执行两个 Promise`);
    const startTime = Date.now();
    const [backendResult, browserResult] = await Promise.allSettled([backendRepairPromise, browserRepairPromise]);
    writeLog(`[applySettings] 并行执行完成, 耗时=${Date.now() - startTime}ms`);

    let anySuccess = false;

    const effectiveBackendResult = backendResult;

    if (effectiveBackendResult.status === 'rejected') {
      setBackendError(effectiveBackendResult.reason?.message || '后端修复失败');
    }

    if (effectiveBackendResult.status === 'fulfilled' && effectiveBackendResult.value) {
      if (effectiveBackendResult.value.repairResult) {
        setRepairResult({
          ...effectiveBackendResult.value.repairResult,
          completed_at: new Date().toISOString(),
        });
      }
      anySuccess = true;
      setPlayMode('backend');

      const previewUrl = effectiveBackendResult.value.previewUrl;
      if (previewUrl) {
        startStreamingPlayback(previewUrl);
      }

      if (audioFile && taskIdRef.current) {
        loadAudioFromUrl(previewUrl, processingOptions.sampleRate).then(repairedBuffer => {
          setBackendProcessedBuffer(repairedBuffer);
        }).catch(err => {
          console.warn('[applySettings] 后台下载修复后音频失败:', err);
        });
      }
    }

    if (browserResult.status === 'fulfilled' && browserResult.value) {
      setBrowserProcessedBuffer(browserResult.value);
      anySuccess = true;
    }

    if (anySuccess) {
      setHasBeenProcessed(true);
      if (!(effectiveBackendResult.status === 'fulfilled' && effectiveBackendResult.value)) {
        setPlayMode('browser');
      }

      if (effectiveBackendResult.status === 'fulfilled' && effectiveBackendResult.value && taskIdRef.current) {
        const trySetBackendDetection = (result: unknown) => {
          if (result && typeof result === 'object') {
            writeLog('[applySettings] 设置修复后检测结果');
            setBackendAIDetection(mapDetectionResult(result as import('../services/backendApi').BackendDetectionResult));
          }
        };

        detectAudio(taskIdRef.current, 'repaired', detectorVersion).then(res => {
          if (res.detection_result) {
            writeLog(`[applySettings] 修复后检测${res.cached ? '缓存命中' : '新结果'}，刷新`);
            trySetBackendDetection(res.detection_result);
          }
        }).catch(() => {});
      }

      if (audioFile && taskIdRef.current) {
        const _backendValue = effectiveBackendResult.status === 'fulfilled' ? effectiveBackendResult.value : null;
        saveSession({
          file: audioFile,
          fileName: audioFile.name,
          fileSize: audioFile.size,
          fileHash: fileHashRef.current || '',
          taskId: taskIdRef.current,
          backendAvailable: effectiveBackendResult.status === 'fulfilled' && !!_backendValue,
          hasBeenProcessed: true,
          wavInfo: wavInfo ? JSON.stringify(wavInfo) : '',
          repairResult: _backendValue?.repairResult
            ? JSON.stringify(_backendValue.repairResult)
            : '',
        });
      }
    }

    const backendFailed = effectiveBackendResult.status === 'rejected' || (effectiveBackendResult.status === 'fulfilled' && (effectiveBackendResult as PromiseFulfilledResult<{previewUrl?: string; repairResult?: unknown}>).value === null);
    if (!backendFailed) {
      setProcessingStep('完成!');
    }
    setProcessingProgress(1);
    setIsProcessing(false);
    setTimeout(() => {
      setProcessingStep('');
      setProcessingProgress(0);
    }, 2000);
  }, [audioBuffer, audioFile, params, processingOptions, originalAIDetection, loadAudioFromUrl, repairWithWorker, wavInfo, startStreamingPlayback, detectorVersion, enableBrowserRepair]);

  const runAIDetection = useCallback(async () => {
    if (!audioBuffer) return;

    const currentTaskId = taskIdRef.current;
    const DETECT_TERMINALS = new Set(['detected', 'completed', 'error']);

    if (currentTaskId && backendAvailable) {
      try {
        // ===== 检测缓存查询与二次确认 =====
        setProcessingStep('查询检测缓存...');
        writeLog(`[runAIDetection] 查询检测缓存: taskId=${currentTaskId}`);

        let statusData: Record<string, unknown> | null = null;
        try {
          const statusRes = await fetch(`/api/v1/status/${currentTaskId}`);
          if (statusRes.ok) {
            statusData = await statusRes.json();
          }
        } catch {}

        // 检查是否有缓存的检测结果
        const hasCachedOriginal = statusData?.detection_result;
        const hasCachedRepaired = statusData?.repaired_detection_result;
        let skipDetectionCache = false;

        if (hasCachedOriginal || hasCachedRepaired) {
          const originalResult = hasCachedOriginal ? (statusData?.detection_result as Record<string, unknown>) : null;
          const repairedResult = hasCachedRepaired ? (statusData?.repaired_detection_result as Record<string, unknown>) : null;

          const originalAIProb = originalResult?.ai_probability as number;
          const repairedAIProb = repairedResult?.ai_probability as number;

          let confirmMessage = '检测到已有 AI 检测结果：\n\n';
          if (originalResult) {
            confirmMessage += `原始音频：AI 概率 ${Math.round((originalAIProb || 0) * 100)}%\n`;
          }
          if (repairedResult) {
            confirmMessage += `修复后音频：AI 概率 ${Math.round((repairedAIProb || 0) * 100)}%\n`;
          }
          confirmMessage += '\n点击「确定」使用已有结果\n点击「取消」重新检测';

          const useCache = window.confirm(confirmMessage);

          if (useCache) {
            writeLog(`[runAIDetection] 用户选择使用缓存的检测结果`);

            // 直接使用缓存结果
            const tryMapDetection = (result: unknown) => {
              if (result && typeof result === 'object') {
                return mapDetectionResult(result as import('../services/backendApi').BackendDetectionResult);
              }
              return null;
            };

            if (hasCachedOriginal) {
              const mapped = tryMapDetection(statusData?.detection_result);
              if (mapped) {
                setOriginalAIDetection(mapped);
                writeLog(`[runAIDetection] 使用缓存的原始检测结果`);
              }
            }
            if (hasCachedRepaired) {
              const mapped = tryMapDetection(statusData?.repaired_detection_result);
              if (mapped) {
                setBackendAIDetection(mapped);
                writeLog(`[runAIDetection] 使用缓存的修复后检测结果`);
              }
            }

            setIsProcessing(false);
            setProcessingStep('');
            setProcessingProgress(0);
            return;
          } else {
            writeLog(`[runAIDetection] 用户选择重新检测，跳过所有缓存`);
            skipDetectionCache = true;
          }
        }

        setIsProcessing(true);
        setProcessingStep('AI检测原始音频...');
        setProcessingProgress(0);

        // 如果用户选择重新检测，跳过从 statusData 恢复缓存结果
        if (!skipDetectionCache) {
          const tryMapDetection = (result: unknown) => {
            if (result && typeof result === 'object') {
              return mapDetectionResult(result as import('../services/backendApi').BackendDetectionResult);
            }
            return null;
          };

          if (statusData?.detection_result) {
            const mapped = tryMapDetection(statusData.detection_result);
            if (mapped) {
              writeLog(`[runAIDetection] 从任务状态恢复原始检测结果`);
              setOriginalAIDetection(mapped);
            }
          }
          if (statusData?.repaired_detection_result) {
            const mapped = tryMapDetection(statusData.repaired_detection_result);
            if (mapped) {
              writeLog(`[runAIDetection] 从任务状态恢复修复后检测结果`);
              setBackendAIDetection(mapped);
            }
          }
        }

        const origRes = await detectAudio(currentTaskId, 'original', detectorVersion, skipDetectionCache);
        if (origRes.detection_result) {
          writeLog(`[runAIDetection] 原始检测${origRes.cached ? '缓存命中' : '有结果'}，更新`);
          setOriginalAIDetection(mapDetectionResult(origRes.detection_result));
        } else {
          closeWS();
          const detectResult = await new Promise<import('../services/backendApi').ProgressEvent>((resolve, reject) => {
            wsControlRef.current = connectProgressWS(
              currentTaskId,
              {
                onProgress: (event) => {
                  setProcessingProgress(event.progress);
                  setProcessingStep(event.step);
                  if (event.detection_result) {
                    setOriginalAIDetection(mapDetectionResult(event.detection_result));
                  }
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
              DETECT_TERMINALS,
            );
          });

          if (detectResult.detection_result) {
            setOriginalAIDetection(mapDetectionResult(detectResult.detection_result));
            setOriginalDetectTime(formatDetectTime());
          }
        }

        if (hasBeenProcessed && backendProcessedBuffer) {
          setProcessingStep('AI检测后端修复音频...');
          const repairedRes = await detectAudio(currentTaskId, 'repaired', detectorVersion, skipDetectionCache);
          if (repairedRes.detection_result) {
            writeLog(`[runAIDetection] 修复后检测${repairedRes.cached ? '缓存命中' : '有结果'}，更新`);
            setBackendAIDetection(mapDetectionResult(repairedRes.detection_result));
            setRepairedDetectTime(formatDetectTime());
          } else {
            closeWS();
            await new Promise<import('../services/backendApi').ProgressEvent>((resolve, reject) => {
              wsControlRef.current = connectProgressWS(
                currentTaskId,
                {
                  onProgress: (evt) => {
                    setProcessingProgress(evt.progress);
                    setProcessingStep(evt.step);
                    if (evt.repaired_detection_result) {
                      setBackendAIDetection(mapDetectionResult(evt.repaired_detection_result));
                      setRepairedDetectTime(formatDetectTime());
                    }
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
                },
                DETECT_TERMINALS,
              );
            });
          }
        }
      } catch (err) {
        console.warn('[runAIDetection] 后端检测失败, 降级本地:', err);
        setBackendError(err instanceof Error ? err.message : String(err));
        const { checkAISong } = await import('../utils/aiSongChecker');
        setOriginalAIDetection(checkAISong(audioBuffer));
        if (hasBeenProcessed && backendProcessedBuffer) {
          setBackendAIDetection(checkAISong(backendProcessedBuffer));
        }
      }
    } else {
      const { checkAISong } = await import('../utils/aiSongChecker');
      setOriginalAIDetection(checkAISong(audioBuffer));
      if (hasBeenProcessed && backendProcessedBuffer) {
        setBackendAIDetection(checkAISong(backendProcessedBuffer));
      }
    }

    setIsProcessing(false);
    setProcessingStep('');
    setProcessingProgress(0);
  }, [audioBuffer, backendProcessedBuffer, backendAvailable, hasBeenProcessed, detectorVersion]);

  const resetParams = useCallback(() => {
    setParams(defaultAIRepairParams);
    setSelectedMode('全面修复');
    resetStoredSettings();
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
    if (playMode === 'original') return audioBuffer;
    if (playMode === 'browser') return browserProcessedBuffer;
    if (playMode === 'backend') return backendProcessedBuffer;
    return audioBuffer;
  }, [playMode, audioBuffer, browserProcessedBuffer, backendProcessedBuffer]);

  const play = useCallback(async () => {
    if (playMode === 'backend' && streamingAudioRef.current && !backendProcessedBuffer) {
      streamingAudioRef.current.play().catch(() => {});
      isPlayingRef.current = true;
      setIsPlaying(true);
      const updateTime = () => {
        if (isPlayingRef.current && streamingAudioRef.current) {
          const current = streamingAudioRef.current.currentTime;
          setCurrentTime(current);
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
      return;
    }

    const context = getAudioContext();
    if (context.state === 'suspended') {
      await context.resume();
      await new Promise(resolve => setTimeout(resolve, 50));
    }

    if (sourceNodeRef.current && !seekInProgressRef.current) {
      stopPlaying();
    } else if (sourceNodeRef.current && seekInProgressRef.current) {
      try { sourceNodeRef.current.stop(); } catch {}
      sourceNodeRef.current.disconnect();
      sourceNodeRef.current = null;
    }
    seekInProgressRef.current = false;

    const source = context.createBufferSource();
    const gain = context.createGain();

    source.buffer = buffer;
    source.connect(gain);
    gain.connect(analyserRef.current!);
    analyserRef.current!.connect(context.destination);

    gain.gain.value = 1.0;

    let playOffset = pausedAtRef.current;
    if (playOffset >= buffer.duration) {
      pausedAtRef.current = 0;
      playOffset = 0;
    }

    source.onended = () => {
      if (isPlayingRef.current) {
        stopPlaying();
        setCurrentTime(0);
        pausedAtRef.current = 0;
      }
    };

    sourceNodeRef.current = source;
    gainNodeRef.current = gain;

    playStartTimeRef.current = performance.now();
    startTimeRef.current = context.currentTime - playOffset;
    source.start(0, playOffset);

    isPlayingRef.current = true;
    setIsPlaying(true);

    const updateTime = () => {
      if (isPlayingRef.current) {
        const elapsed = (performance.now() - playStartTimeRef.current) / 1000;
        const current = playOffset + elapsed;
        if (current >= buffer.duration) {
          stopPlaying();
          setCurrentTime(0);
          pausedAtRef.current = 0;
        } else {
          setCurrentTime(current);
          animationFrameRef.current = requestAnimationFrame(updateTime);
        }
      }
    };
    updateTime();
  }, [playMode, backendProcessedBuffer, getCurrentBuffer, getAudioContext, stopPlaying]);

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

  const switchPlayMode = useCallback((mode: PlayMode) => {
    setPlayMode(mode);

    if (isPlayingRef.current) {
      const currentPosition = currentTime;
      stopPlaying();
      pausedAtRef.current = currentPosition;
      setCurrentTime(currentPosition);
      if (playRef.current) {
        playRef.current();
      }
    }
  }, [currentTime, stopPlaying]);

  const downloadProcessedAudio = useCallback(async (source: 'browser' | 'backend') => {
    const baseName = audioFile
      ? audioFile.name.replace(/\.[^/.]+$/, '')
      : 'audio';
    const fileName = source === 'backend'
      ? `${baseName}_backend_repaired.wav`
      : `${baseName}_browser_repaired.wav`;

    if (source === 'backend' && taskIdRef.current) {
      const url = getDownloadUrl(taskIdRef.current);
      downloadUrl(url, fileName);
      return;
    }

    const targetBuffer = source === 'backend' ? backendProcessedBuffer : browserProcessedBuffer;

    if (targetBuffer) {
      setProcessingStep('正在编码导出...');
      setProcessingProgress(0);
      try {
        const wavData = await encodeWavWithWorker(targetBuffer, processingOptions.bitDepth);
        const blob = new Blob([wavData], { type: 'audio/wav' });
        downloadBlob(blob, fileName);
        setProcessingStep('');
        setProcessingProgress(0);
        return;
      } catch (workerErr) {
        console.warn('[downloadProcessedAudio] Worker编码失败，使用fallback:', workerErr);
        try {
          setProcessingStep('正在编码导出(主线程)...');
          const wav = await audioBufferToWav(targetBuffer, {
            sampleRate: targetBuffer.sampleRate,
            bitDepth: processingOptions.bitDepth,
          });
          const blob = new Blob([wav], { type: 'audio/wav' });
          downloadBlob(blob, fileName);
          setProcessingStep('');
          setProcessingProgress(0);
          return;
        } catch (fallbackErr) {
          console.error('[downloadProcessedAudio] Fallback编码也失败:', fallbackErr);
          setProcessingStep('');
          setProcessingProgress(0);
          alert(`导出失败: ${fallbackErr instanceof Error ? fallbackErr.message : '编码错误'}`);
          return;
        }
      }
    }

    alert('请先完成修复后再下载');
  }, [backendProcessedBuffer, browserProcessedBuffer, audioFile, processingOptions, encodeWavWithWorker, taskIdRef]);

  useEffect(() => {
    return () => {
      stopPlaying();
    };
  }, [stopPlaying]);

  const originalSampleRate = audioBuffer?.sampleRate ?? 0;
  const currentSampleRate = (() => {
    if (playMode === 'browser' && browserProcessedBuffer) return browserProcessedBuffer.sampleRate;
    if (playMode === 'backend' && backendProcessedBuffer) return backendProcessedBuffer.sampleRate;
    return originalSampleRate;
  })();

  return {
    audioFile,
    audioBuffer,
    browserProcessedBuffer,
    backendProcessedBuffer,
    backendPreviewUrl,
    isPlaying,
    currentTime,
    duration,
    isProcessing,
    processingProgress,
    processingStep,
    params,
    audioAnalysis,
    selectedMode,
    playMode,
    repairModes,
    processingOptions,
    originalAIDetection,
    backendAIDetection,
    originalDetectTime,
    repairedDetectTime,
    hasBeenProcessed,
    originalSampleRate,
    currentSampleRate,
    backendAvailable,
    backendDiag,
    runBackendDiag,
    wavInfo,
    repairResult,
    algorithmVersion,
    availableAlgorithms,
    applyAlgorithmVersion,
    detectorVersion,
    availableDetectors,
    setDetectorVersion,
    // 任务卡住相关状态
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
    runAIDetection,
    switchPlayMode,
    setProcessingOptions: updateProcessingOptions,
    downloadProcessedAudio,
    analyserRef,
    // 浏览器修复信息
    browserRepairInfo,
    enableBrowserRepair,
    setEnableBrowserRepair,
  };
}

async function audioBufferToWav(buffer: AudioBuffer, options: { sampleRate: number; bitDepth: 16 | 24 | 32 }): Promise<ArrayBuffer> {
  const numChannels = buffer.numberOfChannels;
  const targetSampleRate = options.sampleRate;
  const bitDepth = options.bitDepth;

  const bytesPerSample = bitDepth / 8;
  const blockAlign = numChannels * bytesPerSample;
  const dataLength = buffer.length * blockAlign;
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
  view.setUint32(24, targetSampleRate, true);
  view.setUint32(28, targetSampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitDepth, true);
  writeString(view, 36, 'data');
  view.setUint32(40, dataLength, true);

  const channels: Float32Array[] = [];
  for (let i = 0; i < numChannels; i++) {
    channels.push(buffer.getChannelData(i));
  }

  let offset = 44;
  for (let i = 0; i < buffer.length; i++) {
    for (let ch = 0; ch < numChannels; ch++) {
      const sample = Math.max(-1, Math.min(1, channels[ch][i]));

      if (bitDepth === 16) {
        view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
        offset += 2;
      } else if (bitDepth === 24) {
        const intSample = sample < 0 ? sample * 0x800000 : sample * 0x7fffff;
        const data = intSample & 0x00ffffff;
        view.setUint8(offset, data & 0xff);
        view.setUint8(offset + 1, (data >> 8) & 0xff);
        view.setUint8(offset + 2, (data >> 16) & 0xff);
        offset += 3;
      } else if (bitDepth === 32) {
        view.setInt32(offset, sample < 0 ? sample * 0x80000000 : sample * 0x7fffffff, true);
        offset += 4;
      }
    }
  }

  return arrayBuffer;
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



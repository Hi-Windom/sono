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
  getPreviewUrl,
  getDownloadUrl,
  downloadWithProgress,
  mapDetectionResult,
  ProcessingOptions,
  fetchAlgorithmVersions,
  AlgorithmVersion,
  QueueStatus,
} from '../services/backendApi';

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
  const [browserAIDetection, setBrowserAIDetection] = useState<AISongDetectionResult | null>(null);
  const [backendAIDetection, setBackendAIDetection] = useState<AISongDetectionResult | null>(null);
  const [hasBeenProcessed, setHasBeenProcessed] = useState(false);
  const [backendAvailable, setBackendAvailable] = useState(false);
  const [backendDiag, setBackendDiag] = useState<string>('未检测');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [algorithmVersion, setAlgorithmVersionState] = useState<string>('v1.1');
  const [availableAlgorithms, setAvailableAlgorithms] = useState<AlgorithmVersion[]>([]);
  const [repairModes, setRepairModes] = useState<RepairMode[]>([]);
  const [detectorVersion, setDetectorVersion] = useState<string>('v1.1');
  const taskIdRef = useRef<string | null>(null);
  const [wavInfo, setWavInfo] = useState<WavInfo | null>(null);
  const [repairResult, setRepairResult] = useState<{
    issues_found: string[];
    original_sample_rate: number;
    output_sample_rate: number;
    output_bit_depth: number;
    duration: number;
    channels: number;
  } | null>(null);
  // 任务卡住状态
  const [isTaskStuck, setIsTaskStuck] = useState(false);
  const [stuckInfo, setStuckInfo] = useState<{ taskId: string; lastProgress: number; lastStep: string; duration: number } | null>(null);
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);

  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<AudioBufferSourceNode | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const startTimeRef = useRef(0);
  const pausedAtRef = useRef(0);
  const animationFrameRef = useRef<number>();
  const isPlayingRef = useRef(false);
  const workerRef = useRef<Worker | null>(null);
  const fileHashRef = useRef<string | null>(null);
  const sessionRestoredRef = useRef(false);

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
        console.log(`[useAudioProcessor] 初始健康检查: ${res.ok ? '后端可用' : '后端不可用'}`);
        if (res.ok) {
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
      })
      .catch(() => {
        setBackendAvailable(false);
        console.log('[useAudioProcessor] 初始健康检查: 后端不可用(请求失败)');
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
    });
  }, [params, processingOptions, selectedMode]);

  useEffect(() => {
    return () => {
      if (workerRef.current) {
        workerRef.current.terminate();
        workerRef.current = null;
      }
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

  useEffect(() => {
    if (sessionRestoredRef.current) return;
    sessionRestoredRef.current = true;

    (async () => {
      const session = await loadSession();
      if (!session || !session.file || !session.taskId) return;

      console.log(`[useAudioProcessor] 发现保存的会话: file=${session.fileName} taskId=${session.taskId}`);

      try {
        const healthRes = await fetch('/health', { signal: AbortSignal.timeout(5000) });
        if (!healthRes.ok) {
          console.log('[useAudioProcessor] 后端不可用，跳过会话恢复');
          return;
        }

        const statusRes = await fetch(`/api/v1/status/${session.taskId}`);
        if (!statusRes.ok) {
          console.log(`[useAudioProcessor] 任务不存在 taskId=${session.taskId}，跳过恢复`);
          await clearSession();
          return;
        }

        const taskStatus = await statusRes.json();
        if (taskStatus.status === 'error') {
          console.log(`[useAudioProcessor] 任务已出错，跳过恢复`);
          await clearSession();
          return;
        }

        console.log(`[useAudioProcessor] 恢复会话: taskId=${session.taskId} status=${taskStatus.status}`);

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
        setBackendAvailable(true);

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
      } catch (e) {
        console.warn('[useAudioProcessor] 会话恢复失败:', e);
        await clearSession();
      }
    })();
  }, [getAudioContext, processingOptions.sampleRate]);

  const stopPlaying = useCallback(() => {
    if (sourceNodeRef.current) {
      try { sourceNodeRef.current.stop(); } catch {}
      sourceNodeRef.current.disconnect();
      sourceNodeRef.current = null;
    }
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }
    isPlayingRef.current = false;
    setIsPlaying(false);
  }, []);

  const loadAudioFile = useCallback(async (file: File) => {
    stopPlaying();
    setAudioFile(file);

    setProcessingStep('计算文件哈希...');
    setIsProcessing(true);
    setProcessingProgress(0);

    const fileHash = await computeFileHash(file);
    fileHashRef.current = fileHash;
    console.log(`[loadAudioFile] fileHash=${fileHash}`);

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
    setBrowserAIDetection(null);
    setBackendAIDetection(null);
    setHasBeenProcessed(false);
    setPlayMode('original');
    setTaskId(null);
    taskIdRef.current = null;
    setRepairResult(null);
    setBackendAvailable(false);

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
        console.log(`[loadAudioFile] 文件已缓存，跳过上传 taskId=${newTaskId}`);
      } else {
        console.log(`[loadAudioFile] 上传成功 taskId=${newTaskId}`);
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

    const wavData = await new Promise<ArrayBuffer>((resolve, reject) => {
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

    worker.terminate();
    workerRef.current = null;

    return wavData;
  }, []);

  const applySettings = useCallback(async () => {
    if (!audioBuffer) return;

    setIsProcessing(true);
    setProcessingProgress(0);
    setProcessingStep('准备修复...');

    const REPAIR_TERMINALS = new Set(['completed', 'error']);
    let currentTaskId = taskIdRef.current;

    if (!currentTaskId && audioFile) {
      try {
        setProcessingStep('上传到后端...');
        setProcessingProgress(0.01);
        const uploadRes = await uploadAudio(audioFile, undefined, fileHashRef.current || undefined);
        currentTaskId = uploadRes.task_id;
        setTaskId(currentTaskId);
        taskIdRef.current = currentTaskId;
        setBackendAvailable(true);
        console.log(`[applySettings] 上传成功 taskId=${currentTaskId}`);
      } catch (uploadErr) {
        const msg = uploadErr instanceof Error ? uploadErr.message : String(uploadErr);
        console.warn(`[applySettings] 上传失败: ${msg}`);
        setBackendAvailable(false);
      }
    }

    const backendProg = { value: 0 };
    const browserProg = { value: 0 };

    const updateCombinedProgress = () => {
      if (currentTaskId) {
        setProcessingProgress(backendProg.value * 0.5 + browserProg.value * 0.5);
      } else {
        setProcessingProgress(browserProg.value);
      }
    };

    const backendRepairPromise = currentTaskId ? (async () => {
      try {
        setBackendAvailable(true);
        console.log(`[applySettings] 后端修复 taskId=${currentTaskId}`);

        await repairAudio(currentTaskId!, params, processingOptions, algorithmVersion);

        const repairResultData = await new Promise<import('../services/backendApi').ProgressEvent>((resolve, reject) => {
          pollProgress(
            currentTaskId!,
            {
              onProgress: (event) => {
                backendProg.value = 0.1 + event.progress * 0.8;
                updateCombinedProgress();
                setProcessingStep(`[后端] ${event.step}`);
              },
              onError: reject,
              onComplete: resolve,
              onStuck: (info) => {
                setIsTaskStuck(true);
                setStuckInfo(info);
              },
              onUnstuck: () => {
                // 进度恢复，自动消失卡住提示
                setIsTaskStuck(false);
              },
              onQueueUpdate: (queue) => {
                setQueueStatus(queue);
              },
            },
            REPAIR_TERMINALS,
          );
        });

        console.log(`[applySettings] 后端轮询结束 status=${repairResultData.status}`);

        if (repairResultData.status !== 'completed') {
          throw new Error(repairResultData.error || `修复失败(status=${repairResultData.status})`);
        }

        backendProg.value = 0.92;
        updateCombinedProgress();
        setProcessingStep('[后端] 加载修复后音频...');

        const previewUrl = getPreviewUrl(currentTaskId!, 'repaired');
        const repairedBuffer = await loadAudioFromUrl(previewUrl, processingOptions.sampleRate);

        backendProg.value = 0.98;
        updateCombinedProgress();

        return { buffer: repairedBuffer, repairResult: repairResultData.repair_result };
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.warn(`[applySettings] 后端修复失败: ${msg}`);
        setBackendAvailable(false);
        return null;
      }
    })() : Promise.resolve(null);

    const browserRepairPromise = (async () => {
      try {
        const { checkAISong } = await import('../utils/aiSongChecker');
        const { enhanceHighFrequencies } = await import('../utils/highFrequencyEnhancer');

        if (!originalAIDetection) {
          setOriginalAIDetection(checkAISong(audioBuffer));
        }

        browserProg.value = 0.05;
        updateCombinedProgress();

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
        };

        const repaired = await repairWithWorker(audioBuffer, workerParams, (progress, step) => {
          browserProg.value = 0.05 + progress * 0.8;
          updateCombinedProgress();
          setProcessingStep(`[浏览器] ${step}`);
        });

        browserProg.value = 0.85;
        updateCombinedProgress();

        const targetSampleRate = processingOptions.sampleRate;
        let finalBuffer: AudioBuffer;

        if (repaired.sampleRate !== targetSampleRate) {
          if (targetSampleRate === 96000) {
            setProcessingStep('[浏览器] 96kHz高频增强重采样...');
            finalBuffer = await enhanceHighFrequencies(repaired, (progress) => {
              browserProg.value = 0.85 + progress * 0.08;
              updateCombinedProgress();
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
        updateCombinedProgress();

        setProcessingStep('[浏览器] 完成');
        // 修复后不再自动触发AI检测，由用户手动触发
        // setBrowserAIDetection(checkAISong(finalBuffer));

        browserProg.value = 1.0;
        updateCombinedProgress()

        return finalBuffer;
      } catch (browserErr) {
        console.error('[applySettings] 浏览器修复失败:', browserErr);
        return null;
      }
    })();

    const [backendResult, browserResult] = await Promise.allSettled([backendRepairPromise, browserRepairPromise]);

    let anySuccess = false;

    if (backendResult.status === 'fulfilled' && backendResult.value) {
      setBackendProcessedBuffer(backendResult.value.buffer);
      if (backendResult.value.repairResult) {
        setRepairResult(backendResult.value.repairResult);
      }
      // 修复后不再自动触发AI检测，由用户手动触发
      // try {
      //   const { checkAISong } = await import('../utils/aiSongChecker');
      //   setBackendAIDetection(checkAISong(backendResult.value.buffer));
      // } catch {}
      anySuccess = true;

      if (audioFile && currentTaskId) {
        saveSession({
          file: audioFile,
          fileName: audioFile.name,
          fileSize: audioFile.size,
          fileHash: fileHashRef.current || '',
          taskId: currentTaskId,
          backendAvailable: true,
          hasBeenProcessed: true,
          wavInfo: wavInfo ? JSON.stringify(wavInfo) : '',
          repairResult: backendResult.value.repairResult ? JSON.stringify(backendResult.value.repairResult) : '',
        });
      }
    }

    if (browserResult.status === 'fulfilled' && browserResult.value) {
      setBrowserProcessedBuffer(browserResult.value);
      anySuccess = true;
    }

    if (anySuccess) {
      setHasBeenProcessed(true);
      if (backendResult.status === 'fulfilled' && backendResult.value) {
        setPlayMode('backend');
      } else {
        setPlayMode('browser');
      }
    }

    setProcessingStep('完成!');
    setProcessingProgress(1);
    setIsProcessing(false);
    setTimeout(() => {
      setProcessingStep('');
      setProcessingProgress(0);
    }, 2000);
  }, [audioBuffer, audioFile, params, processingOptions, originalAIDetection, loadAudioFromUrl, repairWithWorker, wavInfo]);

  const runAIDetection = useCallback(async () => {
    if (!audioBuffer) return;

    const currentTaskId = taskIdRef.current;
    const DETECT_TERMINALS = new Set(['detected', 'completed', 'error']);

    if (currentTaskId && backendAvailable) {
      try {
        setIsProcessing(true);
        setProcessingStep('AI检测原始音频...');
        setProcessingProgress(0);
        await detectAudio(currentTaskId, 'original', detectorVersion);

        const detectResult = await new Promise<import('../services/backendApi').ProgressEvent>((resolve, reject) => {
          pollProgress(
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
                // 进度恢复，自动消失卡住提示
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
        }

        if (hasBeenProcessed && backendProcessedBuffer) {
          setProcessingStep('AI检测后端修复音频...');
          await detectAudio(currentTaskId, 'repaired', detectorVersion);

          await new Promise<import('../services/backendApi').ProgressEvent>((resolve, reject) => {
            pollProgress(
              currentTaskId,
              {
                onProgress: (evt) => {
                  if (evt.repaired_detection_result) {
                    setBackendAIDetection(mapDetectionResult(evt.repaired_detection_result));
                  }
                },
                onError: reject,
                onComplete: resolve,
                onStuck: (info) => {
                  setIsTaskStuck(true);
                  setStuckInfo(info);
                },
                onUnstuck: () => {
                  // 进度恢复，自动消失卡住提示
                  setIsTaskStuck(false);
                },
              },
              DETECT_TERMINALS,
            );
          });
        }
      } catch (err) {
        console.warn('[runAIDetection] 后端检测失败, 降级本地:', err);
        const { checkAISong } = await import('../utils/aiSongChecker');
        setOriginalAIDetection(checkAISong(audioBuffer));
        if (hasBeenProcessed && backendProcessedBuffer) {
          setBackendAIDetection(checkAISong(backendProcessedBuffer));
        }
        if (hasBeenProcessed && browserProcessedBuffer) {
          setBrowserAIDetection(checkAISong(browserProcessedBuffer));
        }
      }
    } else {
      const { checkAISong } = await import('../utils/aiSongChecker');
      setOriginalAIDetection(checkAISong(audioBuffer));
      if (hasBeenProcessed && backendProcessedBuffer) {
        setBackendAIDetection(checkAISong(backendProcessedBuffer));
      }
      if (hasBeenProcessed && browserProcessedBuffer) {
        setBrowserAIDetection(checkAISong(browserProcessedBuffer));
      }
    }

    setIsProcessing(false);
    setProcessingStep('');
    setProcessingProgress(0);
  }, [audioBuffer, browserProcessedBuffer, backendProcessedBuffer, backendAvailable, hasBeenProcessed, detectorVersion]);

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
    console.log('[BackendDiag]\n' + diagText);

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

  const play = useCallback(() => {
    const buffer = getCurrentBuffer();
    if (!buffer) return;

    const context = getAudioContext();
    if (context.state === 'suspended') {
      context.resume();
    }

    if (sourceNodeRef.current) {
      stopPlaying();
    }

    const source = context.createBufferSource();
    const gain = context.createGain();

    source.buffer = buffer;
    source.connect(gain);
    gain.connect(analyserRef.current!);
    analyserRef.current!.connect(context.destination);

    gain.gain.value = 1.0;

    sourceNodeRef.current = source;
    gainNodeRef.current = gain;

    startTimeRef.current = context.currentTime - pausedAtRef.current;
    source.start(0, pausedAtRef.current);

    isPlayingRef.current = true;
    setIsPlaying(true);

    const updateTime = () => {
      if (isPlayingRef.current) {
        const current = context.currentTime - startTimeRef.current;
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

    source.onended = () => {
      if (isPlayingRef.current) {
        stopPlaying();
        setCurrentTime(0);
        pausedAtRef.current = 0;
      }
    };
  }, [getCurrentBuffer, getAudioContext, stopPlaying]);

  const pause = useCallback(() => {
    pausedAtRef.current = currentTime;
    stopPlaying();
  }, [currentTime, stopPlaying]);

  const seek = useCallback((time: number) => {
    const wasPlaying = isPlayingRef.current;
    if (isPlayingRef.current) {
      stopPlaying();
    }
    pausedAtRef.current = time;
    setCurrentTime(time);
    if (wasPlaying) {
      play();
    }
  }, [stopPlaying, play]);

  const switchPlayMode = useCallback((mode: PlayMode) => {
    setPlayMode(mode);

    if (isPlayingRef.current) {
      const currentPosition = currentTime;
      stopPlaying();
      pausedAtRef.current = currentPosition;
      setCurrentTime(currentPosition);
      play();
    }
  }, [currentTime, stopPlaying, play]);

  const downloadProcessedAudio = useCallback(async (source: 'browser' | 'backend') => {
    const targetBuffer = source === 'backend' ? backendProcessedBuffer : browserProcessedBuffer;
    if (!targetBuffer) return;

    const baseName = audioFile
      ? audioFile.name.replace(/\.[^/.]+$/, '')
      : 'audio';
    const fileName = source === 'backend'
      ? `${baseName}_backend_repaired.wav`
      : `${baseName}_browser_repaired.wav`;

    if (source === 'backend' && backendAvailable && taskId) {
      try {
        const url = getDownloadUrl(taskId);
        setIsProcessing(true);
        setProcessingStep('下载后端修复音频...');
        setProcessingProgress(0);

        const arrayBuffer = await downloadWithProgress(url, (loaded, total, speed) => {
          const pct = total > 0 ? loaded / total : 0;
          setProcessingProgress(pct);
          setProcessingStep(`下载中 ${formatBytes(loaded)}/${formatBytes(total)} ${formatSpeed(speed)}`);
        });

        const blob = new Blob([arrayBuffer], { type: 'audio/wav' });
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);

        setIsProcessing(false);
        setProcessingStep('');
        setProcessingProgress(0);
        return;
      } catch {
        setIsProcessing(false);
        setProcessingStep('');
        setProcessingProgress(0);
      }
    }

    try {
      const wavData = await encodeWavWithWorker(targetBuffer, processingOptions.bitDepth);
      const blob = new Blob([wavData], { type: 'audio/wav' });
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch {
      const wav = await audioBufferToWav(targetBuffer, {
        sampleRate: targetBuffer.sampleRate,
        bitDepth: processingOptions.bitDepth,
      });
      const blob = new Blob([wav], { type: 'audio/wav' });
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    }
  }, [backendAvailable, taskId, backendProcessedBuffer, browserProcessedBuffer, audioFile, processingOptions.bitDepth, encodeWavWithWorker]);

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
    browserAIDetection,
    backendAIDetection,
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
    setDetectorVersion,
    // 任务卡住相关状态
    isTaskStuck,
    stuckInfo,
    queueStatus,
    resetStuckState,
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



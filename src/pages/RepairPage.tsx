import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';
import { AudioUploader } from '../components/AudioUploader';
import { DualTrackUploader } from '../components/DualTrackUploader';
import { AIRepairPanel } from '../components/AIRepairPanel';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { DownloadModal, DownloadFileInfo, DualTrackDownloadUrls } from '../components/DownloadModal';
import { RepairCacheModal, CacheHitInfo } from '../components/RepairCacheModal';
import { useAudioProcessor, generateExportFilename } from '../hooks/useAudioProcessor';
import { uploadDualAudio, repairDualAudio, repairDualFromHash, getDownloadUrl, getPreviewUrl, connectProgressWS, WSProgressControl, VocalRepairParams, InstrumentRepairParams, defaultVocalRepairParams, defaultInstrumentRepairParams, fetchRenderCache, lookupDualRepairCache, mapParamsToBackend, mapVocalParamsToBackend, mapInstrumentParamsToBackend, connectCacheWS, CacheUpdateEvent, RenderCacheEntry, fetchFileInfoByHash } from '../services/backendApi';
import { useBackend } from '../contexts/BackendContext';
import { saveSettings, loadSettings } from '../utils/settingsStorage';
import { computeFileHash } from '../utils/fileHash';
import { useRepairSessionStore } from '../store/repairSessionStore';

export { useBackend };

export default function RepairPage() {
  const navigate = useNavigate();
  const { backendAvailable: globalBackendAvailable } = useBackend();
  const {
    audioFile,
    audioBuffer,
    backendProcessedBuffer,
    isProcessing,
    isDecodingAudio,
    processingProgress,
    processingStep,
    processingSource,
    params,
    audioAnalysis,
    selectedMode,
    repairModes,
    duration,
    processingOptions,
    hasBeenProcessed,
    originalSampleRate,
    currentSampleRate,
    backendDiag,
    runBackendDiag,
    wavInfo,
    repairResult,
    backendWaveformPeaks,
    originalWaveformPeaks,
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
    updateParam,
    resetParams,
    applyRepairMode,
    applySettings,
    setProcessingOptions,
    isRenderLoading,
    fileHash,
    saveProfile,
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
    setIsProcessing,
    setProcessingStep,
    setProcessingProgress,
    setProcessingSource,
    setBackendError,
    setHasBeenProcessed,
    setRepairResult,
    setBackendProcessedBuffer,
    setBackendWaveformPeaks,
    loadAudioFromUrl,
    setTaskId,
    setIsTaskStuck,
    setStuckInfo,
    setQueueStatus,
  } = useAudioProcessor();

  const [showDiag, setShowDiag] = useState(false);
  const [instantDownloadInfo, setInstantDownloadInfo] = useState<DownloadFileInfo | null>(null);

  const isDualTrackMode = useRepairSessionStore(s => s.isDualTrackMode);
  const dualTrackVocalFileHash = useRepairSessionStore(s => s.dualTrackVocalFileHash);
  const dualTrackAccompanimentFileHash = useRepairSessionStore(s => s.dualTrackAccompanimentFileHash);
  const dualTrackVocalFileName = useRepairSessionStore(s => s.dualTrackVocalFileName);
  const dualTrackAccompanimentFileName = useRepairSessionStore(s => s.dualTrackAccompanimentFileName);
  const dualTrackHasBeenProcessed = useRepairSessionStore(s => s.dualTrackHasBeenProcessed);
  const persistedVocalInfo = useRepairSessionStore(s => s.dualTrackVocalInfo);
  const persistedAccompanimentInfo = useRepairSessionStore(s => s.dualTrackAccompanimentInfo);
  const persistedRenderCaches = useRepairSessionStore(s => s.dualTrackRenderCaches);
  const sessionActions = useMemo(() => {
    const { setDualTrackMode, setDualTrackFiles, setDualTrackProcessed, setDualTrackFileInfo, setDualTrackRenderCaches, clearDualTrack, clearAll } = useRepairSessionStore.getState();
    return {
      setDualTrackMode,
      setDualTrackFiles,
      setDualTrackProcessed,
      setDualTrackFileInfo,
      setDualTrackRenderCaches,
      clearDualTrack,
      clearAll,
    };
  }, []);

  const [dualTrackTaskId, setDualTrackTaskId] = useState<string | null>(null);
  const [dualTrackVocalTaskId, setDualTrackVocalTaskId] = useState<string | null>(null);
  const [dualTrackAccompanimentTaskId, setDualTrackAccompanimentTaskId] = useState<string | null>(null);
  const [dualTrackVocalFile, setDualTrackVocalFile] = useState<File | null>(null);
  const [dualTrackAccompanimentFile, setDualTrackAccompanimentFile] = useState<File | null>(null);
  const [dualTrackDownloadUrl, setDualTrackDownloadUrl] = useState<string | null>(null);
  const [dualTrackRepairResult, setDualTrackRepairResult] = useState<any>(null);
  const [dualTrackFilesSelected, setDualTrackFilesSelected] = useState(false);
  const [dualTrackVocalInfo, setDualTrackVocalInfo] = useState<{ sample_rate: number; channels: number; duration: number } | null>(null);
  const [dualTrackAccompanimentInfo, setDualTrackAccompanimentInfo] = useState<{ sample_rate: number; channels: number; duration: number } | null>(null);
  const [dualCacheHitInfo, setDualCacheHitInfo] = useState<CacheHitInfo | null>(null);
  const [showDualRepairCacheModal, setShowDualRepairCacheModal] = useState(false);
  const forceDualReRepairRef = useRef(false);

  const [dualTrackVocalParams, setDualTrackVocalParams] = useState<VocalRepairParams>(() => {
    const saved = loadSettings();
    return { ...defaultVocalRepairParams, ...saved.dualTrackVocalParams };
  });
  const [dualTrackAccompanimentParams, setDualTrackAccompanimentParams] = useState<InstrumentRepairParams>(() => {
    const saved = loadSettings();
    return { ...defaultInstrumentRepairParams, ...saved.dualTrackInstrumentParams };
  });
  const [mixRatio, setMixRatio] = useState(() => {
    const saved = loadSettings();
    return saved.dualTrackMixRatio ?? 0.5;
  });
  const [dualTrackUrls, setDualTrackUrls] = useState<DualTrackDownloadUrls | null>(null);
  const dualTrackRenderCachesRef = useRef<RenderCacheEntry[]>([]);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  const wsDualTrackRef = useRef<WSProgressControl | null>(null);

  const dualTrackHasFiles = dualTrackFilesSelected || (!!dualTrackVocalFileHash && !!dualTrackAccompanimentFileHash);

  useEffect(() => {
    if (isDualTrackMode && persistedVocalInfo && !dualTrackVocalInfo) {
      setDualTrackVocalInfo(persistedVocalInfo);
    }
    if (isDualTrackMode && persistedAccompanimentInfo && !dualTrackAccompanimentInfo) {
      setDualTrackAccompanimentInfo(persistedAccompanimentInfo);
    }
  }, [isDualTrackMode, persistedVocalInfo, persistedAccompanimentInfo, dualTrackVocalInfo, dualTrackAccompanimentInfo]);

  const stopDualTrackPolling = useCallback(() => {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = null;
    }
    if (wsDualTrackRef.current) {
      wsDualTrackRef.current.close();
      wsDualTrackRef.current = null;
    }
  }, []);

  const startDualTrackPolling = useCallback((taskId: string) => {
    stopDualTrackPolling();

    wsDualTrackRef.current = connectProgressWS(taskId, {
      onProgress: (event) => {
        setProcessingProgress(event.progress);
        setProcessingStep(event.step);
      },
      onComplete: async (status) => {
        sessionActions.setDualTrackProcessed(true);
        setDualTrackRepairResult(status);
        const downloadUrl = getDownloadUrl(taskId);
        setDualTrackDownloadUrl(downloadUrl);
        setTaskId(taskId);
        try {
          const buffer = await loadAudioFromUrl(downloadUrl, processingOptions.sampleRate, true);
          setBackendProcessedBuffer(buffer);
          setBackendWaveformPeaks(null);
        } catch (e) {
          console.error('加载双轨处理结果失败:', e);
        }
        setProcessingStep('准备渲染交付...');
        setProcessingProgress(0);
        try {
          await renderAndDownload();
        } catch (e) {
          console.error('双轨渲染交付失败:', e);
        }
        setCacheTriggerKey(k => k + 1);
      },
      onError: (error) => {
        setIsProcessing(false);
        setBackendError(error.message || '双轨处理失败');
      },
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
    });
  }, [stopDualTrackPolling, setProcessingProgress, setProcessingStep, setIsProcessing, setBackendError, loadAudioFromUrl, setBackendProcessedBuffer, setBackendWaveformPeaks, setIsTaskStuck, setStuckInfo, setQueueStatus, processingOptions.sampleRate, renderAndDownload, setTaskId, sessionActions]);

  const handleDualTrackUpload = useCallback(async (vocalFile: File, accompanimentFile: File) => {
    try {
      setIsProcessing(true);
      setProcessingStep('计算文件哈希...');
      setProcessingSource('backend');
      setDualTrackVocalFile(vocalFile);
      setDualTrackAccompanimentFile(accompanimentFile);

      const [vocalHash, accompanimentHash] = await Promise.all([
        computeFileHash(vocalFile),
        computeFileHash(accompanimentFile),
      ]);

      sessionActions.setDualTrackMode(true);
      sessionActions.setDualTrackFiles(vocalHash, vocalFile.name, accompanimentHash, accompanimentFile.name);
      sessionActions.setDualTrackProcessed(false);

      setProcessingStep('上传双轨文件...');

      const uploadResult = await uploadDualAudio(
        vocalFile,
        accompanimentFile,
        (loaded, total, speed) => {
          const progress = loaded / total;
          setProcessingProgress(progress * 0.1);
          setProcessingStep(`上传中 ${(progress * 100).toFixed(0)}%`);
        },
        undefined,
        vocalHash,
        accompanimentHash
      );

      setDualTrackTaskId(uploadResult.task_id);
      setDualTrackVocalTaskId(uploadResult.vocal_task_id);
      setDualTrackAccompanimentTaskId(uploadResult.accompaniment_task_id);
      setDualTrackFilesSelected(true);
      setDualTrackVocalInfo(uploadResult.vocal_info || null);
      setDualTrackAccompanimentInfo(uploadResult.accompaniment_info || null);
      sessionActions.setDualTrackFileInfo(uploadResult.vocal_info || null, uploadResult.accompaniment_info || null);
      setIsProcessing(false);
      setProcessingStep('');
      setProcessingProgress(0);

    } catch (error) {
      console.error('双轨上传失败:', error);
      setBackendError(error instanceof Error ? error.message : '双轨上传失败');
      setIsProcessing(false);
    }
  }, [setIsProcessing, setProcessingStep, setProcessingProgress, setProcessingSource, setBackendError, sessionActions]);

  const handleSwitchToSingleTrack = useCallback(() => {
    sessionActions.setDualTrackMode(false);
    setDualTrackTaskId(null);
    setDualTrackVocalTaskId(null);
    setDualTrackAccompanimentTaskId(null);
    setDualTrackDownloadUrl(null);
    setDualTrackRepairResult(null);
    stopDualTrackPolling();
  }, [stopDualTrackPolling, sessionActions]);

  const handleDualTrackVocalParamChange = useCallback((key: keyof VocalRepairParams, value: number) => {
    setDualTrackVocalParams(prev => ({ ...prev, [key]: value }));
  }, []);

  const handleDualTrackAccompanimentParamChange = useCallback((key: keyof InstrumentRepairParams, value: number) => {
    setDualTrackAccompanimentParams(prev => ({ ...prev, [key]: value }));
  }, []);

  const handleDualTrackFileReplace = useCallback(async (type: 'vocal' | 'accompaniment', newFile: File) => {
    const vocal = type === 'vocal' ? newFile : dualTrackVocalFile;
    const accompaniment = type === 'accompaniment' ? newFile : dualTrackAccompanimentFile;

    if (type === 'vocal') setDualTrackVocalFile(newFile);
    else setDualTrackAccompanimentFile(newFile);

    sessionActions.setDualTrackProcessed(false);
    setDualTrackDownloadUrl(null);

    if (!vocal || !accompaniment) return;

    try {
      setIsProcessing(true);
      setProcessingStep('重新上传双轨文件...');
      setProcessingSource('backend');

      const [newVocalHash, newAccompanimentHash] = await Promise.all([
        computeFileHash(vocal),
        computeFileHash(accompaniment),
      ]);

      // 检查是否选择了相同的文件（哈希未变则无需重新上传，但需清除旧task_id让修复走hash分支）
      if (type === 'vocal' && newVocalHash === dualTrackVocalFileHash) {
        console.log('人声音频未变化，跳过重新上传');
        setDualTrackTaskId(null);
        setDualTrackVocalTaskId(null);
        setDualTrackAccompanimentTaskId(null);
        setIsProcessing(false);
        setProcessingStep('');
        setProcessingProgress(0);
        return;
      }
      if (type === 'accompaniment' && newAccompanimentHash === dualTrackAccompanimentFileHash) {
        console.log('伴奏音频未变化，跳过重新上传');
        setDualTrackTaskId(null);
        setDualTrackVocalTaskId(null);
        setDualTrackAccompanimentTaskId(null);
        setIsProcessing(false);
        setProcessingStep('');
        setProcessingProgress(0);
        return;
      }

      sessionActions.setDualTrackFiles(newVocalHash, vocal.name, newAccompanimentHash, accompaniment.name);

      const uploadResult = await uploadDualAudio(
        vocal,
        accompaniment,
        (loaded, total, speed) => {
          const progress = loaded / total;
          setProcessingProgress(progress * 0.1);
          setProcessingStep(`上传中 ${(progress * 100).toFixed(0)}%`);
        },
        undefined,
        newVocalHash,
        newAccompanimentHash
      );

      setDualTrackTaskId(uploadResult.task_id);
      setDualTrackVocalTaskId(uploadResult.vocal_task_id);
      setDualTrackAccompanimentTaskId(uploadResult.accompaniment_task_id);
      setDualTrackVocalInfo(uploadResult.vocal_info || null);
      setDualTrackAccompanimentInfo(uploadResult.accompaniment_info || null);
      setIsProcessing(false);
      setProcessingStep('');
      setProcessingProgress(0);
    } catch (error) {
      console.error('双轨重新上传失败:', error);
      setBackendError(error instanceof Error ? error.message : '双轨重新上传失败');
      setDualTrackTaskId(null);
      setDualTrackVocalTaskId(null);
      setDualTrackAccompanimentTaskId(null);
      setIsProcessing(false);
    }
  }, [dualTrackVocalFile, dualTrackAccompanimentFile, dualTrackVocalFileHash, dualTrackAccompanimentFileHash, setIsProcessing, setProcessingStep, setProcessingProgress, setProcessingSource, setBackendError, sessionActions]);

  const handleDualTrackRepair = useCallback(async () => {
    const hasFiles = dualTrackVocalFile && dualTrackAccompanimentFile;
    const hasHashes = dualTrackVocalFileHash && dualTrackAccompanimentFileHash;

    if (!hasFiles && !hasHashes) {
      setBackendError('请先上传人声和伴奏文件');
      return;
    }

    if (hasHashes && !forceDualReRepairRef.current) {
      try {
        const mainParams = mapParamsToBackend(params, processingOptions, algorithmVersion);
        const vParams = mapVocalParamsToBackend(dualTrackVocalParams, processingOptions, algorithmVersion);
        const aParams = mapInstrumentParamsToBackend(dualTrackAccompanimentParams, processingOptions, algorithmVersion);
        console.log('[双轨缓存] 发送缓存查询', {
          vocalHash: dualTrackVocalFileHash?.slice(0, 12),
          accHash: dualTrackAccompanimentFileHash?.slice(0, 12),
          mainParamsKeys: Object.keys(mainParams),
          vParamsKeys: Object.keys(vParams),
          aParamsKeys: Object.keys(aParams),
          mixRatio,
        });
        const cacheResult = await lookupDualRepairCache(dualTrackVocalFileHash, dualTrackAccompanimentFileHash, mainParams, vParams, aParams, mixRatio);
        if (cacheResult.found) {
          setDualCacheHitInfo({
            repair: {
              task_id: cacheResult.task_id || '',
              output_size: cacheResult.output_size || 0,
              repair_result: cacheResult.repair_result || undefined,
              detection_result: cacheResult.detection_result,
              repaired_detection_result: cacheResult.repaired_detection_result,
            },
            renderCaches: [],
          });
          if (cacheResult.task_id) {
            try {
              const renderCaches = await fetchRenderCache(cacheResult.task_id);
              setDualCacheHitInfo(prev => prev ? { ...prev, renderCaches } : null);
            } catch {}
          }
          setShowDualRepairCacheModal(true);
          setIsProcessing(false);
          return;
        }
      } catch (cacheErr) {
        console.error('双轨缓存查询失败:', cacheErr);
      }
    }
    forceDualReRepairRef.current = false;

    try {
      setIsProcessing(true);
      setProcessingStep('开始双轨修复...');
      setProcessingSource('backend');
      sessionActions.setDualTrackProcessed(false);
      setDualTrackDownloadUrl(null);

      if (dualTrackTaskId && dualTrackVocalTaskId && dualTrackAccompanimentTaskId) {
        await repairDualAudio(
          dualTrackTaskId,
          dualTrackVocalTaskId,
          dualTrackAccompanimentTaskId,
          params,
          processingOptions,
          algorithmVersion,
          dualTrackVocalParams,
          dualTrackAccompanimentParams,
          mixRatio
        );
        setProcessingStep('等待处理完成...');
        startDualTrackPolling(dualTrackTaskId);
      } else if (hasHashes) {
        const result = await repairDualFromHash(
          dualTrackVocalFileHash,
          dualTrackAccompanimentFileHash,
          dualTrackVocalFileName,
          dualTrackAccompanimentFileName,
          params,
          processingOptions,
          algorithmVersion,
          dualTrackVocalParams,
          dualTrackAccompanimentParams,
          mixRatio
        );
        setDualTrackTaskId(result.task_id);
        setDualTrackVocalTaskId(result.vocal_task_id);
        setDualTrackAccompanimentTaskId(result.accompaniment_task_id);
        setProcessingStep('等待处理完成...');
        startDualTrackPolling(result.task_id);
      } else {
        setBackendError('请先上传人声和伴奏文件');
        setIsProcessing(false);
      }
    } catch (error) {
      console.error('双轨修复失败:', error);
      setBackendError(error instanceof Error ? error.message : '双轨修复失败');
      setIsProcessing(false);
    }
  }, [dualTrackVocalFile, dualTrackAccompanimentFile, dualTrackVocalFileHash, dualTrackAccompanimentFileHash, dualTrackVocalFileName, dualTrackAccompanimentFileName, dualTrackTaskId, dualTrackVocalTaskId, dualTrackAccompanimentTaskId, params, processingOptions, algorithmVersion, dualTrackVocalParams, dualTrackAccompanimentParams, mixRatio, setIsProcessing, setProcessingStep, setProcessingSource, setBackendError, startDualTrackPolling, sessionActions]);

  const handleUseDualCache = useCallback(async (cachedTaskId: string) => {
    setShowDualRepairCacheModal(false);
    setDualTrackTaskId(cachedTaskId);
    setTaskId(cachedTaskId);

    const cache = dualCacheHitInfo?.repair;
    if (cache?.repair_result) {
      setDualTrackRepairResult(cache.repair_result);
    }

    sessionActions.setDualTrackProcessed(true);

    const previewUrl = getPreviewUrl(cachedTaskId, 'repaired');
    try {
      const buffer = await loadAudioFromUrl(previewUrl, processingOptions.sampleRate, true);
      setBackendProcessedBuffer(buffer);
      setBackendWaveformPeaks(null);
    } catch (e) {
      console.error('加载双轨缓存音频失败:', e);
    }

    setProcessingStep('准备渲染交付...');
    setProcessingProgress(0);
    try {
      await renderAndDownload();
    } catch (e) {
      console.error('双轨渲染交付失败:', e);
    }
    setCacheTriggerKey(k => k + 1);
  }, [dualCacheHitInfo, processingOptions.sampleRate, renderAndDownload, sessionActions, setTaskId, loadAudioFromUrl, setBackendProcessedBuffer, setBackendWaveformPeaks]);

  const handleDualReRepair = useCallback(() => {
    setShowDualRepairCacheModal(false);
    setDualCacheHitInfo(null);
    forceDualReRepairRef.current = true;
    handleDualTrackRepair();
  }, [handleDualTrackRepair]);

  const handleCloseDualRepairCache = useCallback(() => {
    setShowDualRepairCacheModal(false);
  }, []);

  useEffect(() => {
    if (!isDualTrackMode || !dualTrackVocalFileHash || !dualTrackAccompanimentFileHash) return;
    if (dualTrackTaskId) return;

    let cancelled = false;
    (async () => {
      try {
        const mainParams = mapParamsToBackend(params, processingOptions, algorithmVersion);
        const vParams = mapVocalParamsToBackend(dualTrackVocalParams, processingOptions, algorithmVersion);
        const aParams = mapInstrumentParamsToBackend(dualTrackAccompanimentParams, processingOptions, algorithmVersion);
        console.log('[双轨] mount 查询缓存', {
          vocalHash: dualTrackVocalFileHash?.slice(0, 12),
          accHash: dualTrackAccompanimentFileHash?.slice(0, 12),
          mainParamsKeys: Object.keys(mainParams),
        });
        const cacheResult = await lookupDualRepairCache(dualTrackVocalFileHash, dualTrackAccompanimentFileHash, mainParams, vParams, aParams, mixRatio);
        if (cancelled) return;
        if (cacheResult.found && cacheResult.task_id) {
          console.log('[双轨] mount 缓存命中', { taskId: cacheResult.task_id });
          setDualTrackTaskId(cacheResult.task_id);
          setTaskId(cacheResult.task_id);
          if (cacheResult.repair_result) {
            setDualTrackRepairResult(cacheResult.repair_result);
            sessionActions.setDualTrackProcessed(true);
          }
        }
      } catch (e) {
        console.warn('[双轨] mount 缓存查询失败', e);
      }

      try {
        const fileInfo = await fetchFileInfoByHash([dualTrackVocalFileHash, dualTrackAccompanimentFileHash]);
        if (cancelled) return;
        if (fileInfo[dualTrackVocalFileHash]) {
          console.log('[双轨] mount 恢复人声文件信息', fileInfo[dualTrackVocalFileHash]);
          setDualTrackVocalInfo(fileInfo[dualTrackVocalFileHash]);
        }
        if (fileInfo[dualTrackAccompanimentFileHash]) {
          console.log('[双轨] mount 恢复伴奏文件信息', fileInfo[dualTrackAccompanimentFileHash]);
          setDualTrackAccompanimentInfo(fileInfo[dualTrackAccompanimentFileHash]);
        }
      } catch (e) {
        console.warn('[双轨] mount 文件信息查询失败', e);
      }
    })();
    return () => { cancelled = true; };
  }, [isDualTrackMode, dualTrackVocalFileHash, dualTrackAccompanimentFileHash, dualTrackTaskId]);

  useEffect(() => {
    if (!isDualTrackMode) return;

    const wsControl = connectCacheWS((event: CacheUpdateEvent) => {
      if (event.task_id === dualTrackTaskId || !dualTrackTaskId) {
        setCacheTriggerKey(k => k + 1);
      }
    });

    return () => wsControl.close();
  }, [isDualTrackMode, dualTrackTaskId]);

  useEffect(() => {
    if (isDualTrackMode) {
      saveSettings({
        dualTrackVocalParams: dualTrackVocalParams,
        dualTrackInstrumentParams: dualTrackAccompanimentParams,
        dualTrackMixRatio: mixRatio,
      });
    }
  }, [isDualTrackMode, dualTrackVocalParams, dualTrackAccompanimentParams, mixRatio]);

  const renderResultInfo = useMemo(() => {
    if (!autoRenderInfo) return null;
    return {
      filename: `${(audioFile?.name || 'audio').replace(/\.[^/.]+$/, '')}_repaired.wav`,
      fileSize: autoRenderInfo.duration && autoRenderInfo.output_sample_rate && autoRenderInfo.channels && autoRenderInfo.output_bit_depth
        ? `${((autoRenderInfo.duration * autoRenderInfo.output_sample_rate * autoRenderInfo.channels * (autoRenderInfo.output_bit_depth / 8)) / (1024 * 1024)).toFixed(2)} MB`
        : '—',
      sampleRate: autoRenderInfo.output_sample_rate ? `${autoRenderInfo.output_sample_rate / 1000} kHz` : 'N/A',
      bitDepth: autoRenderInfo.output_bit_depth || 24,
      channels: autoRenderInfo.channels || 2,
      duration: autoRenderInfo.duration || 0,
      algorithmVersion: algorithmVersion,
    };
  }, [autoRenderInfo, audioFile, algorithmVersion]);

  const renderCacheRefreshRef = useRef<(() => Promise<void>) | null>(null);
  const handleRegisterCacheRefresh = useCallback((fn: () => Promise<void>) => {
    renderCacheRefreshRef.current = fn;
  }, []);
  const [cacheTriggerKey, setCacheTriggerKey] = useState(0);

  useEffect(() => {
    if (hasBeenProcessed) {
      setCacheTriggerKey(k => k + 1);
    }
  }, [hasBeenProcessed]);

  const prevRenderLoadingRef = useRef(false);
  useEffect(() => {
    if (prevRenderLoadingRef.current && !isRenderLoading) {
      setCacheTriggerKey(k => k + 1);
    }
    prevRenderLoadingRef.current = isRenderLoading;
  }, [isRenderLoading]);

  // 双轨模式修复完成时也触发缓存刷新
  useEffect(() => {
    if (dualTrackHasBeenProcessed) {
      setCacheTriggerKey(k => k + 1);
    }
  }, [dualTrackHasBeenProcessed]);

  const [stuckDuration, setStuckDuration] = useState(0);
  const stuckTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (isTaskStuck && stuckInfo) {
      setStuckDuration(stuckInfo.duration);
      stuckTimerRef.current = setInterval(() => {
        setStuckDuration(prev => prev + 1);
      }, 1000);
    } else {
      setStuckDuration(0);
      if (stuckTimerRef.current) {
        clearInterval(stuckTimerRef.current);
        stuckTimerRef.current = null;
      }
    }

    return () => {
      if (stuckTimerRef.current) {
        clearInterval(stuckTimerRef.current);
      }
    };
  }, [isTaskStuck, stuckInfo]);

  const [profileSaveMsg, setProfileSaveMsg] = useState('');

  const handleSaveProfile = useCallback((name: string) => {
    if (!name.trim()) return;
    saveProfile(name.trim());
    setProfileSaveMsg('配置已保存');
    setTimeout(() => setProfileSaveMsg(''), 2000);
  }, [saveProfile]);

  useEffect(() => {
    return () => {
      stopDualTrackPolling();
    };
  }, [stopDualTrackPolling]);

  const hasBackendResult = !!backendProcessedBuffer || !!repairResult;

  return (
    <ErrorBoundary>
    <div className="min-h-screen bg-dark py-6">
      <Header />

      {isProcessing && (
        <div className="sticky top-0 z-40 bg-dark/95 backdrop-blur border-b border-white/5">
          <div className="container mx-auto px-4 max-w-7xl py-2">
            <div className="flex items-center gap-3">
              <div className={`w-4 h-4 rounded-full animate-spin flex-shrink-0 ${isTaskStuck ? 'bg-yellow-500' : 'bg-gradient-to-r from-cyan-500 to-purple-500'}`} />
              <span className={`text-sm truncate flex items-center gap-2 ${isTaskStuck ? 'text-yellow-400' : 'text-cyan-400'}`}>
                {processingSource && (
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium flex-shrink-0 ${
                    processingSource === 'backend'
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                      : 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                  }`}>
                    {processingSource === 'backend' ? '后端' : ''}
                  </span>
                )}
                {isTaskStuck ? '任务可能已卡住...' : (processingStep || '正在处理音频...')}
              </span>
              {queueStatus && queueStatus.detecting + queueStatus.repairing > 0 && (
                <span className="text-xs text-gray-500 flex-shrink-0">
                  队列: {queueStatus.detecting + queueStatus.repairing}
                </span>
              )}
              <div className="flex-1 min-w-0">
                <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-300 ${isTaskStuck ? 'bg-yellow-500' : 'bg-gradient-to-r from-cyan-500 via-purple-500 to-yellow-500'}`}
                    style={{ width: `${processingProgress * 100}%` }}
                  />
                </div>
              </div>
              <span className="text-gray-400 text-xs flex-shrink-0 w-10 text-right">{Math.round(processingProgress * 100)}%</span>
            </div>
            {isTaskStuck && stuckInfo && (
              <div className="mt-1.5 text-xs text-yellow-400">
                已卡住 {Math.round(stuckDuration)} 秒 @ {stuckInfo.lastStep}
              </div>
            )}
          </div>
          {isTaskStuck && (
            <div className="border-t border-yellow-500/20 bg-yellow-500/5 px-4 py-2">
              <div className="container mx-auto max-w-7xl">
                <div className="flex items-start gap-3">
                  <svg className="w-4 h-4 text-yellow-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <div className="flex-1 min-w-0">
                    <p className="text-yellow-400 text-xs">任务执行似乎卡住了 - "{stuckInfo?.lastStep}" 已超过 {Math.round(stuckInfo?.duration || 0)} 秒</p>
                    <div className="flex gap-2 mt-1.5">
                      <button onClick={cancelCurrentTask} className="px-2.5 py-1 bg-red-500/20 hover:bg-red-500/30 text-red-400 text-xs rounded transition-colors">取消任务</button>
                      <button onClick={() => { resetStuckState(); if (processingStep.includes('修复')) applySettings(); }} className="px-2.5 py-1 bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-400 text-xs rounded transition-colors">重试</button>
                      <button onClick={resetStuckState} className="px-2.5 py-1 bg-white/5 hover:bg-white/10 text-gray-400 text-xs rounded transition-colors">继续等待</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="container mx-auto px-4 max-w-7xl mt-4">
        <button
          onClick={() => {
            if (isProcessing) {
              const confirmed = window.confirm('当前有正在进行的修复任务，返回首页将中断任务。是否确认返回？');
              if (!confirmed) return;
            }
            navigate('/');
          }}
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          <span>返回首页</span>
          {isProcessing && (
            <span className="ml-2 px-1.5 py-0.5 bg-yellow-500/20 text-yellow-400 text-[10px] rounded">
              处理中
            </span>
          )}
        </button>
      </div>

      <div className="container mx-auto px-4 py-6 max-w-7xl">
        <div className="w-full max-w-4xl mx-auto mb-6">
          <div className="flex items-center justify-center gap-4 p-1 bg-dark/80 rounded-xl border border-white/10">
            <button
              onClick={() => {
                if (isDualTrackMode) {
                  handleSwitchToSingleTrack();
                }
              }}
              className={`flex-1 py-2.5 px-6 rounded-lg font-medium transition ${
                !isDualTrackMode
                  ? 'bg-gradient-to-r from-secondary/80 to-primary/80 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              单轨上传
            </button>
            <button
              onClick={() => {
                if (!isDualTrackMode) {
                  sessionActions.setDualTrackMode(true);
                }
              }}
              className={`flex-1 py-2.5 px-6 rounded-lg font-medium transition ${
                isDualTrackMode
                  ? 'bg-gradient-to-r from-secondary/80 to-primary/80 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              双轨上传
            </button>
          </div>
        </div>

        {(isDualTrackMode ? !dualTrackHasFiles : !audioFile) ? (
          <div className="flex flex-col items-center py-10">
            {isDualTrackMode ? (
              <DualTrackUploader onFilesSelect={handleDualTrackUpload} isLoading={isProcessing} />
            ) : (
              <AudioUploader onFileSelect={loadAudioFile} />
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-7 space-y-6">
              {isDualTrackMode ? (
                <>
                  <div className="bg-gradient-to-br from-pink-500/10 to-dark/60 border border-pink-500/20 rounded-xl p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        <div className="w-9 h-9 bg-pink-500/20 rounded-lg flex items-center justify-center border border-pink-400/20 shrink-0">
                          <svg className="w-4 h-4 text-pink-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <h3 className="text-white font-medium truncate text-sm">{dualTrackVocalFile?.name || dualTrackVocalFileName || '人声轨'}</h3>
                            {(dualTrackVocalFile?.name || dualTrackVocalFileName) && (
                              <span className="text-[10px] px-1.5 py-0.5 bg-pink-500/20 text-pink-300 rounded shrink-0 uppercase">
                                {(dualTrackVocalFile?.name || dualTrackVocalFileName).split('.').pop()}
                              </span>
                            )}
                          </div>
                          <p className="text-gray-500 text-xs mt-0.5">
                            {dualTrackVocalFile
                              ? `${((dualTrackVocalFile.size) / (1024 * 1024)).toFixed(2)} MB`
                              : dualTrackVocalFileHash
                                ? <span className="text-cyan-400">已上传</span>
                                : '未上传'}
                            {dualTrackHasBeenProcessed && <span className="text-green-400 ml-1.5">✓ 已修复</span>}
                          </p>
                        </div>
                      </div>
                      <label className="flex items-center gap-1 px-2 py-1 bg-white/5 hover:bg-white/10 border border-white/10 rounded cursor-pointer transition text-gray-500 hover:text-white text-xs shrink-0">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                        替换
                        <input type="file" accept="audio/*" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleDualTrackFileReplace('vocal', f); e.target.value = ''; }} />
                      </label>
                    </div>
                  </div>
                  <div className="bg-gradient-to-br from-purple-500/10 to-dark/60 border border-purple-500/20 rounded-xl p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        <div className="w-9 h-9 bg-purple-500/20 rounded-lg flex items-center justify-center border border-purple-400/20 shrink-0">
                          <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <h3 className="text-white font-medium truncate text-sm">{dualTrackAccompanimentFile?.name || dualTrackAccompanimentFileName || '伴奏轨'}</h3>
                            {(dualTrackAccompanimentFile?.name || dualTrackAccompanimentFileName) && (
                              <span className="text-[10px] px-1.5 py-0.5 bg-purple-500/20 text-purple-300 rounded shrink-0 uppercase">
                                {(dualTrackAccompanimentFile?.name || dualTrackAccompanimentFileName).split('.').pop()}
                              </span>
                            )}
                          </div>
                          <p className="text-gray-500 text-xs mt-0.5">
                            {dualTrackAccompanimentFile
                              ? `${((dualTrackAccompanimentFile.size) / (1024 * 1024)).toFixed(2)} MB`
                              : dualTrackAccompanimentFileHash
                                ? <span className="text-cyan-400">已上传</span>
                                : '未上传'}
                            {dualTrackHasBeenProcessed && <span className="text-green-400 ml-1.5">✓ 已修复</span>}
                          </p>
                        </div>
                      </div>
                      <label className="flex items-center gap-1 px-2 py-1 bg-white/5 hover:bg-white/10 border border-white/10 rounded cursor-pointer transition text-gray-500 hover:text-white text-xs shrink-0">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                        替换
                        <input type="file" accept="audio/*" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleDualTrackFileReplace('accompaniment', f); e.target.value = ''; }} />
                      </label>
                    </div>
                  </div>
                  {dualTrackHasBeenProcessed && dualTrackTaskId && (
                    <button
                      onClick={() => navigate(`/compare?taskId=${dualTrackTaskId}&mode=dual`)}
                      className="flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-pink-500/20 to-purple-500/20 hover:from-pink-500/30 hover:to-purple-500/30 border border-pink-400/30 hover:border-pink-400/50 rounded-lg text-pink-400 text-sm font-medium transition-all w-full justify-center"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
                      <span>前往 AB 对比</span>
                      <span className="text-xs opacity-60 ml-1">人声 / 伴奏 / 合并</span>
                    </button>
                  )}
                </>
              ) : (
              <div className={`bg-primary/50 border border-white/10 rounded-xl p-6${isDecodingAudio ? ' audio-card-loading' : ''}`}>
                <div className="flex items-center justify-between mb-4 gap-3">
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <div className="w-12 h-12 bg-gradient-to-br from-cyan-500/20 to-purple-500/20 rounded-lg flex items-center justify-center border border-cyan-400/20 shrink-0">
                      <svg className="w-6 h-6 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                      </svg>
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-white font-semibold text-lg truncate">
                        {audioFile?.name}
                      </h3>
                      <p className="text-gray-400 text-sm">
                        <>
                          {((audioFile?.size || 0) / (1024 * 1024)).toFixed(2)} MB
                          {' • '}
                          {(wavInfo ? wavInfo.sampleRate : originalSampleRate) / 1000} kHz
                          {wavInfo && ` • ${wavInfo.bitDepth}bit`}
                          {' • '}
                          {wavInfo ? (wavInfo.channels === 1 ? '单声道' : '立体声') : (audioBuffer ? (audioBuffer.numberOfChannels === 1 ? '单声道' : '立体声') : '')}
                          {hasBeenProcessed && (
                            <span className="text-green-400 ml-2">✓ 已修复</span>
                          )}
                        </>
                      </p>
                    </div>
                  </div>
                  <label className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg cursor-pointer transition text-gray-400 hover:text-white text-sm shrink-0">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    替换文件
                    <input
                      type="file"
                      accept="audio/*"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) loadAudioFile(file);
                        e.target.value = '';
                      }}
                    />
                  </label>
                </div>

                {taskId && hasBeenProcessed && (
                  <div className="mt-4 space-y-2">
                    <button
                      onClick={() => navigate(`/compare?taskId=${taskId}`)}
                      className="flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-cyan-500/20 to-purple-500/20 hover:from-cyan-500/30 hover:to-purple-500/30 border border-cyan-400/30 hover:border-cyan-400/50 rounded-lg text-cyan-400 text-sm font-medium transition-all w-full justify-center"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                      </svg>
                      <span>前往 AB 对比</span>
                      <span className="text-xs opacity-60 ml-1">原始 / 修复后</span>
                    </button>
                  </div>
                )}
              </div>
              )}

              {backendError && (
                <div className="mt-4 p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
                  <div className="flex items-start gap-3">
                    <svg className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <div className="flex-1">
                      <p className="text-red-400 text-sm font-medium">后端处理出错</p>
                      <p className="text-gray-400 text-xs mt-1">{backendError}</p>
                    </div>
                    <button onClick={clearBackendError} className="text-gray-500 hover:text-white text-lg">×</button>
                  </div>
                </div>
              )}

            </div>

            <div className="lg:col-span-5 space-y-6">
              <AIRepairPanel
                params={params}
                fileHash={fileHash}
                analysis={audioAnalysis}
                selectedMode={selectedMode}
                modes={repairModes}
                processingOptions={processingOptions}
                algorithmVersion={algorithmVersion}
                availableAlgorithms={availableAlgorithms}
                onAlgorithmChange={applyAlgorithmVersion}
                onParamChange={updateParam}
                onReset={resetParams}
                onModeSelect={applyRepairMode}
                onApply={isDualTrackMode ? undefined : applySettings}
                onOptionsChange={setProcessingOptions}
                disabled={isProcessing}
                duration={duration}
                channels={audioBuffer?.numberOfChannels ?? 2}
                backendAvailable={globalBackendAvailable}
                onSaveProfile={handleSaveProfile}
                taskId={isDualTrackMode ? dualTrackTaskId : taskId}
                onRenderCacheRefresh={handleRegisterCacheRefresh}
                cacheTriggerKey={cacheTriggerKey}
                onInstantDownload={(cacheEntry) => {
                  const downloadUrl = `/api/v1/download-file/${cacheEntry.filename}`;
                  setRenderDownloadUrl(downloadUrl);
                  
                  const fileName = isDualTrackMode
                    ? (dualTrackVocalFileName || dualTrackAccompanimentFileName || 'audio')
                    : (audioFile?.name || 'audio');
                  
                  const fileDuration = isDualTrackMode
                    ? (dualTrackVocalInfo ? Math.max(dualTrackVocalInfo.duration, dualTrackAccompanimentInfo?.duration || 0) : 0)
                    : (duration || 0);
                  
                  setInstantDownloadInfo({
                    filename: generateExportFilename(fileName, cacheEntry.algorithm_version, cacheEntry.sample_rate, cacheEntry.bit_depth),
                    fileSize: `${(cacheEntry.size / (1024 * 1024)).toFixed(2)} MB`,
                    sampleRate: `${cacheEntry.sample_rate / 1000} kHz`,
                    bitDepth: cacheEntry.bit_depth,
                    channels: 2,
                    duration: fileDuration,
                    algorithmVersion: cacheEntry.algorithm_version,
                  });
                  
                  if (isDualTrackMode) {
                    const caches = dualTrackRenderCachesRef.current;
                    const algoVer = cacheEntry.algorithm_version;
                    const sr = cacheEntry.sample_rate;
                    const bd = cacheEntry.bit_depth;
                    const merged = caches.find(c => c.track_type === 'both' && c.algorithm_version === algoVer && c.sample_rate === sr && c.bit_depth === bd);
                    const vocal = caches.find(c => c.track_type === 'vocal' && c.algorithm_version === algoVer && c.sample_rate === sr && c.bit_depth === bd);
                    const accompaniment = caches.find(c => c.track_type === 'accompaniment' && c.algorithm_version === algoVer && c.sample_rate === sr && c.bit_depth === bd);
                    setDualTrackUrls({
                      merged: merged ? `/api/v1/download-file/${merged.filename}` : undefined,
                      vocal: vocal ? `/api/v1/download-file/${vocal.filename}` : undefined,
                      accompaniment: accompaniment ? `/api/v1/download-file/${accompaniment.filename}` : undefined,
                    });
                  } else {
                    setDualTrackUrls(null);
                  }
                  setShowDownloadModal(true);
                }}
                isDualTrackMode={isDualTrackMode}
                vocalParams={dualTrackVocalParams}
                accompanimentParams={dualTrackAccompanimentParams}
                mixRatio={mixRatio}
                onVocalParamChange={handleDualTrackVocalParamChange}
                onAccompanimentParamChange={handleDualTrackAccompanimentParamChange}
                onMixRatioChange={setMixRatio}
                onDualTrackRepair={isDualTrackMode ? handleDualTrackRepair : undefined}
                dualTrackVocalInfo={dualTrackVocalInfo}
                dualTrackAccompanimentInfo={dualTrackAccompanimentInfo}
                onRenderCachesLoaded={(caches) => { dualTrackRenderCachesRef.current = caches; sessionActions.setDualTrackRenderCaches(caches); }}
                persistedRenderCaches={isDualTrackMode ? (persistedRenderCaches as RenderCacheEntry[]) : undefined}
              />

              {profileSaveMsg && (
                <div className={`text-xs text-center ${profileSaveMsg.includes('失败') ? 'text-red-400' : 'text-green-400'}`}>
                  {profileSaveMsg}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {showDownloadModal && instantDownloadInfo && (
        <DownloadModal
          isOpen={showDownloadModal}
          backendInfo={instantDownloadInfo}
          backendDownloadUrl={renderDownloadUrl}
          dualTrackUrls={dualTrackUrls}
          onClose={() => setShowDownloadModal(false)}
        />
      )}

      {showRepairCacheModal && cacheHitInfo && (
        <RepairCacheModal
          isOpen={showRepairCacheModal}
          cacheHit={cacheHitInfo}
          audioFileName={audioFile?.name}
          algorithmVersion={algorithmVersion}
          onUseRepairCache={handleUseRepairCache}
          onRenderCacheDownload={handleRenderCacheDownload}
          onReRepair={handleReRepair}
          onClose={handleCloseRepairCacheModal}
        />
      )}

      {showDualRepairCacheModal && dualCacheHitInfo && (
        <RepairCacheModal
          isOpen={showDualRepairCacheModal}
          cacheHit={dualCacheHitInfo}
          audioFileName={dualTrackVocalFileName || dualTrackAccompanimentFileName || '双轨音频'}
          algorithmVersion={algorithmVersion}
          onUseRepairCache={handleUseRepairCache}
          onUseDualCache={handleUseDualCache}
          onRenderCacheDownload={handleRenderCacheDownload}
          onReRepair={handleDualReRepair}
          onClose={handleCloseDualRepairCache}
          isDualTrack={true}
        />
      )}
    </div>
    </ErrorBoundary>
  );
}

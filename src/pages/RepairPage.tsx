import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';
import { AudioUploader } from '../components/AudioUploader';
import { DualTrackUploader } from '../components/DualTrackUploader';
import { AIRepairPanel } from '../components/AIRepairPanel';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { DownloadModal, DownloadFileInfo } from '../components/DownloadModal';
import { RepairCacheModal } from '../components/RepairCacheModal';
import { useAudioProcessor, generateExportFilename } from '../hooks/useAudioProcessor';
import { uploadDualAudio, repairDualAudio, getTrackStatus, getDownloadUrl } from '../services/backendApi';
import { useBackend } from '../contexts/BackendContext';
import { AIRepairParams, defaultAIRepairParams } from '../utils/advancedAudioProcessing';

// 导出给其他页面使用
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
  } = useAudioProcessor();

  const [showDiag, setShowDiag] = useState(false);
  const [instantDownloadInfo, setInstantDownloadInfo] = useState<DownloadFileInfo | null>(null);
  const [isDualTrackMode, setIsDualTrackMode] = useState(false);
  const [dualTrackTaskId, setDualTrackTaskId] = useState<string | null>(null);
  const [dualTrackVocalTaskId, setDualTrackVocalTaskId] = useState<string | null>(null);
  const [dualTrackAccompanimentTaskId, setDualTrackAccompanimentTaskId] = useState<string | null>(null);
  const [dualTrackVocalFile, setDualTrackVocalFile] = useState<File | null>(null);
  const [dualTrackAccompanimentFile, setDualTrackAccompanimentFile] = useState<File | null>(null);
  const [dualTrackHasBeenProcessed, setDualTrackHasBeenProcessed] = useState(false);
  const [dualTrackDownloadUrl, setDualTrackDownloadUrl] = useState<string | null>(null);
  const [dualTrackRepairResult, setDualTrackRepairResult] = useState<any>(null);
  const [dualTrackFilesSelected, setDualTrackFilesSelected] = useState(false);
  const [dualTrackVocalParams, setDualTrackVocalParams] = useState<AIRepairParams>({ ...defaultAIRepairParams });
  const [dualTrackAccompanimentParams, setDualTrackAccompanimentParams] = useState<AIRepairParams>({ ...defaultAIRepairParams });
  const [mixRatio, setMixRatio] = useState(0.5);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const stopDualTrackPolling = useCallback(() => {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startDualTrackPolling = useCallback((taskId: string) => {
    stopDualTrackPolling();

    const poll = async () => {
      try {
        const status = await getTrackStatus(taskId);
        setProcessingProgress(status.progress);
        setProcessingStep(status.step);

        if (status.status === 'completed') {
          setIsProcessing(false);
          setDualTrackHasBeenProcessed(true);
          setDualTrackRepairResult(status);
          const downloadUrl = getDownloadUrl(taskId);
          setDualTrackDownloadUrl(downloadUrl);
          try {
            const buffer = await loadAudioFromUrl(downloadUrl, processingOptions.sampleRate, true);
            setBackendProcessedBuffer(buffer);
            setBackendWaveformPeaks(null);
          } catch (e) {
            console.error('加载双轨处理结果失败:', e);
          }
        } else if (status.status === 'error') {
          setIsProcessing(false);
          setBackendError(status.step || '双轨处理失败');
        } else {
          pollRef.current = setTimeout(poll, 1000);
        }
      } catch (error) {
        console.error('轮询双轨状态失败:', error);
        pollRef.current = setTimeout(poll, 2000);
      }
    };

    poll();
  }, [stopDualTrackPolling, setProcessingProgress, setProcessingStep, setIsProcessing, setBackendError, loadAudioFromUrl, setBackendProcessedBuffer, processingOptions.sampleRate]);

  const handleDualTrackUpload = useCallback(async (vocalFile: File, accompanimentFile: File) => {
    try {
      setIsProcessing(true);
      setProcessingStep('上传双轨文件...');
      setProcessingSource('backend');
      setDualTrackVocalFile(vocalFile);
      setDualTrackAccompanimentFile(accompanimentFile);

      const uploadResult = await uploadDualAudio(
        vocalFile,
        accompanimentFile,
        (loaded, total, speed) => {
          const progress = loaded / total;
          setProcessingProgress(progress * 0.1);
          setProcessingStep(`上传中 ${(progress * 100).toFixed(0)}%`);
        }
      );

      setDualTrackTaskId(uploadResult.task_id);
      setDualTrackVocalTaskId(uploadResult.vocal_task_id);
      setDualTrackAccompanimentTaskId(uploadResult.accompaniment_task_id);
      setDualTrackFilesSelected(true);
      setIsProcessing(false);
      setProcessingStep('');
      setProcessingProgress(0);

    } catch (error) {
      console.error('双轨上传失败:', error);
      setBackendError(error instanceof Error ? error.message : '双轨上传失败');
      setIsProcessing(false);
    }
  }, [setIsProcessing, setProcessingStep, setProcessingProgress, setProcessingSource, setBackendError]);

  const handleSwitchToSingleTrack = useCallback(() => {
    setIsDualTrackMode(false);
    setDualTrackTaskId(null);
    setDualTrackVocalTaskId(null);
    setDualTrackAccompanimentTaskId(null);
    setDualTrackVocalFile(null);
    setDualTrackAccompanimentFile(null);
    setDualTrackHasBeenProcessed(false);
    setDualTrackDownloadUrl(null);
    setDualTrackRepairResult(null);
    stopDualTrackPolling();
  }, [stopDualTrackPolling]);

  const handleDualTrackVocalParamChange = useCallback((key: keyof AIRepairParams, value: number) => {
    setDualTrackVocalParams(prev => ({ ...prev, [key]: value }));
  }, []);

  const handleDualTrackAccompanimentParamChange = useCallback((key: keyof AIRepairParams, value: number) => {
    setDualTrackAccompanimentParams(prev => ({ ...prev, [key]: value }));
  }, []);

  const handleDualTrackRepair = useCallback(async () => {
    if (!dualTrackVocalFile || !dualTrackAccompanimentFile) {
      setBackendError('请先上传人声和伴奏文件');
      return;
    }
    if (!dualTrackTaskId || !dualTrackVocalTaskId || !dualTrackAccompanimentTaskId) {
      setBackendError('任务ID缺失，请重新上传文件');
      return;
    }
    try {
      setIsProcessing(true);
      setProcessingStep('开始双轨修复...');
      setProcessingSource('backend');
      setDualTrackHasBeenProcessed(false);
      setDualTrackDownloadUrl(null);

      await repairDualAudio(
        dualTrackTaskId,
        dualTrackVocalTaskId,
        dualTrackAccompanimentTaskId,
        dualTrackVocalParams,
        processingOptions,
        algorithmVersion,
        dualTrackVocalParams,
        dualTrackAccompanimentParams,
        mixRatio
      );

      setProcessingStep('等待处理完成...');
      startDualTrackPolling(dualTrackTaskId!);
    } catch (error) {
      console.error('双轨修复失败:', error);
      setBackendError(error instanceof Error ? error.message : '双轨修复失败');
      setIsProcessing(false);
    }
  }, [dualTrackVocalFile, dualTrackAccompanimentFile, dualTrackTaskId, dualTrackVocalTaskId, dualTrackAccompanimentTaskId, dualTrackVocalParams, dualTrackAccompanimentParams, mixRatio, processingOptions, algorithmVersion, setIsProcessing, setProcessingStep, setProcessingSource, setBackendError, startDualTrackPolling]);

  useEffect(() => {
    if (!isDualTrackMode && audioFile) {
    }
  }, [isDualTrackMode, audioFile]);

  useEffect(() => {
    if (isDualTrackMode && availableAlgorithms.length > 0) {
      const v30 = availableAlgorithms.find(a => a.name === 'v3.0');
      const v30a = availableAlgorithms.find(a => a.name === 'v3.0a');
      if (v30 && algorithmVersion !== 'v3.0' && algorithmVersion !== 'v3.0a') {
        applyAlgorithmVersion('v3.0');
      } else if (v30a && algorithmVersion !== 'v3.0' && algorithmVersion !== 'v3.0a') {
        applyAlgorithmVersion('v3.0a');
      }
    }
  }, [isDualTrackMode, availableAlgorithms, algorithmVersion, applyAlgorithmVersion]);

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

  const handleSaveProfile = useCallback(async (name: string) => {
    if (!name.trim()) return;
    const result = await saveProfile(name.trim());
    if (result.success) {
      setProfileSaveMsg('配置已保存');
      setTimeout(() => setProfileSaveMsg(''), 2000);
    } else {
      setProfileSaveMsg(result.message || '保存失败');
      setTimeout(() => setProfileSaveMsg(''), 3000);
    }
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
                  setIsDualTrackMode(true);
                }
              }}
              className={`flex-1 py-2.5 px-6 rounded-lg font-medium transition ${
                isDualTrackMode
                  ? 'bg-gradient-to-r from-secondary/80 to-primary/80 text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              双轨上传 (v3.0)
            </button>
          </div>
        </div>

        {(!audioFile && !dualTrackFilesSelected) ? (
          <div className="flex flex-col items-center py-10">
            {isDualTrackMode ? (
              <DualTrackUploader onFilesSelect={handleDualTrackUpload} />
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
                            <h3 className="text-white font-medium truncate text-sm">{dualTrackVocalFile?.name || '人声轨'}</h3>
                            {dualTrackVocalFile?.name && (
                              <span className="text-[10px] px-1.5 py-0.5 bg-pink-500/20 text-pink-300 rounded shrink-0 uppercase">
                                {dualTrackVocalFile.name.split('.').pop()}
                              </span>
                            )}
                          </div>
                          <p className="text-gray-500 text-xs mt-0.5">
                            {((dualTrackVocalFile?.size || 0) / (1024 * 1024)).toFixed(2)} MB
                            {dualTrackHasBeenProcessed && <span className="text-green-400 ml-1.5">✓ 已修复</span>}
                          </p>
                        </div>
                      </div>
                      <label className="flex items-center gap-1 px-2 py-1 bg-white/5 hover:bg-white/10 border border-white/10 rounded cursor-pointer transition text-gray-500 hover:text-white text-xs shrink-0">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                        替换
                        <input type="file" accept="audio/*" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) { setDualTrackVocalFile(f); setDualTrackHasBeenProcessed(false); setDualTrackDownloadUrl(null); } e.target.value = ''; }} />
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
                            <h3 className="text-white font-medium truncate text-sm">{dualTrackAccompanimentFile?.name || '伴奏轨'}</h3>
                            {dualTrackAccompanimentFile?.name && (
                              <span className="text-[10px] px-1.5 py-0.5 bg-purple-500/20 text-purple-300 rounded shrink-0 uppercase">
                                {dualTrackAccompanimentFile.name.split('.').pop()}
                              </span>
                            )}
                          </div>
                          <p className="text-gray-500 text-xs mt-0.5">
                            {((dualTrackAccompanimentFile?.size || 0) / (1024 * 1024)).toFixed(2)} MB
                            {dualTrackHasBeenProcessed && <span className="text-green-400 ml-1.5">✓ 已修复</span>}
                          </p>
                        </div>
                      </div>
                      <label className="flex items-center gap-1 px-2 py-1 bg-white/5 hover:bg-white/10 border border-white/10 rounded cursor-pointer transition text-gray-500 hover:text-white text-xs shrink-0">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                        替换
                        <input type="file" accept="audio/*" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) { setDualTrackAccompanimentFile(f); setDualTrackHasBeenProcessed(false); setDualTrackDownloadUrl(null); } e.target.value = ''; }} />
                      </label>
                    </div>
                  </div>
                  {dualTrackHasBeenProcessed && dualTrackDownloadUrl && (
                    <button
                      onClick={() => {
                        setRenderDownloadUrl(dualTrackDownloadUrl);
                        setInstantDownloadInfo({
                          filename: generateExportFilename('dual_track', algorithmVersion, processingOptions.sampleRate, processingOptions.bitDepth, 'dual'),
                          fileSize: '—',
                          sampleRate: `${processingOptions.sampleRate / 1000} kHz`,
                          bitDepth: processingOptions.bitDepth,
                          channels: 2,
                          duration: 0,
                          algorithmVersion: algorithmVersion,
                        });
                        setShowDownloadModal(true);
                      }}
                      className="flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-cyan-500/20 to-purple-500/20 hover:from-cyan-500/30 hover:to-purple-500/30 border border-cyan-400/30 hover:border-cyan-400/50 rounded-lg text-cyan-400 text-sm font-medium transition-all w-full justify-center"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                      <span>下载双轨修复结果</span>
                    </button>
                  )}
                </>
              ) : (
              <div className={`bg-primary/50 border border-white/10 rounded-xl p-6${isDecodingAudio ? ' audio-card-loading' : ''}`}>
                <div className="flex items-center justify-between mb-4 gap-3">
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <div className="w-12 h-12 bg-gradient-to-br from-cyan-500/20 to-purple-500/20 rounded-lg flex items-center justify-center border border-cyan-400/20 shrink-0">
                      <svg className="w-6 h-6 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        {isDualTrackMode ? (
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                        ) : (
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2z" />
                        )}
                      </svg>
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-white font-semibold text-lg truncate">
                        {isDualTrackMode 
                          ? `${dualTrackVocalFile?.name} + ${dualTrackAccompanimentFile?.name}` 
                          : audioFile?.name}
                      </h3>
                      <p className="text-gray-400 text-sm">
                        {isDualTrackMode ? (
                          <>
                            🎤 人声: {((dualTrackVocalFile?.size || 0) / (1024 * 1024)).toFixed(2)} MB
                            {' • '}
                            🎵 伴奏: {((dualTrackAccompanimentFile?.size || 0) / (1024 * 1024)).toFixed(2)} MB
                            {dualTrackHasBeenProcessed && <span className="text-green-400 ml-2">✓ 已修复</span>}
                          </>
                        ) : (
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
                        )}
                      </p>
                    </div>
                  </div>
                  {isDualTrackMode ? (
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
                          if (file) {
                            setDualTrackVocalFile(file);
                            setDualTrackHasBeenProcessed(false);
                            setDualTrackDownloadUrl(null);
                          }
                          e.target.value = '';
                        }}
                      />
                    </label>
                  ) : (
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
                  )}
                </div>

                {((isDualTrackMode && dualTrackHasBeenProcessed && dualTrackDownloadUrl) || (!isDualTrackMode && taskId && hasBeenProcessed)) && (
                  <div className="mt-4">
                    {isDualTrackMode && dualTrackDownloadUrl ? (
                      <button
                        onClick={() => {
                          setRenderDownloadUrl(dualTrackDownloadUrl);
                          setInstantDownloadInfo({
                            filename: generateExportFilename('dual_track', algorithmVersion, processingOptions.sampleRate, processingOptions.bitDepth, 'dual'),
                            fileSize: '—',
                            sampleRate: `${processingOptions.sampleRate / 1000} kHz`,
                            bitDepth: processingOptions.bitDepth,
                            channels: 2,
                            duration: 0,
                            algorithmVersion: algorithmVersion,
                          });
                          setShowDownloadModal(true);
                        }}
                        className="flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-cyan-500/20 to-purple-500/20 hover:from-cyan-500/30 hover:to-purple-500/30 border border-cyan-400/30 hover:border-cyan-400/50 rounded-lg text-cyan-400 text-sm font-medium transition-all w-full justify-center"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        <span>下载双轨修复结果</span>
                      </button>
                    ) : (
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
                    )}
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
                  setInstantDownloadInfo({
                    filename: generateExportFilename(audioFile?.name, cacheEntry.algorithm_version, cacheEntry.sample_rate, cacheEntry.bit_depth),
                    fileSize: `${(cacheEntry.size / (1024 * 1024)).toFixed(2)} MB`,
                    sampleRate: `${cacheEntry.sample_rate / 1000} kHz`,
                    bitDepth: cacheEntry.bit_depth,
                    channels: 2,
                    duration: cacheEntry.duration || 0,
                    algorithmVersion: cacheEntry.algorithm_version,
                  });
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
          downloadUrl={renderDownloadUrl || ''}
          fileInfo={instantDownloadInfo}
          onClose={() => setShowDownloadModal(false)}
        />
      )}

      {showRepairCacheModal && cacheHitInfo && (
        <RepairCacheModal
          cacheInfo={cacheHitInfo}
          onUseCache={handleUseRepairCache}
          onReRepair={handleReRepair}
          onClose={handleCloseRepairCacheModal}
          onDownload={handleRenderCacheDownload}
        />
      )}
    </div>
    </ErrorBoundary>
  );
}

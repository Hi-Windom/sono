import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate, useBlocker } from 'react-router-dom';
import { Header } from '../components/Header';
import { AudioUploader } from '../components/AudioUploader';
import { AIRepairPanel } from '../components/AIRepairPanel';
import { DualTrackPanel } from '../components/DualTrackPanel';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { DownloadModal, DownloadFileInfo } from '../components/DownloadModal';
import { RepairCacheModal, CacheHitInfo } from '../components/RepairCacheModal';
import { useAudioProcessor, generateExportFilename } from '../hooks/useAudioProcessor';
import { useBackend } from '../contexts/BackendContext';
import { saveSettings, loadSettings } from '../utils/settingsStorage';
import { useRepairSessionStore } from '../store/repairSessionStore';
import { LeaveConfirmModal } from '../components/LeaveConfirmModal';

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
    params,
    audioAnalysis,
    selectedMode,
    repairModes,
    duration,
    processingOptions,
    hasBeenProcessed,
    originalSampleRate,
    wavInfo,
    repairResult,
    algorithmVersion,
    availableAlgorithms,
    applyAlgorithmVersion,
    isTaskStuck,
    stuckInfo,
    queueStatus,
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
  } = useAudioProcessor();

  const [showDiag, setShowDiag] = useState(false);
  const [instantDownloadInfo, setInstantDownloadInfo] = useState<DownloadFileInfo | null>(null);
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);
  const [profileSaveMsg, setProfileSaveMsg] = useState('');

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      (isProcessing || isRenderLoading) &&
      currentLocation.pathname !== nextLocation.pathname
  );

  useEffect(() => {
    if (blocker.state === 'blocked') {
      setShowLeaveConfirm(true);
    }
  }, [blocker]);

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (isProcessing || isRenderLoading) {
        e.preventDefault();
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isProcessing, isRenderLoading]);

  const isDualTrackMode = useRepairSessionStore(s => s.isDualTrackMode);

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

  const handleSaveProfile = useCallback((name: string) => {
    if (!name.trim()) return;
    saveProfile(name.trim());
    setProfileSaveMsg('配置已保存');
    setTimeout(() => setProfileSaveMsg(''), 2000);
  }, [saveProfile]);

  const handleSwitchToSingleTrack = useCallback(() => {
    useRepairSessionStore.getState().setDualTrackMode(false);
  }, []);

  const renderCacheRefreshRef = useRef<(() => Promise<void>) | null>(null);
  const handleRegisterCacheRefresh = useCallback((fn: () => Promise<void>) => {
    renderCacheRefreshRef.current = fn;
  }, []);

  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-gradient-to-br from-dark via-dark/95 to-dark">
        <Header />

        <main className="container mx-auto px-4 py-6 max-w-6xl">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-2xl font-bold text-white">音频修复</h1>
              <p className="text-gray-400 text-sm mt-1">使用 AI 技术修复音频中的瑕疵</p>
            </div>
            <div className="flex items-center gap-2">
              {isDualTrackMode && (
                <button
                  onClick={handleSwitchToSingleTrack}
                  className="px-3 py-1.5 text-sm text-gray-400 hover:text-white hover:bg-white/5 rounded-lg transition"
                >
                  返回单轨模式
                </button>
              )}
              <button
                onClick={() => setShowDiag(!showDiag)}
                className={`px-3 py-1.5 text-sm rounded-lg transition ${
                  showDiag
                    ? 'bg-gradient-to-r from-secondary/80 to-primary/80 text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                双轨上传 (v3.0)
              </button>
            </div>
          </div>

          {showDiag && (
            <div className="mb-6 p-4 bg-gradient-to-r from-pink-500/10 to-purple-500/10 border border-pink-500/20 rounded-xl">
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 bg-pink-500/20 rounded-lg flex items-center justify-center shrink-0">
                  <svg className="w-4 h-4 text-pink-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div>
                  <h3 className="text-pink-400 font-medium text-sm">双轨修复模式说明</h3>
                  <p className="text-gray-400 text-xs mt-1">
                    双轨模式允许您分别上传人声轨和伴奏轨，使用 v3.0+ 算法进行独立修复，
                    并支持实时混音控制。适合需要对人声和伴奏进行差异化处理的场景。
                  </p>
                  <button
                    onClick={() => {
                    setShowDiag(false);
                    useRepairSessionStore.getState().setDualTrackMode(true);
                  }}
                    className="mt-2 px-3 py-1 text-xs bg-pink-500/20 hover:bg-pink-500/30 text-pink-400 rounded-lg transition"
                  >
                    切换到双轨模式
                  </button>
                </div>
              </div>
            </div>
          )}

          {(!audioFile && !isDualTrackMode) ? (
            <div className="flex flex-col items-center py-10">
              <AudioUploader onFileSelect={loadAudioFile} />
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-7 space-y-6">
                {isDualTrackMode ? (
                  <DualTrackPanel
                    params={params}
                    processingOptions={processingOptions}
                    algorithmVersion={algorithmVersion}
                    availableAlgorithms={availableAlgorithms}
                    onAlgorithmChange={applyAlgorithmVersion}
                    onParamChange={updateParam}
                  />
                ) : (
                  <>
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
                  </>
                )}
              </div>

              <div className="lg:col-span-5 space-y-6">
                {!isDualTrackMode && (
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
                    onApply={applySettings}
                    onOptionsChange={setProcessingOptions}
                    disabled={isProcessing}
                    duration={duration}
                    channels={audioBuffer?.numberOfChannels ?? 2}
                    backendAvailable={globalBackendAvailable}
                    onSaveProfile={handleSaveProfile}
                    taskId={taskId}
                    onRenderCacheRefresh={handleRegisterCacheRefresh}
                    cacheTriggerKey={cacheTriggerKey}
                    onInstantDownload={(cacheEntry) => {
                      const downloadUrl = `/api/v1/download-file/${cacheEntry.filename}`;
                      setRenderDownloadUrl(downloadUrl);
                      setInstantDownloadInfo({
                        filename: generateExportFilename(audioFile?.name || 'audio', cacheEntry.algorithm_version, cacheEntry.sample_rate, cacheEntry.bit_depth),
                        fileSize: `${(cacheEntry.size / (1024 * 1024)).toFixed(2)} MB`,
                        sampleRate: `${cacheEntry.sample_rate / 1000} kHz`,
                        bitDepth: cacheEntry.bit_depth,
                        channels: 2,
                        duration: duration || 0,
                        algorithmVersion: cacheEntry.algorithm_version,
                      });
                      setShowDownloadModal(true);
                    }}
                  />
                )}

                {profileSaveMsg && (
                  <div className={`text-xs text-center ${profileSaveMsg.includes('失败') ? 'text-red-400' : 'text-green-400'}`}>
                    {profileSaveMsg}
                  </div>
                )}
              </div>
            </div>
          )}

          {showDownloadModal && instantDownloadInfo && (
            <DownloadModal
              isOpen={showDownloadModal}
              backendInfo={instantDownloadInfo}
              backendDownloadUrl={renderDownloadUrl}
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

          {showLeaveConfirm && (
            <LeaveConfirmModal
              isOpen={showLeaveConfirm}
              onConfirm={() => {
                setShowLeaveConfirm(false);
                blocker.proceed?.();
              }}
              onCancel={() => {
                setShowLeaveConfirm(false);
                blocker.reset?.();
              }}
              title="离开修复页面"
              tasks={[
                ...(isProcessing ? [{ name: '音频修复', step: processingStep || '处理中', progress: processingProgress }] : []),
                ...(isRenderLoading ? [{ name: '渲染导出', step: '渲染中...', progress: 0 }] : []),
              ]}
            />
          )}
        </main>
      </div>
    </ErrorBoundary>
  );
}
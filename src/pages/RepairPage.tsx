import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';
import { AudioUploader } from '../components/AudioUploader';
import { AudioPlayer } from '../components/AudioPlayer';
import { WaveformVisualizer } from '../components/WaveformVisualizer';
import { SpectrumVisualizer } from '../components/SpectrumVisualizer';
import { AIRepairPanel } from '../components/AIRepairPanel';
import { DownloadButton } from '../components/DownloadButton';
import { AIDetectionComparison } from '../components/AIDetectionComparison';
import { useAudioProcessor } from '../hooks/useAudioProcessor';

export default function RepairPage() {
  const navigate = useNavigate();
  const {
    audioFile,
    audioBuffer,
    browserProcessedBuffer,
    backendProcessedBuffer,
    isPlaying,
    currentTime,
    duration,
    isProcessing,
    isDecodingAudio,
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
    backendWaveformPeaks,
    algorithmVersion,
    availableAlgorithms,
    applyAlgorithmVersion,
    detectorVersion,
    availableDetectors,
    setDetectorVersion,
    // 任务卡住相关
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
    setProcessingOptions,
    downloadProcessedAudio,
    analyserRef,
    // 浏览器修复信息
    browserRepairInfo,
    enableBrowserRepair,
    setEnableBrowserRepair,
  } = useAudioProcessor();

  const [showDiag, setShowDiag] = useState(false);

  // 实时更新卡住秒数
  const [stuckDuration, setStuckDuration] = useState(0);
  const stuckTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (isTaskStuck && stuckInfo) {
      // 立即设置初始值
      setStuckDuration(stuckInfo.duration);
      // 每秒更新一次
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

  const hasBrowserResult = !!browserProcessedBuffer;
  const hasBackendResult = !!backendProcessedBuffer || !!repairResult;

  const activeBuffer = playMode === 'browser' ? (browserProcessedBuffer ?? audioBuffer)
    : playMode === 'backend' ? (backendProcessedBuffer ?? audioBuffer)
    : audioBuffer;

  const isBufferReady = playMode === 'browser' ? !!browserProcessedBuffer
    : playMode === 'backend' ? !!backendProcessedBuffer
    : true;

  const browserBufferInfo = browserProcessedBuffer ? {
    sampleRate: browserProcessedBuffer.sampleRate,
    channels: browserProcessedBuffer.numberOfChannels,
    duration: browserProcessedBuffer.duration,
  } : null;

  return (
    <div className="min-h-screen bg-dark py-6">
      <Header />

      {isProcessing && (
        <div className="sticky top-0 z-40 bg-dark/95 backdrop-blur border-b border-white/5">
          <div className="container mx-auto px-4 max-w-7xl py-2">
            <div className="flex items-center gap-3">
              <div className={`w-4 h-4 rounded-full animate-spin flex-shrink-0 ${isTaskStuck ? 'bg-yellow-500' : 'bg-gradient-to-r from-cyan-500 to-purple-500'}`} />
              <span className={`text-sm truncate ${isTaskStuck ? 'text-yellow-400' : 'text-cyan-400'}`}>
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
                      <button onClick={() => { resetStuckState(); if (processingStep.includes('检测')) runAIDetection(); else if (processingStep.includes('修复')) applySettings(); }} className="px-2.5 py-1 bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-400 text-xs rounded transition-colors">重试</button>
                      <button onClick={resetStuckState} className="px-2.5 py-1 bg-white/5 hover:bg-white/10 text-gray-400 text-xs rounded transition-colors">继续等待</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 返回首页按钮 */}
      <div className="container mx-auto px-4 max-w-7xl mt-4">
        <button
          onClick={() => {
            // 如果有正在进行的任务，显示二次确认
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
        {!audioFile ? (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="mb-4 text-sm">
              <span
                className={backendAvailable ? 'text-green-400' : 'text-yellow-400'}
                style={{ cursor: 'pointer', textDecoration: 'underline' }}
                onClick={async () => { await runBackendDiag(); setShowDiag(true); }}
              >
                {backendAvailable ? '● 后端已连接' : '● 后端不可用(点击诊断)'}
              </span>
            </div>
            <AudioUploader onFileSelect={loadAudioFile} />
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-7 space-y-6">
              <div className={`bg-primary/50 border border-white/10 rounded-xl p-6${isDecodingAudio ? ' audio-card-loading' : ''}`}>
                <div className="flex items-center justify-between mb-6 gap-3">
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <div className="w-12 h-12 bg-gradient-to-br from-cyan-500/20 to-purple-500/20 rounded-lg flex items-center justify-center border border-cyan-400/20 shrink-0">
                      <svg className="w-6 h-6 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2z" />
                      </svg>
                    </div>
                    <div className="min-w-0">
                      <h3 className="text-white font-semibold text-lg truncate">
                        {audioFile.name}
                      </h3>
                      <p className="text-gray-400 text-sm">
                        {(audioFile.size / (1024 * 1024)).toFixed(2)} MB
                        {' • '}
                        {(wavInfo ? wavInfo.sampleRate : originalSampleRate) / 1000} kHz
                        {wavInfo && ` • ${wavInfo.bitDepth}bit`}
                        {' • '}
                        {wavInfo ? (wavInfo.channels === 1 ? '单声道' : '立体声') : (audioBuffer ? (audioBuffer.numberOfChannels === 1 ? '单声道' : '立体声') : '')}
                        {hasBeenProcessed && (
                          <span className="text-green-400 ml-2">✓ 已修复</span>
                        )}
                        {' • '}
                        <span
                          className={backendAvailable ? 'text-green-400' : 'text-yellow-400'}
                          style={{ cursor: 'pointer', textDecoration: 'underline' }}
                          onClick={async () => { await runBackendDiag(); setShowDiag(true); }}
                        >
                          {backendAvailable ? '后端已连接' : '后端不可用(点击诊断)'}
                        </span>
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

                <AudioPlayer
                  isPlaying={isPlaying}
                  currentTime={currentTime}
                  duration={duration}
                  playMode={playMode}
                  hasBrowserResult={hasBrowserResult}
                  hasBackendResult={hasBackendResult}
                  onPlay={play}
                  onPause={pause}
                  onSeek={seek}
                  onSwitchPlayMode={switchPlayMode}
                />

                {analyserRef.current && (
                  <div className="mt-6">
                    <SpectrumVisualizer
                      analyser={analyserRef.current}
                      color={playMode === 'original' ? '#6B7280' : '#00D9FF'}
                      label={playMode === 'original' ? '原始频谱' : '修复后频谱'}
                    />
                  </div>
                )}

                <div className="mt-6">
                  <WaveformVisualizer
                    key={`waveform-${playMode}-${isBufferReady}`}
                    audioBuffer={activeBuffer}
                    waveformPeaks={playMode === 'backend' && !activeBuffer ? backendWaveformPeaks : null}
                    color={playMode === 'original' ? '#6B7280' : playMode === 'browser' ? '#A855F7' : '#00D9FF'}
                    label={playMode === 'original' ? '原始波形' : playMode === 'browser' ? (isBufferReady ? '浏览器修复波形' : '浏览器修复波形 (加载中...)') : (isBufferReady ? '后端修复波形' : '后端修复波形 (预览中...)')}
                    currentTime={currentTime}
                    duration={duration}
                    onSeek={seek}
                  />
                </div>
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

              <AIDetectionComparison
                before={originalAIDetection}
                backendAfter={backendAIDetection}
                onDetect={runAIDetection}
                isProcessing={isProcessing}
                detectorVersion={detectorVersion}
                onDetectorVersionChange={setDetectorVersion}
                availableDetectors={availableDetectors}
                algorithmVersion={algorithmVersion}
                originalDetectTime={originalDetectTime || undefined}
                repairedDetectTime={repairedDetectTime || undefined}
              />
            </div>

            <div className="lg:col-span-5 space-y-6">
              <AIRepairPanel
                params={params}
                analysis={audioAnalysis}
                selectedMode={selectedMode}
                modes={repairModes}
                processingOptions={processingOptions}
                algorithmVersion={algorithmVersion}
                availableAlgorithms={availableAlgorithms}
                enableBrowserRepair={enableBrowserRepair}
                onAlgorithmChange={applyAlgorithmVersion}
                onParamChange={updateParam}
                onReset={resetParams}
                onModeSelect={applyRepairMode}
                onApply={applySettings}
                onOptionsChange={setProcessingOptions}
                onEnableBrowserRepairChange={setEnableBrowserRepair}
                disabled={isProcessing}
                duration={duration}
                channels={audioBuffer?.numberOfChannels ?? 2}
                backendAvailable={backendAvailable}
              />

              <DownloadButton
                onDownloadBackend={() => downloadProcessedAudio('backend')}
                onDownloadBrowser={() => downloadProcessedAudio('browser')}
                hasBackendResult={hasBackendResult}
                hasBrowserResult={hasBrowserResult}
                backendRepairResult={repairResult}
                browserBufferInfo={browserBufferInfo}
                audioFileName={audioFile?.name}
                bitDepth={processingOptions.bitDepth}
                backendAlgorithmVersion={algorithmVersion}
                browserAlgorithmVersion={browserRepairInfo?.algorithmVersion}
                backendCompletedAt={repairResult?.completed_at}
                browserCompletedAt={browserRepairInfo?.completedAt}
              />
            </div>
          </div>
        )}
      </div>

      {showDiag && (
        <div
          style={{
            position: 'fixed', bottom: 0, left: 0, right: 0,
            background: 'rgba(0,0,0,0.95)', color: '#0f0',
            fontFamily: 'monospace', fontSize: 12,
            padding: 16, zIndex: 9999, maxHeight: '50vh', overflow: 'auto',
            borderTop: '2px solid #0f0',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ color: '#0f0', fontWeight: 'bold' }}>后端连接诊断</span>
            <button
              onClick={() => setShowDiag(false)}
              style={{ color: '#f00', background: 'none', border: 'none', cursor: 'pointer', fontSize: 16 }}
            >✕ 关闭</button>
          </div>
          <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{backendDiag}</pre>
          <button
            onClick={runBackendDiag}
            style={{
              marginTop: 8, padding: '4px 12px',
              background: '#0f0', color: '#000', border: 'none',
              cursor: 'pointer', fontWeight: 'bold',
            }}
          >重新检测</button>
        </div>
      )}
    </div>
  );
}

import React, { useState } from 'react';
import { Header } from '../components/Header';
import { AudioUploader } from '../components/AudioUploader';
import { AudioPlayer } from '../components/AudioPlayer';
import { WaveformVisualizer } from '../components/WaveformVisualizer';
import { SpectrumVisualizer } from '../components/SpectrumVisualizer';
import { AIRepairPanel } from '../components/AIRepairPanel';
import { AIDetectionComparison } from '../components/AIDetectionComparison';
import { DownloadModal, DownloadFileInfo } from '../components/DownloadModal';
import { useAudioProcessor, generateExportFilename } from '../hooks/useAudioProcessor';

export default function Home() {
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
    processingSource,
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
    setDetectorVersion,
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
    enableBrowserRepair,
    setEnableBrowserRepair,
    backendError,
    clearBackendError,
    renderAndDownload,
    browserRepairInfo,
    isRenderLoading,
    taskId,
    renderDownloadUrl,
    setRenderDownloadUrl,
    showDownloadModal,
    setShowDownloadModal,
    originalWaveformPeaks,
  } = useAudioProcessor();

  const [showDiag, setShowDiag] = useState(false);
  const [instantDownloadInfo, setInstantDownloadInfo] = useState<DownloadFileInfo | null>(null);

  const hasBrowserResult = !!browserProcessedBuffer;
  const hasBackendResult = !!backendProcessedBuffer || !!repairResult;

  const activeBuffer = playMode === 'browser' ? browserProcessedBuffer
    : playMode === 'backend' ? backendProcessedBuffer
    : audioBuffer;

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
              <div className="w-4 h-4 bg-gradient-to-r from-cyan-500 to-purple-500 rounded-full animate-spin flex-shrink-0" />
              <span className="text-cyan-400 text-sm truncate flex items-center gap-2">
                {processingSource && (
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium flex-shrink-0 ${
                    processingSource === 'backend'
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                      : 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                  }`}>
                    {processingSource === 'backend' ? '后端' : '浏览器'}
                  </span>
                )}
                {processingStep || '正在处理音频...'}
              </span>
              <div className="flex-1 min-w-0">
                <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-cyan-500 via-purple-500 to-yellow-500 transition-all duration-300"
                    style={{ width: `${processingProgress * 100}%` }}
                  />
                </div>
              </div>
              <span className="text-gray-400 text-xs flex-shrink-0 w-10 text-right">{Math.round(processingProgress * 100)}%</span>
            </div>
          </div>
        </div>
      )}

      <div className="container mx-auto px-4 py-8 max-w-7xl">
        {!audioFile ? (
          <div className="max-w-2xl mx-auto space-y-6">
            <div className="flex flex-col items-center justify-center py-12">
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
            {/* CacheManager moved to /cache-manager page */}
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
                    audioBuffer={activeBuffer ?? audioBuffer}
                    waveformPeaks={playMode === 'original' && !(activeBuffer ?? audioBuffer) ? originalWaveformPeaks : null}
                    label={playMode !== 'original' && activeBuffer ? '修复后波形' : '原始波形'}
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
                onInstantDownload={(cacheEntry) => {
                  const downloadUrl = `/api/v1/download-file/${cacheEntry.filename}`;
                  setRenderDownloadUrl(downloadUrl);
                  setInstantDownloadInfo({
                    filename: generateExportFilename(audioFile?.name, cacheEntry.algorithm_version, cacheEntry.sample_rate, cacheEntry.bit_depth),
                    fileSize: `${(cacheEntry.size / (1024 * 1024)).toFixed(2)} MB`,
                    sampleRate: `${cacheEntry.sample_rate / 1000} kHz`,
                    bitDepth: cacheEntry.bit_depth,
                    channels: 2,
                    duration: duration,
                    algorithmVersion: cacheEntry.algorithm_version,
                  });
                  setShowDownloadModal(true);
                }}
              />

              {/* CacheManager moved to /cache-manager page */}
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

      <DownloadModal
        isOpen={showDownloadModal}
        onClose={() => {
          setShowDownloadModal(false);
          setInstantDownloadInfo(null);
        }}
        backendInfo={instantDownloadInfo || (hasBackendResult && repairResult ? {
          filename: generateExportFilename(audioFile?.name, algorithmVersion, repairResult.output_sample_rate || processingOptions.sampleRate, repairResult.output_bit_depth || processingOptions.bitDepth),
          fileSize: repairResult.duration && repairResult.output_sample_rate && repairResult.channels && repairResult.output_bit_depth
            ? `${((repairResult.duration * repairResult.output_sample_rate * repairResult.channels * (repairResult.output_bit_depth / 8)) / (1024 * 1024)).toFixed(2)} MB`
            : '—',
          sampleRate: repairResult.output_sample_rate ? `${(repairResult.output_sample_rate / 1000).toFixed(1)} kHz` : 'N/A',
          bitDepth: repairResult.output_bit_depth || 32,
          channels: repairResult.channels || 2,
          duration: repairResult.duration || 0,
          algorithmVersion: algorithmVersion,
          completedAt: repairResult.completed_at,
        } : null)}
        browserInfo={hasBrowserResult && browserBufferInfo ? {
          filename: generateExportFilename(audioFile?.name, browserRepairInfo?.algorithmVersion || algorithmVersion, browserBufferInfo.sampleRate, processingOptions.bitDepth, 'browser'),
          fileSize: `${((browserBufferInfo.duration * browserBufferInfo.sampleRate * browserBufferInfo.channels * (processingOptions.bitDepth / 8)) / (1024 * 1024)).toFixed(2)} MB`,
          sampleRate: `${browserBufferInfo.sampleRate / 1000} kHz`,
          bitDepth: processingOptions.bitDepth,
          channels: browserBufferInfo.channels,
          duration: browserBufferInfo.duration,
          algorithmVersion: browserRepairInfo?.algorithmVersion,
          completedAt: browserRepairInfo?.completedAt,
        } : null}
        backendDownloadUrl={renderDownloadUrl}
        backendDownloadAction={hasBackendResult ? async () => {
          const result = await renderAndDownload();
          if (result?.downloadUrl) {
            setRenderDownloadUrl(result.downloadUrl);
          }
        } : undefined}
        browserDownloadAction={hasBrowserResult ? () => downloadProcessedAudio('browser') : undefined}
        isBackendLoading={isRenderLoading}
      />
    </div>
  );
}

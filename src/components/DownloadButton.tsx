import React from 'react';

interface DownloadButtonProps {
  onDownloadBackend?: () => void;
  onDownloadBrowser?: () => void;
  hasBackendResult: boolean;
  hasBrowserResult: boolean;
  backendRepairResult?: {
    issues_found: string[];
    original_sample_rate: number;
    output_sample_rate: number;
    output_bit_depth: number;
    duration: number;
    channels: number;
  } | null;
  browserBufferInfo?: {
    sampleRate: number;
    channels: number;
    duration: number;
  } | null;
  audioFileName?: string;
  bitDepth: number;
}

export function DownloadButton({
  onDownloadBackend,
  onDownloadBrowser,
  hasBackendResult,
  hasBrowserResult,
  backendRepairResult,
  browserBufferInfo,
  audioFileName,
  bitDepth,
}: DownloadButtonProps) {
  const baseName = audioFileName
    ? audioFileName.replace(/\.[^/.]+$/, '')
    : 'audio';

  const estimateSize = (duration: number, sampleRate: number, channels: number, bd: number) =>
    ((duration * sampleRate * channels * (bd / 8)) / (1024 * 1024)).toFixed(2);

  return (
    <div className="space-y-3">
      {hasBackendResult && (
        <div>
          <button
            onClick={onDownloadBackend}
            className="w-full py-3 px-6 rounded-xl font-bold text-base flex items-center justify-center gap-3 transition-all bg-gradient-to-r from-cyan-600 to-cyan-500 text-white hover:scale-[1.02] shadow-lg shadow-cyan-500/30"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            导出后端修复音频
          </button>
          {backendRepairResult && (
            <div className="mt-2 p-2 bg-black/20 rounded-lg space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">文件名</span>
                <span className="text-white truncate ml-4 max-w-[200px]" title={`${baseName}_backend_repaired.wav`}>{baseName}_backend_repaired.wav</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">文件大小</span>
                <span className="text-white">{estimateSize(backendRepairResult.duration, backendRepairResult.output_sample_rate, backendRepairResult.channels, backendRepairResult.output_bit_depth)} MB</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">采样率</span>
                <span className="text-cyan-400">{backendRepairResult.output_sample_rate / 1000} kHz</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">位深</span>
                <span className="text-cyan-400">{backendRepairResult.output_bit_depth} bit</span>
              </div>
            </div>
          )}
        </div>
      )}

      {hasBrowserResult && (
        <div>
          <button
            onClick={onDownloadBrowser}
            className="w-full py-3 px-6 rounded-xl font-bold text-base flex items-center justify-center gap-3 transition-all bg-gradient-to-r from-purple-600 to-purple-500 text-white hover:scale-[1.02] shadow-lg shadow-purple-500/30"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            导出浏览器修复音频
          </button>
          {browserBufferInfo && (
            <div className="mt-2 p-2 bg-black/20 rounded-lg space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">文件名</span>
                <span className="text-white truncate ml-4 max-w-[200px]" title={`${baseName}_browser_repaired.wav`}>{baseName}_browser_repaired.wav</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">文件大小</span>
                <span className="text-white">{estimateSize(browserBufferInfo.duration, browserBufferInfo.sampleRate, browserBufferInfo.channels, bitDepth)} MB</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">采样率</span>
                <span className="text-purple-400">{browserBufferInfo.sampleRate / 1000} kHz</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">位深</span>
                <span className="text-purple-400">{bitDepth} bit</span>
              </div>
            </div>
          )}
        </div>
      )}

      {!hasBackendResult && !hasBrowserResult && (
        <button
          disabled
          className="w-full py-4 px-6 rounded-xl font-bold text-lg flex items-center justify-center gap-3 bg-gray-700 text-gray-500 cursor-not-allowed"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          请先修复音频
        </button>
      )}
    </div>
  );
}

import React, { useState, useCallback, useEffect } from 'react';
import { parseFilenameFromDisposition } from '../services/backendApi';

export interface DownloadFileInfo {
  filename: string;
  fileSize: string;
  sampleRate: string;
  bitDepth: number;
  channels: number;
  duration: number;
  algorithmVersion?: string;
  completedAt?: string;
}

interface DownloadModalProps {
  isOpen: boolean;
  onClose: () => void;
  backendInfo?: DownloadFileInfo | null;
  browserInfo?: DownloadFileInfo | null;
  backendDownloadUrl?: string | null;
  backendDownloadAction?: () => void;
  browserDownloadAction?: () => void;
  isBackendLoading?: boolean;
}

export function DownloadModal({
  isOpen,
  onClose,
  backendInfo,
  browserInfo,
  backendDownloadUrl,
  backendDownloadAction,
  browserDownloadAction,
  isBackendLoading = false,
}: DownloadModalProps) {
  const [copySuccess, setCopySuccess] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [editingBackendName, setEditingBackendName] = useState(false);
  const [backendFilename, setBackendFilename] = useState('');
  const [editingBrowserName, setEditingBrowserName] = useState(false);
  const [browserFilename, setBrowserFilename] = useState('');

  useEffect(() => {
    if (backendInfo?.filename) setBackendFilename(backendInfo.filename);
  }, [backendInfo?.filename]);

  useEffect(() => {
    if (browserInfo?.filename) setBrowserFilename(browserInfo.filename);
  }, [browserInfo?.filename]);

  const handleCopyLink = useCallback(async (url: string) => {
    try {
      const fullUrl = new URL(url, window.location.origin).href;
      await navigator.clipboard.writeText(fullUrl);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } catch {
      const textArea = document.createElement('textarea');
      textArea.value = new URL(url, window.location.origin).href;
      textArea.style.position = 'fixed';
      textArea.style.opacity = '0';
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    }
  }, []);

  const handleDownload = useCallback(async (url: string, fallbackFilename: string) => {
    setDownloading(true);
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error('下载失败');
      const disposition = res.headers.get('Content-Disposition');
      const parsedName = parseFilenameFromDisposition(disposition);
      const saveName = fallbackFilename || parsedName || 'audio.wav';
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = saveName;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        URL.revokeObjectURL(blobUrl);
        document.body.removeChild(a);
      }, 5000);
    } catch (e) {
      console.warn('下载失败:', e);
    } finally {
      setDownloading(false);
    }
  }, []);

  const handleBrowserDownload = useCallback(() => {
    if (!browserDownloadAction) return;
    setDownloading(true);
    try {
      browserDownloadAction();
    } finally {
      setTimeout(() => setDownloading(false), 1000);
    }
  }, [browserDownloadAction]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative bg-[#0D1117] border border-white/10 rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center">
              <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
            </div>
            <div>
              <h2 className="text-white font-bold text-lg">导出音频</h2>
              <p className="text-gray-500 text-xs">选择下载方式，支持断点续传和多线程</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-white/10 rounded-lg text-gray-400 hover:text-white transition"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-3">
          {backendInfo && (
            <div className="bg-cyan-500/5 border border-cyan-500/20 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-2 h-2 rounded-full bg-cyan-400" />
                <span className="text-cyan-400 font-medium text-sm">后端修复</span>
              </div>
              <div className="space-y-1.5 text-xs">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-gray-400">文件名</span>
                    {!editingBackendName && (
                      <button
                        onClick={() => setEditingBackendName(true)}
                        className="text-gray-500 hover:text-cyan-400 transition text-[10px]"
                      >
                        ✏️ 修改
                      </button>
                    )}
                  </div>
                  {editingBackendName ? (
                    <input
                      type="text"
                      value={backendFilename}
                      onChange={(e) => setBackendFilename(e.target.value)}
                      onBlur={() => {
                        if (!backendFilename.trim()) setBackendFilename(backendInfo.filename);
                        setEditingBackendName(false);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          if (!backendFilename.trim()) setBackendFilename(backendInfo.filename);
                          setEditingBackendName(false);
                        }
                      }}
                      autoFocus
                      className="w-full px-2 py-1 bg-black/30 border border-cyan-500/30 rounded text-white text-xs focus:outline-none focus:border-cyan-400"
                    />
                  ) : (
                    <span className="text-white truncate block max-w-[280px]" title={backendFilename}>{backendFilename}</span>
                  )}
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">文件大小</span>
                  <span className="text-white">{backendInfo.fileSize}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">音频格式</span>
                  <span className="text-cyan-400">{backendInfo.sampleRate} / {backendInfo.bitDepth} bit</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">声道</span>
                  <span className="text-white">{backendInfo.channels === 2 ? '立体声' : backendInfo.channels === 1 ? '单声道' : `${backendInfo.channels}声道`}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">时长</span>
                  <span className="text-white">{Math.floor(backendInfo.duration / 60)}:{(backendInfo.duration % 60).toFixed(1).padStart(4, '0')}</span>
                </div>
                {backendInfo.algorithmVersion && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">修复算法</span>
                    <span className="text-cyan-400">{backendInfo.algorithmVersion}</span>
                  </div>
                )}
                {backendInfo.completedAt && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">完成时间</span>
                    <span className="text-white">{new Date(backendInfo.completedAt).toLocaleString('zh-CN')}</span>
                  </div>
                )}
              </div>
              {backendDownloadUrl && (
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={() => handleDownload(backendDownloadUrl, backendFilename)}
                    disabled={downloading || isBackendLoading}
                    className="flex-1 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-lg text-cyan-400 text-xs font-medium transition disabled:opacity-50"
                  >
                    {downloading ? '下载中...' : '⬇ 下载'}
                  </button>
                  <button
                    onClick={() => handleCopyLink(backendDownloadUrl)}
                    className="px-3 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-gray-400 text-xs transition"
                  >
                    {copySuccess ? '✓ 已复制' : '📋 复制链接'}
                  </button>
                </div>
              )}
              {!backendDownloadUrl && backendDownloadAction && (
                <div className="mt-3">
                  <button
                    onClick={() => backendDownloadAction()}
                    disabled={downloading || isBackendLoading}
                    className="w-full py-2 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-lg text-cyan-400 text-xs font-medium transition disabled:opacity-50"
                  >
                    {isBackendLoading ? '渲染中...' : '⬇ 渲染'}
                  </button>
                </div>
              )}
            </div>
          )}

          {browserInfo && (
            <div className="bg-purple-500/5 border border-purple-500/20 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-2 h-2 rounded-full bg-purple-400" />
                <span className="text-purple-400 font-medium text-sm">浏览器修复</span>
              </div>
              <div className="space-y-1.5 text-xs">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-gray-400">文件名</span>
                    {!editingBrowserName && (
                      <button
                        onClick={() => setEditingBrowserName(true)}
                        className="text-gray-500 hover:text-purple-400 transition text-[10px]"
                      >
                        ✏️ 修改
                      </button>
                    )}
                  </div>
                  {editingBrowserName ? (
                    <input
                      type="text"
                      value={browserFilename}
                      onChange={(e) => setBrowserFilename(e.target.value)}
                      onBlur={() => {
                        if (!browserFilename.trim()) setBrowserFilename(browserInfo.filename);
                        setEditingBrowserName(false);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          if (!browserFilename.trim()) setBrowserFilename(browserInfo.filename);
                          setEditingBrowserName(false);
                        }
                      }}
                      autoFocus
                      className="w-full px-2 py-1 bg-black/30 border border-purple-500/30 rounded text-white text-xs focus:outline-none focus:border-purple-400"
                    />
                  ) : (
                    <span className="text-white truncate block max-w-[280px]" title={browserFilename}>{browserFilename}</span>
                  )}
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">文件大小</span>
                  <span className="text-white">{browserInfo.fileSize}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">音频格式</span>
                  <span className="text-purple-400">{browserInfo.sampleRate} / {browserInfo.bitDepth} bit</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">声道</span>
                  <span className="text-white">{browserInfo.channels === 2 ? '立体声' : browserInfo.channels === 1 ? '单声道' : `${browserInfo.channels}声道`}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">时长</span>
                  <span className="text-white">{Math.floor(browserInfo.duration / 60)}:{(browserInfo.duration % 60).toFixed(1).padStart(4, '0')}</span>
                </div>
                {browserInfo.algorithmVersion && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">修复算法</span>
                    <span className="text-purple-400">{browserInfo.algorithmVersion}</span>
                  </div>
                )}
                {browserInfo.completedAt && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">完成时间</span>
                    <span className="text-white">{new Date(browserInfo.completedAt).toLocaleString('zh-CN')}</span>
                  </div>
                )}
              </div>
              {browserDownloadAction && (
                <div className="mt-3">
                  <button
                    onClick={handleBrowserDownload}
                    disabled={downloading}
                    className="w-full py-2 bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/30 rounded-lg text-purple-400 text-xs font-medium transition disabled:opacity-50"
                  >
                    {downloading ? '导出中...' : '⬇ 导出下载'}
                  </button>
                </div>
              )}
            </div>
          )}

          {!backendInfo && !browserInfo && (
            <div className="text-center py-8 text-gray-500 text-sm">
              暂无可导出的音频
            </div>
          )}
        </div>

        {backendDownloadUrl && (
          <div className="mt-4 p-3 bg-emerald-500/5 border border-emerald-500/20 rounded-lg">
            <div className="flex items-center gap-2 text-xs text-emerald-400/80">
              <span>💡</span>
              <span>下载链接支持 Range 请求，可使用多线程下载器（IDM、aria2 等）加速，最多 16 线程</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

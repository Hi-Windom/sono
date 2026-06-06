import React, { useState, useCallback, useEffect, useRef } from 'react';
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
  taskId?: string;
}

function formatSpeed(bytesPerSec: number): string {
  if (!bytesPerSec || bytesPerSec <= 0) return '';
  if (bytesPerSec < 1024) return `${bytesPerSec.toFixed(0)} B/s`;
  if (bytesPerSec < 1024 * 1024) return `${(bytesPerSec / 1024).toFixed(1)} KB/s`;
  return `${(bytesPerSec / 1024 / 1024).toFixed(1)} MB/s`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export interface DualTrackDownloadUrls {
  merged?: string;
  vocal?: string;
  accompaniment?: string;
}

interface DownloadModalProps {
  isOpen: boolean;
  onClose: () => void;
  backendInfo?: DownloadFileInfo | null;
  backendDownloadUrl?: string | null;
  backendDownloadAction?: () => void;
  isBackendLoading?: boolean;
  dualTrackUrls?: DualTrackDownloadUrls | null;
  taskId?: string;
  dualTrackTaskId?: string;
  dualTrackVocalTaskId?: string;
  dualTrackAccompanimentTaskId?: string;
}

export function DownloadModal({
  isOpen,
  onClose,
  backendInfo,
  backendDownloadUrl,
  backendDownloadAction,
  isBackendLoading = false,
  dualTrackUrls,
  taskId,
  dualTrackTaskId,
  dualTrackVocalTaskId,
  dualTrackAccompanimentTaskId,
}: DownloadModalProps) {
  const [copySuccess, setCopySuccess] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [dlProgress, setDlProgress] = useState(0);
  const [dlLoaded, setDlLoaded] = useState(0);
  const [dlTotal, setDlTotal] = useState(0);
  const [dlSpeed, setDlSpeed] = useState(0);
  const [mp3Loading, setMp3Loading] = useState(false);
  const [mp3Error, setMp3Error] = useState<string | null>(null);
  const [m4aLoading, setM4aLoading] = useState(false);
  const [m4aError, setM4aError] = useState<string | null>(null);
  const [editingBackendName, setEditingBackendName] = useState(false);
  const [backendFilename, setBackendFilename] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (backendInfo?.filename) setBackendFilename(backendInfo.filename);
  }, [backendInfo?.filename]);

  useEffect(() => {
    if (!isOpen) {
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
      setDownloading(false);
      setDlProgress(0);
      setDlLoaded(0);
      setDlTotal(0);
      setDlSpeed(0);
      setMp3Loading(false);
      setMp3Error(null);
      setM4aLoading(false);
      setM4aError(null);
    }
  }, [isOpen]);

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

  const extractFilenameFromDownloadUrl = useCallback((url: string): string | null => {
    if (!url) return null;
    const m = url.match(/\/download-file\/(.+?)(?:\?|$)/);
    if (m && m[1]) {
      try {
        return decodeURIComponent(m[1]);
      } catch {
        return m[1];
      }
    }
    return null;
  }, []);

  const handleDownloadMp3 = useCallback(async (source: { taskId?: string; url?: string }) => {
    setMp3Loading(true);
    setMp3Error(null);
    try {
      let res: Response;
      if (source.url) {
        const filename = extractFilenameFromDownloadUrl(source.url);
        if (!filename) {
          throw new Error('无法从下载 URL 解析文件名');
        }
        res = await fetch(`/api/v1/download-mp3-file/${encodeURIComponent(filename)}`);
      } else if (source.taskId) {
        res = await fetch(`/api/v1/download-mp3/${source.taskId}`);
      } else {
        throw new Error('缺少 taskId 或 url');
      }
      if (!res.ok) {
        if (res.status === 404) throw new Error('WAV音频文件不存在，请先完成修复');
        if (res.status === 500) throw new Error('MP3编码失败，请检查服务器日志');
        throw new Error(`服务器错误 (HTTP ${res.status})`);
      }
      const contentType = res.headers.get('content-type') || '';
      if (!contentType.includes('audio/')) {
        throw new Error(`服务器返回了非音频内容 (${contentType})，请重试`);
      }
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `${(source.taskId || 'audio')}.mp3`;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        URL.revokeObjectURL(blobUrl);
        document.body.removeChild(a);
      }, 5000);
    } catch (e) {
      if (e instanceof TypeError) {
        setMp3Error('网络连接失败，请检查网络后重试');
      } else {
        const msg = e instanceof Error ? e.message : String(e);
        setMp3Error(msg);
      }
    } finally {
      setMp3Loading(false);
    }
  }, []);

  const handleDownloadM4a = useCallback(async (source: { taskId?: string; url?: string }) => {
    setM4aLoading(true);
    setM4aError(null);
    try {
      let res: Response;
      if (source.url) {
        const filename = extractFilenameFromDownloadUrl(source.url);
        if (!filename) {
          throw new Error('无法从下载 URL 解析文件名');
        }
        res = await fetch(`/api/v1/download-m4a-file/${encodeURIComponent(filename)}`);
      } else if (source.taskId) {
        res = await fetch(`/api/v1/download-m4a/${source.taskId}`);
      } else {
        throw new Error('缺少 taskId 或 url');
      }
      if (!res.ok) {
        if (res.status === 404) throw new Error('WAV音频文件不存在，请先完成修复');
        if (res.status === 501) throw new Error('服务器不支持M4A编码（ffmpeg未安装）');
        if (res.status === 500) throw new Error('M4A编码失败，请检查服务器日志');
        throw new Error(`服务器错误 (HTTP ${res.status})`);
      }
      const contentType = res.headers.get('content-type') || '';
      if (!contentType.includes('audio/')) {
        throw new Error(`服务器返回了非音频内容 (${contentType})，请重试`);
      }
      const disposition = res.headers.get('Content-Disposition');
      let downloadName = `${(source.taskId || 'audio')}.m4a`;
      if (disposition) {
        const utf8Match = disposition.match(/filename\*=UTF-8''(.+)/);
        if (utf8Match) {
          downloadName = decodeURIComponent(utf8Match[1]);
        } else {
          const asciiMatch = disposition.match(/filename="?(.+?)"?$/);
          if (asciiMatch) downloadName = asciiMatch[1];
        }
      }
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = downloadName;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        URL.revokeObjectURL(blobUrl);
        document.body.removeChild(a);
      }, 5000);
    } catch (e) {
      if (e instanceof TypeError) {
        setM4aError('网络连接失败，请检查网络后重试');
      } else {
        const msg = e instanceof Error ? e.message : String(e);
        setM4aError(msg);
      }
    } finally {
      setM4aLoading(false);
    }
  }, []);

  const handleDownload = useCallback(async (url: string, fallbackFilename: string) => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setDownloading(true);
    setDlProgress(0);
    setDlLoaded(0);
    setDlTotal(0);
    setDlSpeed(0);

    try {
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) {
        throw new Error(`下载失败: HTTP ${res.status}`);
      }

      const contentLength = parseInt(res.headers.get('Content-Length') || '0', 10);
      setDlTotal(contentLength);

      const disposition = res.headers.get('Content-Disposition');
      const parsedName = parseFilenameFromDisposition(disposition);
      const saveName = fallbackFilename || parsedName || 'audio.wav';

      const reader = res.body?.getReader();
      if (!reader) {
        throw new Error('ReadableStream not supported');
      }

      const chunks: Uint8Array[] = [];
      let loaded = 0;
      const startTime = performance.now();
      let lastUpdate = startTime;
      let lastLoaded = 0;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        chunks.push(value);
        loaded += value.length;
        setDlLoaded(loaded);

        const now = performance.now();
        const elapsed = (now - lastUpdate) / 1000;
        if (elapsed >= 0.3) {
          const speed = (loaded - lastLoaded) / elapsed;
          setDlSpeed(speed);
          lastLoaded = loaded;
          lastUpdate = now;
        }

        if (contentLength > 0) {
          setDlProgress(loaded / contentLength);
        } else {
          setDlProgress(Math.min(0.95, 0.5 + loaded / (50 * 1024 * 1024) * 0.45));
        }
      }

      const totalElapsed = (performance.now() - startTime) / 1000;
      if (totalElapsed > 0) {
        setDlSpeed(loaded / totalElapsed);
      }
      setDlProgress(1);

      const blob = new Blob(chunks, { type: 'audio/wav' });
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
      if ((e as Error).name === 'AbortError') return;
      try {
        const a = document.createElement('a');
        a.href = url;
        a.download = fallbackFilename || 'audio.wav';
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
      } catch (fallbackErr) {
        alert('下载失败，请尝试复制链接使用下载器下载');
      }
    } finally {
      setDownloading(false);
      abortRef.current = null;
    }
  }, []);

  const dualTrackFilename = backendInfo?.filename
    ? `【合并_】${backendInfo.filename}`
    : '【合并_】audio.wav';
  const vocalTrackFilename = backendInfo?.filename
    ? backendInfo.filename.replace(/\.wav$/i, '') + '_人声.wav'
    : '人声.wav';
  const accompanimentTrackFilename = backendInfo?.filename
    ? backendInfo.filename.replace(/\.wav$/i, '') + '_伴奏.wav'
    : '伴奏.wav';

  if (!isOpen) return null;

  const showProgress = downloading && dlLoaded > 0;

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
          {dualTrackUrls && backendInfo ? (
            <>
              <div className="bg-cyan-500/5 border border-cyan-500/20 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-2 h-2 rounded-full bg-cyan-400" />
                  <span className="text-cyan-400 font-medium text-sm">双轨导出 - 合并轨</span>
                </div>
                <div className="space-y-1.5 text-xs">
                  <div className="flex justify-between">
                    <span className="text-gray-400">文件名</span>
                    <span className="text-white truncate max-w-[200px]" title={dualTrackFilename}>{dualTrackFilename}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">文件大小</span>
                    <span className="text-white">{backendInfo?.fileSize || '—'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">音频格式</span>
                    <span className="text-cyan-400">{backendInfo?.sampleRate || '—'} / {backendInfo?.bitDepth || '—'} bit</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">声道</span>
                    <span className="text-white">{backendInfo?.channels === 1 ? '单声道' : backendInfo?.channels === 2 ? '立体声' : (backendInfo?.channels ? `${backendInfo.channels} 声道` : '—')}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">时长</span>
                    <span className="text-white">{backendInfo?.duration ? `${backendInfo.duration.toFixed(1)}s` : '—'}</span>
                  </div>
                  {backendInfo?.algorithmVersion && (
                    <div className="flex justify-between">
                      <span className="text-gray-400">算法版本</span>
                      <span className="text-purple-400">{backendInfo.algorithmVersion}</span>
                    </div>
                  )}
                  {backendInfo?.completedAt && (
                    <div className="flex justify-between">
                      <span className="text-gray-400">完成时间</span>
                      <span className="text-gray-300">{backendInfo.completedAt}</span>
                    </div>
                  )}
                </div>
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={() => handleDownload(dualTrackUrls.merged || backendDownloadUrl!, dualTrackFilename)}
                    disabled={(!dualTrackUrls.merged && !backendDownloadUrl) || downloading || isBackendLoading}
                    className="flex-1 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-lg text-cyan-400 text-xs font-medium transition disabled:opacity-50"
                  >
                    {downloading ? `下载中 ${Math.round(dlProgress * 100)}%` : '⬇ WAV'}
                  </button>
                  <button
                    onClick={() => handleDownloadM4a({ taskId: dualTrackTaskId ?? undefined, url: dualTrackUrls.merged ?? backendDownloadUrl ?? undefined })}
                    disabled={(!dualTrackUrls.merged && !backendDownloadUrl) || m4aLoading || downloading || isBackendLoading}
                    className="flex-1 py-2 bg-orange-500/20 hover:bg-orange-500/30 border border-orange-500/30 rounded-lg text-orange-400 text-xs font-medium transition disabled:opacity-50"
                  >
                    {m4aLoading ? '编码中...' : '⬇ M4A'}
                  </button>
                  <button
                    onClick={() => handleDownloadMp3({ taskId: dualTrackTaskId ?? undefined, url: dualTrackUrls.merged ?? backendDownloadUrl ?? undefined })}
                    disabled={(!dualTrackUrls.merged && !backendDownloadUrl) || mp3Loading || downloading || isBackendLoading}
                    className="flex-1 py-2 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/30 rounded-lg text-emerald-400 text-xs font-medium transition disabled:opacity-50"
                  >
                    {mp3Loading ? '编码中...' : '⬇ MP3'}
                  </button>
                  <button
                    onClick={() => handleCopyLink(dualTrackUrls.merged || backendDownloadUrl!)}
                    disabled={!dualTrackUrls.merged && !backendDownloadUrl}
                    className="px-3 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-gray-400 text-xs transition disabled:opacity-50"
                  >
                    {copySuccess ? '✓ 已复制' : '📋'}
                  </button>
                </div>
              </div>
              {dualTrackUrls.vocal && (
                <div className="bg-purple-500/5 border border-purple-500/20 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-2 h-2 rounded-full bg-purple-400" />
                    <span className="text-purple-400 font-medium text-sm">人声轨</span>
                  </div>
                  <div className="mt-3 flex gap-2">
                    <button
                      onClick={() => handleDownload(dualTrackUrls.vocal!, vocalTrackFilename)}
                      disabled={downloading || isBackendLoading}
                      className="flex-1 py-2 bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/30 rounded-lg text-purple-400 text-xs font-medium transition disabled:opacity-50"
                    >
                      {downloading ? `下载中 ${Math.round(dlProgress * 100)}%` : '⬇ WAV'}
                    </button>
                    <button
                      onClick={() => handleDownloadM4a({ taskId: dualTrackVocalTaskId ?? undefined, url: dualTrackUrls.vocal ?? undefined })}
                      disabled={m4aLoading || downloading || isBackendLoading}
                      className="flex-1 py-2 bg-orange-500/20 hover:bg-orange-500/30 border border-orange-500/30 rounded-lg text-orange-400 text-xs font-medium transition disabled:opacity-50"
                    >
                      {m4aLoading ? '编码中...' : '⬇ M4A'}
                    </button>
                    <button
                      onClick={() => handleDownloadMp3({ taskId: dualTrackVocalTaskId ?? undefined, url: dualTrackUrls.vocal ?? undefined })}
                      disabled={mp3Loading || downloading || isBackendLoading}
                      className="flex-1 py-2 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/30 rounded-lg text-emerald-400 text-xs font-medium transition disabled:opacity-50"
                    >
                      {mp3Loading ? '编码中...' : '⬇ MP3'}
                    </button>
                    <button
                      onClick={() => handleCopyLink(dualTrackUrls.vocal!)}
                      className="px-3 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-gray-400 text-xs transition"
                    >
                      {copySuccess ? '✓ 已复制' : '📋'}
                    </button>
                  </div>
                </div>
              )}
              {dualTrackUrls.accompaniment && (
                <div className="bg-amber-500/5 border border-amber-500/20 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-2 h-2 rounded-full bg-amber-400" />
                    <span className="text-amber-400 font-medium text-sm">伴奏轨</span>
                  </div>
                  <div className="mt-3 flex gap-2">
                    <button
                      onClick={() => handleDownload(dualTrackUrls.accompaniment!, accompanimentTrackFilename)}
                      disabled={downloading || isBackendLoading}
                      className="flex-1 py-2 bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/30 rounded-lg text-amber-400 text-xs font-medium transition disabled:opacity-50"
                    >
                      {downloading ? `下载中 ${Math.round(dlProgress * 100)}%` : '⬇ WAV'}
                    </button>
                    <button
                      onClick={() => handleDownloadM4a({ taskId: dualTrackAccompanimentTaskId ?? undefined, url: dualTrackUrls.accompaniment ?? undefined })}
                      disabled={m4aLoading || downloading || isBackendLoading}
                      className="flex-1 py-2 bg-orange-500/20 hover:bg-orange-500/30 border border-orange-500/30 rounded-lg text-orange-400 text-xs font-medium transition disabled:opacity-50"
                    >
                      {m4aLoading ? '编码中...' : '⬇ M4A'}
                    </button>
                    <button
                      onClick={() => handleDownloadMp3({ taskId: dualTrackAccompanimentTaskId ?? undefined, url: dualTrackUrls.accompaniment ?? undefined })}
                      disabled={mp3Loading || downloading || isBackendLoading}
                      className="flex-1 py-2 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/30 rounded-lg text-emerald-400 text-xs font-medium transition disabled:opacity-50"
                    >
                      {mp3Loading ? '编码中...' : '⬇ MP3'}
                    </button>
                    <button
                      onClick={() => handleCopyLink(dualTrackUrls.accompaniment!)}
                      className="px-3 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-gray-400 text-xs transition"
                    >
                      {copySuccess ? '✓ 已复制' : '📋'}
                    </button>
                  </div>
                </div>
              )}
              {(mp3Error || m4aError) && (
                <div className="mt-2 text-red-400 text-[10px] text-center">
                  {mp3Error && `MP3 转换失败: ${mp3Error}`}
                  {mp3Error && m4aError && ' | '}
                  {m4aError && `M4A 转换失败: ${m4aError}`}
                </div>
              )}
            </>
          ) : backendInfo ? (
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

              {showProgress && (
                <div className="mt-3 space-y-1.5">
                  <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-cyan-500 to-cyan-400 transition-all duration-200 rounded-full"
                      style={{ width: `${Math.round(dlProgress * 100)}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] text-gray-400">
                    <span>{formatBytes(dlLoaded)}{dlTotal > 0 ? ` / ${formatBytes(dlTotal)}` : ''}</span>
                    <span>{formatSpeed(dlSpeed)}</span>
                  </div>
                </div>
              )}

              {backendDownloadUrl && (
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={() => handleDownload(backendDownloadUrl, backendFilename)}
                    disabled={downloading || isBackendLoading}
                    className="flex-1 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-lg text-cyan-400 text-xs font-medium transition disabled:opacity-50"
                  >
                    {downloading ? `下载中 ${Math.round(dlProgress * 100)}%` : '⬇ WAV'}
                  </button>
                  <button
                    onClick={() => handleDownloadM4a({ taskId: taskId ?? undefined, url: backendDownloadUrl ?? undefined })}
                    disabled={m4aLoading || downloading || isBackendLoading}
                    className="flex-1 py-2 bg-orange-500/20 hover:bg-orange-500/30 border border-orange-500/30 rounded-lg text-orange-400 text-xs font-medium transition disabled:opacity-50"
                  >
                    {m4aLoading ? '编码中...' : '⬇ M4A'}
                  </button>
                  <button
                    onClick={() => handleDownloadMp3({ taskId: taskId ?? undefined, url: backendDownloadUrl ?? undefined })}
                    disabled={mp3Loading || downloading || isBackendLoading}
                    className="flex-1 py-2 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/30 rounded-lg text-emerald-400 text-xs font-medium transition disabled:opacity-50"
                  >
                    {mp3Loading ? '编码中...' : '⬇ MP3'}
                  </button>
                  <button
                    onClick={() => handleCopyLink(backendDownloadUrl)}
                    className="px-3 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-gray-400 text-xs transition"
                  >
                    {copySuccess ? '✓ 已复制' : '📋'}
                  </button>
                </div>
              )}
              {(mp3Error || m4aError) && (
                <div className="mt-2 text-red-400 text-[10px] text-center">
                  {mp3Error && `MP3 转换失败: ${mp3Error}`}
                  {mp3Error && m4aError && ' | '}
                  {m4aError && `M4A 转换失败: ${m4aError}`}
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
          ) : (
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

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useBlocker } from 'react-router-dom';
import { Header } from '../components/Header';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { LeaveConfirmModal } from '../components/LeaveConfirmModal';
import { useBackend } from '../contexts/BackendContext';
import { AIDetectionCard } from '../components/AIDetectionComparison';
import { AISongDetectionResult } from '../utils/aiSongChecker';
import {
  detectFile,
  detectByPath,
  getAudioFiles,
  AudioFileInfo,
  connectProgressWS,
  mapDetectionResult,
  BackendDetectionResult,
  fetchDetectorVersions,
  DetectorVersion,
} from '../services/backendApi';

type SlotSource = 'none' | 'local' | 'server';
type SlotStatus = 'idle' | 'uploading' | 'detecting' | 'done' | 'error';

interface DetectSlotState {
  source: SlotSource;
  localFile: File | null;
  localFileName: string;
  serverFileId: string;
  serverFileName: string;
  taskId: string;
  status: SlotStatus;
  progress: number;
  step: string;
  result: AISongDetectionResult | null;
  detectTime: string;
  error: string;
}

function createEmptySlot(): DetectSlotState {
  return {
    source: 'none',
    localFile: null,
    localFileName: '',
    serverFileId: '',
    serverFileName: '',
    taskId: '',
    status: 'idle',
    progress: 0,
    step: '',
    result: null,
    detectTime: '',
    error: '',
  };
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function getFileTypeLabel(t: string): string {
  switch (t) {
    case 'upload': return '原始';
    case 'output': return '修复后';
    case 'render': return '交付';
    default: return t;
  }
}

export default function DetectPage() {
  const { backendAvailable: globalBackendAvailable } = useBackend();
  const [slotA, setSlotA] = useState<DetectSlotState>(createEmptySlot());
  const [slotB, setSlotB] = useState<DetectSlotState>(createEmptySlot());
  const [serverFiles, setServerFiles] = useState<AudioFileInfo[]>([]);
  const [serverFilesLoading, setServerFilesLoading] = useState(false);
  const [showServerPicker, setShowServerPicker] = useState<'a' | 'b' | null>(null);
  const [detectorVersion, setDetectorVersion] = useState('v1.1');
  const [detectorVersions, setDetectorVersions] = useState<DetectorVersion[]>([]);
  const wsControlRef = useRef<{ a: ReturnType<typeof connectProgressWS> | null; b: ReturnType<typeof connectProgressWS> | null }>({ a: null, b: null });
  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);

  const isDetecting = slotA.status === 'uploading' || slotA.status === 'detecting' || slotB.status === 'uploading' || slotB.status === 'detecting';

  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isDetecting &&
      currentLocation.pathname !== nextLocation.pathname
  );

  useEffect(() => {
    if (blocker.state === 'blocked') {
      setShowLeaveConfirm(true);
    }
  }, [blocker]);

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (isDetecting) {
        e.preventDefault();
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDetecting]);

  useEffect(() => {
    fetchDetectorVersions()
      .then(v => setDetectorVersions(v))
      .catch(() => {});
  }, []);

  useEffect(() => {
    setServerFilesLoading(true);
    getAudioFiles()
      .then(data => setServerFiles(data.files || []))
      .catch(() => {})
      .finally(() => setServerFilesLoading(false));
  }, []);

  useEffect(() => {
    return () => {
      wsControlRef.current.a?.close();
      wsControlRef.current.b?.close();
    };
  }, []);

  const startDetection = useCallback(async (slotId: 'a' | 'b', slot: DetectSlotState, setSlot: React.Dispatch<React.SetStateAction<DetectSlotState>>) => {
    if (slot.source === 'none') return;

    wsControlRef.current[slotId]?.close();
    wsControlRef.current[slotId] = null;

    setSlot(prev => ({ ...prev, status: 'uploading', progress: 0, step: '提交检测...', error: '', result: null, detectTime: '' }));

    try {
      let res: { task_id: string; status: string };
      if (slot.source === 'local' && slot.localFile) {
        res = await detectFile(slot.localFile, detectorVersion);
      } else if (slot.source === 'server' && slot.serverFileId) {
        res = await detectByPath(slot.serverFileId, detectorVersion);
      } else {
        setSlot(prev => ({ ...prev, status: 'error', error: '请先选择音频文件' }));
        return;
      }

      const taskId = res.task_id;
      setSlot(prev => ({ ...prev, taskId, status: 'detecting', progress: 0.05, step: '检测中...' }));

      const control = connectProgressWS(taskId, {
        onProgress: (event) => {
          if (event.progress !== undefined) {
            setSlot(prev => ({ ...prev, progress: event.progress, step: event.step || '' }));
          }
        },
        onComplete: (event) => {
          const detectionResult = event.detection_result as BackendDetectionResult | undefined;
          const now = new Date();
          const timeStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
          if (detectionResult) {
            const mapped = mapDetectionResult(detectionResult);
            setSlot(prev => ({ ...prev, status: 'done', progress: 1, step: '', result: mapped, detectTime: timeStr }));
          } else {
            setSlot(prev => ({ ...prev, status: 'done', progress: 1, step: '', detectTime: timeStr }));
          }
          wsControlRef.current[slotId] = null;
        },
        onError: (err) => {
          setSlot(prev => ({ ...prev, status: 'error', error: err.message, step: '' }));
          wsControlRef.current[slotId] = null;
        },
      }, new Set(['detected', 'completed', 'error']));

      wsControlRef.current[slotId] = control;
    } catch (e) {
      setSlot(prev => ({ ...prev, status: 'error', error: e instanceof Error ? e.message : '检测失败', step: '' }));
    }
  }, [detectorVersion]);

  const handleLocalFile = useCallback((slotId: 'a' | 'b', file: File) => {
    const setSlot = slotId === 'a' ? setSlotA : setSlotB;
    setSlot({
      source: 'local',
      localFile: file,
      localFileName: file.name,
      serverFileId: '',
      serverFileName: '',
      taskId: '',
      status: 'idle',
      progress: 0,
      step: '',
      result: null,
      detectTime: '',
      error: '',
    });
  }, []);

  const handleServerFile = useCallback((slotId: 'a' | 'b', file: AudioFileInfo) => {
    const setSlot = slotId === 'a' ? setSlotA : setSlotB;
    setSlot({
      source: 'server',
      localFile: null,
      localFileName: '',
      serverFileId: file.file_id,
      serverFileName: file.filename,
      taskId: '',
      status: 'idle',
      progress: 0,
      step: '',
      result: null,
      detectTime: '',
      error: '',
    });
    setShowServerPicker(null);
  }, []);

  const resetSlot = useCallback((slotId: 'a' | 'b') => {
    wsControlRef.current[slotId]?.close();
    wsControlRef.current[slotId] = null;
    const setSlot = slotId === 'a' ? setSlotA : setSlotB;
    setSlot(createEmptySlot());
  }, []);

  const renderSlot = (slotId: 'a' | 'b', slot: DetectSlotState, label: string, color: string, cardColor: string) => {
    const setSlot = slotId === 'a' ? setSlotA : setSlotB;
    const hasFile = slot.source !== 'none';
    const isBusy = slot.status === 'uploading' || slot.status === 'detecting';

    return (
      <div className="bg-gradient-to-br from-primary/60 to-dark/60 rounded-xl border border-white/10 overflow-hidden">
        <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            <span className="text-white font-medium text-sm">{label}</span>
          </div>
          {hasFile && (
            <button
              onClick={() => resetSlot(slotId)}
              className="text-gray-500 text-xs px-2 py-0.5 rounded bg-white/5 border border-white/10"
            >
              清除
            </button>
          )}
        </div>

        <div className="p-4">
          {!hasFile ? (
            <div className="space-y-3">
              <label className="block">
                <input
                  type="file"
                  accept="audio/*,.wav,.mp3,.flac,.ogg,.aac,.m4a,.wma"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleLocalFile(slotId, f);
                  }}
                />
                <div className="border-2 border-dashed border-white/10 rounded-lg p-6 text-center cursor-pointer">
                  <svg className="w-8 h-8 text-gray-500 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <p className="text-gray-400 text-sm">点击上传本地音频</p>
                  <p className="text-gray-600 text-xs mt-1">WAV / MP3 / FLAC / OGG / AAC</p>
                </div>
              </label>

              <div className="flex items-center gap-3">
                <div className="flex-1 h-px bg-white/10" />
                <span className="text-gray-500 text-xs">或</span>
                <div className="flex-1 h-px bg-white/10" />
              </div>

              <button
                onClick={() => setShowServerPicker(slotId)}
                className="w-full border border-white/10 rounded-lg p-4 text-center"
              >
                <svg className="w-6 h-6 text-gray-500 mx-auto mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                </svg>
                <p className="text-gray-400 text-sm">选择服务端音频</p>
                <p className="text-gray-600 text-xs mt-0.5">{serverFiles.length} 个可用文件</p>
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-3 bg-black/30 rounded-lg p-3">
                <svg className="w-5 h-5 shrink-0" style={{ color }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                </svg>
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm font-medium truncate">
                    {slot.source === 'local' ? slot.localFileName : slot.serverFileName}
                  </p>
                  <p className="text-gray-500 text-xs">
                    {slot.source === 'local' ? '本地上传' : '服务端音频'}
                  </p>
                </div>
              </div>

              {isBusy && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-400">{slot.step || '检测中...'}</span>
                    <span style={{ color }}>{Math.round(slot.progress * 100)}%</span>
                  </div>
                  <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-300"
                      style={{ width: `${slot.progress * 100}%`, backgroundColor: color }}
                    />
                  </div>
                </div>
              )}

              {slot.status === 'error' && (
                <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                  <p className="text-red-400 text-xs">{slot.error}</p>
                </div>
              )}

              {slot.status === 'done' && slot.result && (
                <AIDetectionCard
                  title={label}
                  result={slot.result}
                  color={cardColor}
                  algorithmVersion={detectorVersion}
                  detectTime={slot.detectTime || undefined}
                />
              )}

              {slot.status !== 'done' && !isBusy && (
                <button
                  onClick={() => startDetection(slotId, slot, setSlot)}
                  className="w-full py-2.5 rounded-lg text-sm font-medium text-white"
                  style={{ background: `linear-gradient(135deg, ${color}60, ${color}30)`, border: `1px solid ${color}40` }}
                >
                  开始检测
                </button>
              )}

              {slot.status === 'done' && (
                <button
                  onClick={() => startDetection(slotId, slot, setSlot)}
                  className="w-full py-2 rounded-lg text-xs font-medium bg-white/5 border border-white/10 text-gray-400"
                >
                  重新检测
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderServerPicker = () => {
    if (!showServerPicker) return null;
    const slotId = showServerPicker;

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowServerPicker(null)}>
        <div className="bg-[#1a1a2e] border border-white/10 rounded-xl w-full max-w-md max-h-[70vh] flex flex-col mx-4" onClick={e => e.stopPropagation()}>
          <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
            <span className="text-white font-medium text-sm">选择服务端音频</span>
            <button onClick={() => setShowServerPicker(null)} className="text-gray-400 text-xs">关闭</button>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {serverFilesLoading ? (
              <div className="flex items-center justify-center py-8 gap-2">
                <div className="w-5 h-5 rounded-full animate-spin border-2 border-cyan-500/30 border-t-cyan-500" />
                <span className="text-gray-400 text-sm">加载中...</span>
              </div>
            ) : serverFiles.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-gray-500 text-sm">暂无服务端音频</p>
                <p className="text-gray-600 text-xs mt-1">请先在修复页上传音频</p>
              </div>
            ) : (
              serverFiles.map(f => (
                <button
                  key={f.file_id}
                  onClick={() => handleServerFile(slotId, f)}
                  className="w-full flex items-center gap-3 p-3 bg-white/5 border border-white/10 rounded-lg text-left"
                >
                  <div className="w-8 h-8 bg-cyan-500/10 rounded flex items-center justify-center shrink-0">
                    <svg className="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                    </svg>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-xs font-medium truncate">{f.filename}</p>
                    <p className="text-gray-500 text-xs mt-0.5">
                      {getFileTypeLabel(f.type)} · {formatFileSize(f.size)}
                    </p>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      </div>
    );
  };

  const renderComparison = () => {
    if (!slotA.result || !slotB.result) return null;

    const diffAi = (slotB.result.aiProbability - slotA.result.aiProbability) * 100;
    const diffHuman = (slotB.result.humanProbability - slotA.result.humanProbability) * 100;
    const isImproved = diffAi < -3;
    const isNeutral = Math.abs(diffAi) <= 3;

    return (
      <div className="mt-6 bg-gradient-to-br from-primary/60 to-dark/60 rounded-xl border border-white/10 p-4">
        <h3 className="text-white font-medium text-sm mb-3 flex items-center gap-2">
          <svg className="w-4 h-4 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 01-2-2H5a2 2 0 01-2 2v6a2 2 0 012 2h2a2 2 0 012-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 012 2h2a2 2 0 012-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          对比摘要
        </h3>
        <div className="grid grid-cols-2 gap-4 text-center">
          <div>
            <p className="text-gray-500 text-xs mb-1">AI概率差异</p>
            <p className={`text-lg font-bold ${isImproved ? 'text-green-400' : isNeutral ? 'text-gray-400' : 'text-red-400'}`}>
              {diffAi > 0 ? '+' : ''}{diffAi.toFixed(1)}%
            </p>
          </div>
          <div>
            <p className="text-gray-500 text-xs mb-1">人类概率差异</p>
            <p className={`text-lg font-bold ${diffHuman > 3 ? 'text-green-400' : Math.abs(diffHuman) <= 3 ? 'text-gray-400' : 'text-red-400'}`}>
              {diffHuman > 0 ? '+' : ''}{diffHuman.toFixed(1)}%
            </p>
          </div>
        </div>
        <div className="mt-3 text-center">
          <span className={`px-3 py-1 rounded-full text-xs font-medium ${
            isImproved ? 'bg-green-500/20 text-green-400' : isNeutral ? 'bg-gray-500/20 text-gray-400' : 'bg-red-500/20 text-red-400'
          }`}>
            B相对A: {isImproved ? 'AI特征减少' : isNeutral ? '基本持平' : 'AI特征增加'}
          </span>
        </div>
      </div>
    );
  };

  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-dark py-6">
        <Header />

        <div className="container mx-auto px-4 max-w-5xl mt-4">

          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-bold text-xl">AI检测分析</h2>
            <div className="flex items-center gap-2">
              <span className="text-gray-500 text-xs">检测版本</span>
              <select
                value={detectorVersion}
                onChange={(e) => setDetectorVersion(e.target.value)}
                className="appearance-none text-white text-xs font-medium py-1 pl-2 pr-5 rounded-md border bg-cyan-500/20 border-cyan-400/40 cursor-pointer"
                style={{
                  backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2300D9FF' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
                  backgroundPosition: 'right 0.25rem center',
                  backgroundRepeat: 'no-repeat',
                  backgroundSize: '1.5em 1.5em',
                }}
              >
                {detectorVersions.length > 0
                  ? [...detectorVersions].reverse().map(v => (
                    <option key={v.name} value={v.name} className="bg-gray-800">{v.label || v.name}</option>
                  ))
                  : [
                    <option key="v1.1" value="v1.1" className="bg-gray-800">v1.1</option>,
                    <option key="v1.0" value="v1.0" className="bg-gray-800">v1.0</option>,
                  ]
                }
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {renderSlot('a', slotA, '音频 A', '#9CA3AF', 'from-red-900/30 to-primary/30')}
            {renderSlot('b', slotB, '音频 B', '#00D9FF', 'from-cyan-900/30 to-primary/30')}
          </div>

          {renderComparison()}

          <div className="mt-4 p-3 bg-black/20 rounded-lg">
            <p className="text-gray-500 text-xs text-center">
              基于音频特征的启发式分析，仅供参考，不作为可靠判断依据
            </p>
          </div>
        </div>

        {renderServerPicker()}

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
            title="离开检测页面"
            tasks={[
              ...(slotA.status === 'uploading' || slotA.status === 'detecting'
                ? [{ name: '音频 A 检测', step: slotA.step || '检测中', progress: slotA.progress }]
                : []),
              ...(slotB.status === 'uploading' || slotB.status === 'detecting'
                ? [{ name: '音频 B 检测', step: slotB.step || '检测中', progress: slotB.progress }]
                : []),
            ]}
          />
        )}
      </div>
    </ErrorBoundary>
  );
}

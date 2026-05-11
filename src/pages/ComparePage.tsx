import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';
import { SpectrumVisualizer } from '../components/SpectrumVisualizer';
import { WaveformVisualizer } from '../components/WaveformVisualizer';
import { ErrorBoundary } from '../components/ErrorBoundary';

type CompareMode = 'original' | 'repaired';

interface CacheTask {
  id: string;
  filename: string;
  status: string;
  output_exists: boolean;
  original_exists: boolean;
  created_at: string;
}

const API_BASE = '/api/v1';

const audioBufferCache = new Map<string, { buffer: AudioBuffer; timestamp: number }>();
const CACHE_TTL = 30 * 60 * 1000;

function getCachedBuffer(taskId: string, type: 'original' | 'repaired'): AudioBuffer | null {
  const key = `${taskId}:${type}`;
  const entry = audioBufferCache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.timestamp > CACHE_TTL) {
    audioBufferCache.delete(key);
    return null;
  }
  return entry.buffer;
}

function setCachedBuffer(taskId: string, type: 'original' | 'repaired', buffer: AudioBuffer) {
  audioBufferCache.set(`${taskId}:${type}`, { buffer, timestamp: Date.now() });
}

function formatTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export { audioBufferCache, getCachedBuffer, setCachedBuffer };

export default function ComparePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const taskId = searchParams.get('taskId') || '';

  const [taskInfoLoading, setTaskInfoLoading] = useState(false);
  const [taskInfo, setTaskInfo] = useState<Record<string, unknown> | null>(null);
  const [taskInfoError, setTaskInfoError] = useState<string | null>(null);
  const [tasks, setTasks] = useState<CacheTask[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);

  const [originalBuffer, setOriginalBuffer] = useState<AudioBuffer | null>(null);
  const [repairedBuffer, setRepairedBuffer] = useState<AudioBuffer | null>(null);
  const [originalLoading, setOriginalLoading] = useState(false);
  const [repairedLoading, setRepairedLoading] = useState(false);
  const [originalError, setOriginalError] = useState<string | null>(null);
  const [repairedError, setRepairedError] = useState<string | null>(null);
  const [compareMode, setCompareMode] = useState<CompareMode>('original');
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<AudioBufferSourceNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);
  const startTimeRef = useRef(0);
  const pauseOffsetRef = useRef(0);
  const animFrameRef = useRef<number>();

  const activeBuffer = compareMode === 'original' ? originalBuffer : repairedBuffer;
  const activeLoading = compareMode === 'original' ? originalLoading : repairedLoading;

  useEffect(() => {
    if (taskId) return;
    let cancelled = false;
    setTasksLoading(true);
    fetch(`${API_BASE}/cache/info`)
      .then(res => res.ok ? res.json() : Promise.reject(new Error('获取缓存信息失败')))
      .then(data => {
        if (!cancelled) {
          const completed = (data.tasks || []).filter((t: CacheTask) => t.output_exists);
          setTasks(completed);
        }
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setTasksLoading(false); });
    return () => { cancelled = true; };
  }, [taskId]);

  useEffect(() => {
    if (!taskId) {
      setTaskInfo(null);
      setOriginalBuffer(null);
      setRepairedBuffer(null);
      setTaskInfoError(null);
      setOriginalError(null);
      setRepairedError(null);
      return;
    }

    let cancelled = false;

    setTaskInfoLoading(true);
    setTaskInfoError(null);
    fetch(`${API_BASE}/status/${taskId}`)
      .then(res => {
        if (!res.ok) throw new Error(`任务不存在 (HTTP ${res.status})`);
        return res.json();
      })
      .then(data => {
        if (!cancelled) setTaskInfo(data);
      })
      .catch(e => {
        if (!cancelled) setTaskInfoError(e instanceof Error ? e.message : '获取任务信息失败');
      })
      .finally(() => {
        if (!cancelled) setTaskInfoLoading(false);
      });

    return () => { cancelled = true; };
  }, [taskId]);

  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContext();
    }
    return audioContextRef.current;
  }, []);

  useEffect(() => {
    if (!taskId) return;

    const cached = getCachedBuffer(taskId, 'original');
    if (cached) {
      setOriginalBuffer(cached);
      setOriginalLoading(false);
      return;
    }

    let cancelled = false;
    setOriginalLoading(true);
    setOriginalError(null);

    fetch(`${API_BASE}/preview/${taskId}?type=original`)
      .then(res => {
        if (!res.ok) throw new Error(`原始音频不可用 (HTTP ${res.status})`);
        return res.arrayBuffer();
      })
      .then(ab => {
        const ctx = getAudioContext();
        return ctx.decodeAudioData(ab);
      })
      .then(buffer => {
        if (!cancelled) {
          setCachedBuffer(taskId, 'original', buffer);
          setOriginalBuffer(buffer);
        }
      })
      .catch(e => {
        if (!cancelled) setOriginalError(e instanceof Error ? e.message : '原始音频加载失败');
      })
      .finally(() => {
        if (!cancelled) setOriginalLoading(false);
      });

    return () => { cancelled = true; };
  }, [taskId, getAudioContext]);

  useEffect(() => {
    if (!taskId) return;

    const cached = getCachedBuffer(taskId, 'repaired');
    if (cached) {
      setRepairedBuffer(cached);
      setRepairedLoading(false);
      return;
    }

    let cancelled = false;
    setRepairedLoading(true);
    setRepairedError(null);

    fetch(`${API_BASE}/preview/${taskId}?type=repaired`)
      .then(res => {
        if (!res.ok) throw new Error(`修复后音频不可用 (HTTP ${res.status})`);
        return res.arrayBuffer();
      })
      .then(ab => {
        const ctx = getAudioContext();
        return ctx.decodeAudioData(ab);
      })
      .then(buffer => {
        if (!cancelled) {
          setCachedBuffer(taskId, 'repaired', buffer);
          setRepairedBuffer(buffer);
        }
      })
      .catch(e => {
        if (!cancelled) setRepairedError(e instanceof Error ? e.message : '修复后音频加载失败');
      })
      .finally(() => {
        if (!cancelled) setRepairedLoading(false);
      });

    return () => { cancelled = true; };
  }, [taskId, getAudioContext]);

  useEffect(() => {
    if (!audioContextRef.current) return;
    if (analyserRef.current) return;
    const analyser = audioContextRef.current.createAnalyser();
    analyser.fftSize = 256;
    analyserRef.current = analyser;

    const gain = audioContextRef.current.createGain();
    gain.gain.value = 1;
    gainNodeRef.current = gain;

    analyser.connect(gain);
    gain.connect(audioContextRef.current.destination);

    return () => {
      analyser.disconnect();
      gain.disconnect();
      analyserRef.current = null;
      gainNodeRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (activeBuffer) setDuration(activeBuffer.duration);
  }, [activeBuffer]);

  const stopPlayback = useCallback(() => {
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    if (sourceNodeRef.current) {
      try { sourceNodeRef.current.stop(); } catch { /* already stopped */ }
      sourceNodeRef.current = null;
    }
    setIsPlaying(false);
  }, []);

  const play = useCallback(() => {
    if (!activeBuffer || !audioContextRef.current) return;

    stopPlayback();

    const ctx = audioContextRef.current;
    if (ctx.state === 'suspended') ctx.resume();

    if (!analyserRef.current) {
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;
      const gain = ctx.createGain();
      gain.gain.value = 1;
      gainNodeRef.current = gain;
      analyser.connect(gain);
      gain.connect(ctx.destination);
    }

    const source = ctx.createBufferSource();
    source.buffer = activeBuffer;
    source.connect(analyserRef.current);

    const offset = pauseOffsetRef.current;
    source.start(0, offset);
    startTimeRef.current = ctx.currentTime - offset;
    sourceNodeRef.current = source;
    setIsPlaying(true);

    const updateProgress = () => {
      if (!sourceNodeRef.current) return;
      const elapsed = ctx.currentTime - startTimeRef.current;
      setCurrentTime(elapsed);
      if (elapsed < activeBuffer.duration) {
        animFrameRef.current = requestAnimationFrame(updateProgress);
      } else {
        setCurrentTime(activeBuffer.duration);
        pauseOffsetRef.current = 0;
        setIsPlaying(false);
        sourceNodeRef.current = null;
      }
    };
    animFrameRef.current = requestAnimationFrame(updateProgress);
  }, [activeBuffer, stopPlayback]);

  const pause = useCallback(() => {
    if (!audioContextRef.current) return;
    pauseOffsetRef.current = audioContextRef.current.currentTime - startTimeRef.current;
    stopPlayback();
  }, [stopPlayback]);

  const seek = useCallback((time: number) => {
    if (!activeBuffer) return;
    const t = Math.max(0, Math.min(time, activeBuffer.duration));
    pauseOffsetRef.current = t;
    setCurrentTime(t);
    if (isPlaying) {
      stopPlayback();
      setTimeout(play, 0);
    }
  }, [activeBuffer, isPlaying, stopPlayback, play]);

  const switchMode = useCallback((mode: CompareMode) => {
    if (mode === compareMode) return;
    const wasPlaying = isPlaying;
    pause();
    setCompareMode(mode);
    pauseOffsetRef.current = 0;
    setCurrentTime(0);
    if (wasPlaying) {
      setTimeout(play, 100);
    }
  }, [compareMode, isPlaying, pause, play]);

  const selectTask = useCallback((id: string) => {
    setSearchParams({ taskId: id });
  }, [setSearchParams]);

  useEffect(() => {
    return () => {
      stopPlayback();
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close();
      }
    };
  }, [stopPlayback]);

  const modeLabel: Record<CompareMode, string> = { original: '原始音频', repaired: '修复后' };
  const modeColor: Record<CompareMode, string> = { original: '#6B7280', repaired: '#00D9FF' };

  const renderTaskList = () => (
    <div className="space-y-3">
      {tasksLoading ? (
        <div className="flex items-center justify-center py-12 gap-3">
          <div className="w-6 h-6 rounded-full animate-spin border-2 border-cyan-500/30 border-t-cyan-500" />
          <span className="text-gray-400 text-sm">加载任务列表...</span>
        </div>
      ) : tasks.length === 0 ? (
        <div className="text-center py-12">
          <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
            </svg>
          </div>
          <p className="text-gray-400 text-sm mb-2">暂无可对比的修复任务</p>
          <p className="text-gray-600 text-xs">请先在修复页完成音频修复</p>
          <button
            onClick={() => navigate('/repair')}
            className="mt-4 px-4 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/30 rounded-lg text-cyan-400 text-sm transition-colors"
          >
            前往修复
          </button>
        </div>
      ) : (
        tasks.map(task => (
          <button
            key={task.id}
            onClick={() => selectTask(task.id)}
            className="w-full flex items-center gap-4 p-4 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-cyan-400/30 rounded-xl transition-all text-left"
          >
            <div className="w-10 h-10 bg-gradient-to-br from-cyan-500/20 to-purple-500/20 rounded-lg flex items-center justify-center border border-cyan-400/20 shrink-0">
              <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
              </svg>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-white text-sm font-medium truncate">{task.filename}</p>
              <p className="text-gray-500 text-xs mt-0.5">
                {task.created_at ? new Date(task.created_at).toLocaleString('zh-CN') : ''}
                {' • '}
                <span className="text-green-400">已修复</span>
              </p>
            </div>
            <svg className="w-4 h-4 text-gray-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        ))
      )}
    </div>
  );

  const renderPlayer = () => {
    if (taskInfoLoading && !taskInfo) {
      return (
        <div className="flex flex-col items-center gap-4 py-12">
          <div className="w-10 h-10 rounded-full animate-spin border-2 border-cyan-500/30 border-t-cyan-500" />
          <p className="text-gray-400 text-sm">加载任务信息...</p>
        </div>
      );
    }

    if (taskInfoError && !taskInfo) {
      return (
        <div className="flex flex-col items-center gap-4 py-12">
          <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center">
            <svg className="w-8 h-8 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <p className="text-red-400 text-sm font-medium">{taskInfoError}</p>
          <button
            onClick={() => setSearchParams({})}
            className="mt-2 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-gray-400 hover:text-white text-sm transition-colors"
          >
            选择其他任务
          </button>
        </div>
      );
    }

    return (
      <>
        <div className="flex items-center justify-between mb-6 gap-3">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <div className="w-12 h-12 bg-gradient-to-br from-cyan-500/20 to-purple-500/20 rounded-lg flex items-center justify-center border border-cyan-400/20 shrink-0">
              <svg className="w-6 h-6 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
              </svg>
            </div>
            <div className="min-w-0">
              <h3 className="text-white font-semibold text-lg truncate">
                {(taskInfo?.original_filename as string) || 'audio'}
              </h3>
              <p className="text-gray-400 text-sm">
                {originalBuffer ? `${(originalBuffer.sampleRate / 1000).toFixed(0)} kHz • ${originalBuffer.numberOfChannels === 1 ? '单声道' : '立体声'}` : '—'}
                {' • '}
                <span className="text-green-400">AB 对比模式</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {(['original', 'repaired'] as CompareMode[]).map((mode) => {
              const buf = mode === 'original' ? originalBuffer : repairedBuffer;
              const isLoading = mode === 'original' ? originalLoading : repairedLoading;
              const loadError = mode === 'original' ? originalError : repairedError;
              const available = !!buf;
              const active = compareMode === mode;
              return (
                <button
                  key={mode}
                  onClick={() => available && switchMode(mode)}
                  disabled={!available}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
                    active
                      ? 'bg-secondary/30 text-secondary border border-secondary/50 shadow-md shadow-secondary/10'
                      : !available
                        ? 'bg-gray-800/30 text-gray-500 cursor-not-allowed border border-gray-700/30 opacity-50'
                        : 'bg-gray-800/50 text-gray-400 hover:bg-gray-700/50 hover:text-gray-200 border border-transparent hover:border-gray-600/50'
                  }`}
                  style={active ? { borderColor: modeColor[mode], color: modeColor[mode], backgroundColor: modeColor[mode] + '15' } : undefined}
                >
                  {isLoading ? (
                    <span className="w-2 h-2 rounded-full border border-gray-400 border-t-transparent animate-spin" />
                  ) : loadError ? (
                    <span className="w-2 h-2 rounded-full bg-red-500/50" />
                  ) : (
                    <span className={`w-2 h-2 rounded-full ${available ? (active ? '' : 'bg-gray-500') : 'bg-gray-600'}`}
                      style={available && active ? { backgroundColor: modeColor[mode] } : undefined}
                    />
                  )}
                  {modeLabel[mode]}
                  {isLoading && <span className="text-[10px] opacity-60 ml-0.5">加载中</span>}
                  {loadError && !isLoading && (
                    <svg className="w-3 h-3 ml-0.5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01" />
                    </svg>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        <div className="bg-gradient-to-br from-primary/90 to-dark/90 rounded-2xl p-4 border border-secondary/30 shadow-xl shadow-black/20">
          <div className="flex items-center justify-center gap-4">
            <button
              onClick={isPlaying ? pause : play}
              disabled={!activeBuffer || activeLoading}
              className="w-14 h-14 rounded-full flex items-center justify-center transition-all duration-200 bg-gradient-to-r from-secondary to-accent hover:scale-110 hover:shadow-lg hover:shadow-secondary/40 active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:scale-100"
            >
              {isPlaying ? (
                <svg className="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
                </svg>
              ) : (
                <svg className="w-6 h-6 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z" />
                </svg>
              )}
            </button>

            <div className="flex-1 min-w-[120px] max-w-xs">
              <div className="text-xs text-gray-400 mb-1 text-center">
                {activeLoading ? '加载中...' : `${formatTime(currentTime)} / ${formatTime(duration)}`}
              </div>
              <input
                type="range"
                min={0}
                max={duration || 0}
                step={0.01}
                value={currentTime}
                onChange={(e) => seek(parseFloat(e.target.value))}
                disabled={!activeBuffer || activeLoading}
                className="w-full h-1.5 bg-gray-700 rounded-full appearance-none cursor-pointer disabled:opacity-30 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:shadow-md [&::-webkit-slider-runnable-track]:rounded-full"
                style={{
                  background: activeBuffer
                    ? `linear-gradient(to right, ${modeColor[compareMode]} ${(currentTime / (duration || 1)) * 100}%, #374151 ${(currentTime / (duration || 1)) * 100}%)`
                    : undefined,
                }}
              />
            </div>
          </div>
        </div>

        {analyserRef.current && activeBuffer && (
          <div className="mt-6">
            <SpectrumVisualizer
              analyser={analyserRef.current}
              color={modeColor[compareMode]}
              label={`${modeLabel[compareMode]} 频谱`}
            />
          </div>
        )}

        <div className="mt-6">
          <WaveformVisualizer
            key={`waveform-${compareMode}-${!!activeBuffer}`}
            audioBuffer={activeBuffer}
            color={modeColor[compareMode]}
            label={activeLoading ? `${modeLabel[compareMode]} 加载中...` : `${modeLabel[compareMode]} 波形`}
            currentTime={currentTime}
            duration={duration}
            onSeek={seek}
          />
        </div>

        <div className="mt-4 flex items-center justify-between text-xs text-gray-500">
          <span>Task ID: {taskId}</span>
          <span>
            {originalLoading && <span className="text-yellow-500/70 mr-3">原始音频加载中</span>}
            {repairedLoading && <span className="text-yellow-500/70 mr-3">修复后音频加载中</span>}
            {originalError && <span className="text-red-400/70 mr-3">原始: {originalError}</span>}
            {repairedError && <span className="text-red-400/70 mr-3">修复: {repairedError}</span>}
            {originalBuffer && repairedBuffer && <span className="text-green-400">双轨已就绪</span>}
            {originalBuffer && !repairedBuffer && !repairedLoading && !repairedError && <span className="text-yellow-500/70">修复后音频未就绪</span>}
          </span>
        </div>
      </>
    );
  };

  return (
    <ErrorBoundary>
      <div className="min-h-screen bg-dark py-6">
        <Header />

        <div className="container mx-auto px-4 max-w-5xl mt-4">
          <div className="flex items-center gap-3 mb-6">
            <button
              onClick={() => navigate('/')}
              className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              <span>返回首页</span>
            </button>
            {taskId && (
              <button
                onClick={() => setSearchParams({})}
                className="flex items-center gap-2 text-gray-500 hover:text-gray-300 transition-colors text-sm"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                </svg>
                <span>选择任务</span>
              </button>
            )}
          </div>

          <div className="bg-primary/50 border border-white/10 rounded-xl p-6">
            {!taskId ? renderTaskList() : renderPlayer()}
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
}

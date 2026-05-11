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

function formatTimePrecise(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return '0:00.0';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 10);
  return `${mins}:${secs.toString().padStart(2, '0')}.${ms}`;
}

export { audioBufferCache, getCachedBuffer, setCachedBuffer };

function getPreviewUrl(taskId: string, type: 'original' | 'repaired'): string {
  return `${API_BASE}/preview/${taskId}?type=${type}`;
}

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
  const [audioReady, setAudioReady] = useState(false);

  const [pointA, setPointA] = useState<number | null>(null);
  const [pointB, setPointB] = useState<number | null>(null);

  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<MediaElementAudioSourceNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);
  const animFrameRef = useRef<number>();
  const abLoopRef = useRef(false);

  const activeBuffer = compareMode === 'original' ? originalBuffer : repairedBuffer;

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

    if (!audioElRef.current) {
      audioElRef.current = new Audio();
      audioElRef.current.preload = 'auto';
      audioElRef.current.crossOrigin = 'anonymous';
    }

    const audio = audioElRef.current;
    const url = getPreviewUrl(taskId, compareMode);
    audio.src = url;
    audio.load();
    setAudioReady(false);
    setDuration(0);
    setCurrentTime(0);

    const onCanPlay = () => {
      setAudioReady(true);
      setDuration(audio.duration || 0);
    };
    const onDurationChange = () => {
      if (audio.duration && isFinite(audio.duration)) {
        setDuration(audio.duration);
      }
    };
    const onEnded = () => {
      if (abLoopRef.current && pointA !== null && pointB !== null) {
        audio.currentTime = pointA;
        audio.play().catch(() => {});
        return;
      }
      setIsPlaying(false);
      setCurrentTime(audio.duration || 0);
    };
    const onError = () => {
      setAudioReady(false);
      if (compareMode === 'original') {
        setOriginalError('原始音频不可用');
      } else {
        setRepairedError('修复后音频不可用');
      }
    };

    audio.addEventListener('canplay', onCanPlay);
    audio.addEventListener('durationchange', onDurationChange);
    audio.addEventListener('ended', onEnded);
    audio.addEventListener('error', onError);

    return () => {
      audio.removeEventListener('canplay', onCanPlay);
      audio.removeEventListener('durationchange', onDurationChange);
      audio.removeEventListener('ended', onEnded);
      audio.removeEventListener('error', onError);
    };
  }, [taskId, compareMode, pointA, pointB]);

  useEffect(() => {
    if (!audioElRef.current) return;
    const audio = audioElRef.current;
    const updateProgress = () => {
      if (!audio.paused) {
        const t = audio.currentTime;
        setCurrentTime(t);
        if (abLoopRef.current && pointB !== null && t >= pointB) {
          const a = pointA ?? 0;
          audio.currentTime = a;
        }
        animFrameRef.current = requestAnimationFrame(updateProgress);
      }
    };
    const onPlay = () => {
      animFrameRef.current = requestAnimationFrame(updateProgress);
    };
    const onPause = () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);
    return () => {
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [pointA, pointB]);

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

    fetch(getPreviewUrl(taskId, 'original'))
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

    fetch(getPreviewUrl(taskId, 'repaired'))
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
    if (!audioElRef.current || !audioContextRef.current) return;
    if (sourceNodeRef.current) return;

    const ctx = audioContextRef.current;
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyserRef.current = analyser;

    const gain = ctx.createGain();
    gain.gain.value = 1;
    gainNodeRef.current = gain;

    try {
      const source = ctx.createMediaElementSource(audioElRef.current);
      sourceNodeRef.current = source;
      source.connect(analyser);
      analyser.connect(gain);
      gain.connect(ctx.destination);
    } catch {
      // already connected
    }

    return () => {
      try {
        sourceNodeRef.current?.disconnect();
        analyser.disconnect();
        gain.disconnect();
      } catch { /* ignore */ }
      sourceNodeRef.current = null;
      analyserRef.current = null;
      gainNodeRef.current = null;
    };
  }, []);

  const play = useCallback(() => {
    const audio = audioElRef.current;
    if (!audio || !audioReady) return;

    const ctx = getAudioContext();
    if (ctx.state === 'suspended') ctx.resume();

    if (!sourceNodeRef.current) {
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;
      const gain = ctx.createGain();
      gain.gain.value = 1;
      gainNodeRef.current = gain;
      try {
        const source = ctx.createMediaElementSource(audio);
        sourceNodeRef.current = source;
        source.connect(analyser);
        analyser.connect(gain);
        gain.connect(ctx.destination);
      } catch {
        // already connected
      }
    }

    audio.play().then(() => {
      setIsPlaying(true);
    }).catch(() => {});
  }, [audioReady, getAudioContext]);

  const pause = useCallback(() => {
    const audio = audioElRef.current;
    if (!audio) return;
    audio.pause();
    setIsPlaying(false);
  }, []);

  const seek = useCallback((time: number) => {
    const audio = audioElRef.current;
    if (!audio || !isFinite(time)) return;
    const t = Math.max(0, Math.min(time, audio.duration || 0));
    audio.currentTime = t;
    setCurrentTime(t);
  }, []);

  const switchMode = useCallback((mode: CompareMode) => {
    if (mode === compareMode) return;
    const wasPlaying = isPlaying;
    const audio = audioElRef.current;
    if (audio) {
      audio.pause();
    }
    setIsPlaying(false);
    setCompareMode(mode);

    const startPos = pointA ?? 0;
    setCurrentTime(startPos);

    setTimeout(() => {
      const a = audioElRef.current;
      if (a && a.readyState >= 3) {
        a.currentTime = startPos;
        if (wasPlaying) {
          a.play().then(() => setIsPlaying(true)).catch(() => {});
        }
      }
    }, 300);
  }, [compareMode, isPlaying, pointA]);

  const setMarkA = useCallback(() => {
    setPointA(currentTime);
    if (pointB !== null && currentTime >= pointB) {
      setPointB(null);
      abLoopRef.current = false;
    }
  }, [currentTime, pointB]);

  const setMarkB = useCallback(() => {
    if (pointA === null) return;
    setPointB(currentTime);
    abLoopRef.current = true;
  }, [currentTime, pointA]);

  const clearAB = useCallback(() => {
    setPointA(null);
    setPointB(null);
    abLoopRef.current = false;
  }, []);

  const selectTask = useCallback((id: string) => {
    setSearchParams({ taskId: id });
  }, [setSearchParams]);

  useEffect(() => {
    return () => {
      const audio = audioElRef.current;
      if (audio) {
        audio.pause();
        audio.src = '';
      }
      if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
        audioContextRef.current.close();
      }
    };
  }, []);

  const modeLabel: Record<CompareMode, string> = { original: '原始音频', repaired: '修复后' };
  const modeColor: Record<CompareMode, string> = { original: '#6B7280', repaired: '#00D9FF' };
  const modeIcon: Record<CompareMode, string> = {
    original: 'M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3',
    repaired: 'M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z',
  };

  const getBufferInfo = (mode: CompareMode) => {
    const buf = mode === 'original' ? originalBuffer : repairedBuffer;
    if (!buf) return null;
    const sr = buf.sampleRate;
    const ch = buf.numberOfChannels;
    const dur = buf.duration;
    const bitDepth = mode === 'repaired' ? 24 : (taskInfo?.original_bit_depth as number || 16);
    const sizeMB = (dur * sr * ch * (bitDepth / 8)) / (1024 * 1024);
    return { sampleRate: sr, channels: ch, duration: dur, bitDepth, sizeMB };
  };

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
                {' \u2022 '}
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
        <div className="mb-4">
          <h3 className="text-white font-semibold text-lg truncate mb-1">
            {(taskInfo?.original_filename as string) || 'audio'}
          </h3>
          <p className="text-gray-500 text-xs">点击卡片切换音频源</p>
        </div>

        <div className="grid grid-cols-2 gap-3 mb-6">
          {(['original', 'repaired'] as CompareMode[]).map((mode) => {
            const buf = mode === 'original' ? originalBuffer : repairedBuffer;
            const isLoading = mode === 'original' ? originalLoading : repairedLoading;
            const loadError = mode === 'original' ? originalError : repairedError;
            const info = getBufferInfo(mode);
            const active = compareMode === mode;
            const color = modeColor[mode];

            return (
              <button
                key={mode}
                onClick={() => switchMode(mode)}
                className={`relative text-left p-4 rounded-xl border transition-all duration-200 ${
                  active
                    ? 'bg-white/8 shadow-lg'
                    : 'bg-white/3 hover:bg-white/6'
                }`}
                style={active ? {
                  borderColor: color + '60',
                  boxShadow: `0 0 20px ${color}15, inset 0 1px 0 ${color}20`,
                } : {
                  borderColor: 'rgba(255,255,255,0.06)',
                }}
              >
                {active && (
                  <div
                    className="absolute top-2 right-2 w-2 h-2 rounded-full"
                    style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}` }}
                  />
                )}

                <div className="flex items-center gap-2 mb-2">
                  <svg className="w-4 h-4" style={{ color }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={modeIcon[mode]} />
                  </svg>
                  <span className="text-sm font-medium" style={{ color }}>
                    {modeLabel[mode]}
                  </span>
                  {isLoading && (
                    <span className="w-3 h-3 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: color + '40', borderTopColor: 'transparent' }} />
                  )}
                  {loadError && !isLoading && (
                    <span className="text-red-400 text-xs">不可用</span>
                  )}
                </div>

                {info ? (
                  <div className="space-y-0.5 text-xs">
                    <div className="flex justify-between">
                      <span className="text-gray-500">规格</span>
                      <span className="text-gray-300">{(info.sampleRate / 1000).toFixed(0)} kHz / {info.bitDepth} bit</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">声道</span>
                      <span className="text-gray-300">{info.channels === 1 ? '单声道' : '立体声'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">时长</span>
                      <span className="text-gray-300">{formatTime(info.duration)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">大小</span>
                      <span className="text-gray-300">{info.sizeMB.toFixed(1)} MB</span>
                    </div>
                  </div>
                ) : isLoading ? (
                  <div className="text-xs text-gray-500">加载中...</div>
                ) : loadError ? (
                  <div className="text-xs text-red-400/60">加载失败</div>
                ) : (
                  <div className="text-xs text-gray-600">等待加载</div>
                )}
              </button>
            );
          })}
        </div>

        <div className="bg-gradient-to-br from-primary/90 to-dark/90 rounded-2xl p-4 border border-secondary/30 shadow-xl shadow-black/20">
          <div className="flex items-center justify-center gap-3">
            <button
              onClick={isPlaying ? pause : play}
              disabled={!audioReady}
              className="w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200 bg-gradient-to-r from-secondary to-accent hover:scale-110 hover:shadow-lg hover:shadow-secondary/40 active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:scale-100 shrink-0"
            >
              {isPlaying ? (
                <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
                </svg>
              ) : (
                <svg className="w-5 h-5 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z" />
                </svg>
              )}
            </button>

            <div className="flex-1 min-w-0">
              <div className="text-xs text-gray-400 mb-1 text-center">
                {!audioReady ? '缓冲中...' : `${formatTime(currentTime)} / ${formatTime(duration)}`}
              </div>
              <div className="relative">
                <input
                  type="range"
                  min={0}
                  max={duration || 0}
                  step={0.01}
                  value={currentTime}
                  onChange={(e) => seek(parseFloat(e.target.value))}
                  disabled={!audioReady}
                  className="w-full h-1.5 bg-gray-700 rounded-full appearance-none cursor-pointer disabled:opacity-30 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:shadow-md [&::-webkit-slider-runnable-track]:rounded-full"
                  style={{
                    background: audioReady
                      ? `linear-gradient(to right, ${modeColor[compareMode]} ${(currentTime / (duration || 1)) * 100}%, #374151 ${(currentTime / (duration || 1)) * 100}%)`
                      : undefined,
                  }}
                />
                {pointA !== null && (
                  <div
                    className="absolute top-0 w-0.5 h-1.5 bg-green-400 rounded-full pointer-events-none"
                    style={{ left: `${(pointA / (duration || 1)) * 100}%` }}
                  />
                )}
                {pointB !== null && (
                  <div
                    className="absolute top-0 w-0.5 h-1.5 bg-red-400 rounded-full pointer-events-none"
                    style={{ left: `${(pointB / (duration || 1)) * 100}%` }}
                  />
                )}
                {pointA !== null && pointB !== null && (
                  <div
                    className="absolute top-0 h-1.5 bg-yellow-400/10 pointer-events-none"
                    style={{
                      left: `${(pointA / (duration || 1)) * 100}%`,
                      width: `${((pointB - pointA) / (duration || 1)) * 100}%`,
                    }}
                  />
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center justify-center gap-2 mt-3">
            <button
              onClick={setMarkA}
              disabled={!audioReady}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                pointA !== null
                  ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                  : 'bg-white/5 text-gray-400 border border-white/10 hover:bg-white/10'
              } disabled:opacity-30 disabled:cursor-not-allowed`}
            >
              A{pointA !== null ? ` ${formatTimePrecise(pointA)}` : ''}
            </button>
            <button
              onClick={setMarkB}
              disabled={!audioReady || pointA === null}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                pointB !== null
                  ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                  : 'bg-white/5 text-gray-400 border border-white/10 hover:bg-white/10'
              } disabled:opacity-30 disabled:cursor-not-allowed`}
            >
              B{pointB !== null ? ` ${formatTimePrecise(pointB)}` : ''}
            </button>
            {abLoopRef.current && (
              <span className="text-yellow-400 text-xs">循环</span>
            )}
            {(pointA !== null || pointB !== null) && (
              <button
                onClick={clearAB}
                className="px-2 py-1 rounded text-xs bg-white/5 text-gray-500 border border-white/10 hover:bg-white/10 hover:text-gray-300 transition-colors"
              >
                清除
              </button>
            )}
          </div>
        </div>

        {analyserRef.current && audioReady && (
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
            label={compareMode === 'original' && originalLoading ? '原始音频 波形加载中...' : compareMode === 'repaired' && repairedLoading ? '修复后 波形加载中...' : activeBuffer ? `${modeLabel[compareMode]} 波形` : `${modeLabel[compareMode]} 等待波形...`}
            currentTime={currentTime}
            duration={duration}
            onSeek={seek}
          />
        </div>

        <div className="mt-3 flex items-center justify-between text-xs text-gray-600">
          <span>{taskId}</span>
          <span>
            {!audioReady && <span className="text-yellow-500/50 mr-2">缓冲中</span>}
            {originalLoading && <span className="text-yellow-500/50 mr-2">原始波形</span>}
            {repairedLoading && <span className="text-yellow-500/50 mr-2">修复后波形</span>}
            {audioReady && originalBuffer && repairedBuffer && <span className="text-green-400/50">就绪</span>}
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

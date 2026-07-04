import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';
import { SpectrumVisualizer } from '../components/SpectrumVisualizer';
import { WaveformVisualizer } from '../components/WaveformVisualizer';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { connectCacheWS } from '../services/backendApi';

type CompareMode = 'original' | 'repaired';
type DualTrackMode = 'vocal' | 'accompaniment' | 'merged';

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

export function formatTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export function formatTimePrecise(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return '0:00.0';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  // 加 1e-9 容差抵消浮点误差（如 5.3 % 1 = 0.2999... 会被 floor 成 2）
  const ms = Math.floor((seconds % 1) * 10 + 1e-9) % 10;
  return `${mins}:${secs.toString().padStart(2, '0')}.${ms}`;
}

export function parseTimeInput(val: string): number | null {
  const trimmed = val.trim();
  if (!trimmed) return null;
  const m = trimmed.match(/^(\d+):([0-5]?\d)(?:\.(\d))?$/);
  if (m) {
    const mins = parseInt(m[1], 10);
    const secs = parseInt(m[2], 10);
    const frac = m[3] ? parseInt(m[3], 10) / 10 : 0;
    return mins * 60 + secs + frac;
  }
  const num = parseFloat(trimmed);
  if (isFinite(num) && num >= 0) return num;
  return null;
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
  const [dualTrackMode, setDualTrackMode] = useState<DualTrackMode | null>(null);

  const [pointA, setPointA] = useState<number | null>(null);
  const [pointB, setPointB] = useState<number | null>(null);
  const [editingA, setEditingA] = useState(false);
  const [editingB, setEditingB] = useState(false);
  const [editAVal, setEditAVal] = useState('');
  const [editBVal, setEditBVal] = useState('');

  // 播放增强：变速 / 音量 / AB 循环计数
  const [playbackRate, setPlaybackRate] = useState(1);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [loopCount, setLoopCount] = useState(0);
  // 循环次数上限：0 表示无限循环
  const [loopLimit, setLoopLimit] = useState(0);
  const [showShortcuts, setShowShortcuts] = useState(false);

  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<MediaElementAudioSourceNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number>();
  const abLoopRef = useRef(false);
  const pendingSeekRef = useRef<number | null>(null);
  const pendingPlayRef = useRef(false);
  const loopCountRef = useRef(0);
  const loopLimitRef = useRef(0);
  const playbackRateRef = useRef(1);
  const volumeRef = useRef(1);
  const mutedRef = useRef(false);

  const activeBuffer = compareMode === 'original' ? originalBuffer : repairedBuffer;

  const fetchTaskList = useCallback(async () => {
    setTasksLoading(true);
    try {
      const res = await fetch(`${API_BASE}/cache/info`);
      if (res.ok) {
        const data = await res.json();
        setTasks(data.tasks || []);
      }
    } catch {
      // ignore
    } finally {
      setTasksLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTaskList();
  }, [fetchTaskList]);

  const wsControlRef = useRef<{ close: () => void } | null>(null);
  const taskIdRef = useRef(taskId);
  taskIdRef.current = taskId;
  // 同步用户可设置的播放参数到 ref，供事件回调读取最新值
  loopLimitRef.current = loopLimit;
  playbackRateRef.current = playbackRate;
  volumeRef.current = volume;
  mutedRef.current = muted;

  // AB 循环重复一次：累加计数，达到上限则停止循环
  const advanceLoop = useCallback(() => {
    loopCountRef.current += 1;
    setLoopCount(loopCountRef.current);
    const limit = loopLimitRef.current;
    if (limit > 0 && loopCountRef.current >= limit) {
      abLoopRef.current = false;
      return false;
    }
    return true;
  }, []);

  // 重置循环计数（A/B 区段变更或清除时调用）
  const resetLoopCount = useCallback(() => {
    loopCountRef.current = 0;
    setLoopCount(0);
  }, []);
  useEffect(() => {
    if (wsControlRef.current) return;
    wsControlRef.current = connectCacheWS(() => {
      if (!taskIdRef.current) {
        fetchTaskList();
      }
    });
  }, []);

  const dualTrackSubIds = useMemo<{ vocalTaskId: string | null; accompanimentTaskId: string | null }>(() => {
    if (!taskInfo) return { vocalTaskId: null, accompanimentTaskId: null };
    const rawParams = taskInfo.params;
    let parsedParams: Record<string, unknown> = {};
    if (typeof rawParams === 'string') {
      try { parsedParams = JSON.parse(rawParams); } catch { parsedParams = {}; }
    } else if (rawParams && typeof rawParams === 'object') {
      parsedParams = rawParams as Record<string, unknown>;
    }
    return {
      vocalTaskId: (parsedParams.vocal_task_id ?? taskInfo.vocal_task_id ?? null) as string | null,
      accompanimentTaskId: (parsedParams.accompaniment_task_id ?? taskInfo.accompaniment_task_id ?? null) as string | null,
    };
  }, [taskInfo]);

  const isDualTrackTask = useMemo(() => {
    if (searchParams.get('mode') === 'dual') return true;
    if (!taskInfo) return false;
    const rawParams = taskInfo.params;
    let parsedParams: Record<string, unknown> = {};
    if (typeof rawParams === 'string') {
      try { parsedParams = JSON.parse(rawParams); } catch { parsedParams = {}; }
    } else if (rawParams && typeof rawParams === 'object') {
      parsedParams = rawParams as Record<string, unknown>;
    }
    if (parsedParams.processing_mode === 'dual') return true;
    return !!(dualTrackSubIds.vocalTaskId && dualTrackSubIds.accompanimentTaskId);
  }, [taskInfo, dualTrackSubIds, searchParams]);

  useEffect(() => {
    if (isDualTrackTask && !dualTrackMode) {
      setDualTrackMode('merged');
    } else if (!isDualTrackTask && dualTrackMode) {
      setDualTrackMode(null);
    }
  }, [isDualTrackTask]);

  const effectiveTaskId = useMemo(() => {
    if (!dualTrackMode) return taskId;
    switch (dualTrackMode) {
      case 'vocal': return dualTrackSubIds.vocalTaskId || taskId;
      case 'accompaniment': return dualTrackSubIds.accompanimentTaskId || taskId;
      case 'merged': return taskId;
    }
  }, [dualTrackMode, dualTrackSubIds, taskId]);

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

    return () => { cancelled = true };
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
    const url = getPreviewUrl(effectiveTaskId, compareMode);
    audio.src = url;
    audio.load();
    setAudioReady(false);

    const onCanPlay = () => {
      setAudioReady(true);
      setDuration(audio.duration || 0);

      if (pendingSeekRef.current !== null) {
        const seekTo = pendingSeekRef.current;
        pendingSeekRef.current = null;
        audio.currentTime = seekTo;
        setCurrentTime(seekTo);
      }
      if (pendingPlayRef.current) {
        pendingPlayRef.current = false;
        audio.play().catch(() => {});
      }
    };
    const onDurationChange = () => {
      if (audio.duration && isFinite(audio.duration)) {
        setDuration(audio.duration);
      }
    };
    const onEnded = () => {
      if (abLoopRef.current && pointA !== null && pointB !== null) {
        if (advanceLoop()) {
          audio.currentTime = pointA;
          audio.play().catch(() => {});
          return;
        }
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
  }, [taskId, effectiveTaskId, compareMode, pointA, pointB, advanceLoop]);

  useEffect(() => {
    if (!audioElRef.current) return;
    const audio = audioElRef.current;
    const updateProgress = () => {
      if (!audio.paused) {
        const t = audio.currentTime;
        setCurrentTime(t);
        if (abLoopRef.current && pointB !== null && t >= pointB) {
          if (advanceLoop()) {
            audio.currentTime = pointA ?? 0;
          } else {
            audio.pause();
          }
        }
        animFrameRef.current = requestAnimationFrame(updateProgress);
      }
    };
    const onPlay = () => {
      setIsPlaying(true);
      animFrameRef.current = requestAnimationFrame(updateProgress);
    };
    const onPause = () => {
      setIsPlaying(false);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
    audio.addEventListener('play', onPlay);
    audio.addEventListener('pause', onPause);
    return () => {
      audio.removeEventListener('play', onPlay);
      audio.removeEventListener('pause', onPause);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [pointA, pointB, advanceLoop]);

  useEffect(() => {
    const handleVisibility = () => {
      if (document.hidden) return;
      const ctx = audioContextRef.current;
      if (ctx && ctx.state === 'suspended') {
        ctx.resume().catch(() => {});
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, []);

  useEffect(() => {
    if (!taskId) return;

    const cached = getCachedBuffer(effectiveTaskId, 'original');
    if (cached) {
      setOriginalBuffer(cached);
      setOriginalLoading(false);
      return;
    }

    let cancelled = false;
    setOriginalLoading(true);
    setOriginalError(null);

    fetch(getPreviewUrl(effectiveTaskId, 'original'))
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
          setCachedBuffer(effectiveTaskId, 'original', buffer);
          setOriginalBuffer(buffer);
        }
      })
      .catch(e => {
        if (!cancelled) setOriginalError(e instanceof Error ? e.message : '原始音频加载失败');
      })
      .finally(() => {
        if (!cancelled) setOriginalLoading(false);
      });

    return () => { cancelled = true };
  }, [taskId, effectiveTaskId, getAudioContext]);

  useEffect(() => {
    if (!taskId) return;

    const cached = getCachedBuffer(effectiveTaskId, 'repaired');
    if (cached) {
      setRepairedBuffer(cached);
      setRepairedLoading(false);
      return;
    }

    let cancelled = false;
    setRepairedLoading(true);
    setRepairedError(null);

    fetch(getPreviewUrl(effectiveTaskId, 'repaired'))
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
          setCachedBuffer(effectiveTaskId, 'repaired', buffer);
          setRepairedBuffer(buffer);
        }
      })
      .catch(e => {
        if (!cancelled) setRepairedError(e instanceof Error ? e.message : '修复后音频加载失败');
      })
      .finally(() => {
        if (!cancelled) setRepairedLoading(false);
      });

    return () => { cancelled = true };
  }, [taskId, effectiveTaskId, getAudioContext]);

  const connectAudioGraph = useCallback((audio: HTMLAudioElement) => {
    const ctx = getAudioContext();
    if (sourceNodeRef.current) return;

    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    analyserRef.current = analyser;

    try {
      const source = ctx.createMediaElementSource(audio);
      sourceNodeRef.current = source;
      source.connect(analyser);
      analyser.connect(ctx.destination);
    } catch {
      // already connected
    }
  }, [getAudioContext]);

  useEffect(() => {
    if (!audioElRef.current || !audioContextRef.current) return;
    if (sourceNodeRef.current) return;
    connectAudioGraph(audioElRef.current);
  }, [connectAudioGraph]);

  const play = useCallback(() => {
    const audio = audioElRef.current;
    if (!audio || !audioReady) return;

    const ctx = getAudioContext();
    if (ctx.state === 'suspended') ctx.resume();

    if (!sourceNodeRef.current) {
      connectAudioGraph(audio);
    }

    audio.play().catch(() => {});
  }, [audioReady, getAudioContext, connectAudioGraph]);

  const pause = useCallback(() => {
    const audio = audioElRef.current;
    if (!audio) return;
    audio.pause();
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
    const savedTime = currentTime;

    setCompareMode(mode);

    pendingSeekRef.current = savedTime;
    pendingPlayRef.current = wasPlaying;
  }, [compareMode, isPlaying, currentTime]);

  // 在原始/修复后之间快速切换（A/B 对比核心操作）
  const swapMode = useCallback(() => {
    setCompareMode((m) => {
      const next = m === 'original' ? 'repaired' : 'original';
      pendingSeekRef.current = currentTime;
      pendingPlayRef.current = isPlaying;
      return next;
    });
  }, [currentTime, isPlaying]);

  // 应用播放速率
  useEffect(() => {
    const audio = audioElRef.current;
    if (audio) audio.playbackRate = playbackRate;
  }, [playbackRate]);

  // 应用音量 / 静音
  useEffect(() => {
    const audio = audioElRef.current;
    if (audio) {
      audio.muted = muted;
      audio.volume = muted ? 0 : volume;
    }
  }, [volume, muted]);

  const switchDualTrackMode = useCallback((mode: DualTrackMode) => {
    if (mode === dualTrackMode) return;
    setDualTrackMode(mode);
    setOriginalBuffer(null);
    setRepairedBuffer(null);
    setOriginalError(null);
    setRepairedError(null);
    setAudioReady(false);
    setCurrentTime(0);
    setDuration(0);
    setPointA(null);
    setPointB(null);
    abLoopRef.current = false;
    resetLoopCount();
    setCompareMode('original');
  }, [dualTrackMode, resetLoopCount]);

  const setMarkA = useCallback(() => {
    setPointA(currentTime);
    if (pointB !== null && currentTime >= pointB) {
      setPointB(null);
      abLoopRef.current = false;
    }
    resetLoopCount();
  }, [currentTime, pointB, resetLoopCount]);

  const setMarkB = useCallback(() => {
    if (pointA === null) return;
    setPointB(currentTime);
    abLoopRef.current = true;
    resetLoopCount();
  }, [currentTime, pointA, resetLoopCount]);

  const clearAB = useCallback(() => {
    setPointA(null);
    setPointB(null);
    abLoopRef.current = false;
    resetLoopCount();
  }, [resetLoopCount]);

  const confirmEditA = useCallback(() => {
    const t = parseTimeInput(editAVal);
    if (t !== null && t >= 0 && t <= (duration || Infinity)) {
      setPointA(t);
      if (pointB !== null && t >= pointB) {
        setPointB(null);
        abLoopRef.current = false;
      }
      resetLoopCount();
    }
    setEditingA(false);
  }, [editAVal, duration, pointB, resetLoopCount]);

  const confirmEditB = useCallback(() => {
    const t = parseTimeInput(editBVal);
    if (t !== null && t >= 0 && t <= (duration || Infinity) && pointA !== null && t > pointA) {
      setPointB(t);
      abLoopRef.current = true;
      resetLoopCount();
    }
    setEditingB(false);
  }, [editBVal, duration, pointA, resetLoopCount]);

  const selectTask = useCallback((id: string) => {
    setSearchParams({ taskId: id });
  }, [setSearchParams]);

  // 键盘快捷键：A/B 对比核心工作流
  useEffect(() => {
    if (!taskId) return;
    const onKeyDown = (e: KeyboardEvent) => {
      // 输入框内不拦截
      const el = document.activeElement;
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || (el as HTMLElement).isContentEditable)) {
        return;
      }
      // 避免与浏览器/修饰键冲突
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const audio = audioElRef.current;
      switch (e.key) {
        case ' ':
        case 'k':
          e.preventDefault();
          if (audio && audioReady) {
            if (audio.paused) play(); else pause();
          }
          break;
        case 's':
        case 'S':
          e.preventDefault();
          swapMode();
          break;
        case 'a':
        case 'A':
          e.preventDefault();
          if (!editingA) setMarkA();
          break;
        case 'b':
        case 'B':
          e.preventDefault();
          if (!editingB) setMarkB();
          break;
        case 'c':
        case 'C':
          e.preventDefault();
          clearAB();
          break;
        case 'l':
        case 'L':
          e.preventDefault();
          if (pointA !== null && pointB !== null) {
            abLoopRef.current = !abLoopRef.current;
            if (abLoopRef.current) resetLoopCount();
          }
          break;
        case 'm':
        case 'M':
          e.preventDefault();
          setMuted((m) => !m);
          break;
        case 'ArrowLeft': {
          e.preventDefault();
          if (audio) seek(audio.currentTime - (e.shiftKey ? 1 : 5));
          break;
        }
        case 'ArrowRight': {
          e.preventDefault();
          if (audio) seek(audio.currentTime + (e.shiftKey ? 1 : 5));
          break;
        }
        default:
          break;
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [taskId, audioReady, play, pause, swapMode, setMarkA, setMarkB, clearAB, editingA, editingB, pointA, pointB, resetLoopCount, seek]);

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
  const modeColor: Record<CompareMode, string> = { original: '#9CA3AF', repaired: '#00D9FF' };
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
            className="mt-4 px-4 py-2 bg-cyan-500/20 border border-cyan-400/30 rounded-lg text-cyan-400 text-sm"
          >
            前往修复
          </button>
        </div>
      ) : (
        tasks.map(task => (
          <button
            key={task.id}
            onClick={() => task.output_exists ? selectTask(task.id) : undefined}
            className={`w-full flex items-center gap-4 p-4 bg-white/5 border rounded-xl text-left ${task.output_exists ? 'border-white/10 cursor-pointer hover:bg-white/[0.07]' : 'border-white/5 cursor-not-allowed opacity-50'}`}
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
                {task.output_exists ? (
                  <span className="text-green-400">已修复</span>
                ) : (
                  <span className="text-yellow-500">文件已过期</span>
                )}
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
            className="mt-2 px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-gray-400 text-sm"
          >
            选择其他任务
          </button>
        </div>
      );
    }

    const color = modeColor[compareMode];

    return (
      <>
        <div className="mb-4">
          <h3 className="text-white font-semibold text-lg truncate mb-1">
            {(taskInfo?.original_filename as string) || 'audio'}
          </h3>
          <p className="text-gray-500 text-xs">点击卡片切换音频源</p>
        </div>

        {dualTrackMode !== null && (
          <div className="flex items-center justify-center mb-5">
            <div className="inline-flex items-center gap-1 p-1 bg-white/5 rounded-xl border border-white/10">
              {([
                { mode: 'vocal' as DualTrackMode, label: '🎤 人声', color: '#EC4899' },
                { mode: 'accompaniment' as DualTrackMode, label: '🎸 伴奏', color: '#A855F7' },
                { mode: 'merged' as DualTrackMode, label: '🎵 合并', color: '#06B6D4' },
              ]).map(({ mode, label, color }) => (
                <button
                  key={mode}
                  onClick={() => switchDualTrackMode(mode)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    dualTrackMode === mode ? 'shadow-md' : 'text-gray-400 hover:text-gray-200'
                  }`}
                  style={dualTrackMode === mode ? {
                    background: `linear-gradient(135deg, ${color}30, ${color}15)`,
                    color,
                    border: `1px solid ${color}50`,
                    boxShadow: `0 0 12px ${color}20`,
                  } : {
                    background: 'transparent',
                    border: '1px solid transparent',
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 mb-6">
          {(['original', 'repaired'] as CompareMode[]).map((mode) => {
            const isLoading = mode === 'original' ? originalLoading : repairedLoading;
            const loadError = mode === 'original' ? originalError : repairedError;
            const info = getBufferInfo(mode);
            const active = compareMode === mode;
            const c = modeColor[mode];

            return (
              <button
                key={mode}
                onClick={() => switchMode(mode)}
                className={`relative text-left p-4 rounded-xl border ${
                  active ? 'bg-white/8 shadow-lg' : 'bg-white/3'
                }`}
                style={active ? {
                  borderColor: c + '60',
                  boxShadow: `0 0 20px ${c}15, inset 0 1px 0 ${c}20`,
                } : {
                  borderColor: 'rgba(255,255,255,0.06)',
                }}
              >
                {active && (
                  <div
                    className="absolute top-2 right-2 w-2 h-2 rounded-full"
                    style={{ backgroundColor: c, boxShadow: `0 0 6px ${c}` }}
                  />
                )}

                <div className="flex items-center gap-2 mb-2">
                  <svg className="w-4 h-4" style={{ color: c }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={modeIcon[mode]} />
                  </svg>
                  <span className="text-sm font-medium" style={{ color: c }}>
                    {modeLabel[mode]}
                  </span>
                  {isLoading && (
                    <span className="w-3 h-3 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: c + '40', borderTopColor: 'transparent' }} />
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

        <div className="bg-gradient-to-br from-[#0d0d12] to-[#08080c] rounded-2xl p-4 sm:p-6 border border-white/5 shadow-2xl shadow-black/40">
          <div className="flex flex-col items-center gap-5">
            <div className="flex items-center gap-5 w-full">
              <button
                onClick={isPlaying ? pause : play}
                disabled={!audioReady}
                className="shrink-0 relative"
              >
                <div
                  className="w-16 h-16 rounded-full flex items-center justify-center transition-transform active:scale-95"
                  style={{
                    background: `linear-gradient(135deg, ${color}40, ${color}20)`,
                    border: `2px solid ${color}50`,
                    boxShadow: isPlaying ? `0 0 24px ${color}30` : 'none',
                  }}
                >
                  {isPlaying ? (
                    <svg className="w-7 h-7 text-white/90" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
                    </svg>
                  ) : (
                    <svg className="w-7 h-7 text-white/90 ml-1" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M8 5v14l11-7z" />
                    </svg>
                  )}
                </div>
                {isPlaying && (
                  <>
                    <div
                      className="absolute inset-0 rounded-full animate-ping"
                      style={{ border: `1px solid ${color}20` }}
                    />
                    <div
                      className="absolute -inset-2 rounded-full animate-pulse"
                      style={{ border: `1px solid ${color}15` }}
                    />
                  </>
                )}
              </button>

              <div className="flex-1 min-w-0 space-y-2">
                <div className="flex items-center justify-between text-xs font-mono">
                  <span style={{ color }}>{formatTime(currentTime)}</span>
                  <span className="text-gray-500">{formatTime(duration)}</span>
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
                    className="w-full h-2 bg-gray-800 rounded-full appearance-none cursor-pointer disabled:opacity-30 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:shadow-md [&::-webkit-slider-runnable-track]:rounded-full"
                    style={{
                      background: audioReady
                        ? `linear-gradient(to right, ${color} ${(currentTime / (duration || 1)) * 100}%, #1f2937 ${(currentTime / (duration || 1)) * 100}%)`
                        : undefined,
                    }}
                  />
                  {pointA !== null && (
                    <div
                      className="absolute top-0 w-0.5 h-2 bg-green-400 rounded-full pointer-events-none"
                      style={{ left: `${(pointA / (duration || 1)) * 100}%` }}
                    />
                  )}
                  {pointB !== null && (
                    <div
                      className="absolute top-0 w-0.5 h-2 bg-red-400 rounded-full pointer-events-none"
                      style={{ left: `${(pointB / (duration || 1)) * 100}%` }}
                    />
                  )}
                  {pointA !== null && pointB !== null && (
                    <div
                      className="absolute top-0 h-2 bg-yellow-400/10 pointer-events-none rounded"
                      style={{
                        left: `${(pointA / (duration || 1)) * 100}%`,
                        width: `${((pointB - pointA) / (duration || 1)) * 100}%`,
                      }}
                    />
                  )}
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-center gap-2">
              <div className="flex items-center gap-1.5">
                <span className="text-green-400 text-xs font-bold w-3">A</span>
                {editingA ? (
                  <input
                    type="text"
                    value={editAVal}
                    onChange={(e) => setEditAVal(e.target.value)}
                    onBlur={confirmEditA}
                    onKeyDown={(e) => { if (e.key === 'Enter') confirmEditA(); if (e.key === 'Escape') setEditingA(false); }}
                    placeholder="0:00.0"
                    className="w-16 px-1.5 py-0.5 text-xs bg-black/40 border border-green-500/30 rounded text-green-400 font-mono text-center"
                    autoFocus
                  />
                ) : (
                  <button
                    onClick={() => {
                      if (pointA === null) {
                        setMarkA();
                      } else {
                        setEditingA(true);
                        setEditAVal(formatTimePrecise(pointA));
                      }
                    }}
                    disabled={!audioReady}
                    className={`px-2 py-0.5 rounded text-xs font-mono ${
                      pointA !== null
                        ? 'bg-green-500/15 text-green-400 border border-green-500/25'
                        : 'bg-white/5 text-gray-400 border border-white/10'
                    } disabled:opacity-30 disabled:cursor-not-allowed`}
                  >
                    {pointA !== null ? formatTimePrecise(pointA) : '设置'}
                  </button>
                )}
              </div>

              <div className="flex items-center gap-1.5">
                <span className="text-red-400 text-xs font-bold w-3">B</span>
                {editingB ? (
                  <input
                    type="text"
                    value={editBVal}
                    onChange={(e) => setEditBVal(e.target.value)}
                    onBlur={confirmEditB}
                    onKeyDown={(e) => { if (e.key === 'Enter') confirmEditB(); if (e.key === 'Escape') setEditingB(false); }}
                    placeholder="0:00.0"
                    className="w-16 px-1.5 py-0.5 text-xs bg-black/40 border border-red-500/30 rounded text-red-400 font-mono text-center"
                    autoFocus
                  />
                ) : (
                  <button
                    onClick={() => {
                      if (pointA === null) return;
                      if (pointB === null) {
                        setMarkB();
                      } else {
                        setEditingB(true);
                        setEditBVal(formatTimePrecise(pointB));
                      }
                    }}
                    disabled={!audioReady || pointA === null}
                    className={`px-2 py-0.5 rounded text-xs font-mono ${
                      pointB !== null
                        ? 'bg-red-500/15 text-red-400 border border-red-500/25'
                        : 'bg-white/5 text-gray-400 border border-white/10'
                    } disabled:opacity-30 disabled:cursor-not-allowed`}
                  >
                    {pointB !== null ? formatTimePrecise(pointB) : '设置'}
                  </button>
                )}
              </div>

              {abLoopRef.current && (
                <span className="text-yellow-400 text-xs flex items-center gap-1">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  循环{loopLimit > 0 ? ` ${loopCount}/${loopLimit}` : ` ×${loopCount}`}
                </span>
              )}
              {(pointA !== null || pointB !== null) && (
                <button
                  onClick={clearAB}
                  className="px-2 py-0.5 rounded text-xs bg-white/5 text-gray-500 border border-white/10"
                >
                  清除
                </button>
              )}
            </div>

            {/* 播放控制：A/B 快速切换 / 变速 / 音量 / 循环次数 */}
            <div className="flex flex-wrap items-center justify-center gap-3 mt-1">
              <button
                onClick={swapMode}
                disabled={!audioReady}
                className="px-3 py-1 rounded-lg text-xs font-medium border transition disabled:opacity-30"
                style={{
                  borderColor: color + '50',
                  background: `linear-gradient(135deg, ${color}25, ${color}10)`,
                  color,
                }}
                title="快捷键 S"
              >
                ⇄ 切换 A/B
              </button>

              <div className="flex items-center gap-1" title="播放速率">
                <span className="text-gray-500 text-[10px]">速率</span>
                {[0.5, 0.75, 1, 1.25, 1.5, 2].map((r) => (
                  <button
                    key={r}
                    onClick={() => setPlaybackRate(r)}
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition ${
                      playbackRate === r
                        ? 'bg-cyan-500/25 text-cyan-300 border border-cyan-400/40'
                        : 'bg-white/5 text-gray-400 border border-white/10 hover:text-gray-200'
                    }`}
                  >
                    {r}×
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-1.5" title="音量（快捷键 M 静音）">
                <button
                  onClick={() => setMuted((m) => !m)}
                  className="text-gray-400 hover:text-white transition"
                >
                  {muted || volume === 0 ? (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15zM17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" /></svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" /></svg>
                  )}
                </button>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={muted ? 0 : volume}
                  onChange={(e) => { setVolume(parseFloat(e.target.value)); if (parseFloat(e.target.value) > 0) setMuted(false); }}
                  className="w-16 h-1.5 bg-gray-800 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white"
                />
              </div>

              <div className="flex items-center gap-1" title="AB 循环次数上限">
                <span className="text-gray-500 text-[10px]">循环</span>
                {[0, 1, 3, 5, 10].map((n) => (
                  <button
                    key={n}
                    onClick={() => { setLoopLimit(n); resetLoopCount(); }}
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition ${
                      loopLimit === n
                        ? 'bg-yellow-500/25 text-yellow-300 border border-yellow-400/40'
                        : 'bg-white/5 text-gray-400 border border-white/10 hover:text-gray-200'
                    }`}
                  >
                    {n === 0 ? '∞' : n}
                  </button>
                ))}
              </div>

              <button
                onClick={() => setShowShortcuts((v) => !v)}
                className="px-2 py-0.5 rounded text-[10px] bg-white/5 text-gray-500 border border-white/10 hover:text-gray-300"
              >
                ⌨ 快捷键
              </button>
            </div>

            {showShortcuts && (
              <div className="mt-2 p-3 bg-black/30 border border-white/5 rounded-lg text-[10px] text-gray-400 grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1">
                <span><kbd className="text-cyan-300">空格</kbd> 播放/暂停</span>
                <span><kbd className="text-cyan-300">S</kbd> 切换 A/B</span>
                <span><kbd className="text-cyan-300">A / B</kbd> 标记 A/B 点</span>
                <span><kbd className="text-cyan-300">C</kbd> 清除标记</span>
                <span><kbd className="text-cyan-300">L</kbd> 开关循环</span>
                <span><kbd className="text-cyan-300">M</kbd> 静音</span>
                <span><kbd className="text-cyan-300">← →</kbd> 快退/快进 5s</span>
                <span><kbd className="text-cyan-300">Shift+← →</kbd> 1s 微调</span>
              </div>
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
          <span>{effectiveTaskId}</span>
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
            {taskId && (
              <button
                onClick={() => setSearchParams({})}
                className="flex items-center gap-2 text-gray-500 text-sm"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                </svg>
                <span>选择任务</span>
              </button>
            )}
          </div>

          <div className="bg-primary/50 border border-white/10 rounded-xl p-4 sm:p-6">
            {!taskId ? renderTaskList() : renderPlayer()}
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
}

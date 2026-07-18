import { useCallback, useEffect, useMemo } from 'react';
import { PlayMode } from './types';
import { writeLog } from './utils';
import type { AudioCoreState, AudioCoreRefs } from './useAudioCore';

interface UseAudioPlaybackOptions {
  state: AudioCoreState;
  refs: AudioCoreRefs;
}

export function useAudioPlayback({ state, refs }: UseAudioPlaybackOptions) {
  const {
    playMode, setPlayMode,
    setIsPlaying,
    currentTime, setCurrentTime,
  } = state;

  const {
    audioContextRef,
    sourceNodeRef,
    gainNodeRef,
    analyserRef,
    startTimeRef,
    playStartTimeRef,
    pausedAtRef,
    animationFrameRef,
    isPlayingRef,
    streamingAudioRef,
    mediaSourceRef,
    playRef,
    audioBufferRef,
    backendProcessedBufferRef,
    seekInProgressRef,
    modeNodesRef,
    activeModeRef,
    pendingObjectURLRef,
    pendingPlayRef,
    durationRef,
  } = refs;

  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext)();
      analyserRef.current = audioContextRef.current.createAnalyser();
      analyserRef.current.fftSize = 256;
      analyserRef.current.connect(audioContextRef.current.destination);
    }
    return audioContextRef.current;
  }, [audioContextRef, analyserRef]);

  const stopAllModeNodes = useCallback((immediate = true) => {
    const context = audioContextRef.current;
    (Object.keys(modeNodesRef.current) as PlayMode[]).forEach((mode) => {
      const node = modeNodesRef.current[mode];
      if (!node) return;
      try {
        node.source.onended = null;
        if (!immediate && context) {
          const now = context.currentTime;
          node.gain.gain.setValueAtTime(node.gain.gain.value, now);
          node.gain.gain.linearRampToValueAtTime(0.0001, now + 0.03);
          node.source.stop(now + 0.03);
        } else {
          try { node.source.stop(); } catch {}
          try { node.source.disconnect(); } catch {}
          try { node.gain.disconnect(); } catch {}
        }
      } catch {}
      modeNodesRef.current[mode] = null;
    });
    sourceNodeRef.current = null;
    gainNodeRef.current = null;
  }, [audioContextRef, modeNodesRef, sourceNodeRef, gainNodeRef]);

  const stopPlaying = useCallback((immediate = true) => {
    stopAllModeNodes(immediate);
    pendingPlayRef.current = false;
    pendingObjectURLRef.current = null;

    if (mediaSourceRef.current) {
      try { mediaSourceRef.current.disconnect(); } catch {}
      mediaSourceRef.current = null;
    }
    if (streamingAudioRef.current) {
      streamingAudioRef.current.pause();
      streamingAudioRef.current.onended = null;
      streamingAudioRef.current.onerror = null;
      streamingAudioRef.current.src = '';
      try { streamingAudioRef.current.load(); } catch {}
      streamingAudioRef.current = null;
    }
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    isPlayingRef.current = false;
    setIsPlaying(false);
  }, [stopAllModeNodes, pendingPlayRef, pendingObjectURLRef, mediaSourceRef, streamingAudioRef, animationFrameRef, isPlayingRef, setIsPlaying]);

  const startStreamingPlayback = useCallback((url: string, mode: PlayMode = 'backend') => {
    stopPlaying();

    const context = getAudioContext();
    if (context.state === 'suspended') {
      context.resume();
    }

    const audio = new Audio();
    audio.crossOrigin = 'anonymous';
    audio.src = url;

    const source = context.createMediaElementSource(audio);
    source.connect(analyserRef.current!);

    streamingAudioRef.current = audio;
    mediaSourceRef.current = source;

    audio.play().catch(err => {
      console.warn('[startStreamingPlayback] 播放失败:', err);
    });

    isPlayingRef.current = true;
    setIsPlaying(true);
    activeModeRef.current = mode;
    setPlayMode(mode);
    startTimeRef.current = context.currentTime;
    pausedAtRef.current = 0;
    setCurrentTime(0);

    const lastUiUpdateRef = { current: 0 };
    const updateTime = () => {
      if (isPlayingRef.current && streamingAudioRef.current) {
        const current = streamingAudioRef.current.currentTime;
        const now = performance.now();
        if (now - lastUiUpdateRef.current >= 100) {
          setCurrentTime(current);
          lastUiUpdateRef.current = now;
        }
        if (streamingAudioRef.current.ended) {
          stopPlaying();
          setCurrentTime(0);
          pausedAtRef.current = 0;
        } else {
          animationFrameRef.current = requestAnimationFrame(updateTime);
        }
      }
    };
    audio.addEventListener('playing', () => {
      updateTime();
    });

    audio.onended = () => {
      if (isPlayingRef.current) {
        stopPlaying();
        setCurrentTime(0);
        pausedAtRef.current = 0;
      }
    };
  }, [getAudioContext, stopPlaying, streamingAudioRef, mediaSourceRef, analyserRef, isPlayingRef, setIsPlaying, activeModeRef, setPlayMode, startTimeRef, pausedAtRef, setCurrentTime, animationFrameRef]);

  const getCurrentBuffer = useCallback(() => {
    if (playMode === 'backend') return backendProcessedBufferRef.current;
    return audioBufferRef.current;
  }, [playMode, backendProcessedBufferRef, audioBufferRef]);

  const play = useCallback(async () => {
    writeLog(`[play] 开始播放: playMode=${playMode}, isPlaying=${isPlayingRef.current}, activeMode=${activeModeRef.current}`);

    if (playMode === 'backend' && streamingAudioRef.current && !backendProcessedBufferRef.current) {
      writeLog(`[play] 使用streaming播放`);
      streamingAudioRef.current.play().catch(() => {});
      isPlayingRef.current = true;
      setIsPlaying(true);
      activeModeRef.current = 'backend';
      const lastUiUpdateRef = { current: 0 };
      const updateTime = () => {
        if (isPlayingRef.current && streamingAudioRef.current) {
          const current = streamingAudioRef.current.currentTime;
          const now = performance.now();
          if (now - lastUiUpdateRef.current >= 100) {
            setCurrentTime(current);
            lastUiUpdateRef.current = now;
          }
          if (streamingAudioRef.current.ended) {
            stopPlaying();
            setCurrentTime(0);
            pausedAtRef.current = 0;
          } else {
            animationFrameRef.current = requestAnimationFrame(updateTime);
          }
        }
      };
      updateTime();
      return;
    }

    if (streamingAudioRef.current) {
      writeLog(`[play] 停止streaming，切换到buffer播放`);
      const resumeTime = streamingAudioRef.current.currentTime;
      streamingAudioRef.current.pause();
      streamingAudioRef.current = null;
      if (mediaSourceRef.current) {
        try { mediaSourceRef.current.disconnect(); } catch {}
        mediaSourceRef.current = null;
      }
      if (resumeTime > 0) {
        pausedAtRef.current = resumeTime;
      }
    }

    const buffer = getCurrentBuffer() ?? audioBufferRef.current;
    if (!buffer) {
      if (durationRef.current > 0 && pendingObjectURLRef.current) {
        writeLog(`[play] buffer未就绪，使用streaming播放`);
        startStreamingPlayback(pendingObjectURLRef.current, 'original');
        pendingPlayRef.current = true;
        return;
      }
      if (durationRef.current > 0) {
        writeLog(`[play] buffer未就绪，标记pendingPlay`);
        pendingPlayRef.current = true;
      }
      return;
    }

    const context = getAudioContext();
    if (context.state === 'suspended') {
      await context.resume();
      await new Promise(resolve => setTimeout(resolve, 50));
    }

    if (seekInProgressRef.current) {
      writeLog(`[play] seek模式，停止所有节点`);
      stopAllModeNodes();
      seekInProgressRef.current = false;
    }

    if (modeNodesRef.current[playMode]) {
      writeLog(`[play] 警告: 当前模式已有节点，先停止`);
      try {
        const node = modeNodesRef.current[playMode]!;
        node.source.onended = null;
        node.source.stop();
        node.source.disconnect();
        node.gain.disconnect();
      } catch {}
      modeNodesRef.current[playMode] = null;
    }

    writeLog(`[play] 创建新节点: mode=${playMode}, bufferDuration=${buffer.duration.toFixed(3)}`);
    const source = context.createBufferSource();
    const gain = context.createGain();

    source.buffer = buffer;
    source.connect(gain);
    gain.connect(analyserRef.current!);

    const fadeInDuration = 0.015;
    gain.gain.setValueAtTime(0, context.currentTime);
    gain.gain.linearRampToValueAtTime(1.0, context.currentTime + fadeInDuration);

    let playOffset = pausedAtRef.current;
    if (playOffset >= buffer.duration) {
      pausedAtRef.current = 0;
      playOffset = 0;
    }

    source.onended = () => {
      writeLog(`[play] 节点播放结束`);
      if (isPlayingRef.current) {
        stopPlaying();
        setCurrentTime(0);
        pausedAtRef.current = 0;
      }
    };

    modeNodesRef.current[playMode] = { source, gain };
    sourceNodeRef.current = source;
    gainNodeRef.current = gain;
    activeModeRef.current = playMode;

    playStartTimeRef.current = performance.now();
    startTimeRef.current = context.currentTime - playOffset;
    source.start(0, playOffset);
    writeLog(`[play] 节点已启动: offset=${playOffset.toFixed(3)}`);

    isPlayingRef.current = true;
    setIsPlaying(true);

    const lastUiUpdateRef = { current: 0 };
    const updateTime = () => {
      if (isPlayingRef.current) {
        const elapsed = (performance.now() - playStartTimeRef.current) / 1000;
        const current = playOffset + elapsed;
        if (current >= buffer.duration) {
          stopPlaying();
          setCurrentTime(0);
          pausedAtRef.current = 0;
        } else {
          const now = performance.now();
          if (now - lastUiUpdateRef.current >= 100) {
            setCurrentTime(current);
            lastUiUpdateRef.current = now;
          }
          animationFrameRef.current = requestAnimationFrame(updateTime);
        }
      }
    };
    updateTime();
  }, [playMode, isPlayingRef, activeModeRef, streamingAudioRef, backendProcessedBufferRef, setIsPlaying, setCurrentTime, stopPlaying, pausedAtRef, animationFrameRef, mediaSourceRef, getCurrentBuffer, audioBufferRef, durationRef, pendingObjectURLRef, startStreamingPlayback, pendingPlayRef, getAudioContext, seekInProgressRef, stopAllModeNodes, modeNodesRef, analyserRef, sourceNodeRef, gainNodeRef, playStartTimeRef, startTimeRef]);

  useEffect(() => {
    playRef.current = play;
  }, [play, playRef]);

  const pause = useCallback(() => {
    if (streamingAudioRef.current) {
      pausedAtRef.current = streamingAudioRef.current.currentTime;
      streamingAudioRef.current.pause();
      isPlayingRef.current = false;
      setIsPlaying(false);
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      return;
    }
    pausedAtRef.current = currentTime;
    stopPlaying();
  }, [streamingAudioRef, pausedAtRef, isPlayingRef, setIsPlaying, animationFrameRef, currentTime, stopPlaying]);

  const seek = useCallback((time: number) => {
    if (streamingAudioRef.current) {
      streamingAudioRef.current.currentTime = time;
      pausedAtRef.current = time;
      setCurrentTime(time);
      return;
    }
    const wasPlaying = isPlayingRef.current;
    if (isPlayingRef.current) {
      stopPlaying();
    }
    pausedAtRef.current = time;
    setCurrentTime(time);
    if (wasPlaying && playRef.current) {
      seekInProgressRef.current = true;
      playRef.current();
    }
  }, [streamingAudioRef, pausedAtRef, setCurrentTime, isPlayingRef, stopPlaying, playRef, seekInProgressRef]);

  const switchPlayMode = useCallback(async (mode: PlayMode) => {
    writeLog(`[switchPlayMode] 开始切换: target=${mode}, current=${activeModeRef.current}, isPlaying=${isPlayingRef.current}`);

    const targetBuffer = mode === 'backend' ? backendProcessedBufferRef.current
      : audioBufferRef.current;
    if (!targetBuffer) {
      writeLog(`[switchPlayMode] 目标buffer为空，只切换状态`);
      setPlayMode(mode);
      return;
    }

    if (!isPlayingRef.current) {
      writeLog(`[switchPlayMode] 未在播放，直接切换状态`);
      setPlayMode(mode);
      return;
    }

    if (activeModeRef.current === mode) {
      writeLog(`[switchPlayMode] 已是目标模式，无需操作`);
      setPlayMode(mode);
      return;
    }

    const context = getAudioContext();
    if (context.state === 'suspended') {
      await context.resume();
    }

    const now = context.currentTime;
    const currentElapsed = now - startTimeRef.current;
    const startPosition = Math.min(currentElapsed, targetBuffer.duration - 0.01);

    writeLog(`[switchPlayMode] 停止当前节点: mode=${activeModeRef.current}, position=${startPosition.toFixed(3)}`);

    if (streamingAudioRef.current) {
      writeLog(`[switchPlayMode] 停止streaming音频`);
      try {
        streamingAudioRef.current.pause();
        streamingAudioRef.current.src = '';
      } catch {}
      streamingAudioRef.current = null;
      if (mediaSourceRef.current) {
        try { mediaSourceRef.current.disconnect(); } catch {}
        mediaSourceRef.current = null;
      }
    }

    const currentNode = modeNodesRef.current[activeModeRef.current];
    if (currentNode) {
      try {
        currentNode.source.onended = null;
        currentNode.source.stop(now);
        currentNode.source.disconnect();
        currentNode.gain.disconnect();
        writeLog(`[switchPlayMode] 旧节点已停止并断开`);
      } catch (e) {
        writeLog(`[switchPlayMode] 停止旧节点出错: ${e}`);
      }
    }

    (Object.keys(modeNodesRef.current) as PlayMode[]).forEach((m) => {
      modeNodesRef.current[m] = null;
    });

    writeLog(`[switchPlayMode] 创建新节点: mode=${mode}, bufferDuration=${targetBuffer.duration.toFixed(3)}`);
    const newSource = context.createBufferSource();
    const newGain = context.createGain();
    newSource.buffer = targetBuffer;
    newSource.connect(newGain);
    newGain.connect(analyserRef.current!);

    newGain.gain.setValueAtTime(0, now);
    newGain.gain.linearRampToValueAtTime(1.0, now + 0.01);

    newSource.onended = () => {
      writeLog(`[switchPlayMode] 新节点播放结束`);
      if (isPlayingRef.current) {
        stopPlaying();
        setCurrentTime(0);
        pausedAtRef.current = 0;
      }
    };

    modeNodesRef.current[mode] = { source: newSource, gain: newGain };
    sourceNodeRef.current = newSource;
    gainNodeRef.current = newGain;
    activeModeRef.current = mode;

    startTimeRef.current = now - startPosition;
    newSource.start(now, startPosition);
    writeLog(`[switchPlayMode] 新节点已启动: startTime=${startTimeRef.current.toFixed(3)}, offset=${startPosition.toFixed(3)}`);

    setPlayMode(mode);

    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }

    const updateTime = () => {
      if (isPlayingRef.current) {
        const elapsed = context.currentTime - startTimeRef.current;
        if (elapsed >= targetBuffer.duration) {
          stopPlaying();
          setCurrentTime(0);
          pausedAtRef.current = 0;
        } else {
          setCurrentTime(elapsed);
          animationFrameRef.current = requestAnimationFrame(updateTime);
        }
      }
    };
    updateTime();
  }, [activeModeRef, isPlayingRef, backendProcessedBufferRef, audioBufferRef, setPlayMode, getAudioContext, startTimeRef, streamingAudioRef, mediaSourceRef, modeNodesRef, analyserRef, sourceNodeRef, gainNodeRef, stopPlaying, setCurrentTime, pausedAtRef, animationFrameRef]);

  const api = useMemo(() => ({
    getAudioContext,
    stopAllModeNodes,
    stopPlaying,
    startStreamingPlayback,
    getCurrentBuffer,
    play,
    pause,
    seek,
    switchPlayMode,
  }), [
    getAudioContext,
    stopAllModeNodes,
    stopPlaying,
    startStreamingPlayback,
    getCurrentBuffer,
    play,
    pause,
    seek,
    switchPlayMode,
  ]);

  return api;
}

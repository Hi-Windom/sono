import { useCallback } from 'react';
import { parseWavHeader } from '../../utils/wavParser';
import { computeFileHash } from '../../utils/fileHash';
import { useRepairSessionStore } from '../../store/repairSessionStore';
import {
  uploadAudio,
  downloadWithProgress,
} from '../../services/backendApi';
import { saveSession, saveAnalysisCache } from '../../utils/sessionDB';
import { WavInfo } from '../../utils/wavParser';
import { AudioAnalysis } from './types';
import { writeLog, formatSpeed, formatBytes } from './utils';
import type { AudioCoreState, AudioCoreRefs } from './useAudioCore';
import type { useAudioWorker } from '../../workers/useAudioWorker';

interface UseAudioDecoderOptions {
  state: AudioCoreState;
  refs: AudioCoreRefs;
  audioWorker: ReturnType<typeof useAudioWorker>;
  setTaskId: (id: string | null) => void;
  setWavInfo: (info: WavInfo | null) => void;
  stopPlaying: () => void;
  closeWS: () => void;
  play: () => void;
  getAudioContext: () => AudioContext;
}

export function useAudioDecoder({
  state,
  refs,
  audioWorker,
  setTaskId,
  setWavInfo,
  stopPlaying,
  closeWS,
  play,
  getAudioContext,
}: UseAudioDecoderOptions) {
  const {
    setAudioFile,
    setAudioBuffer,
    setBackendProcessedBuffer,
    setCurrentTime,
    setHasBeenProcessed,
    setPlayMode,
    setProcessingStep,
    setIsProcessing,
    setIsDecodingAudio,
    setProcessingProgress,
    setBackendError,
    setFileHash,
    setAudioAnalysis,
    setDuration,
    setBackendAvailable,
    setOriginalWaveformPeaks,
  } = state;

  const {
    audioBufferRef,
    backendProcessedBufferRef,
    pendingObjectURLRef,
    pendingPlayRef,
    durationRef,
    loadAudioSeqRef,
    fileHashRef,
    sessionRestoredRef,
    pendingSessionRef,
    processingOptionsRef,
    wavInfoRef,
  } = refs;

  const loadAudioFromUrl = useCallback(async (url: string, targetSampleRate?: number, silent?: boolean): Promise<AudioBuffer> => {
    const arrayBuffer = await downloadWithProgress(url, (loaded, total, speed) => {
      if (silent) return;
      const pct = total > 0 ? loaded / total : 0;
      setProcessingStep(`下载中 ${formatBytes(loaded)}/${formatBytes(total)} ${formatSpeed(speed)}`);
      setProcessingProgress(0.96 + pct * 0.03);
    });

    if (targetSampleRate && targetSampleRate !== getAudioContext().sampleRate) {
      const tempContext = new OfflineAudioContext(1, 1, targetSampleRate);
      const tempBuffer = await tempContext.decodeAudioData(arrayBuffer);
      if (tempBuffer.sampleRate === targetSampleRate) {
        return tempBuffer;
      }
      const resampleLength = Math.ceil(tempBuffer.length * targetSampleRate / tempBuffer.sampleRate);
      const offlineCtx = new OfflineAudioContext(
        tempBuffer.numberOfChannels,
        resampleLength,
        targetSampleRate,
      );
      const source = offlineCtx.createBufferSource();
      source.buffer = tempBuffer;
      source.connect(offlineCtx.destination);
      source.start();
      return offlineCtx.startRendering();
    }

    const context = getAudioContext();
    if (context.state === 'suspended') {
      await context.resume();
    }
    return context.decodeAudioData(arrayBuffer);
  }, [getAudioContext, setProcessingStep, setProcessingProgress]);

  const loadAudioFile = useCallback(async (file: File) => {
    const seq = ++loadAudioSeqRef.current;
    stopPlaying();
    closeWS();
    setBackendError(null);
    setAudioFile(file);

    audioBufferRef.current = null;
    setAudioBuffer(null);
    backendProcessedBufferRef.current = null;
    setBackendProcessedBuffer(null);
    setCurrentTime(0);
    refs.pausedAtRef.current = 0;
    setHasBeenProcessed(false);
    setPlayMode('original');
    useRepairSessionStore.getState().clearSingleTrack();
    setTaskId(null);
    refs.taskIdRef.current = null;
    state.setRepairResult(null);
    state.setBackendWaveformPeaks(null);
    setOriginalWaveformPeaks(null);
    state.setBackendPreviewUrl(null);
    setAudioAnalysis(null);
    setDuration(0);
    durationRef.current = 0;
    setWavInfo(null);

    setProcessingStep('读取音频信息...');
    setIsProcessing(true);
    setIsDecodingAudio(true);
    setProcessingProgress(0.02);
    const headerBuf = await file.slice(0, 44 + 4096).arrayBuffer();
    if (seq !== loadAudioSeqRef.current) return;
    const wavHeaderInfo = parseWavHeader(headerBuf);
    setWavInfo(wavHeaderInfo);

    if (wavHeaderInfo) {
      setDuration(wavHeaderInfo.duration);
      durationRef.current = wavHeaderInfo.duration;
    }

    if (pendingObjectURLRef.current) {
      URL.revokeObjectURL(pendingObjectURLRef.current);
    }
    pendingObjectURLRef.current = URL.createObjectURL(file);

    setProcessingStep('读取文件并计算校验...');
    setProcessingProgress(0.05);

    const [arrayBuf, hash] = await Promise.all([
      file.arrayBuffer(),
      computeFileHash(file),
    ]);
    if (seq !== loadAudioSeqRef.current) return;
    fileHashRef.current = hash;
    setFileHash(hash);
    writeLog(`[loadAudioFile] fileHash=${hash.slice(0, 16)}`);
    setProcessingProgress(0.15);

    let cachedAnalysis: AudioAnalysis | null = null;
    let cachedWavInfo: WavInfo | null = null;
    try {
      const cacheRes = await fetch(`/api/v1/analysis-cache/${hash}`);
      if (cacheRes.ok) {
        const cacheData = await cacheRes.json();
        if (cacheData.found && cacheData.data) {
          const d = cacheData.data;
          if (d.wav_info) cachedWavInfo = JSON.parse(d.wav_info);
          if (d.analysis) cachedAnalysis = JSON.parse(d.analysis);
          writeLog(`[loadAudioFile] 后端分析缓存命中: fileHash=${hash.slice(0, 16)}`);
          if (cachedWavInfo) setWavInfo(cachedWavInfo);
          if (cachedAnalysis) setAudioAnalysis(cachedAnalysis);
        }
      }
    } catch { /* 缓存读取失败，继续正常流程 */ }

    setProcessingStep('解码音频...');
    setProcessingProgress(0.2);

    const context = getAudioContext();
    let buffer: AudioBuffer;
    const workerDecoded = await audioWorker.decodeWav(context, arrayBuf.slice(0));
    const isNonWavFile = !workerDecoded;
    if (workerDecoded) {
      buffer = workerDecoded;
      writeLog(`[loadAudioFile] WAV PCM Worker解码完成`);
      setProcessingProgress(0.55);
    } else {
      const decodedWavUrl = `/api/v1/decoded-wav/${hash}`;
      let usedDecodedCache = false;
      try {
        const headRes = await fetch(decodedWavUrl, { method: 'HEAD' });
        if (headRes.ok && headRes.headers.get('Content-Length')) {
          writeLog(`[loadAudioFile] 发现后端解码WAV缓存，下载快速解码`);
          setProcessingStep('下载解码缓存...');
          const wavBuf = await downloadWithProgress(decodedWavUrl, (loaded, total, speed) => {
            if (seq !== loadAudioSeqRef.current) return;
            const pct = total > 0 ? loaded / total : 0;
            setProcessingProgress(0.2 + pct * 0.3);
            setProcessingStep(`下载解码缓存 ${formatBytes(loaded)}/${formatBytes(total)} ${formatSpeed(speed)}`);
          });
          const cachedBuf = await audioWorker.decodeWav(context, wavBuf);
          if (cachedBuf) {
            buffer = cachedBuf;
            usedDecodedCache = true;
            writeLog(`[loadAudioFile] 后端解码WAV缓存Worker解码完成`);
            setProcessingProgress(0.55);
          }
        }
      } catch { /* 解码缓存不可用，继续正常流程 */ }

      if (!usedDecodedCache) {
        try {
          buffer = await context.decodeAudioData(arrayBuf);
          writeLog(`[loadAudioFile] 浏览器解码完成`);
          setProcessingProgress(0.55);
        } catch (decodeErr) {
          console.warn('[loadAudioFile] 浏览器解码失败:', decodeErr);
          setIsDecodingAudio(false);
          setIsProcessing(false);
          if (arrayBuf.byteLength === 0) {
            setBackendError('解码缓冲区异常，请重新上传文件');
          } else if (decodeErr instanceof DOMException && decodeErr.name === 'EncodingError') {
            setBackendError('浏览器不支持该音频格式，请尝试WAV格式');
          } else {
            setBackendError('音频解码失败：文件已损坏或无法解析');
          }
          return;
        }
      }
    }
    if (seq !== loadAudioSeqRef.current) return;

    audioBufferRef.current = buffer;
    setAudioBuffer(buffer);
    setDuration(buffer.duration);
    durationRef.current = buffer.duration;
    setIsDecodingAudio(false);

    if (pendingPlayRef.current && refs.streamingAudioRef.current) {
      const resumeTime = refs.streamingAudioRef.current.currentTime;
      refs.pausedAtRef.current = resumeTime;
      refs.streamingAudioRef.current.pause();
      refs.streamingAudioRef.current.src = '';
      refs.streamingAudioRef.current = null;
      if (refs.mediaSourceRef.current) {
        try { refs.mediaSourceRef.current.disconnect(); } catch {}
        refs.mediaSourceRef.current = null;
      }
      pendingPlayRef.current = false;
      pendingObjectURLRef.current = null;
      writeLog(`[loadAudioFile] 从streaming切换到BufferSource播放 offset=${resumeTime.toFixed(3)}`);
      play();
    } else if (pendingPlayRef.current) {
      pendingPlayRef.current = false;
      pendingObjectURLRef.current = null;
      writeLog(`[loadAudioFile] 执行pendingPlay`);
      play();
    }

    setProcessingStep('分析音频特征...');
    setProcessingProgress(0.6);
    let analysis = cachedAnalysis;
    if (!analysis) {
      const channelData: Float32Array[] = [];
      for (let ch = 0; ch < buffer.numberOfChannels; ch++) {
        channelData.push(buffer.getChannelData(ch));
      }
      analysis = await audioWorker.analyzeAudio(channelData, buffer.sampleRate, buffer.numberOfChannels);
    }
    setAudioAnalysis(analysis);
    setProcessingProgress(0.85);

    if (!cachedAnalysis) {
      fetch('/api/v1/analysis-cache', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          quick_hash: hash,
          file_name: file.name,
          file_size: file.size,
          wav_info: JSON.stringify(wavHeaderInfo || cachedWavInfo),
          analysis: JSON.stringify(analysis),
        }),
      }).catch(() => { /* 忽略缓存写入失败 */ });
      saveAnalysisCache({
        fileHash: hash,
        fileName: file.name,
        fileSize: file.size,
        wavInfo: JSON.stringify(wavHeaderInfo || cachedWavInfo),
        analysis: JSON.stringify(analysis),
      }).catch(() => {});
    }

    (async () => {
      try {
        writeLog(`[loadAudioFile] 后台上传开始...`);
        setProcessingStep('上传中...');
        const uploadRes = await uploadAudio(file, (loaded, total, speed) => {
          if (seq !== loadAudioSeqRef.current) return;
          const pct = total > 0 ? loaded / total : 0;
          setProcessingProgress(0.85 + pct * 0.15);
          setProcessingStep(`上传中 ${formatBytes(loaded)}/${formatBytes(total)} ${formatSpeed(speed)}`);
        }, hash);
        if (seq !== loadAudioSeqRef.current) return;

        const newTaskId = uploadRes.task_id;
        setTaskId(newTaskId);
        refs.taskIdRef.current = newTaskId;
        setBackendAvailable(true);
        useRepairSessionStore.getState().setSingleTrackFile(hash, file.name);
        if (uploadRes.cached) {
          writeLog(`[loadAudioFile] 文件已缓存，跳过上传 taskId=${newTaskId}`);
        } else {
          writeLog(`[loadAudioFile] 上传成功 taskId=${newTaskId}`);
        }

        if (uploadRes.audio_info && !wavHeaderInfo) {
          const ai = uploadRes.audio_info;
          const infoFromApi: WavInfo = {
            sampleRate: ai.sample_rate,
            channels: ai.channels,
            duration: ai.duration,
            bitDepth: ai.sample_width * 8,
          };
          setWavInfo(infoFromApi);
          setDuration(ai.duration);
          durationRef.current = ai.duration;
          writeLog(`[loadAudioFile] 从audio_info获取规格: sr=${ai.sample_rate} ch=${ai.channels} dur=${ai.duration.toFixed(1)}`);
        }

        saveSession({
          file,
          fileName: file.name,
          fileSize: file.size,
          fileHash: hash,
          taskId: newTaskId,
          backendAvailable: true,
          hasBeenProcessed: false,
          wavInfo: wavInfoRef.current ? JSON.stringify(wavInfoRef.current) : '',
          repairResult: '',
          processingOptions: JSON.stringify(processingOptionsRef.current),
        });

        if (isNonWavFile) {
          fetch(`/api/v1/decoded-wav/${hash}`, { method: 'POST' }).catch(() => {});
          writeLog(`[loadAudioFile] 触发后端解码WAV缓存创建`);
        }

        fetch(`/api/v1/waveform/${hash}`)
          .then(res => res.ok ? res.json() : null)
          .then(data => {
            if (data?.peaks && seq === loadAudioSeqRef.current) {
              setOriginalWaveformPeaks(data.peaks);
              writeLog(`[loadAudioFile] 原始波形缓存已加载`);
            }
          })
          .catch(() => {});

        pendingSessionRef.current = null;
        sessionRestoredRef.current = true;
        writeLog(`[loadAudioFile] 新文件上传完成，阻止旧会话恢复`);
        setIsProcessing(false);
        setProcessingStep('');
        setProcessingProgress(0);
      } catch (err) {
        console.warn('[loadAudioFile] 上传失败:', err);
        setBackendAvailable(false);
        setIsProcessing(false);
        const msg = err instanceof Error ? err.message : String(err);
        setProcessingStep(`上传失败: ${msg}`);
        setBackendError(`上传失败: ${msg}`);
      }
    })();
  }, [
    state,
    refs,
    audioWorker,
    setTaskId,
    setWavInfo,
    stopPlaying,
    closeWS,
    play,
    getAudioContext,
    setAudioFile,
    setAudioBuffer,
    setBackendProcessedBuffer,
    setCurrentTime,
    setHasBeenProcessed,
    setPlayMode,
    setProcessingStep,
    setIsProcessing,
    setIsDecodingAudio,
    setProcessingProgress,
    setBackendError,
    setFileHash,
    setAudioAnalysis,
    setDuration,
    setBackendAvailable,
    setOriginalWaveformPeaks,
    audioBufferRef,
    backendProcessedBufferRef,
    pendingObjectURLRef,
    pendingPlayRef,
    durationRef,
    loadAudioSeqRef,
    fileHashRef,
    sessionRestoredRef,
    pendingSessionRef,
    processingOptionsRef,
    wavInfoRef,
  ]);

  return {
    loadAudioFile,
    loadAudioFromUrl,
  };
}

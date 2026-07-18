import { useRef, useCallback, useMemo } from 'react';
import type { DecodedWavResult, AudioAnalysisResult } from './audioWorker';
import { decodeWavPcm } from '../utils/wavParser';
import { detectAudioIssues } from '../utils/advancedAudioProcessing';

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (reason: unknown) => void;
}

export interface AudioWorkerAPI {
  decodeWav(audioContext: BaseAudioContext, buffer: ArrayBuffer): Promise<AudioBuffer | null>;
  analyzeAudio(channelData: Float32Array[], sampleRate: number, channels: number): Promise<AudioAnalysisResult>;
  decodeAndAnalyze(audioContext: BaseAudioContext, buffer: ArrayBuffer): Promise<{
    audioBuffer: AudioBuffer | null;
    analysis: AudioAnalysisResult | null;
  }>;
  terminate(): void;
}

export function useAudioWorker(): AudioWorkerAPI {
  const workerRef = useRef<Worker | null>(null);
  const pendingRef = useRef<Map<number, PendingRequest>>(new Map());
  const nextIdRef = useRef(0);
  const workerAvailableRef = useRef<boolean | null>(null);

  const getWorker = useCallback((): Worker | null => {
    if (workerRef.current) return workerRef.current;

    try {
      console.log('[useAudioWorker] 正在创建Worker...');
      const worker = new Worker(
        new URL('./audioWorker.ts', import.meta.url),
        { type: 'module' },
      );
      worker.onmessage = (e: MessageEvent) => {
        console.log(`[useAudioWorker] 收到Worker消息: type=${e.data?.type}, id=${e.data?.id}`);
        const { id } = e.data;
        const pending = pendingRef.current.get(id);
        if (pending) {
          pendingRef.current.delete(id);
          if (e.data?.type === 'error') {
            pending.reject(new Error(e.data.error || 'Worker error'));
          } else {
            pending.resolve(e.data);
          }
        }
      };
      worker.onerror = (err) => {
        console.warn('[useAudioWorker] Worker error:', err);
        for (const [id, pending] of pendingRef.current) {
          pending.reject(new Error('Worker error'));
          pendingRef.current.delete(id);
        }
      };
      workerRef.current = worker;
      workerAvailableRef.current = true;
      console.log('[useAudioWorker] Worker创建成功');
      return worker;
    } catch (err) {
      console.warn('[useAudioWorker] Worker creation failed, using main thread fallback:', err);
      workerAvailableRef.current = false;
      return null;
    }
  }, []);

  const sendToWorker = useCallback(<T>(msg: { type: string; id: number; [key: string]: unknown }, transfer?: Transferable[], timeoutMs = 10000): Promise<T> => {
    return new Promise((resolve, reject) => {
      const worker = getWorker();
      if (!worker) {
        console.warn('[useAudioWorker] Worker not available, rejecting');
        reject(new Error('Worker not available'));
        return;
      }
      console.log(`[useAudioWorker] 发送消息到Worker: type=${msg.type}, id=${msg.id}, transfer=${transfer ? transfer.length : 0}`);
      pendingRef.current.set(msg.id, { resolve, reject });
      if (transfer && transfer.length > 0) {
        worker.postMessage(msg, transfer);
      } else {
        worker.postMessage(msg);
      }

      setTimeout(() => {
        const pending = pendingRef.current.get(msg.id);
        if (pending) {
          console.warn(`[useAudioWorker] Worker超时: type=${msg.type}, id=${msg.id}, timeout=${timeoutMs}ms`);
          pendingRef.current.delete(msg.id);
          reject(new Error(`Worker timeout after ${timeoutMs}ms for ${msg.type}`));
        }
      }, timeoutMs);
    });
  }, [getWorker]);

  const decodeWav = useCallback(async (audioContext: BaseAudioContext, buffer: ArrayBuffer): Promise<AudioBuffer | null> => {
    const worker = getWorker();
    if (!worker) {
      return decodeWavPcm(audioContext, buffer);
    }

    const id = nextIdRef.current++;
    try {
      const bufferCopy = buffer.slice(0);
      const response = await sendToWorker<{ type: string; id: number; result: DecodedWavResult | null }>(
        { type: 'decode-wav', id, buffer: bufferCopy },
        [bufferCopy],
      );
      if (!response.result) return null;
      const { channelData, sampleRate, channels, totalFrames } = response.result;
      const audioBuffer = audioContext.createBuffer(channels, totalFrames, sampleRate);
      for (let ch = 0; ch < channels; ch++) {
        audioBuffer.copyToChannel(channelData[ch], ch);
      }
      return audioBuffer;
    } catch (err) {
      console.warn('[useAudioWorker] decodeWav worker failed, falling back:', err);
      return decodeWavPcm(audioContext, buffer);
    }
  }, [getWorker, sendToWorker]);

  const analyzeAudio = useCallback(async (channelData: Float32Array[], sampleRate: number, channels: number): Promise<AudioAnalysisResult> => {
    const worker = getWorker();
    if (!worker) {
      const fakeBuffer = { getChannelData: (ch: number) => channelData[ch], numberOfChannels: channels, sampleRate, length: channelData[0]?.length || 0 } as unknown as AudioBuffer;
      return detectAudioIssues(fakeBuffer);
    }

    const id = nextIdRef.current++;
    try {
      const response = await sendToWorker<{ type: string; id: number; result: AudioAnalysisResult }>(
        { type: 'analyze-audio', id, channelData, sampleRate, channels },
      );
      return response.result;
    } catch {
      const fakeBuffer = { getChannelData: (ch: number) => channelData[ch], numberOfChannels: channels, sampleRate, length: channelData[0]?.length || 0 } as unknown as AudioBuffer;
      return detectAudioIssues(fakeBuffer);
    }
  }, [getWorker, sendToWorker]);

  const decodeAndAnalyze = useCallback(async (audioContext: BaseAudioContext, buffer: ArrayBuffer): Promise<{
    audioBuffer: AudioBuffer | null;
    analysis: AudioAnalysisResult | null;
  }> => {
    const worker = getWorker();
    if (!worker) {
      const audioBuffer = decodeWavPcm(audioContext, buffer);
      if (!audioBuffer) return { audioBuffer: null, analysis: null };
      const analysis = detectAudioIssues(audioBuffer);
      return { audioBuffer, analysis };
    }

    const id = nextIdRef.current++;
    try {
      const bufferCopy = buffer.slice(0);
      const response = await sendToWorker<{
        type: string; id: number;
        decode: DecodedWavResult | null;
        analysis: AudioAnalysisResult | null;
      }>({ type: 'decode-and-analyze', id, buffer: bufferCopy }, [bufferCopy]);

      if (!response.decode) return { audioBuffer: null, analysis: null };

      const { channelData, sampleRate, channels, totalFrames } = response.decode;
      const audioBuffer = audioContext.createBuffer(channels, totalFrames, sampleRate);
      for (let ch = 0; ch < channels; ch++) {
        audioBuffer.copyToChannel(channelData[ch], ch);
      }
      return { audioBuffer, analysis: response.analysis };
    } catch (err) {
      console.warn('[useAudioWorker] decodeAndAnalyze worker failed, falling back:', err);
      const audioBuffer = decodeWavPcm(audioContext, buffer);
      if (!audioBuffer) return { audioBuffer: null, analysis: null };
      const analysis = detectAudioIssues(audioBuffer);
      return { audioBuffer, analysis };
    }
  }, [getWorker, sendToWorker]);

  const terminate = useCallback(() => {
    if (workerRef.current) {
      workerRef.current.terminate();
      workerRef.current = null;
      workerAvailableRef.current = null;
    }
    for (const [id, pending] of pendingRef.current) {
      pending.reject(new Error('Worker terminated'));
    }
    pendingRef.current.clear();
  }, []);

  const api = useMemo<AudioWorkerAPI>(() => ({
    decodeWav,
    analyzeAudio,
    decodeAndAnalyze,
    terminate,
  }), [decodeWav, analyzeAudio, decodeAndAnalyze, terminate]);

  return api;
}

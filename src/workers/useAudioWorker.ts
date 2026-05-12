import { useRef, useCallback } from 'react';
import type { DecodedWavResult, AudioAnalysisResult } from './audioWorker';
import { decodeWavPcm } from '../utils/wavParser';
import { detectAudioIssues } from '../utils/advancedAudioProcessing';

interface PendingRequest {
  resolve: (value: any) => void;
  reject: (reason: any) => void;
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
      const worker = new Worker(
        new URL('./audioWorker.ts', import.meta.url),
        { type: 'module' },
      );
      worker.onmessage = (e: MessageEvent) => {
        const { id } = e.data;
        const pending = pendingRef.current.get(id);
        if (pending) {
          pendingRef.current.delete(id);
          pending.resolve(e.data);
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
      return worker;
    } catch (err) {
      console.warn('[useAudioWorker] Worker creation failed, using main thread fallback:', err);
      workerAvailableRef.current = false;
      return null;
    }
  }, []);

  const sendToWorker = useCallback(<T>(msg: { type: string; id: number; [key: string]: any }, transfer?: Transferable[]): Promise<T> => {
    return new Promise((resolve, reject) => {
      const worker = getWorker();
      if (!worker) {
        reject(new Error('Worker not available'));
        return;
      }
      pendingRef.current.set(msg.id, { resolve, reject });
      if (transfer && transfer.length > 0) {
        worker.postMessage(msg, transfer);
      } else {
        worker.postMessage(msg);
      }
    });
  }, [getWorker]);

  const decodeWav = useCallback(async (audioContext: BaseAudioContext, buffer: ArrayBuffer): Promise<AudioBuffer | null> => {
    const worker = getWorker();
    if (!worker) {
      return decodeWavPcm(audioContext, buffer);
    }

    const id = nextIdRef.current++;
    try {
      const response = await sendToWorker<{ type: string; id: number; result: DecodedWavResult | null }>(
        { type: 'decode-wav', id, buffer },
        [buffer],
      );
      if (!response.result) return null;
      const { channelData, sampleRate, channels, totalFrames } = response.result;
      const audioBuffer = audioContext.createBuffer(channels, totalFrames, sampleRate);
      for (let ch = 0; ch < channels; ch++) {
        audioBuffer.copyToChannel(channelData[ch], ch);
      }
      return audioBuffer;
    } catch {
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
      const response = await sendToWorker<{
        type: string; id: number;
        decode: DecodedWavResult | null;
        analysis: AudioAnalysisResult | null;
      }>({ type: 'decode-and-analyze', id, buffer }, [buffer]);

      if (!response.decode) return { audioBuffer: null, analysis: null };

      const { channelData, sampleRate, channels, totalFrames } = response.decode;
      const audioBuffer = audioContext.createBuffer(channels, totalFrames, sampleRate);
      for (let ch = 0; ch < channels; ch++) {
        audioBuffer.copyToChannel(channelData[ch], ch);
      }
      return { audioBuffer, analysis: response.analysis };
    } catch {
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
    pendingRef.current.clear();
  }, []);

  return { decodeWav, analyzeAudio, decodeAndAnalyze, terminate };
}

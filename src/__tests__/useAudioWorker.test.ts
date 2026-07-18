import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAudioWorker } from '../workers/useAudioWorker';

// Mock Worker
class MockWorker {
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: ErrorEvent) => void) | null = null;
  terminated = false;

  constructor() {
    setTimeout(() => {
      if (this.onmessage) {
        this.onmessage(new MessageEvent('message', { data: { type: 'ready' } }));
      }
    }, 0);
  }

  postMessage(msg: unknown) {
    if (this.terminated) return;
    
    const data = msg as { type: string; id: number };
    
    setTimeout(() => {
      if (this.terminated) return;
      
      if (data.type === 'decode-wav') {
        if (this.onmessage) {
          this.onmessage(new MessageEvent('message', {
            data: {
              type: 'decode-wav-result',
              id: data.id,
              sampleRate: 44100,
              numberOfChannels: 2,
              length: 1000,
              channelData: [new Float32Array(1000), new Float32Array(1000)],
            },
          }));
        }
      } else if (data.type === 'analyze-audio') {
        if (this.onmessage) {
          this.onmessage(new MessageEvent('message', {
            data: {
              type: 'analyze-result',
              id: data.id,
              analysis: {
                rms: -20,
                peak: -3,
                sampleRate: 44100,
                duration: 1,
                spectralFlatness: 0.5,
                dynamicRange: 10,
                peakLevel: 0.7,
                stereoImbalance: 0.1,
              },
            },
          }));
        }
      }
    }, 10);
  }

  terminate() {
    this.terminated = true;
  }
}

vi.stubGlobal('Worker', MockWorker);

// Mock AudioContext
class MockAudioContext {
  sampleRate = 44100;
  
  createBuffer(channels: number, length: number, sampleRate: number) {
    return {
      numberOfChannels: channels,
      length,
      sampleRate,
      duration: length / sampleRate,
      getChannelData: (ch: number) => new Float32Array(length),
    };
  }
  
  decodeAudioData(buffer: ArrayBuffer) {
    const view = new DataView(buffer);
    const sampleRate = 44100;
    const length = Math.floor(buffer.byteLength / 4);
    return Promise.resolve({
      sampleRate,
      length,
      numberOfChannels: 1,
      duration: length / sampleRate,
      getChannelData: () => new Float32Array(length),
    });
  }
}

vi.stubGlobal('AudioContext', MockAudioContext);

describe('useAudioWorker - 引用稳定性', () => {
  it('返回对象引用在重渲染时保持稳定', () => {
    const { result, rerender } = renderHook(() => useAudioWorker());
    
    const firstResult = result.current;
    rerender();
    const secondResult = result.current;
    
    expect(firstResult).toBe(secondResult);
  });
  
  it('decodeWav 函数引用稳定', () => {
    const { result, rerender } = renderHook(() => useAudioWorker());
    
    const firstFn = result.current.decodeWav;
    rerender();
    const secondFn = result.current.decodeWav;
    
    expect(firstFn).toBe(secondFn);
  });
  
  it('analyzeAudio 函数引用稳定', () => {
    const { result, rerender } = renderHook(() => useAudioWorker());
    
    const firstFn = result.current.analyzeAudio;
    rerender();
    const secondFn = result.current.analyzeAudio;
    
    expect(firstFn).toBe(secondFn);
  });
  
  it('terminate 函数引用稳定', () => {
    const { result, rerender } = renderHook(() => useAudioWorker());
    
    const firstFn = result.current.terminate;
    rerender();
    const secondFn = result.current.terminate;
    
    expect(firstFn).toBe(secondFn);
  });
});

describe('useAudioWorker - terminate 清理', () => {
  it('terminate 会 reject 所有 pending Promise', async () => {
    const { result } = renderHook(() => useAudioWorker());
    
    const audioCtx = new (window.AudioContext as unknown as typeof MockAudioContext)();
    const buffer = new ArrayBuffer(1000);
    
    let caughtError: Error | null = null;
    const promise = result.current.decodeWav(audioCtx as unknown as BaseAudioContext, buffer)
      .catch((e) => {
        caughtError = e as Error;
      });
    
    await act(async () => {
      result.current.terminate();
    });
    
    await promise;
    
    expect(caughtError).not.toBeNull();
    expect(caughtError?.message).toContain('Worker terminated');
  });
  
  it('多次调用 terminate 安全', () => {
    const { result } = renderHook(() => useAudioWorker());
    
    expect(() => {
      result.current.terminate();
      result.current.terminate();
    }).not.toThrow();
  });
});

describe('useAudioWorker - 超时机制', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  
  afterEach(() => {
    vi.useRealTimers();
  });
  
  it('Worker 超时后 reject 并降级', async () => {
    class SlowWorker extends MockWorker {
      postMessage(msg: unknown) {
      }
    }
    vi.stubGlobal('Worker', SlowWorker);
    
    const { result } = renderHook(() => useAudioWorker());
    
    const audioCtx = new MockAudioContext();
    const buffer = new ArrayBuffer(1000);
    
    let resultValue: unknown = null;
    let error: Error | null = null;
    
    await act(async () => {
      const promise = result.current.decodeWav(audioCtx as unknown as BaseAudioContext, buffer)
        .then(r => { resultValue = r; })
        .catch(e => { error = e as Error; });
      
      vi.advanceTimersByTime(11000);
      
      await promise.catch(() => {});
    });
    
    vi.stubGlobal('Worker', MockWorker);
    
    expect(error).not.toBeNull();
    expect(error?.message).toContain('timeout');
  });
});

describe('useAudioWorker - fallback 机制', () => {
  it('Worker 失败时回退到主线程解码', async () => {
    class FailingWorker extends MockWorker {
      postMessage(msg: unknown) {
        setTimeout(() => {
          if (this.onerror) {
            this.onerror(new ErrorEvent('error', { message: 'Worker error' }));
          }
        }, 5);
      }
    }
    vi.stubGlobal('Worker', FailingWorker);
    
    const { result } = renderHook(() => useAudioWorker());
    
    const audioCtx = new MockAudioContext();
    const wavBuffer = createWavBuffer(1000, 44100, 1);
    
    const decoded = await result.current.decodeWav(
      audioCtx as unknown as BaseAudioContext,
      wavBuffer
    );
    
    vi.stubGlobal('Worker', MockWorker);
    
    expect(decoded).not.toBeNull();
  });
});

function createWavBuffer(sampleCount: number, sampleRate: number, channels: number): ArrayBuffer {
  const dataSize = sampleCount * channels * 2;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  
  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };
  
  writeString(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, channels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * channels * 2, true);
  view.setUint16(32, channels * 2, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, dataSize, true);
  
  return buffer;
}

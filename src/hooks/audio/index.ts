import { useCallback, useEffect } from 'react';
import { loadSettings, saveSettings, resetSettings as resetStoredSettings, saveProfileToStorage } from '../../utils/settingsStorage';
import { useRepairSessionStore } from '../../store/repairSessionStore';
import { parseWavHeader } from '../../utils/wavParser';
import { saveSession, loadSession, clearSession } from '../../utils/sessionDB';
import { getPreviewUrl, downloadWithProgress, fetchAlgorithmVersions, ProcessingOptions } from '../../services/backendApi';
import { AIRepairParams, RepairMode, defaultAIRepairParams } from '../../utils/advancedAudioProcessing';
import { WavInfo } from '../../utils/wavParser';
import { useAudioCore } from './useAudioCore';
import { useAudioPlayback } from './useAudioPlayback';
import { useAudioDecoder } from './useAudioDecoder';
import { useAudioExport } from './useAudioExport';
import { useAudioRepair } from './useAudioRepair';
import { writeLog, createValidWavBlob } from './utils';
export type { AudioAnalysis, PlayMode, ProcessingOptions } from './types';
export { defaultProcessingOptions } from './types';
export { generateExportFilename } from './utils';

export function useAudioProcessor() {
  const { audioWorker, state, refs, setTaskId, setWavInfo } = useAudioCore();

  const playback = useAudioPlayback({ state, refs });
  const audioExport = useAudioExport({ state, refs });

  const decoder = useAudioDecoder({
    state,
    refs,
    audioWorker,
    setTaskId,
    setWavInfo,
    stopPlaying: playback.stopPlaying,
    closeWS: () => {
      if (refs.wsControlRef.current) {
        refs.wsControlRef.current.close();
        refs.wsControlRef.current = null;
      }
    },
    play: playback.play,
    getAudioContext: playback.getAudioContext,
  });

  const repair = useAudioRepair({
    state,
    refs,
    setTaskId,
    _setWavInfo: setWavInfo,
    loadAudioFromUrl: decoder.loadAudioFromUrl,
    renderAndDownload: audioExport.renderAndDownload,
  });

  const applyRepairMode = useCallback((mode: RepairMode) => {
    state.setSelectedMode(mode.name);
    state.setParams(mode.params);
  }, [state]);

  const updateParam = useCallback((key: keyof AIRepairParams, value: number) => {
    refs.userEditingParamRef.current = true;
    state.setParams(prev => ({ ...prev, [key]: value }));
  }, [refs.userEditingParamRef, state]);

  useEffect(() => {
    if (!refs.userEditingParamRef.current) return;
    refs.userEditingParamRef.current = false;
    if (state.repairModes.length === 0) return;
    const matched = state.repairModes.find(m => {
      return (Object.keys(m.params) as (keyof AIRepairParams)[]).every(
        k => m.params[k] === state.params[k]
      );
    });
    state.setSelectedMode(matched ? matched.name : '');
  }, [state.params, state.repairModes, refs.userEditingParamRef, state]);

  const updateProcessingOptions = useCallback((options: Partial<ProcessingOptions>) => {
    state.setProcessingOptionsState(prev => ({ ...prev, ...options }));
  }, [state]);

  const resetParams = useCallback(() => {
    state.setParams(defaultAIRepairParams);
    state.setSelectedMode('全面修复');
    resetStoredSettings();
  }, [state]);

  const getSavedProfiles = useCallback((): import('../../utils/settingsStorage').ProfileConfig[] => {
    const settings = loadSettings();
    return settings.savedProfiles || [];
  }, []);

  const saveProfile = useCallback((name: string) => {
    saveProfileToStorage(name, state.params, state.algorithmVersion);
  }, [state.params, state.algorithmVersion]);

  const applyProfile = useCallback((id: string) => {
    const settings = loadSettings();
    const profile = (settings.savedProfiles || []).find(p => p.id === id);
    if (!profile) return;
    state.setParams(profile.params);
    state.setAlgorithmVersionState(profile.algorithmVersion);
    state.setSelectedMode('');
  }, [state]);

  const deleteProfile = useCallback((id: string) => {
    const settings = loadSettings();
    const updated = (settings.savedProfiles || []).filter(p => p.id !== id);
    saveSettings({ savedProfiles: updated });
  }, []);

  const renameProfile = useCallback((id: string, newName: string) => {
    const settings = loadSettings();
    const updated = (settings.savedProfiles || []).map(p =>
      p.id === id ? { ...p, name: newName } : p
    );
    saveSettings({ savedProfiles: updated });
  }, []);

  const clearBackendError = useCallback(() => state.setBackendError(null), [state]);

  const runBackendDiag = useCallback(async () => {
    const lines: string[] = [];
    lines.push(`时间: ${new Date().toLocaleTimeString()}`);
    lines.push(`页面URL: ${window.location.href}`);
    lines.push(`hostname: ${window.location.hostname}`);
    lines.push(`protocol: ${window.location.protocol}`);

    lines.push('');
    lines.push('--- /health 测试 ---');
    try {
      const t0 = performance.now();
      const res = await fetch('/health', { signal: AbortSignal.timeout(5000) });
      const t1 = performance.now();
      const text = await res.text();
      lines.push(`状态: ${res.status} ${res.statusText}`);
      lines.push(`耗时: ${Math.round(t1 - t0)}ms`);
      lines.push(`响应: ${text.substring(0, 200)}`);
    } catch (e: unknown) {
      lines.push(`失败: ${e instanceof Error ? e.message : String(e)}`);
    }

    lines.push('');
    lines.push('--- /api/v1/upload 测试(有效WAV) ---');
    try {
      const wavBlob = createValidWavBlob(1, 44100, 0.5);
      const file = new File([wavBlob], 'diag.wav', { type: 'audio/wav' });
      const form = new FormData();
      form.append('file', file);
      const t0 = performance.now();
      const res = await fetch('/api/v1/upload', { method: 'POST', body: form, signal: AbortSignal.timeout(5000) });
      const t1 = performance.now();
      const text = await res.text();
      lines.push(`状态: ${res.status} ${res.statusText}`);
      lines.push(`耗时: ${Math.round(t1 - t0)}ms`);
      lines.push(`响应: ${text.substring(0, 200)}`);
    } catch (e: unknown) {
      lines.push(`失败: ${e instanceof Error ? e.message : String(e)}`);
    }

    lines.push('');
    lines.push('--- 完整流程测试: 上传→检测→轮询(有效WAV) ---');
    try {
      const wavBlob = createValidWavBlob(1, 44100, 0.5);
      const file = new File([wavBlob], 'diag.wav', { type: 'audio/wav' });
      const form = new FormData();
      form.append('file', file);
      const uploadRes = await fetch('/api/v1/upload', { method: 'POST', body: form, signal: AbortSignal.timeout(10000) });
      const uploadData = await uploadRes.json();
      lines.push(`上传: status=${uploadRes.status} task_id=${uploadData.task_id}`);

      if (uploadData.task_id) {
        const detectRes = await fetch('/api/v1/detect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_id: uploadData.task_id, type: 'original' }),
          signal: AbortSignal.timeout(5000),
        });
        const detectData = await detectRes.json();
        lines.push(`检测提交: status=${detectRes.status} msg=${detectData.message || detectData.detail}`);

        lines.push('轮询状态(最多30次, 每2秒):');
        for (let i = 0; i < 30; i++) {
          await new Promise(r => setTimeout(r, 2000));
          try {
            const statusRes = await fetch(`/api/v1/status/${uploadData.task_id}`, { signal: AbortSignal.timeout(5000) });
            const statusData = await statusRes.json();
            lines.push(`  [${i+1}] status=${statusData.status} progress=${statusData.progress?.toFixed?.(2) ?? statusData.progress} step=${statusData.step} err=${statusData.error || 'none'}`);
            if (['completed', 'detected', 'error'].includes(statusData.status)) break;
          } catch (e: unknown) {
            lines.push(`  [${i+1}] 轮询失败: ${e instanceof Error ? e.message : String(e)}`);
            break;
          }
        }
      }
    } catch (e: unknown) {
      lines.push(`完整流程失败: ${e instanceof Error ? e.message : String(e)}`);
    }

    const diagText = lines.join('\n');
    state.setBackendDiag(diagText);
    writeLog('[BackendDiag]\n' + diagText);

    const hasHealthOk = lines.some(l => l.includes('"status":"ok"'));
    const has200 = lines.some(l => l.includes('状态: 200'));
    state.setBackendAvailable(hasHealthOk && has200);
    return diagText;
  }, [state]);

  useEffect(() => {
    saveSettings({
      aiRepairParams: state.params,
      exportOptions: state.processingOptions,
      stemSettings: {
        vocalGain: 0,
        instrumentalGain: 0,
        vocalBalance: 0,
      },
      selectedMode: state.selectedMode,
      algorithmVersion: state.algorithmVersion,
    });
  }, [state.params, state.processingOptions, state.selectedMode, state.algorithmVersion]);

  useEffect(() => {
    fetch('/health', { signal: AbortSignal.timeout(5000) })
      .then(res => {
        state.setBackendAvailable(res.ok);
        writeLog(`[useAudioProcessor] 初始健康检查: ${res.ok ? '后端可用' : '后端不可用'}`);
        if (res.ok) {
          fetchAlgorithmVersions().then(versions => {
            if (versions.length > 0) {
              state.setAvailableAlgorithms(versions);
              const current = versions.find(v => v.name === state.algorithmVersion);
              if (current && state.algorithmVersion) {
                if (current.modes && current.modes.length > 0) {
                  const modes: RepairMode[] = current.modes.map(m => ({
                    name: m.name,
                    description: m.description,
                    icon: m.icon,
                    params: { ...defaultAIRepairParams, ...m.params } as AIRepairParams,
                  }));
                  state.setRepairModes(modes);
                  state.setSelectedMode(modes[0].name);
                }
                refs.versionInitializedRef.current = true;
                writeLog(`[useAudioProcessor] 版本 ${current.name} 可用，已加载模式`);
              } else {
                const latestVersion = versions[0];
                writeLog(`[useAudioProcessor] 当前版本 '${state.algorithmVersion}' 无效或未设置，自动选择最新: ${latestVersion.name}`);
                state.setAlgorithmVersionState(latestVersion.name);
                saveSettings({ algorithmVersion: latestVersion.name });
                if (latestVersion.modes && latestVersion.modes.length > 0) {
                  const modes: RepairMode[] = latestVersion.modes.map(m => ({
                    name: m.name,
                    description: m.description,
                    icon: m.icon,
                    params: { ...defaultAIRepairParams, ...m.params } as AIRepairParams,
                  }));
                  state.setRepairModes(modes);
                  state.setSelectedMode(modes[0].name);
                }
                refs.versionInitializedRef.current = true;
              }
            }
          });
        }
      })
      .catch(() => {
        state.setBackendAvailable(false);
        writeLog('[useAudioProcessor] 初始健康检查: 后端不可用(请求失败)');
      });
  }, []);

  useEffect(() => {
    if (state.availableAlgorithms.length > 0 && !refs.versionInitializedRef.current) {
      const current = state.availableAlgorithms.find(v => v.name === state.algorithmVersion);
      if (current) {
        if (current.modes && current.modes.length > 0) {
          const modes: RepairMode[] = current.modes.map(m => ({
            name: m.name,
            description: m.description,
            icon: m.icon,
            params: { ...defaultAIRepairParams, ...m.params } as AIRepairParams,
          }));
          state.setRepairModes(modes);
          state.setSelectedMode(modes[0].name);
        }
        refs.versionInitializedRef.current = true;
        writeLog(`[useAudioProcessor] 版本 ${current.name} 可用，已加载模式`);
      } else {
        const defaultVersion = state.availableAlgorithms[0];
        writeLog(`[useAudioProcessor] 当前版本 ${state.algorithmVersion} 不可用，自动切换到 ${defaultVersion.name}`);
        state.setAlgorithmVersionState(defaultVersion.name);
        if (defaultVersion.modes && defaultVersion.modes.length > 0) {
          const modes: RepairMode[] = defaultVersion.modes.map(m => ({
            name: m.name,
            description: m.description,
            icon: m.icon,
            params: { ...defaultAIRepairParams, ...m.params } as AIRepairParams,
          }));
          state.setRepairModes(modes);
          state.setSelectedMode(modes[0].name);
        }
        refs.versionInitializedRef.current = true;
      }
    }
  }, [state.availableAlgorithms, state.algorithmVersion, state, refs]);

  const backendAvailableRef = refs.backendAvailableRef;
  const healthFailCountRef = refs.healthFailCountRef;

  useEffect(() => {
    backendAvailableRef.current = state.backendAvailable;
  }, [state.backendAvailable, backendAvailableRef]);

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch('/health', { signal: AbortSignal.timeout(15000) });
        const wasAvailable = backendAvailableRef.current;
        const isAvailable = res.ok;

        if (isAvailable) {
          healthFailCountRef.current = 0;
          state.setBackendAvailable(true);
          if (!wasAvailable) {
            writeLog('[useAudioProcessor] 后端恢复可用');
            fetchAlgorithmVersions().then(versions => {
              if (versions.length > 0) {
                state.setAvailableAlgorithms(versions);
                const current = versions.find(v => v.name === state.algorithmVersion) || versions[0];
                if (current.modes && current.modes.length > 0) {
                  const modes: RepairMode[] = current.modes.map(m => ({
                    name: m.name,
                    description: m.description,
                    icon: m.icon,
                    params: { ...defaultAIRepairParams, ...m.params } as AIRepairParams,
                  }));
                  state.setRepairModes(modes);
                  state.setSelectedMode(modes[0].name);
                }
              }
            });
          }
        } else {
          healthFailCountRef.current++;
          if (backendAvailableRef.current && healthFailCountRef.current >= 3) {
            console.warn('[useAudioProcessor] 后端健康检查连续3次失败，标记为不可用');
            state.setBackendAvailable(false);
            healthFailCountRef.current = 0;
          }
        }
      } catch {
        healthFailCountRef.current++;
        if (backendAvailableRef.current && healthFailCountRef.current >= 3) {
          console.warn('[useAudioProcessor] 后端健康检查连续3次失败，标记为不可用');
          state.setBackendAvailable(false);
          healthFailCountRef.current = 0;
        }
      }
    };

    checkHealth();

    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    return () => {
      repair.closeWS();
      audioWorker.terminate();
    };
  }, [repair, audioWorker]);

  useEffect(() => {
    if (refs.sessionRestoredRef.current || !state.backendAvailable) return;

    const sessionStore = useRepairSessionStore.getState();
    if (sessionStore.isDualTrackMode) {
      writeLog('[useAudioProcessor] 双轨模式，跳过单轨会话恢复');
      refs.sessionRestoredRef.current = true;
      return;
    }

    const seq = ++refs.restoreSeqRef.current;

    (async () => {
      try {
        if (!refs.pendingSessionRef.current) {
          const session = await loadSession();
          if (seq !== refs.restoreSeqRef.current) return;

          if (!session || !session.taskId) {
            refs.sessionRestoredRef.current = true;
            return;
          }

          writeLog(`[useAudioProcessor] 发现保存的会话: file=${session.fileName} taskId=${session.taskId} hasFile=${!!session.file} fileSize=${session.file?.size ?? 0}`);

          refs.pendingSessionRef.current = {
            file: session.file,
            fileName: session.fileName,
            fileHash: session.fileHash || '',
            taskId: session.taskId,
            hasBeenProcessed: session.hasBeenProcessed,
            wavInfo: session.wavInfo,
            repairResult: session.repairResult,
            processingOptions: session.processingOptions,
          };
        }

        const session = refs.pendingSessionRef.current;

        if (state.audioFile) {
          writeLog(`[useAudioProcessor] 用户已加载文件 ${state.audioFile.name}，跳过旧会话恢复`);
          refs.pendingSessionRef.current = null;
          refs.sessionRestoredRef.current = true;
          return;
        }

        let taskExists = true;
        let taskStatus: { status: string; [k: string]: unknown } | null = null;
        try {
          const statusRes = await fetch(`/api/v1/status/${session.taskId}`);
          if (seq !== refs.restoreSeqRef.current) return;

          if (!statusRes.ok) {
            writeLog(`[useAudioProcessor] 任务不存在 taskId=${session.taskId} (HTTP ${statusRes.status})，清除会话`);
            taskExists = false;
          } else {
            taskStatus = await statusRes.json();
            if (seq !== refs.restoreSeqRef.current) return;
            if (taskStatus.status === 'error') {
              writeLog(`[useAudioProcessor] 任务已出错，清除会话`);
              taskExists = false;
            }
          }
        } catch (netErr) {
          if (seq !== refs.restoreSeqRef.current) return;
          writeLog(`[useAudioProcessor] 任务状态检查网络错误: ${netErr instanceof Error ? netErr.message : String(netErr)}，跳过恢复（不清除会话）`);
          refs.pendingSessionRef.current = null;
          refs.sessionRestoredRef.current = true;
          return;
        }

        if (!taskExists) {
          await clearSession();
          refs.pendingSessionRef.current = null;
          refs.sessionRestoredRef.current = true;
          return;
        }

        writeLog(`[useAudioProcessor] 恢复会话: taskId=${session.taskId} status=${taskStatus!.status}`);

        let arrayBuf: ArrayBuffer | null = null;
        let restoredFile: File | null = null;

        try {
          const originalUrl = getPreviewUrl(session.taskId, 'original');
          arrayBuf = await downloadWithProgress(originalUrl);
          if (seq !== refs.restoreSeqRef.current) return;
          if (arrayBuf.byteLength === 0) throw new Error('下载的原始音频为空');
          restoredFile = new File([arrayBuf], session.fileName || 'audio.wav', { type: 'audio/wav' });
          writeLog(`[useAudioProcessor] 从后端下载原始音频成功: ${arrayBuf.byteLength} bytes`);
        } catch (dlErr) {
          if (seq !== refs.restoreSeqRef.current) return;
          writeLog(`[useAudioProcessor] 后端下载失败: ${dlErr instanceof Error ? dlErr.message : String(dlErr)}，尝试 IndexedDB File 回退`);
          arrayBuf = null;
        }

        if (!arrayBuf && session.file && session.file.size > 0) {
          try {
            arrayBuf = await session.file.arrayBuffer();
            if (seq !== refs.restoreSeqRef.current) return;
            if (arrayBuf.byteLength === 0) throw new Error('arrayBuffer 为空');
            restoredFile = session.file instanceof File
              ? session.file
              : new File([arrayBuf], session.fileName || 'audio.wav', { type: 'audio/wav' });
            writeLog(`[useAudioProcessor] IndexedDB File 回退成功: ${arrayBuf.byteLength} bytes`);
          } catch (fileErr) {
            if (seq !== refs.restoreSeqRef.current) return;
            writeLog(`[useAudioProcessor] IndexedDB File 也失败: ${fileErr instanceof Error ? fileErr.message : String(fileErr)}`);
            arrayBuf = null;
          }
        }

        if (!arrayBuf) {
          writeLog(`[useAudioProcessor] 无法获取音频数据，跳过恢复（不清除会话，下次刷新可重试）`);
          refs.pendingSessionRef.current = null;
          refs.sessionRestoredRef.current = true;
          return;
        }

        state.setAudioFile(restoredFile);
        refs.fileHashRef.current = session.fileHash;

        const context = playback.getAudioContext();
        const wavHeaderInfo = parseWavHeader(arrayBuf.slice(0, 44 + 4096));
        setWavInfo(wavHeaderInfo);
        if (!wavHeaderInfo && session.fileHash) {
          try {
            const infoRes = await fetch(`/api/v1/audio-info/${session.fileHash}`);
            if (seq !== refs.restoreSeqRef.current) return;
            if (infoRes.ok) {
              const ai = await infoRes.json();
              if (seq !== refs.restoreSeqRef.current) return;
              const infoFromApi: WavInfo = {
                sampleRate: ai.sample_rate,
                channels: ai.channels,
                duration: ai.duration,
                bitDepth: ai.sample_width * 8,
              };
              setWavInfo(infoFromApi);
            }
          } catch {}
        }
        const { audioBuffer: workerBuffer, analysis: workerAnalysis } = await audioWorker.decodeAndAnalyze(context, arrayBuf);
        if (seq !== refs.restoreSeqRef.current) return;
        const buffer = workerBuffer || await context.decodeAudioData(arrayBuf);
        if (seq !== refs.restoreSeqRef.current) return;

        state.setAudioBuffer(buffer);
        state.setDuration(buffer.duration);
        refs.durationRef.current = buffer.duration;
        state.setCurrentTime(0);
        refs.pausedAtRef.current = 0;

        if (workerAnalysis) state.setAudioAnalysis(workerAnalysis);

        setTaskId(session.taskId);
        refs.taskIdRef.current = session.taskId;

        if (session.hasBeenProcessed && taskStatus!.status === 'completed') {
          try {
            const previewUrl = getPreviewUrl(session.taskId, 'repaired');
            const repairedBuffer = await downloadWithProgress(previewUrl);
            if (seq !== refs.restoreSeqRef.current) return;
            const tempContext = new OfflineAudioContext(1, 1, state.processingOptions.sampleRate);
            const decoded = await tempContext.decodeAudioData(repairedBuffer);
            refs.backendProcessedBufferRef.current = decoded;
            state.setBackendProcessedBuffer(decoded);
            state.setHasBeenProcessed(true);
            state.setPlayMode('backend');
          } catch (e) {
            console.warn('[useAudioProcessor] 恢复修复后音频失败:', e);
          }
        }

        if (session.repairResult) {
          try { state.setRepairResult(JSON.parse(session.repairResult)); } catch {}
        }
        if (session.processingOptions) {
          try {
            const restoredOpts = JSON.parse(session.processingOptions);
            if (restoredOpts.sampleRate && restoredOpts.bitDepth) {
              state.setProcessingOptionsState(prev => ({ ...prev, ...restoredOpts }));
            }
          } catch {}
        }

        if (restoredFile) {
          saveSession({
            file: restoredFile,
            fileName: session.fileName,
            fileSize: restoredFile.size,
            fileHash: session.fileHash,
            taskId: session.taskId,
            backendAvailable: true,
            hasBeenProcessed: session.hasBeenProcessed,
            wavInfo: refs.wavInfoRef.current ? JSON.stringify(refs.wavInfoRef.current) : '',
            repairResult: session.repairResult || '',
            processingOptions: session.processingOptions || JSON.stringify(refs.processingOptionsRef.current),
          });
        }

        refs.sessionRestoredRef.current = true;
        refs.pendingSessionRef.current = null;
        writeLog(`[useAudioProcessor] 会话恢复完成 seq=${seq}`);
      } catch (e) {
        if (seq !== refs.restoreSeqRef.current) return;
        console.warn('[useAudioProcessor] 会话恢复失败（不清除会话，下次刷新可重试）:', e);
        refs.pendingSessionRef.current = null;
        refs.sessionRestoredRef.current = true;
      }
    })();
  }, [state.backendAvailable, playback, audioWorker, state, refs, setTaskId, setWavInfo]);

  useEffect(() => {
    return () => {
      playback.stopPlaying();
    };
  }, [playback]);

  const originalSampleRate = state.audioBuffer?.sampleRate ?? 0;
  const currentSampleRate = (() => {
    if (state.playMode === 'backend' && state.backendProcessedBuffer) return state.backendProcessedBuffer.sampleRate;
    return originalSampleRate;
  })();

  return {
    audioFile: state.audioFile,
    fileHash: state.fileHash,
    audioBuffer: state.audioBuffer,
    backendProcessedBuffer: state.backendProcessedBuffer,
    backendPreviewUrl: state.backendPreviewUrl,
    isPlaying: state.isPlaying,
    currentTime: state.currentTime,
    duration: state.duration,
    isProcessing: state.isProcessing,
    isDecodingAudio: state.isDecodingAudio,
    processingProgress: state.processingProgress,
    processingStep: state.processingStep,
    processingSource: state.processingSource,
    setProcessingSource: state.setProcessingSource,
    params: state.params,
    audioAnalysis: state.audioAnalysis,
    selectedMode: state.selectedMode,
    playMode: state.playMode,
    repairModes: state.repairModes,
    processingOptions: state.processingOptions,
    hasBeenProcessed: state.hasBeenProcessed,
    originalSampleRate,
    currentSampleRate,
    backendAvailable: state.backendAvailable,
    backendDiag: state.backendDiag,
    runBackendDiag,
    wavInfo: state.wavInfo,
    repairResult: state.repairResult,
    backendWaveformPeaks: state.backendWaveformPeaks,
    algorithmVersion: state.algorithmVersion,
    availableAlgorithms: state.availableAlgorithms,
    applyAlgorithmVersion: repair.applyAlgorithmVersion,
    isTaskStuck: state.isTaskStuck,
    stuckInfo: state.stuckInfo,
    queueStatus: state.queueStatus,
    resetStuckState: repair.resetStuckState,
    cancelCurrentTask: repair.cancelCurrentTask,
    backendError: state.backendError,
    clearBackendError,
    loadAudioFile: decoder.loadAudioFile,
    play: playback.play,
    pause: playback.pause,
    seek: playback.seek,
    updateParam,
    resetParams,
    applyRepairMode,
    applySettings: repair.applySettings,
    switchPlayMode: playback.switchPlayMode,
    setProcessingOptions: updateProcessingOptions,
    getSavedProfiles,
    saveProfile,
    applyProfile,
    deleteProfile,
    renameProfile,
    analyserRef: refs.analyserRef,
    isRenderLoading: state.isRenderLoading,
    taskId: state.taskId,
    renderAndDownload: audioExport.renderAndDownload,
    renderDownloadUrl: state.renderDownloadUrl,
    setRenderDownloadUrl: state.setRenderDownloadUrl,
    showDownloadModal: state.showDownloadModal,
    setShowDownloadModal: state.setShowDownloadModal,
    autoRenderInfo: state.autoRenderInfo,
    showRepairCacheModal: state.showRepairCacheModal,
    setShowRepairCacheModal: state.setShowRepairCacheModal,
    cacheHitInfo: state.cacheHitInfo,
    handleUseRepairCache: repair.handleUseRepairCache,
    handleRenderCacheDownload: repair.handleRenderCacheDownload,
    handleReRepair: repair.handleReRepair,
    handleCloseRepairCacheModal: repair.handleCloseRepairCacheModal,
    originalWaveformPeaks: state.originalWaveformPeaks,
    setIsProcessing: state.setIsProcessing,
    setProcessingStep: state.setProcessingStep,
    setProcessingProgress: state.setProcessingProgress,
    setBackendError: state.setBackendError,
    setHasBeenProcessed: state.setHasBeenProcessed,
    setRepairResult: state.setRepairResult,
    setBackendProcessedBuffer: state.setBackendProcessedBuffer,
    setBackendWaveformPeaks: state.setBackendWaveformPeaks,
    loadAudioFromUrl: decoder.loadAudioFromUrl,
    setTaskId,
    setIsTaskStuck: state.setIsTaskStuck,
    setStuckInfo: state.setStuckInfo,
    setQueueStatus: state.setQueueStatus,
  };
}

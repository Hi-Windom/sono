import { useCallback, useMemo } from 'react';
import {
  uploadAudio,
  repairAudio,
  connectProgressWS,
  getPreviewUrl,
  cancelTask,
  mapParamsToBackend,
  lookupRepairCache,
  fetchRenderCache,
  RenderCacheEntry,
  ProcessingOptions,
} from '../../services/backendApi';
import { useRepairSessionStore } from '../../store/repairSessionStore';
import { saveSession } from '../../utils/sessionDB';
import { AIRepairParams, RepairMode, defaultAIRepairParams } from '../../utils/advancedAudioProcessing';
import { writeLog, formatBytes, formatSpeed } from './utils';
import type { AudioCoreState, AudioCoreRefs } from './useAudioCore';
import type { RenderResult } from './useAudioExport';
import { useToast } from '../../components/Toast';

interface UseAudioRepairOptions {
  state: AudioCoreState;
  refs: AudioCoreRefs;
  setTaskId: (id: string | null) => void;
  _setWavInfo: (info: import('../../utils/wavParser').WavInfo | null) => void;
  loadAudioFromUrl: (url: string, targetSampleRate?: number, silent?: boolean) => Promise<AudioBuffer>;
  renderAndDownload: (overrideOptions?: ProcessingOptions, overrideAlgoVersion?: string) => Promise<RenderResult | null>;
}

export function useAudioRepair({
  state,
  refs,
  setTaskId,
  loadAudioFromUrl,
  renderAndDownload,
}: UseAudioRepairOptions) {
  const toast = useToast();
  const {
    audioFile,
    audioBuffer,
    params,
    setParams,
    processingOptions,
    setHasBeenProcessed,
    setIsProcessing,
    setProcessingProgress,
    setProcessingStep,
    setProcessingSource,
    setBackendError,
    setBackendAvailable,
    setBackendPreviewUrl,
    setRepairResult,
    setBackendWaveformPeaks,
    setCacheHitInfo,
    setShowRepairCacheModal,
    setRenderDownloadUrl,
    setShowDownloadModal,
    setAutoRenderInfo,
    algorithmVersion,
    setAlgorithmVersionState,
    availableAlgorithms,
    setRepairModes,
    setSelectedMode,
    setIsTaskStuck,
    setStuckInfo,
    setQueueStatus,
  } = state;

  const {
    taskIdRef,
    wsControlRef,
    fileHashRef,
    forceReRepairRef,
    forceRenderRef,
    renderActiveRef,
    processingOptionsRef,
    wavInfoRef,
    backendProcessedBufferRef,
  } = refs;

  const applyAlgorithmVersion = useCallback((version: string) => {
    setAlgorithmVersionState(version);
    setRenderDownloadUrl(null);
    setCacheHitInfo(null);
    setShowRepairCacheModal(false);
    setShowDownloadModal(false);
    setAutoRenderInfo(null);
    state.setBackendProcessedBuffer(null);
    setRepairResult(null);
    setHasBeenProcessed(false);
    setBackendPreviewUrl(null);
    setBackendWaveformPeaks(null);
    const algoInfo = availableAlgorithms.find(a => a.name === version);
    if (!algoInfo) return;

    if (algoInfo.defaultParams) {
      setParams(prev => ({ ...prev, ...algoInfo.defaultParams }));
    }
    if (algoInfo.modes && algoInfo.modes.length > 0) {
      const modes: RepairMode[] = algoInfo.modes.map(m => ({
        name: m.name,
        description: m.description,
        icon: m.icon,
        params: { ...defaultAIRepairParams, ...m.params } as AIRepairParams,
      }));
      setRepairModes(modes);
      setSelectedMode(modes[0].name);
    }
  }, [availableAlgorithms, setAlgorithmVersionState, setRenderDownloadUrl, setCacheHitInfo, setShowRepairCacheModal, setShowDownloadModal, setAutoRenderInfo, state, setRepairResult, setHasBeenProcessed, setBackendPreviewUrl, setBackendWaveformPeaks, setParams, setRepairModes, setSelectedMode]);

  const closeWS = useCallback(() => {
    if (wsControlRef.current) {
      wsControlRef.current.close();
      wsControlRef.current = null;
    }
  }, [wsControlRef]);

  const applySettings = useCallback(async () => {
    if (!audioBuffer) {
      console.warn('[applySettings] audioBuffer 为空，无法开始修复');
      toast.warning('请先上传音频文件');
      return;
    }

    setIsProcessing(true);
    setProcessingProgress(0);
    const REPAIR_TERMINALS = new Set(['completed', 'error']);
    let currentTaskId = taskIdRef.current;
    const backendProg = { value: 0 };

    writeLog(`[applySettings] ===== 开始修复流程 =====`);
    writeLog(`[applySettings] 初始状态: currentTaskId=${currentTaskId}, fileHash=${fileHashRef.current || 'none'}`);

    let effectiveAlgorithmVersion = algorithmVersion;
    if (availableAlgorithms.length > 0) {
      const current = availableAlgorithms.find(v => v.name === algorithmVersion);
      if (!current) {
        effectiveAlgorithmVersion = availableAlgorithms[0].name;
        writeLog(`[applySettings] 当前版本 ${algorithmVersion} 不可用，使用有效版本 ${effectiveAlgorithmVersion}`);
        setAlgorithmVersionState(effectiveAlgorithmVersion);
      }
    }

    const currentParamsForCache = mapParamsToBackend(params, processingOptions, effectiveAlgorithmVersion);

    if (fileHashRef.current && !forceReRepairRef.current) {
      writeLog(`[applySettings] 查询缓存: hash=${fileHashRef.current}`);
      try {
        const cacheResult = await lookupRepairCache(fileHashRef.current, currentParamsForCache);
        if (cacheResult.found) {
          writeLog(`[applySettings] ✅ 修复缓存命中 taskId=${cacheResult.task_id}`);
          setIsProcessing(false);
          setCacheHitInfo({
            repair: {
              task_id: cacheResult.task_id || '',
              output_size: cacheResult.output_size || 0,
              repair_result: cacheResult.repair_result || undefined,
              detection_result: cacheResult.detection_result,
              repaired_detection_result: cacheResult.repaired_detection_result,
            },
            renderCaches: [],
          });
          let renderCaches: RenderCacheEntry[] = [];
          const cachedTaskId = cacheResult.task_id;
          if (cachedTaskId) {
            try {
              renderCaches = await fetchRenderCache(cachedTaskId);
              writeLog(`[applySettings] 渲染缓存: ${renderCaches.length} 个命中`);
            } catch {
              writeLog(`[applySettings] 渲染缓存查询失败`);
            }
          }
          setCacheHitInfo(prev => prev ? { ...prev, renderCaches } : null);
          setShowRepairCacheModal(true);
          return;
        } else {
          writeLog(`[applySettings] 缓存未命中`);
        }
      } catch (cacheErr) {
        writeLog(`[applySettings] 缓存查询失败: ${cacheErr instanceof Error ? cacheErr.message : String(cacheErr)}`);
      }
    }
    if (forceReRepairRef.current) {
      forceReRepairRef.current = false;
    }

    writeLog(`[applySettings] 进入正常修复流程`);

    if (!currentTaskId) {
      if (!audioFile) {
        writeLog(`[applySettings] 没有音频文件，无法创建任务`);
        console.warn('[applySettings] audioFile 为空，无法创建任务');
        toast.error('请先上传音频文件');
        setIsProcessing(false);
        return;
      }

      setProcessingStep('上传到后端...');
      setProcessingProgress(0.01);
      let uploadRes;
      try {
        uploadRes = await uploadAudio(audioFile, (loaded, total, speed) => {
          const pct = total > 0 ? loaded / total : 0;
          setProcessingProgress(0.01 + pct * 0.09);
          setProcessingStep(`上传中 ${formatBytes(loaded)}/${formatBytes(total)} ${formatSpeed(speed)}`);
        }, fileHashRef.current || undefined);
      } catch (uploadErr) {
        const msg = uploadErr instanceof Error ? uploadErr.message : String(uploadErr);
        console.warn('[applySettings] 上传失败:', msg);
        writeLog(`[applySettings] 上传失败: ${msg}`);
        setBackendError('上传失败: ' + msg);
        setProcessingStep('[上传失败] ' + msg);
        setIsProcessing(false);
        toast.error(`上传失败: ${msg}`);
        return;
      }
      currentTaskId = uploadRes.task_id;
      setTaskId(currentTaskId);
      taskIdRef.current = currentTaskId;
      setBackendAvailable(true);
      writeLog(`[applySettings] 上传完成: taskId=${currentTaskId}, cached=${uploadRes.cached}`);
    } else {
      writeLog(`[applySettings] 跳过上传: currentTaskId=${currentTaskId}, audioFile=${!!audioFile}`);
    }
    
    writeLog(`[applySettings] 创建 Promise 前: taskIdRef=${taskIdRef.current}`);

    const updateCombinedProgress = (source: string) => {
      writeLog(`[progress][${source}] taskId=${taskIdRef.current}, backend=${backendProg.value.toFixed(2)}`);
      setProcessingProgress(backendProg.value);
    };

    const backendRepairPromise = taskIdRef.current ? (async () => {
      try {
        setBackendAvailable(true);
        const taskId = taskIdRef.current!;
        writeLog(`[backend] 开始修复 taskId=${taskId}`);

        const repairResultData = await new Promise<import('../../services/backendApi').ProgressEvent>((resolve, reject) => {
          wsControlRef.current = connectProgressWS(
            taskId,
            {
              onProgress: (event) => {
                backendProg.value = 0.1 + event.progress * 0.8;
                updateCombinedProgress('backend-ws');
                setProcessingSource('backend');
                setProcessingStep(event.step);
              },
              onError: reject,
              onComplete: resolve,
              onStuck: (info) => {
                setIsTaskStuck(true);
                setStuckInfo(info);
              },
              onUnstuck: () => {
                setIsTaskStuck(false);
              },
              onQueueUpdate: (queue) => {
                setQueueStatus(queue);
              },
            },
            REPAIR_TERMINALS,
          );
          repairAudio(taskId, params, processingOptions, effectiveAlgorithmVersion).catch(reject);
        });
        writeLog(`[backend] WebSocket 连接完成, status=${repairResultData.status}`);

        writeLog(`[applySettings] 后端轮询结束 status=${repairResultData.status}`);

        if (repairResultData.status !== 'completed') {
          throw new Error(repairResultData.error || `修复失败(status=${repairResultData.status})`);
        }

        const previewUrl = getPreviewUrl(taskId, 'repaired');
        setBackendPreviewUrl(previewUrl);

        return { previewUrl, repairResult: repairResultData.repair_result };
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.warn(`[applySettings] 后端修复失败: ${msg}`);
        setBackendError(msg);
        setProcessingSource('backend');
        setProcessingStep('修复失败: ' + msg);
        setBackendAvailable(false);
        toast.error(`修复失败: ${msg}`);
        return null;
      }
    })() : Promise.resolve(null);

    writeLog(`[applySettings] 开始后端修复`);
    const startTime = Date.now();
    const backendResult = await backendRepairPromise;
    writeLog(`[applySettings] 修复完成, 耗时=${Date.now() - startTime}ms`);

    let anySuccess = false;

    if (backendResult) {
      if (backendResult.repairResult) {
        setRepairResult({
          ...backendResult.repairResult,
          completed_at: new Date().toISOString(),
        });
        if (backendResult.repairResult.waveform_peaks) {
          setBackendWaveformPeaks(backendResult.repairResult.waveform_peaks);
        }
      }
      anySuccess = true;

      const previewUrl = backendResult.previewUrl;
      if (previewUrl) {
        writeLog(`[applySettings] 修复完成，预览URL已就绪: ${previewUrl}`);
      }

      if (audioFile && taskIdRef.current) {
        loadAudioFromUrl(previewUrl, processingOptionsRef.current.sampleRate, true).then(repairedBuffer => {
          writeLog(`[applySettings] buffer加载完成: duration=${repairedBuffer.duration.toFixed(3)}`);
          backendProcessedBufferRef.current = repairedBuffer;
          state.setBackendProcessedBuffer(repairedBuffer);
        }).catch(err => {
          console.warn('[applySettings] 后台下载修复后音频失败:', err);
        });
      }
    }

    if (anySuccess) {
      setHasBeenProcessed(true);
      useRepairSessionStore.getState().setSingleTrackProcessed(true);

      if (audioFile && taskIdRef.current) {
        saveSession({
          file: audioFile,
          fileName: audioFile.name,
          fileSize: audioFile.size,
          fileHash: fileHashRef.current || '',
          taskId: taskIdRef.current,
          backendAvailable: !!backendResult,
          hasBeenProcessed: true,
          wavInfo: wavInfoRef.current ? JSON.stringify(wavInfoRef.current) : '',
          repairResult: backendResult?.repairResult
            ? JSON.stringify(backendResult.repairResult)
            : '',
          processingOptions: JSON.stringify(processingOptionsRef.current),
        });
      }

      if (backendResult && taskIdRef.current) {
        forceRenderRef.current = true;
        if (renderActiveRef.current) {
          writeLog('[applySettings] renderAndDownload 已在进行，跳过');
        } else {
          const currentOpts = { ...processingOptions };
          renderAndDownload(currentOpts, effectiveAlgorithmVersion).then(result => {
            if (result?.downloadUrl) {
              setRenderDownloadUrl(result.downloadUrl);
            }
          }).catch(err => {
            writeLog(`[applySettings] 自动渲染失败: ${err}`);
          });
        }
      }
    }

    if (backendResult) {
      setProcessingStep('完成!');
    }
    setProcessingProgress(1);

    if (!backendResult) {
      setIsProcessing(false);
      setTimeout(() => {
        setProcessingStep('');
        setProcessingSource(null);
        setProcessingProgress(0);
      }, 2000);
    }
  }, [
    audioBuffer,
    audioFile,
    params,
    processingOptions,
    algorithmVersion,
    availableAlgorithms,
    setIsProcessing,
    setProcessingProgress,
    setProcessingStep,
    setProcessingSource,
    setBackendError,
    setBackendAvailable,
    setBackendPreviewUrl,
    setRepairResult,
    setBackendWaveformPeaks,
    setCacheHitInfo,
    setShowRepairCacheModal,
    setRenderDownloadUrl,
    setAutoRenderInfo,
    setHasBeenProcessed,
    setAlgorithmVersionState,
    setIsTaskStuck,
    setStuckInfo,
    setQueueStatus,
    setTaskId,
    taskIdRef,
    wsControlRef,
    fileHashRef,
    forceReRepairRef,
    forceRenderRef,
    renderActiveRef,
    processingOptionsRef,
    wavInfoRef,
    backendProcessedBufferRef,
    state,
    loadAudioFromUrl,
    renderAndDownload,
    toast,
  ]);

  const resetStuckState = useCallback(() => {
    setIsTaskStuck(false);
    setStuckInfo(null);
  }, [setIsTaskStuck, setStuckInfo]);

  const cancelCurrentTask = useCallback(async () => {
    const currentTaskId = taskIdRef.current;
    if (currentTaskId) {
      try {
        await cancelTask(currentTaskId);
      } catch (e) {
        console.warn('[cancelCurrentTask] 后端取消失败:', e);
      }
    }
    closeWS();
    resetStuckState();
    setIsProcessing(false);
    setProcessingStep('');
    setProcessingProgress(0);
  }, [taskIdRef, closeWS, resetStuckState, setIsProcessing, setProcessingStep, setProcessingProgress]);

  const handleUseRepairCache = useCallback((taskId: string) => {
    setShowRepairCacheModal(false);
    writeLog(`[handleUseRepairCache] 使用修复缓存 taskId=${taskId}`);

    const cache = state.cacheHitInfo?.repair;
    if (!cache) return;

    if (taskId && taskId !== taskIdRef.current) {
      setTaskId(taskId);
      taskIdRef.current = taskId;
    }

    setBackendAvailable(true);

    if (cache.repair_result) {
      setRepairResult({
        ...cache.repair_result,
        completed_at: new Date().toISOString(),
      });
      if (cache.repair_result.waveform_peaks) {
        setBackendWaveformPeaks(cache.repair_result.waveform_peaks);
      }
    }

    const previewUrl = getPreviewUrl(taskId, 'repaired');
    setBackendPreviewUrl(previewUrl);
    setHasBeenProcessed(true);

    if (audioFile && taskId) {
      loadAudioFromUrl(previewUrl, processingOptionsRef.current.sampleRate, true).then(repairedBuffer => {
        backendProcessedBufferRef.current = repairedBuffer;
        state.setBackendProcessedBuffer(repairedBuffer);
      }).catch(err => {
        console.warn('[handleUseRepairCache] 后台下载缓存音频失败:', err);
      });
    }

    saveSession({
      file: audioFile,
      fileName: audioFile.name,
      fileSize: audioFile.size,
      fileHash: fileHashRef.current || '',
      taskId,
      backendAvailable: true,
      hasBeenProcessed: true,
      wavInfo: wavInfoRef.current ? JSON.stringify(wavInfoRef.current) : '',
      repairResult: cache.repair_result ? JSON.stringify(cache.repair_result) : '',
      processingOptions: JSON.stringify(processingOptionsRef.current),
    });

    writeLog(`[handleUseRepairCache] 开始调用 renderAndDownload`);
    forceRenderRef.current = false;
    const currentOpts = { ...processingOptions };
    renderAndDownload(currentOpts, algorithmVersion).then(result => {
      writeLog(`[handleUseRepairCache] renderAndDownload 完成: ${!!result}`);
      if (result?.downloadUrl) {
        setRenderDownloadUrl(result.downloadUrl);
      }
      setShowDownloadModal(true);
    }).catch((err) => {
      writeLog(`[handleUseRepairCache] renderAndDownload 失败: ${err}`);
      setShowDownloadModal(true);
    });
  }, [state, setShowRepairCacheModal, taskIdRef, setTaskId, setBackendAvailable, setRepairResult, setBackendWaveformPeaks, setBackendPreviewUrl, setHasBeenProcessed, audioFile, loadAudioFromUrl, processingOptionsRef, backendProcessedBufferRef, fileHashRef, wavInfoRef, forceRenderRef, processingOptions, renderAndDownload, algorithmVersion, setRenderDownloadUrl, setShowDownloadModal]);

  const handleRenderCacheDownload = useCallback((cache: RenderCacheEntry, downloadUrl: string, _filename: string) => {
    writeLog(`[handleRenderCacheDownload] 秒下: ${cache.filename}`);
    setRenderDownloadUrl(downloadUrl);
    setAutoRenderInfo({
      output_sample_rate: cache.sample_rate,
      output_bit_depth: cache.bit_depth,
      duration: refs.durationRef.current,
      channels: 2,
    });
    setShowDownloadModal(true);
  }, [setRenderDownloadUrl, setAutoRenderInfo, setShowDownloadModal, refs.durationRef]);

  const handleReRepair = useCallback(() => {
    writeLog(`[handleReRepair] 用户选择重新修复`);
    setShowRepairCacheModal(false);
    setCacheHitInfo(null);
    setIsProcessing(true);
    forceReRepairRef.current = true;
    applySettings();
  }, [setShowRepairCacheModal, setCacheHitInfo, setIsProcessing, forceReRepairRef, applySettings]);

  const handleCloseRepairCacheModal = useCallback(() => {
    writeLog(`[handleCloseRepairCacheModal] 关闭模态框`);
    setShowRepairCacheModal(false);
    setIsProcessing(false);
  }, [setShowRepairCacheModal, setIsProcessing]);

  const api = useMemo(() => ({
    applyAlgorithmVersion,
    closeWS,
    applySettings,
    resetStuckState,
    cancelCurrentTask,
    handleUseRepairCache,
    handleRenderCacheDownload,
    handleReRepair,
    handleCloseRepairCacheModal,
  }), [
    applyAlgorithmVersion,
    closeWS,
    applySettings,
    resetStuckState,
    cancelCurrentTask,
    handleUseRepairCache,
    handleRenderCacheDownload,
    handleReRepair,
    handleCloseRepairCacheModal,
  ]);

  return api;
}

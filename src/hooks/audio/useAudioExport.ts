import { useCallback } from 'react';
import {
  renderAudio,
  waitRenderWithWS,
  fetchRenderCache,
  ProcessingOptions,
} from '../../services/backendApi';
import { generateExportFilename, writeLog } from './utils';
import type { AudioCoreState, AudioCoreRefs } from './useAudioCore';

interface UseAudioExportOptions {
  state: AudioCoreState;
  refs: AudioCoreRefs;
}

export interface RenderResult {
  downloadUrl: string;
  fileName: string;
  renderInfo: {
    output_sample_rate: number;
    output_bit_depth: number;
    duration: number;
    channels: number;
  };
}

export function useAudioExport({ state, refs }: UseAudioExportOptions) {
  const {
    audioFile,
    setIsProcessing,
    setProcessingSource,
    setProcessingStep,
    setProcessingProgress,
    setIsRenderLoading,
    setAutoRenderInfo,
    setRepairResult,
  } = state;

  const {
    taskIdRef,
    renderActiveRef,
    forceRenderRef,
    processingOptionsRef,
    algorithmVersionRef,
    wsControlRef,
    durationRef,
  } = refs;

  const renderAndDownload = useCallback(async (overrideOptions?: ProcessingOptions, overrideAlgoVersion?: string): Promise<RenderResult | null> => {
    if (renderActiveRef.current) {
      writeLog('[renderAndDownload] 已有渲染在进行中，跳过');
      return null;
    }
    renderActiveRef.current = true;

    const opts = overrideOptions || processingOptionsRef.current;
    const algoVer = overrideAlgoVersion || algorithmVersionRef.current;
    const fileName = generateExportFilename(audioFile?.name, algoVer, opts.sampleRate, opts.bitDepth);

    if (!taskIdRef.current) return null;

    try {
      if (!forceRenderRef.current) {
        const caches = await fetchRenderCache(taskIdRef.current);
        const hit = caches.find(c => c.sample_rate === opts.sampleRate && c.bit_depth === opts.bitDepth && c.algorithm_version === algoVer);
        if (hit) {
          writeLog(`[renderAndDownload] 渲染缓存命中: ${hit.filename}`);
          const renderInfo = {
            output_sample_rate: hit.sample_rate,
            output_bit_depth: hit.bit_depth,
            duration: durationRef.current,
            channels: 2,
          };
          setAutoRenderInfo(renderInfo);
          renderActiveRef.current = false;
          return {
            downloadUrl: `/api/v1/download-file/${hit.filename}`,
            fileName,
            renderInfo,
          };
        }
      }
    } catch { /* 忽略缓存查询失败，继续渲染 */ }

    try {
      writeLog(`[renderAndDownload] 开始渲染: sr=${opts.sampleRate} bd=${opts.bitDepth}`);
      setIsProcessing(true);
      setProcessingSource('backend');
      setProcessingStep('渲染交付规格...');
      setProcessingProgress(0);
      setIsRenderLoading(true);
      await renderAudio(taskIdRef.current, opts.sampleRate, opts.bitDepth, opts.masteringStyle, algoVer, opts.qualityMode);
      const { promise, close } = waitRenderWithWS(taskIdRef.current, (progress, step) => {
        writeLog(`[renderAndDownload] 渲染进度: ${progress} step=${step}`);
        setProcessingProgress(progress);
        setProcessingStep(step);
      });
      wsControlRef.current = { close };
      const renderRes = await promise;
      wsControlRef.current = null;
      setIsRenderLoading(false);
      if (!renderRes.render_filename || !renderRes.render_result) {
        throw new Error('渲染结果不完整');
      }
      writeLog(`[renderAndDownload] 渲染完成: sr=${renderRes.render_result.output_sample_rate} bd=${renderRes.render_result.output_bit_depth}`);
      const renderInfo = {
        output_sample_rate: renderRes.render_result!.output_sample_rate,
        output_bit_depth: renderRes.render_result!.output_bit_depth,
        duration: renderRes.render_result!.duration,
        channels: renderRes.render_result!.channels,
      };
      setAutoRenderInfo(renderInfo);
      setRepairResult(prev => prev ? {
        ...prev,
        output_sample_rate: renderInfo.output_sample_rate,
        output_bit_depth: renderInfo.output_bit_depth,
      } : null);
      setProcessingStep('');
      setProcessingSource(null);
      setProcessingProgress(0);
      setIsProcessing(false);
      renderActiveRef.current = false;
      forceRenderRef.current = false;
      return {
        downloadUrl: `/api/v1/download-file/${renderRes.render_filename}`,
        fileName,
        renderInfo,
      };
    } catch (renderErr) {
      wsControlRef.current?.close();
      wsControlRef.current = null;
      setIsRenderLoading(false);
      setIsProcessing(false);
      writeLog(`[renderAndDownload] 渲染失败: ${renderErr}`);
      setProcessingStep('');
      setProcessingSource(null);
      setProcessingProgress(0);
      renderActiveRef.current = false;
      return null;
    }
  }, [
    audioFile,
    setIsProcessing,
    setProcessingSource,
    setProcessingStep,
    setProcessingProgress,
    setIsRenderLoading,
    setAutoRenderInfo,
    setRepairResult,
    taskIdRef,
    renderActiveRef,
    forceRenderRef,
    processingOptionsRef,
    algorithmVersionRef,
    wsControlRef,
    durationRef,
  ]);

  return {
    renderAndDownload,
  };
}

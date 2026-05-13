import { useCallback, useEffect, useRef } from 'react';
import { useDualTrackStore, type DualTrackState } from '../store/dualTrackStore';
import { computeFileHash } from '../utils/fileHash';
import { AIRepairParams } from '../utils/advancedAudioProcessing';
import {
  uploadDualAudio,
  repairDualAudio,
  repairDualFromHash,
  lookupDualRepairCache,
  fetchRenderCache,
  renderAudio,
  waitRenderWithWS,
  connectProgressWS,
  getDownloadUrl,
  mapParamsToBackend,
  type ProcessingOptions,
  type VocalRepairParams,
  type InstrumentRepairParams,
  type RenderResult,
  type WSProgressControl,
} from '../services/backendApi';

export function useDualTrackProcessor() {
  const store = useDualTrackStore();
  const wsRef = useRef<WSProgressControl | null>(null);
  const renderWsRef = useRef<{ close: () => void } | null>(null);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
      renderWsRef.current?.close();
    };
  }, []);

  const upload = useCallback(async (vocalFile: File, accompanimentFile: File) => {
    store.setUpload(vocalFile, accompanimentFile);

    try {
      const [vocalHash, accompanimentHash] = await Promise.all([
        computeFileHash(vocalFile),
        computeFileHash(accompanimentFile),
      ]);

      store.setUploadProgress(0, '上传中...');

      const result = await uploadDualAudio(
        vocalFile,
        accompanimentFile,
        (_loaded, _total) => {
          const pct = _loaded / _total;
          store.setUploadProgress(pct, `上传中 ${(pct * 100).toFixed(0)}%`);
        },
        undefined,
        vocalHash,
        accompanimentHash,
      );

      store.setVocalFileHash(vocalHash);
      store.setAccompanimentFileHash(accompanimentHash);
      store.setUploadResult(result);
    } catch (e) {
      const msg = e instanceof Error ? e.message : '双轨上传失败';
      store.setUploadError(msg);
      throw e;
    }
  }, [store]);

  const checkCache = useCallback(async (
    params: AIRepairParams,
    options: ProcessingOptions,
    algorithmVersion?: string,
  ) => {
    const { vocalFileHash, accompanimentFileHash } = useDualTrackStore.getState();
    if (!vocalFileHash || !accompanimentFileHash) return null;

    try {
      const backendParams = mapParamsToBackend(params, options, algorithmVersion);
      const result = await lookupDualRepairCache(vocalFileHash, accompanimentFileHash, backendParams);
      if (result.found) {
        store.setCacheHit(result);
        store.setShowCacheModal(true);
      }
      return result;
    } catch {
      return null;
    }
  }, [store]);

  const repair = useCallback(async (
    params: AIRepairParams,
    options: ProcessingOptions,
    algorithmVersion?: string,
    vocalParams?: VocalRepairParams,
    accompanimentParams?: InstrumentRepairParams,
    mixRatio?: number,
  ) => {
    const state = useDualTrackStore.getState();
    const { mainTaskId, vocalTaskId, accompanimentTaskId, vocalFileHash, accompanimentFileHash, vocalFileName, accompanimentFileName } = state;

    if (!mainTaskId || !vocalTaskId || !accompanimentTaskId) {
      if (vocalFileHash && accompanimentFileHash) {
        store.setRepairStatus('repairing');
        store.setRepairProgress(0, '开始双轨修复...');

        const result = await repairDualFromHash(
          vocalFileHash,
          accompanimentFileHash,
          vocalFileName,
          accompanimentFileName,
          params,
          options,
          algorithmVersion,
          vocalParams,
          accompanimentParams,
          mixRatio,
        );

        store.setMainTaskId(result.task_id);
        store.setVocalTaskId(result.vocal_task_id);
        store.setAccompanimentTaskId(result.accompaniment_task_id);
        startWsPolling(result.task_id, store, wsRef);
      } else {
        throw new Error('请先上传人声和伴奏文件');
      }
    } else {
      store.setRepairStatus('repairing');
      store.setRepairProgress(0, '开始双轨修复...');

      await repairDualAudio(
        mainTaskId,
        vocalTaskId,
        accompanimentTaskId,
        params,
        options,
        algorithmVersion,
        vocalParams,
        accompanimentParams,
        mixRatio,
      );

      startWsPolling(mainTaskId, store, wsRef);
    }
  }, [store]);

  const useRepairCache = useCallback(async (cachedTaskId: string) => {
    store.setShowCacheModal(false);
    store.setRepairStatus('cached');
    store.setMainTaskId(cachedTaskId);

    try {
      const result = await renderWithTaskId(cachedTaskId, store, renderWsRef);
      if (result) {
        store.setRenderStatus('done');
        await refreshRenderCacheInner(cachedTaskId, store);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : '缓存渲染失败';
      store.setRenderError(msg);
    }
  }, [store]);

  const render = useCallback(async (
    options?: ProcessingOptions,
  ): Promise<RenderResult | null> => {
    const { mainTaskId } = useDualTrackStore.getState();
    if (!mainTaskId) return null;

    store.setRenderStatus('rendering');
    store.setRenderProgress(0, '渲染交付规格...');

    try {
      const result = await renderWithTaskId(mainTaskId, store, renderWsRef);
      if (result) {
        store.setRenderStatus('done');
        await refreshRenderCacheInner(mainTaskId, store);
      }
      return result;
    } catch (e) {
      const msg = e instanceof Error ? e.message : '渲染失败';
      store.setRenderError(msg);
      return null;
    }
  }, [store]);

  const refreshRenderCache = useCallback(async () => {
    const { mainTaskId } = useDualTrackStore.getState();
    if (!mainTaskId) return;
    await refreshRenderCacheInner(mainTaskId, store);
  }, [store]);

  const reset = useCallback(() => {
    wsRef.current?.close();
    renderWsRef.current?.close();
    wsRef.current = null;
    renderWsRef.current = null;
    store.reset();
  }, [store]);

  return {
    upload,
    checkCache,
    repair,
    useRepairCache,
    render,
    refreshRenderCache,
    reset,
    state: store,
  };
}

function startWsPolling(
  taskId: string,
  store: DualTrackState,
  wsRef: React.MutableRefObject<WSProgressControl | null>,
) {
  const wsControl = connectProgressWS(taskId, {
    onProgress: (event) => {
      store.setRepairProgress(event.progress, event.step || '');
    },
    onComplete: async () => {
      store.setRepairStatus('done');
      try {
        const result = await renderWithTaskId(taskId, store, null);
        if (result) {
          store.setRenderStatus('done');
          await refreshRenderCacheInner(taskId, store);
        }
      } catch (e) {
        console.error('[dualTrack] 渲染失败:', e);
        await refreshRenderCacheInner(taskId, store);
      }
    },
    onError: (error) => {
      store.setRepairError(error.message || '双轨修复失败');
    },
    onStuck: () => {
      store.setRepairProgress(0, '任务执行似乎卡住了...');
    },
    onUnstuck: () => {
      store.setRepairProgress(0, '任务恢复执行');
    },
  });
  wsRef.current = wsControl;
}

async function renderWithTaskId(
  taskId: string,
  store: DualTrackState,
  wsRef: React.MutableRefObject<{ close: () => void } | null> | null,
): Promise<RenderResult | null> {
  store.setRenderStatus('rendering');

  try {
    await renderAudio(taskId, 44100, 24);
    const { promise, close } = waitRenderWithWS(taskId, (progress, step) => {
      store.setRenderProgress(progress, step || '');
    });
    if (wsRef) wsRef.current = { close };
    const result = await promise;
    if (wsRef) wsRef.current = null;
    return result;
  } catch (e) {
    if (wsRef) wsRef.current = null;
    throw e;
  }
}

async function refreshRenderCacheInner(taskId: string, store: DualTrackState) {
  try {
    const caches = await fetchRenderCache(taskId);
    store.setRenderCaches(caches);
  } catch {
    // 缓存刷新失败不阻塞流程
  }
}
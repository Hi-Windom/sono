import { create } from 'zustand';
import type { AudioInfo, RenderCacheEntry, DualRepairCacheLookupResult } from '../services/backendApi';

export type UploadStatus = 'idle' | 'uploading' | 'done' | 'error';
export type RepairStatus = 'idle' | 'repairing' | 'done' | 'error' | 'cached';
export type RenderStatus = 'idle' | 'rendering' | 'done' | 'error';

export interface DualTrackState {
  uploadStatus: UploadStatus
  uploadProgress: number
  uploadStep: string
  vocalFile: File | null
  accompanimentFile: File | null
  vocalFileName: string
  accompanimentFileName: string
  vocalFileHash: string
  accompanimentFileHash: string

  mainTaskId: string | null
  vocalTaskId: string | null
  accompanimentTaskId: string | null

  vocalInfo: AudioInfo | null
  accompanimentInfo: AudioInfo | null

  repairStatus: RepairStatus
  repairProgress: number
  repairStep: string
  repairError: string | null
  repairResult: unknown | null

  renderStatus: RenderStatus
  renderProgress: number
  renderStep: string
  renderError: string | null
  renderCaches: RenderCacheEntry[]

  cacheHit: DualRepairCacheLookupResult | null
  showCacheModal: boolean

  setUpload: (vocal: File, accompaniment: File) => void
  setUploadProgress: (progress: number, step: string) => void
  setUploadResult: (result: {
    task_id: string
    vocal_task_id: string
    accompaniment_task_id: string
    vocal_info?: AudioInfo | null
    accompaniment_info?: AudioInfo | null
  }) => void
  setUploadError: (error: string) => void
  setVocalFileHash: (hash: string) => void
  setAccompanimentFileHash: (hash: string) => void
  setMainTaskId: (id: string) => void
  setVocalTaskId: (id: string) => void
  setAccompanimentTaskId: (id: string) => void
  setRepairStatus: (status: RepairStatus) => void
  setRepairProgress: (progress: number, step: string) => void
  setRepairError: (error: string) => void
  setRepairResult: (result: unknown) => void
  setRenderStatus: (status: RenderStatus) => void
  setRenderProgress: (progress: number, step: string) => void
  setRenderError: (error: string) => void
  setRenderCaches: (caches: RenderCacheEntry[]) => void
  setCacheHit: (hit: DualRepairCacheLookupResult | null) => void
  setShowCacheModal: (show: boolean) => void
  reset: () => void
}

const initialState = {
  uploadStatus: 'idle' as UploadStatus,
  uploadProgress: 0,
  uploadStep: '',
  vocalFile: null as File | null,
  accompanimentFile: null as File | null,
  vocalFileName: '',
  accompanimentFileName: '',
  vocalFileHash: '',
  accompanimentFileHash: '',
  mainTaskId: null as string | null,
  vocalTaskId: null as string | null,
  accompanimentTaskId: null as string | null,
  vocalInfo: null as AudioInfo | null,
  accompanimentInfo: null as AudioInfo | null,
  repairStatus: 'idle' as RepairStatus,
  repairProgress: 0,
  repairStep: '',
  repairError: null as string | null,
  repairResult: null as unknown | null,
  renderStatus: 'idle' as RenderStatus,
  renderProgress: 0,
  renderStep: '',
  renderError: null as string | null,
  renderCaches: [] as RenderCacheEntry[],
  cacheHit: null as DualRepairCacheLookupResult | null,
  showCacheModal: false,
};

export const useDualTrackStore = create<DualTrackState>()(
  (set) => ({
    ...initialState,

    setUpload: (vocal, accompaniment) => set({
      uploadStatus: 'uploading',
      uploadProgress: 0,
      uploadStep: '计算文件哈希...',
      vocalFile: vocal,
      accompanimentFile: accompaniment,
      vocalFileName: vocal.name,
      accompanimentFileName: accompaniment.name,
    }),

    setUploadProgress: (progress, step) => set({
      uploadProgress: progress,
      uploadStep: step,
    }),

    setUploadResult: (result) => set({
      uploadStatus: 'done',
      uploadProgress: 1,
      uploadStep: '上传完成',
      mainTaskId: result.task_id,
      vocalTaskId: result.vocal_task_id,
      accompanimentTaskId: result.accompaniment_task_id,
      vocalInfo: result.vocal_info ?? null,
      accompanimentInfo: result.accompaniment_info ?? null,
    }),

    setUploadError: (error) => set({
      uploadStatus: 'error',
      repairError: error,
    }),

    setVocalFileHash: (hash) => set({ vocalFileHash: hash }),
    setAccompanimentFileHash: (hash) => set({ accompanimentFileHash: hash }),
    setMainTaskId: (id) => set({ mainTaskId: id }),
    setVocalTaskId: (id) => set({ vocalTaskId: id }),
    setAccompanimentTaskId: (id) => set({ accompanimentTaskId: id }),

    setRepairStatus: (status) => set({ repairStatus: status }),
    setRepairProgress: (progress, step) => set({ repairProgress: progress, repairStep: step }),
    setRepairError: (error) => set({ repairStatus: 'error', repairError: error }),
    setRepairResult: (result) => set({ repairResult: result }),

    setRenderStatus: (status) => set({ renderStatus: status }),
    setRenderProgress: (progress, step) => set({ renderProgress: progress, renderStep: step }),
    setRenderError: (error) => set({ renderStatus: 'error', renderError: error }),
    setRenderCaches: (caches) => set({ renderCaches: caches }),

    setCacheHit: (hit) => set({ cacheHit: hit }),
    setShowCacheModal: (show) => set({ showCacheModal: show }),

    reset: () => set({ ...initialState }),
  }),
);
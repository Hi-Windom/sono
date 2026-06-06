import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface DualTrackAudioMeta {
  sample_rate: number;
  channels: number;
  duration: number;
}

interface RenderCacheEntryMeta {
  filename: string;
  size: number;
  sample_rate: number;
  bit_depth: number;
  track_type?: string;
  algorithm_version?: string;
}

interface RepairSessionState {
  isDualTrackMode: boolean;
  singleTrackFileHash: string;
  singleTrackFileName: string;
  singleTrackHasBeenProcessed: boolean;
  dualTrackVocalFileHash: string;
  dualTrackAccompanimentFileHash: string;
  dualTrackVocalFileName: string;
  dualTrackAccompanimentFileName: string;
  dualTrackHasBeenProcessed: boolean;
  dualTrackVocalInfo: DualTrackAudioMeta | null;
  dualTrackAccompanimentInfo: DualTrackAudioMeta | null;
  dualTrackRenderCaches: RenderCacheEntryMeta[];
  setDualTrackMode: (mode: boolean) => void;
  setSingleTrackFile: (hash: string, name: string) => void;
  setSingleTrackProcessed: (processed: boolean) => void;
  setDualTrackFiles: (vocalHash: string, vocalName: string, accHash: string, accName: string) => void;
  setDualTrackProcessed: (processed: boolean) => void;
  setDualTrackFileInfo: (vocalInfo: DualTrackAudioMeta | null, accompanimentInfo: DualTrackAudioMeta | null) => void;
  setDualTrackRenderCaches: (caches: RenderCacheEntryMeta[]) => void;
  clearSingleTrack: () => void;
  clearDualTrack: () => void;
  clearAll: () => void;
}

export const useRepairSessionStore = create<RepairSessionState>()(
  persist(
    (set) => ({
      isDualTrackMode: false,
      singleTrackFileHash: '',
      singleTrackFileName: '',
      singleTrackHasBeenProcessed: false,
      dualTrackVocalFileHash: '',
      dualTrackAccompanimentFileHash: '',
      dualTrackVocalFileName: '',
      dualTrackAccompanimentFileName: '',
      dualTrackHasBeenProcessed: false,
      dualTrackVocalInfo: null,
      dualTrackAccompanimentInfo: null,
      dualTrackRenderCaches: [],
      setDualTrackMode: (mode) => set({ isDualTrackMode: mode }),
      setSingleTrackFile: (hash, name) => set({ singleTrackFileHash: hash, singleTrackFileName: name }),
      setSingleTrackProcessed: (processed) => set({ singleTrackHasBeenProcessed: processed }),
      setDualTrackFiles: (vocalHash, vocalName, accHash, accName) => set({
        dualTrackVocalFileHash: vocalHash,
        dualTrackVocalFileName: vocalName,
        dualTrackAccompanimentFileHash: accHash,
        dualTrackAccompanimentFileName: accName,
      }),
      setDualTrackProcessed: (processed) => set({ dualTrackHasBeenProcessed: processed }),
      setDualTrackFileInfo: (vocalInfo, accompanimentInfo) => set({
        dualTrackVocalInfo: vocalInfo,
        dualTrackAccompanimentInfo: accompanimentInfo,
      }),
      setDualTrackRenderCaches: (caches) => set({ dualTrackRenderCaches: caches }),
      clearSingleTrack: () => set({
        singleTrackFileHash: '',
        singleTrackFileName: '',
        singleTrackHasBeenProcessed: false,
      }),
      clearDualTrack: () => set({
        isDualTrackMode: false,
        dualTrackVocalFileHash: '',
        dualTrackAccompanimentFileHash: '',
        dualTrackVocalFileName: '',
        dualTrackAccompanimentFileName: '',
        dualTrackHasBeenProcessed: false,
        dualTrackVocalInfo: null,
        dualTrackAccompanimentInfo: null,
        dualTrackRenderCaches: [],
      }),
      clearAll: () => set({
        isDualTrackMode: false,
        singleTrackFileHash: '',
        singleTrackFileName: '',
        singleTrackHasBeenProcessed: false,
        dualTrackVocalFileHash: '',
        dualTrackAccompanimentFileHash: '',
        dualTrackVocalFileName: '',
        dualTrackAccompanimentFileName: '',
        dualTrackHasBeenProcessed: false,
        dualTrackVocalInfo: null,
        dualTrackAccompanimentInfo: null,
        dualTrackRenderCaches: [],
      }),
    }),
    {
      name: 'repair-session',
      version: 2,
      onRehydrateStorage: () => (_state, error) => {
        if (error) {
          console.error('[repairSessionStore] rehydrate error:', error);
          try { localStorage.removeItem('repair-session'); } catch {}
        }
      },
    },
  ),
);
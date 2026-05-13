import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { useState, useEffect } from 'react';

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

  setDualTrackMode: (mode: boolean) => void;
  setSingleTrackFile: (hash: string, name: string) => void;
  setSingleTrackProcessed: (processed: boolean) => void;
  setDualTrackFiles: (vocalHash: string, vocalName: string, accHash: string, accName: string) => void;
  setDualTrackProcessed: (processed: boolean) => void;
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
      }),
    }),
    {
      name: 'repair-session',
      version: 1,
      onRehydrateStorage: () => {
        return (_state, error) => {
          if (error) {
            console.error('[repairSessionStore] 水合失败，清除损坏数据:', error);
            try {
              localStorage.removeItem('repair-session');
            } catch {}
          }
        };
      },
      migrate: (persisted, version) => {
        if (version === 0) {
          const old = persisted as Record<string, unknown>;
          return {
            isDualTrackMode: (old.isDualTrackMode as boolean) ?? false,
            singleTrackFileHash: (old.singleTrackFileHash as string) ?? '',
            singleTrackFileName: (old.singleTrackFileName as string) ?? '',
            singleTrackHasBeenProcessed: (old.singleTrackHasBeenProcessed as boolean) ?? false,
            dualTrackVocalFileHash: (old.dualTrackVocalFileHash as string) ?? '',
            dualTrackAccompanimentFileHash: (old.dualTrackAccompanimentFileHash as string) ?? '',
            dualTrackVocalFileName: (old.dualTrackVocalFileName as string) ?? '',
            dualTrackAccompanimentFileName: (old.dualTrackAccompanimentFileName as string) ?? '',
            dualTrackHasBeenProcessed: (old.dualTrackHasBeenProcessed as boolean) ?? false,
          };
        }
        return persisted as RepairSessionState;
      },
    },
  ),
);

export function useRepairSessionHydrated(): boolean {
  const [hydrated, setHydrated] = useState(() => useRepairSessionStore.persist.hasHydrated());

  useEffect(() => {
    if (useRepairSessionStore.persist.hasHydrated()) {
      setHydrated(true);
      return;
    }
    const unsubFinish = useRepairSessionStore.persist.onFinishHydration(() => {
      setHydrated(true);
    });
    return unsubFinish;
  }, []);

  return hydrated;
}

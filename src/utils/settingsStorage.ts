import { AIRepairParams, defaultAIRepairParams } from './advancedAudioProcessing';

export interface ProfileConfig {
  id: string;
  name: string;
  algorithmVersion: string;
  params: AIRepairParams;
  createdAt: string;
}

export interface AppSettings {
  aiRepairParams: AIRepairParams;
  exportOptions: {
    sampleRate: number;
    bitDepth: 16 | 24 | 32;
  };
  stemSettings: {
    vocalGain: number;
    instrumentalGain: number;
    vocalBalance: number;
  };
  selectedMode: string;
  algorithmVersion: string;
  savedProfiles: ProfileConfig[];
}

const SETTINGS_KEY = 'ai-music-repair-settings';

export const defaultSettings: AppSettings = {
  aiRepairParams: defaultAIRepairParams,
  exportOptions: {
    sampleRate: 48000,
    bitDepth: 24,
  },
  stemSettings: {
    vocalGain: 0,
    instrumentalGain: 0,
    vocalBalance: 0,
  },
  selectedMode: '全面修复',
  algorithmVersion: '',
  savedProfiles: [],
};

export function loadSettings(): AppSettings {
  try {
    const stored = localStorage.getItem(SETTINGS_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return {
        ...defaultSettings,
        ...parsed,
        aiRepairParams: {
          ...defaultSettings.aiRepairParams,
          ...parsed.aiRepairParams,
        },
        exportOptions: {
          ...defaultSettings.exportOptions,
          ...parsed.exportOptions,
        },
        savedProfiles: Array.isArray(parsed.savedProfiles) ? parsed.savedProfiles : [],
        algorithmVersion: parsed.algorithmVersion || defaultSettings.algorithmVersion,
      };
    }
  } catch (error) {
    console.error('Failed to load settings:', error);
  }
  return defaultSettings;
}

export function saveSettings(settings: Partial<AppSettings>) {
  try {
    const current = loadSettings();
    const toSave = { ...current, ...settings };
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(toSave));
  } catch (error) {
    console.error('Failed to save settings:', error);
  }
}

export function resetSettings() {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(defaultSettings));
  } catch (error) {
    console.error('Failed to reset settings:', error);
  }
}

export function getSavedProfiles(): ProfileConfig[] {
  const settings = loadSettings();
  return settings.savedProfiles || [];
}

export function saveProfileToStorage(name: string, params: AIRepairParams, algorithmVersion: string): void {
  const settings = loadSettings();
  const newProfile: ProfileConfig = {
    id: typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36),
    name,
    algorithmVersion,
    params: { ...params },
    createdAt: new Date().toISOString(),
  };
  const updated = [...(settings.savedProfiles || []), newProfile];
  saveSettings({ savedProfiles: updated });
}

export function applyProfileById(id: string): void {
  const settings = loadSettings();
  const profile = (settings.savedProfiles || []).find(p => p.id === id);
  if (!profile) return;
  saveSettings({
    aiRepairParams: { ...profile.params },
    algorithmVersion: profile.algorithmVersion,
  });
}

export function deleteProfileById(id: string): void {
  const settings = loadSettings();
  const updated = (settings.savedProfiles || []).filter(p => p.id !== id);
  saveSettings({ savedProfiles: updated });
}

export function renameProfileById(id: string, newName: string): void {
  const settings = loadSettings();
  const updated = (settings.savedProfiles || []).map(p =>
    p.id === id ? { ...p, name: newName } : p
  );
  saveSettings({ savedProfiles: updated });
}
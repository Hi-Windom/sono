import { AIRepairParams, defaultAIRepairParams } from './advancedAudioProcessing';

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
  detectorVersion: string;
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
  detectorVersion: 'v1.0',
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
        // 确保版本字段有默认值
        algorithmVersion: parsed.algorithmVersion || defaultSettings.algorithmVersion,
        detectorVersion: parsed.detectorVersion || defaultSettings.detectorVersion,
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
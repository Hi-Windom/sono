import React from 'react';
import { AudioEffectParams } from '../utils/audioUtils';

interface EffectsPanelProps {
  params: AudioEffectParams;
  onUpdate: (key: keyof AudioEffectParams, value: number) => void;
  onReset: () => void;
  isProcessing: boolean;
  disabled: boolean;
}

interface SliderControlProps {
  label: string;
  description: string;
  value: number;
  min?: number;
  max?: number;
  onChange: (value: number) => void;
  disabled: boolean;
}

function SliderControl({ label, description, value, min = 0, max = 1, onChange, disabled }: SliderControlProps) {
  return (
    <div className="bg-primary/50 rounded-xl p-4 border border-secondary/20">
      <div className="flex justify-between items-center mb-2">
        <label className="text-white font-medium">{label}</label>
        <span className="text-secondary text-sm font-mono">{value.toFixed(2)}</span>
      </div>
      <p className="text-gray-400 text-sm mb-3">{description}</p>
      <input
        type="range"
        min={min}
        max={max}
        step={0.01}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        disabled={disabled}
        className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
        style={{
          background: `linear-gradient(to right, #00D9FF 0%, #00D9FF ${(value / max) * 100}%, #374151 ${(value / max) * 100}%, #374151 100%)`,
        }}
      />
    </div>
  );
}

export function EffectsPanel({ params, onUpdate, onReset, isProcessing, disabled }: EffectsPanelProps) {
  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-white text-lg font-bold flex items-center gap-2">
          <svg className="w-5 h-5 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
          </svg>
          音频效果
        </h3>
        <button
          onClick={onReset}
          disabled={disabled}
          className="px-4 py-2 text-sm text-gray-400 hover:text-white transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          重置
        </button>
      </div>

      {isProcessing && (
        <div className="mb-4 p-3 bg-secondary/10 border border-secondary/30 rounded-lg flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-secondary/30 border-t-secondary rounded-full animate-spin" />
          <span className="text-secondary text-sm">处理中...</span>
        </div>
      )}

      <div className="space-y-4">
        <SliderControl
          label="降噪"
          description="减少背景噪音"
          value={params.noiseReduction}
          onChange={(v) => onUpdate('noiseReduction', v)}
          disabled={disabled}
        />

        <div className="bg-primary/50 rounded-xl p-4 border border-secondary/20">
          <div className="flex items-center gap-2 mb-3">
            <svg className="w-4 h-4 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
            </svg>
            <span className="text-white font-medium">均衡器</span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-gray-400 text-sm">低音</span>
                <span className="text-secondary text-sm font-mono">{params.bass.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={-1}
                max={1}
                step={0.01}
                value={params.bass}
                onChange={(e) => onUpdate('bass', parseFloat(e.target.value))}
                disabled={disabled}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
              />
            </div>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-gray-400 text-sm">中音</span>
                <span className="text-secondary text-sm font-mono">{params.mid.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={-1}
                max={1}
                step={0.01}
                value={params.mid}
                onChange={(e) => onUpdate('mid', parseFloat(e.target.value))}
                disabled={disabled}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
              />
            </div>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-gray-400 text-sm">高音</span>
                <span className="text-secondary text-sm font-mono">{params.treble.toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={-1}
                max={1}
                step={0.01}
                value={params.treble}
                onChange={(e) => onUpdate('treble', parseFloat(e.target.value))}
                disabled={disabled}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
              />
            </div>
          </div>
        </div>

        <SliderControl
          label="压缩器"
          description="减小动态范围，使声音更平稳"
          value={params.compression}
          onChange={(v) => onUpdate('compression', v)}
          disabled={disabled}
        />

        <SliderControl
          label="音量标准化"
          description="调整音量到最佳水平"
          value={params.normalize}
          onChange={(v) => onUpdate('normalize', v)}
          disabled={disabled}
        />
      </div>
    </div>
  );
}

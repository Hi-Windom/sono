import React, { useState } from 'react';
import { AIRepairParams, RepairMode } from '../utils/advancedAudioProcessing';
import { ProcessingOptions, AlgorithmVersion } from '../services/backendApi';

interface AIRepairPanelProps {
  params: AIRepairParams;
  analysis: {
    spectralFlatness: number;
    dynamicRange: number;
    stereoBalance: number;
    peakLevel: number;
    issues: string[];
  } | null;
  selectedMode: string;
  modes: RepairMode[];
  processingOptions: ProcessingOptions;
  algorithmVersion: string;
  availableAlgorithms: AlgorithmVersion[];
  onAlgorithmChange: (version: string) => void;
  onParamChange: (key: keyof AIRepairParams, value: number) => void;
  onReset: () => void;
  onModeSelect: (mode: RepairMode) => void;
  onApply?: () => void;
  onOptionsChange?: (options: ProcessingOptions) => void;
  disabled?: boolean;
}

const sampleRateOptions = [
  { value: 44100, label: '44.1k' },
  { value: 48000, label: '48k' },
  { value: 96000, label: '96k' },
];

const bitDepthOptions: { value: 16 | 24 | 32; label: string }[] = [
  { value: 16, label: '16bit' },
  { value: 24, label: '24bit' },
  { value: 32, label: '32bit' },
];

export function AIRepairPanel({
  params,
  analysis,
  selectedMode,
  modes,
  processingOptions,
  algorithmVersion,
  availableAlgorithms,
  onAlgorithmChange,
  onParamChange,
  onReset,
  onModeSelect,
  onApply,
  onOptionsChange,
  disabled,
}: AIRepairPanelProps) {
  const [showParams, setShowParams] = useState(false);

  const paramLabels: Record<keyof AIRepairParams, string> = {
    deClipping: '去削波',
    noiseReduction: '降噪',
    deEssing: '去齿音',
    deCrackle: '去毛刺',
    dePop: '去爆音',
    harmonicEnhance: '谐波增强',
    dynamicRange: '动态范围',
    softness: '柔和处理',
    presenceBoost: '临场增强',
    bassEnhance: '低音增强',
    spatialEnhance: '空间感',
    transientRepair: '瞬态修复',
  };

  const paramKeys = Object.keys(paramLabels) as (keyof AIRepairParams)[];

  return (
    <div className="bg-gradient-to-br from-primary/80 to-dark/80 rounded-xl p-5 border border-secondary/20">
      <h3 className="text-white font-bold mb-4 flex items-center gap-2">
        <svg className="w-5 h-5 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
        AI音频修复
      </h3>

      {analysis && (
        <div className="mb-4 p-3 bg-black/30 rounded-lg">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-gray-400">频谱平坦度: </span>
              <span className={analysis.spectralFlatness > 0.6 ? 'text-warning' : 'text-white'}>
                {(analysis.spectralFlatness * 100).toFixed(0)}%
              </span>
            </div>
            <div>
              <span className="text-gray-400">动态范围: </span>
              <span className="text-white">{analysis.dynamicRange.toFixed(1)} dB</span>
            </div>
            <div>
              <span className="text-gray-400">峰值电平: </span>
              <span className="text-white">{(analysis.peakLevel * 100).toFixed(0)}%</span>
            </div>
            <div>
              <span className="text-gray-400">立体声: </span>
              <span className="text-white">{analysis.stereoBalance.toFixed(2)}</span>
            </div>
          </div>
          {analysis.issues.length > 0 && (
            <div className="mt-2">
              <span className="text-warning text-xs">问题: </span>
              <span className="text-gray-300 text-xs">{analysis.issues.join('、')}</span>
            </div>
          )}
        </div>
      )}

      {availableAlgorithms.length > 0 && (
        <div className="mb-4 p-3 bg-gradient-to-r from-cyan-900/30 to-purple-900/30 rounded-lg border border-cyan-500/20">
          <div className="flex items-center justify-between">
            <h4 className="text-cyan-400 text-sm font-medium flex items-center gap-1.5">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
              </svg>
              算法版本
            </h4>
            <div className="relative">
              <select
                value={algorithmVersion}
                onChange={(e) => onAlgorithmChange(e.target.value)}
                disabled={disabled}
                className="appearance-none bg-cyan-500/20 text-white text-sm font-medium py-1.5 pl-3 pr-8 rounded-lg border border-cyan-400/40 focus:outline-none focus:border-cyan-400 cursor-pointer hover:bg-cyan-500/30 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {availableAlgorithms.map((algo) => (
                  <option key={algo.name} value={algo.name} className="bg-gray-900 text-white">
                    {algo.label} — {algo.description}
                  </option>
                ))}
              </select>
              <svg className="w-4 h-4 text-cyan-400 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>
        </div>
      )}

      <div className="mb-4">
        <h4 className="text-secondary text-sm font-medium mb-3">预设模式</h4>
        <div className="grid grid-cols-2 gap-2">
          {modes.map((mode) => (
            <button
              key={mode.name}
              onClick={() => onModeSelect(mode)}
              disabled={disabled}
              className={`relative p-3 rounded-xl text-left transition-all duration-300
                ${selectedMode === mode.name
                  ? 'bg-gradient-to-br from-secondary/30 to-accent/30 border-2 border-secondary shadow-lg shadow-secondary/20'
                  : 'bg-gray-800/50 hover:bg-gray-800 border-2 border-transparent hover:border-gray-700'
                }
                ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
              `}
            >
              <div className="text-2xl mb-1">{mode.icon}</div>
              <div className="text-white font-medium text-sm">{mode.name}</div>
              <div className="text-gray-400 text-xs mt-1 line-clamp-2">{mode.description}</div>
              {selectedMode === mode.name && (
                <div className="absolute top-2 right-2">
                  <svg className="w-4 h-4 text-secondary" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                </div>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-4 p-3 bg-black/20 rounded-lg">
        <h4 className="text-secondary text-sm font-medium mb-3">处理选项</h4>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-gray-400 text-xs mb-2 block">目标采样率</label>
            <div className="flex gap-1">
              {sampleRateOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => onOptionsChange?.({ ...processingOptions, sampleRate: option.value })}
                  disabled={disabled}
                  className={`flex-1 py-1.5 px-2 rounded-lg text-xs transition-all ${
                    processingOptions.sampleRate === option.value
                      ? 'bg-secondary/30 text-white border border-secondary/50'
                      : 'bg-primary/30 text-gray-400 border border-gray-700 hover:border-secondary/30'
                  } ${disabled ? 'opacity-50' : ''}`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-gray-400 text-xs mb-2 block">位深</label>
            <div className="flex gap-1">
              {bitDepthOptions.map((option) => (
                <button
                  key={option.value}
                  onClick={() => onOptionsChange?.({ ...processingOptions, bitDepth: option.value })}
                  disabled={disabled}
                  className={`flex-1 py-1.5 px-2 rounded-lg text-xs transition-all ${
                    processingOptions.bitDepth === option.value
                      ? 'bg-secondary/30 text-white border border-secondary/50'
                      : 'bg-primary/30 text-gray-400 border border-gray-700 hover:border-secondary/30'
                  } ${disabled ? 'opacity-50' : ''}`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        <p className="text-gray-500 text-xs mt-2">采样率和位深在修复时应用，修改后需重新修复</p>
      </div>

      <div className="mb-4">
        <button
          onClick={() => setShowParams(!showParams)}
          className="w-full flex items-center justify-between py-2 px-3 bg-black/20 rounded-lg hover:bg-black/30 transition"
        >
          <span className="text-secondary text-sm font-medium">修复参数</span>
          <svg
            className={`w-4 h-4 text-gray-400 transition-transform ${showParams ? 'rotate-180' : ''}`}
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {showParams && (
          <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
            {paramKeys.map((key) => (
              <div key={key}>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-gray-300 text-xs font-medium">
                    {paramLabels[key]}
                  </label>
                  <span className="text-secondary text-xs">
                    {(params[key] ?? 0).toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={params[key] ?? 0}
                  onChange={(e) => onParamChange(key, parseFloat(e.target.value))}
                  disabled={disabled}
                  className="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer slider-accent"
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <button
          onClick={onReset}
          disabled={disabled}
          className={`px-4 py-2.5 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition text-sm
            ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          `}
        >
          重置
        </button>
        <button
          onClick={onApply}
          disabled={disabled}
          className={`px-4 py-2.5 bg-gradient-to-r from-cyan-500 to-purple-500 hover:from-cyan-400 hover:to-purple-400 text-white rounded-lg transition shadow-lg shadow-cyan-500/20 text-sm font-medium
            ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          `}
        >
          开始修复
        </button>
      </div>
    </div>
  );
}

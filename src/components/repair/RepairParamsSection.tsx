import React, { useState } from 'react';
import { AIRepairParams } from '../../utils/advancedAudioProcessing';
import { VocalRepairParams, InstrumentRepairParams } from '../../services/backendApi';

interface RepairParamsSectionProps {
  isDualTrackMode: boolean;
  params: AIRepairParams;
  vocalParams?: VocalRepairParams;
  accompanimentParams?: InstrumentRepairParams;
  mixRatio: number;
  speed: number;
  onParamChange: (key: keyof AIRepairParams, value: number) => void;
  onVocalParamChange?: (key: keyof VocalRepairParams, value: number) => void;
  onAccompanimentParamChange?: (key: keyof InstrumentRepairParams, value: number) => void;
  onMixRatioChange?: (ratio: number) => void;
  onSpeedChange?: (speed: number) => void;
  onSaveProfile?: (name: string) => void;
  disabled?: boolean;
}

const vocalParamLabels: Record<keyof VocalRepairParams, string> = {
  deClipping: '去削波',
  dePop: '去爆音',
  formantRepair: '口型修复',
  deEssing: '齿音抑制',
  breathEnhance: '气息增强',
  aiRepair: 'AI 修复',
  bassEnhance: '低音增强',
  airTexture: '空气质感',
  loudness: '响度优化',
  exciter: '激励器',
  compressor: '压缩器',
  spatial: '空间感',
  warmth: '温暖度',
  smartCompressor: '智能压缩',
  transientAware: '瞬态感知',
  resonanceSuppress: '共振抑制',
  aiRepairAdaptive: '自适应AI修复',
  exciterImproved: '改进激励器',
  deEsserImproved: '改进齿音抑制',
  speed: '速度',
};

const instParamLabels: Record<keyof InstrumentRepairParams, string> = {
  deClipping: '去削波',
  dePop: '去爆音',
  timbreProtect: '音色保护',
  dynamicRange: '动态控制',
  noiseReduction: '降噪',
  spatialEnhance: '空间增强',
  warmth: '温暖度',
  loudness: '响度优化',
  stereo_enhance: '立体声增强',
  exciter: '激励器',
  transient: '瞬态感知',
  resonance: '共振抑制',
  bassEnhance: '低音增强',
  airTexture: '空气感',
  speed: '速度',
};

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
  warmth: '温暖度',
  clarity: '清晰度',
  exciter: '激励器',
  compressor: '压缩器',
  smartCompressor: '智能压缩',
  transientAware: '瞬态感知',
  resonanceSuppress: '共振抑制',
  aiRepairAdaptive: '自适应AI修复',
  airTexture: '空气感',
  loudnessOptimize: '响度优化',
};

const basicParamKeys: (keyof AIRepairParams)[] = [
  'deClipping', 'noiseReduction', 'deEssing', 'dePop',
  'bassEnhance', 'dynamicRange', 'transientRepair', 'clarity',
];

const proParamKeys: (keyof AIRepairParams)[] = [
  'exciter', 'compressor', 'smartCompressor', 'transientAware',
  'resonanceSuppress', 'aiRepairAdaptive', 'airTexture', 'loudnessOptimize',
  'warmth', 'harmonicEnhance', 'presenceBoost', 'spatialEnhance', 'deCrackle', 'softness',
];

function ParamSlider({
  label,
  value,
  onChange,
  disabled,
  labelColor = 'text-gray-300',
  valueColor = 'text-secondary',
  height = 'h-1.5',
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  disabled?: boolean;
  labelColor?: string;
  valueColor?: string;
  height?: string;
}) {
  return (
    <div>
      <div className="flex justify-between items-center mb-1">
        <label className={`${labelColor} text-xs font-medium`}>
          {label}
        </label>
        <span className={`${valueColor} text-xs`}>
          {value.toFixed(2)}
        </span>
      </div>
      <input
        type="range" min="0" max="1" step="0.01"
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        disabled={disabled}
        className={`w-full ${height} bg-gray-700 rounded-lg appearance-none cursor-pointer slider-accent`}
      />
    </div>
  );
}

export function RepairParamsSection({
  isDualTrackMode,
  params,
  vocalParams,
  accompanimentParams,
  mixRatio,
  speed,
  onParamChange,
  onVocalParamChange,
  onAccompanimentParamChange,
  onMixRatioChange,
  onSpeedChange,
  onSaveProfile,
  disabled,
}: RepairParamsSectionProps) {
  const [showParams, setShowParams] = useState<boolean | string>(false);
  const [showProParams, setShowProParams] = useState(false);

  const vocalParamKeys = (Object.keys(vocalParamLabels) as (keyof VocalRepairParams)[]).filter(k => k !== 'speed');
  const instParamKeys = (Object.keys(instParamLabels) as (keyof InstrumentRepairParams)[]).filter(k => k !== 'speed');

  if (isDualTrackMode) {
    return (
      <div className="mb-4 space-y-3">
        <div>
          <button
            onClick={() => setShowParams(showParams === 'vocal' ? false : 'vocal')}
            className="w-full flex items-center justify-between py-2 px-3 bg-pink-500/10 rounded-lg hover:bg-pink-500/15 transition border border-pink-500/20"
          >
            <span className="text-pink-400 text-sm font-medium flex items-center gap-1.5">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
              人声参数
            </span>
            <svg
              className={`w-4 h-4 text-pink-400/60 transition-transform ${showParams === 'vocal' ? 'rotate-180' : ''}`}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {showParams === 'vocal' && vocalParams && onVocalParamChange && (
            <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
              {vocalParamKeys.map((key) => (
                <ParamSlider
                  key={key}
                  label={vocalParamLabels[key]}
                  value={vocalParams[key] ?? 0}
                  onChange={(v) => onVocalParamChange(key, v)}
                  disabled={disabled}
                  labelColor="text-pink-300"
                  valueColor="text-pink-400"
                />
              ))}
            </div>
          )}
        </div>

        <div>
          <button
            onClick={() => setShowParams(showParams === 'accompaniment' ? false : 'accompaniment')}
            className="w-full flex items-center justify-between py-2 px-3 bg-purple-500/10 rounded-lg hover:bg-purple-500/15 transition border border-purple-500/20"
          >
            <span className="text-purple-400 text-sm font-medium flex items-center gap-1.5">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
              伴奏参数
            </span>
            <svg
              className={`w-4 h-4 text-purple-400/60 transition-transform ${showParams === 'accompaniment' ? 'rotate-180' : ''}`}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {showParams === 'accompaniment' && accompanimentParams && onAccompanimentParamChange && (
            <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
              {instParamKeys.map((key) => (
                <ParamSlider
                  key={key}
                  label={instParamLabels[key]}
                  value={accompanimentParams[key] ?? 0}
                  onChange={(v) => onAccompanimentParamChange(key, v)}
                  disabled={disabled}
                  labelColor="text-purple-300"
                  valueColor="text-purple-400"
                />
              ))}
            </div>
          )}
        </div>

        <div className="p-3 bg-gradient-to-r from-cyan-500/5 to-blue-500/5 rounded-lg border border-white/5">
          <div className="flex justify-between items-center mb-2">
            <span className="text-gray-300 text-xs font-medium">速度</span>
            <span className="text-xs text-gray-400">
              {speed < 0.8 ? '慢速' : speed > 1.2 ? '快速' : '原速'}
              <span className="ml-1 text-white font-medium">{speed.toFixed(2)}x</span>
            </span>
          </div>
          <div className="relative pt-1 pb-5">
            <input
              type="range"
              min="0"
              max="1"
              step="0.001"
              value={Math.log2(speed / 0.5) / 2}
              onChange={(e) => {
                const pos = parseFloat(e.target.value);
                const newSpeed = 0.5 * Math.pow(4, pos);
                onSpeedChange?.(Math.round(newSpeed * 100) / 100);
              }}
              disabled={disabled}
              className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer slider-accent"
            />
            <div className="absolute left-0 right-0 top-8 text-[10px] text-gray-500 select-none pointer-events-none">
              {[0.5, 0.75, 1.0, 1.25, 1.5, 2.0].map((tick) => {
                const pos = Math.log2(tick / 0.5) / 2;
                return (
                  <div
                    key={tick}
                    className="absolute flex flex-col items-center"
                    style={{ left: `${pos * 100}%`, transform: 'translateX(-50%)' }}
                  >
                    <div className="w-px h-1.5 bg-gray-500/40 mb-0.5" />
                    <span>{tick}x</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div className="p-3 bg-gradient-to-r from-pink-500/5 to-purple-500/5 rounded-lg border border-white/5">
          <div className="flex justify-between items-center mb-2">
            <span className="text-gray-300 text-xs font-medium">混合比例</span>
            <span className="text-xs text-gray-400">
              {mixRatio < 0.3 ? '偏伴奏' : mixRatio > 0.7 ? '偏人声' : '均衡'}
              <span className="ml-1 text-white font-medium">{(mixRatio * 100).toFixed(0)}%</span>
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={mixRatio}
            onChange={(e) => onMixRatioChange?.(parseFloat(e.target.value))}
            disabled={disabled}
            className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer slider-accent"
          />
          <div className="flex justify-between text-[10px] text-gray-500 mt-1">
            <span>纯伴奏</span>
            <span>均衡</span>
            <span>纯人声</span>
          </div>
        </div>
      </div>
    );
  }

  return (
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
        <div className="mt-3">
          <div className="grid grid-cols-2 gap-x-4 gap-y-3">
            {basicParamKeys.map((key) => (
              <ParamSlider
                key={key}
                label={paramLabels[key]}
                value={params[key] ?? 0}
                onChange={(v) => onParamChange(key, v)}
                disabled={disabled}
              />
            ))}
          </div>

          <button
            type="button"
            onClick={() => setShowProParams(!showProParams)}
            className="mt-3 w-full flex items-center justify-between py-1.5 px-2 bg-black/20 rounded-lg hover:bg-black/30 transition text-xs"
          >
            <span className="text-cyan-400/80 font-medium">高级参数（专业用户）</span>
            <svg
              className={`w-3.5 h-3.5 text-gray-400 transition-transform ${showProParams ? 'rotate-180' : ''}`}
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {showProParams && (
            <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-3">
              {proParamKeys.map((key) => (
                <ParamSlider
                  key={key}
                  label={paramLabels[key]}
                  value={params[key] ?? 0}
                  onChange={(v) => onParamChange(key, v)}
                  disabled={disabled}
                  labelColor="text-gray-400"
                />
              ))}
            </div>
          )}
        </div>
      )}

      {onSaveProfile && showParams && (
        <button
          onClick={() => {
            const name = prompt('请输入配置名称：');
            if (name) onSaveProfile(name);
          }}
          className="w-full mb-3 py-2 rounded-lg bg-purple-500/20 hover:bg-purple-500/30 text-purple-400 text-sm font-medium transition"
        >
          💾 保存当前参数为配置
        </button>
      )}
    </div>
  );
}

import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { AIRepairParams, RepairMode } from '../utils/advancedAudioProcessing';
import { ProcessingOptions, AlgorithmVersion, fetchMemoryInfo, MemoryInfoResult, fetchStorageEstimate, StorageEstimateResult, fetchRenderCache, RenderCacheEntry, VocalRepairParams, InstrumentRepairParams, SignalProfile } from '../services/backendApi';
import AlgorithmSelector from './AlgorithmSelector';
import { RepairProfileDisplay } from './repair/RepairProfileDisplay';
import { RepairModeSelector } from './repair/RepairModeSelector';
import { VolumeSlider } from './repair/VolumeSlider';
import { DeliverySpecsSection } from './repair/DeliverySpecsSection';
import { StorageEstimateCard } from './repair/StorageEstimateCard';
import { RenderCacheList } from './repair/RenderCacheList';
import { RepairParamsSection } from './repair/RepairParamsSection';
import { estimateFileSize, DualTrackAudioInfo } from './repair/shared';

interface AIRepairPanelProps {
  params: AIRepairParams;
  fileHash?: string | null;
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
  duration?: number;
  channels?: number;
  backendAvailable?: boolean;
  onSaveProfile?: (name: string) => void;
  taskId?: string | null;
  onRenderCacheRefresh?: (fn: () => Promise<void>) => void;
  cacheTriggerKey?: number;
  onInstantDownload?: (cacheEntry: RenderCacheEntry) => void;
  onRenderCachesLoaded?: (caches: RenderCacheEntry[]) => void;
  isDualTrackMode?: boolean;
  vocalParams?: VocalRepairParams;
  accompanimentParams?: InstrumentRepairParams;
  mixRatio?: number;
  onVocalParamChange?: (key: keyof VocalRepairParams, value: number) => void;
  onAccompanimentParamChange?: (key: keyof InstrumentRepairParams, value: number) => void;
  onMixRatioChange?: (ratio: number) => void;
  speed?: number;
  onSpeedChange?: (speed: number) => void;
  onDualTrackRepair?: () => void;
  dualTrackVocalInfo?: DualTrackAudioInfo | null;
  dualTrackAccompanimentInfo?: DualTrackAudioInfo | null;
  persistedRenderCaches?: RenderCacheEntry[];
  /** v4.0+ 分析驱动管线修复后回传的信号诊断画像（无则不展示）。 */
  repairProfile?: SignalProfile | null;
}

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
  duration = 0,
  channels = 2,
  backendAvailable = false,
  onSaveProfile,
  taskId,
  onRenderCacheRefresh,
  cacheTriggerKey,
  onInstantDownload,
  onRenderCachesLoaded,
  isDualTrackMode = false,
  vocalParams,
  accompanimentParams,
  mixRatio = 0.5,
  speed = 1.0,
  onVocalParamChange,
  onAccompanimentParamChange,
  onMixRatioChange,
  onSpeedChange,
  onDualTrackRepair,
  dualTrackVocalInfo,
  dualTrackAccompanimentInfo,
  persistedRenderCaches,
  repairProfile,
}: AIRepairPanelProps) {
  const outputVolume = processingOptions.outputVolume ?? 0;
  const effectiveDuration = useMemo(() => {
    if (isDualTrackMode && dualTrackVocalInfo && dualTrackAccompanimentInfo) {
      return Math.max(dualTrackVocalInfo.duration, dualTrackAccompanimentInfo.duration);
    }
    return duration;
  }, [isDualTrackMode, duration, dualTrackVocalInfo, dualTrackAccompanimentInfo]);

  const effectiveChannels = useMemo(() => {
    if (isDualTrackMode && dualTrackVocalInfo && dualTrackAccompanimentInfo) {
      return Math.max(dualTrackVocalInfo.channels, dualTrackAccompanimentInfo.channels);
    }
    return channels;
  }, [isDualTrackMode, channels, dualTrackVocalInfo, dualTrackAccompanimentInfo]);
  const filteredAlgorithms = useMemo(() => {
    if (isDualTrackMode) {
      return availableAlgorithms.filter(a => a.supportsDualTrack === true);
    }
    return availableAlgorithms;
  }, [isDualTrackMode, availableAlgorithms]);
  const [memoryInfo, setMemoryInfo] = useState<MemoryInfoResult | null>(null);
  const [storageEstimate, setStorageEstimate] = useState<StorageEstimateResult | null>(null);
  const memoryFetchRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const storageFetchRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [renderCaches, setRenderCaches] = useState<RenderCacheEntry[]>(persistedRenderCaches || []);
  const cacheCheckRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!backendAvailable) {
      setMemoryInfo(null);
      return;
    }
    const fetchDuration = effectiveDuration > 0 ? effectiveDuration : 300;
    const fetchChannels = effectiveChannels > 0 ? effectiveChannels : 2;
    if (memoryFetchRef.current) clearTimeout(memoryFetchRef.current);
    memoryFetchRef.current = setTimeout(() => {
      fetchMemoryInfo(fetchDuration, fetchChannels, processingOptions.sampleRate, algorithmVersion).then(setMemoryInfo);
    }, 300);
    return () => { if (memoryFetchRef.current) clearTimeout(memoryFetchRef.current); };
  }, [effectiveDuration, effectiveChannels, processingOptions.sampleRate, algorithmVersion, backendAvailable]);

  useEffect(() => {
    if (!backendAvailable) {
      setStorageEstimate(null);
      return;
    }
    const fetchDuration = effectiveDuration > 0 ? effectiveDuration : 300;
    const fetchChannels = effectiveChannels > 0 ? effectiveChannels : 2;
    if (storageFetchRef.current) clearTimeout(storageFetchRef.current);
    storageFetchRef.current = setTimeout(() => {
      fetchStorageEstimate(fetchDuration, fetchChannels, processingOptions.sampleRate, processingOptions.bitDepth).then(setStorageEstimate);
    }, 300);
    return () => { if (storageFetchRef.current) clearTimeout(storageFetchRef.current); };
  }, [effectiveDuration, effectiveChannels, processingOptions.sampleRate, processingOptions.bitDepth, backendAvailable]);

  const refreshRenderCache = useCallback(async () => {
    if (!taskId || !backendAvailable) {
      return;
    }
    const caches = await fetchRenderCache(taskId);
    setRenderCaches(caches);
    onRenderCachesLoaded?.(caches);
  }, [taskId, backendAvailable]);

  useEffect(() => {
    if (!taskId || !backendAvailable) {
      return;
    }
    if (cacheCheckRef.current) clearTimeout(cacheCheckRef.current);
    cacheCheckRef.current = setTimeout(refreshRenderCache, 500);
    return () => {
      if (cacheCheckRef.current) clearTimeout(cacheCheckRef.current);
    };
  }, [taskId, backendAvailable, algorithmVersion, refreshRenderCache, cacheTriggerKey]);

  useEffect(() => {
    if (onRenderCacheRefresh) onRenderCacheRefresh(refreshRenderCache);
  }, [refreshRenderCache, onRenderCacheRefresh]);

  const currentEstimate = useMemo(() => {
    if (effectiveDuration <= 0) return null;
    return estimateFileSize(
      effectiveDuration,
      processingOptions.sampleRate,
      processingOptions.bitDepth,
      effectiveChannels
    );
  }, [effectiveDuration, effectiveChannels, processingOptions.sampleRate, processingOptions.bitDepth]);

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

      {repairProfile && <RepairProfileDisplay repairProfile={repairProfile} />}

      {filteredAlgorithms.length > 0 ? (
        <div className="mb-4 p-3 bg-gradient-to-r from-cyan-900/30 to-purple-900/30 rounded-lg border border-cyan-500/20">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-cyan-400 text-sm font-medium flex items-center gap-1.5 shrink-0">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
              </svg>
              算法版本
            </h4>
            <div className="max-w-[240px] sm:max-w-none">
              <AlgorithmSelector
                value={algorithmVersion}
                algorithms={filteredAlgorithms}
                onChange={onAlgorithmChange}
                disabled={disabled}
              />
            </div>
          </div>
        </div>
      ) : (
        <div className="mb-4 p-3 bg-yellow-900/20 rounded-lg border border-yellow-500/20">
          <p className="text-yellow-400/70 text-xs">当前平台暂无可用算法版本，移动端优化版本开发中...</p>
        </div>
      )}

      <RepairModeSelector
        modes={modes}
        selectedMode={selectedMode}
        onModeSelect={onModeSelect}
        disabled={disabled}
      />

      <DeliverySpecsSection
        processingOptions={processingOptions}
        onOptionsChange={onOptionsChange || (() => {})}
        disabled={disabled}
      >
        <VolumeSlider
          outputVolume={outputVolume}
          onChange={(v) => onOptionsChange?.({ ...processingOptions, outputVolume: v })}
          disabled={disabled}
        />
        <StorageEstimateCard
          currentEstimate={currentEstimate}
          storageEstimate={storageEstimate}
          memoryInfo={memoryInfo}
        >
          <RenderCacheList
            renderCaches={renderCaches}
            algorithmVersion={algorithmVersion}
            processingOptions={{ sampleRate: processingOptions.sampleRate, bitDepth: processingOptions.bitDepth }}
            effectiveDuration={effectiveDuration}
            effectiveChannels={effectiveChannels}
            isDualTrackMode={isDualTrackMode}
            onOptionsChange={(opts) => onOptionsChange?.({ ...processingOptions, ...opts })}
            onInstantDownload={onInstantDownload}
            disabled={disabled}
          />
        </StorageEstimateCard>
      </DeliverySpecsSection>

      <RepairParamsSection
        isDualTrackMode={isDualTrackMode}
        params={params}
        vocalParams={vocalParams}
        accompanimentParams={accompanimentParams}
        mixRatio={mixRatio}
        speed={speed}
        onParamChange={onParamChange}
        onVocalParamChange={onVocalParamChange}
        onAccompanimentParamChange={onAccompanimentParamChange}
        onMixRatioChange={onMixRatioChange}
        onSpeedChange={onSpeedChange}
        onSaveProfile={onSaveProfile}
        disabled={disabled}
      />

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
          onClick={isDualTrackMode ? onDualTrackRepair : onApply}
          disabled={disabled || (isDualTrackMode && !onDualTrackRepair)}
          className={`px-4 py-2.5 bg-gradient-to-r ${isDualTrackMode ? 'from-pink-500 to-purple-500 hover:from-pink-400 hover:to-purple-400 shadow-pink-500/20' : 'from-cyan-500 to-purple-500 hover:from-cyan-400 hover:to-purple-400 shadow-cyan-500/20'} text-white rounded-lg transition shadow-lg text-sm font-medium
            ${disabled || (isDualTrackMode && !onDualTrackRepair) ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          `}
        >
          {isDualTrackMode ? '双轨修复' : '开始修复'}
        </button>
      </div>
    </div>
  );
}

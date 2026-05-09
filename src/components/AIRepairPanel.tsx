import React, { useState, useMemo, useEffect, useRef } from 'react';
import { AIRepairParams, RepairMode } from '../utils/advancedAudioProcessing';
import { ProcessingOptions, AlgorithmVersion, fetchMemoryInfo, MemoryInfoResult, fetchStorageEstimate, StorageEstimateResult } from '../services/backendApi';

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
  enableBrowserRepair: boolean;
  onAlgorithmChange: (version: string) => void;
  onParamChange: (key: keyof AIRepairParams, value: number) => void;
  onReset: () => void;
  onModeSelect: (mode: RepairMode) => void;
  onApply?: () => void;
  onOptionsChange?: (options: ProcessingOptions) => void;
  onEnableBrowserRepairChange?: (enabled: boolean) => void;
  disabled?: boolean;
  duration?: number;
  channels?: number;
}

const sampleRateOptions = [
  { value: 44100, label: '44.1k', recommended: true },
  { value: 48000, label: '48k', recommended: true },
  { value: 96000, label: '96k', recommended: false },
];

const bitDepthOptions: { value: 16 | 24 | 32; label: string; recommended?: boolean }[] = [
  { value: 16, label: '16bit', recommended: false },
  { value: 24, label: '24bit', recommended: true },
  { value: 32, label: '32bit', recommended: false },
];

// 平台检测
const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

// 计算预估文件大小（MB）
function estimateFileSize(
  duration: number,
  sampleRate: number,
  bitDepth: number,
  channels: number
): { size: number; sizeMiB: number; sizeMB: number } {
  // 原始字节数 = 采样率 × 时长 × 位深/8 × 通道数
  const bytes = sampleRate * duration * (bitDepth / 8) * channels;
  // WAV文件头约44字节
  const totalBytes = bytes + 44;
  // MiB (1024进制) - 操作系统显示的大小
  const sizeMiB = totalBytes / (1024 * 1024);
  // MB (1000进制) - 存储厂商使用
  const sizeMB = totalBytes / (1000 * 1000);
  // 返回MB值（根据平台选择）
  const size = isMobile ? sizeMB : sizeMiB;
  return { size, sizeMiB, sizeMB };
}

// 格式化大小显示
function formatSize(size: number, sizeMiB: number, sizeMB: number): string {
  if (isMobile) {
    // 移动端显示MB（1000进制），因为存储厂商使用此标准
    return `${sizeMB.toFixed(1)} MB`;
  }
  // 桌面端显示MiB（1024进制），因为操作系统使用此标准
  return `${sizeMiB.toFixed(1)} MiB (${sizeMB.toFixed(1)} MB)`;
}

// 判断是否为推荐组合
function isRecommendedCombo(sampleRate: number, bitDepth: number): boolean {
  // 推荐组合：48k/24bit 或 44.1k/24bit
  return (sampleRate === 48000 || sampleRate === 44100) && bitDepth === 24;
}

// 警告阈值 186MB（留出余量）
const WARNING_THRESHOLD_MB = 186;

export function AIRepairPanel({
  params,
  analysis,
  selectedMode,
  modes,
  processingOptions,
  algorithmVersion,
  availableAlgorithms,
  enableBrowserRepair,
  onAlgorithmChange,
  onParamChange,
  onReset,
  onModeSelect,
  onApply,
  onOptionsChange,
  onEnableBrowserRepairChange,
  disabled,
  duration = 0,
  channels = 2,
}: AIRepairPanelProps) {
  const [showParams, setShowParams] = useState(false);
  const [memoryInfo, setMemoryInfo] = useState<MemoryInfoResult | null>(null);
  const [storageEstimate, setStorageEstimate] = useState<StorageEstimateResult | null>(null);
  const memoryFetchRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const storageFetchRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (duration <= 0) {
      setMemoryInfo(null);
      return;
    }
    if (memoryFetchRef.current) clearTimeout(memoryFetchRef.current);
    memoryFetchRef.current = setTimeout(() => {
      fetchMemoryInfo(duration, channels, processingOptions.sampleRate, algorithmVersion).then(setMemoryInfo);
    }, 300);
    return () => { if (memoryFetchRef.current) clearTimeout(memoryFetchRef.current); };
  }, [duration, channels, processingOptions.sampleRate, algorithmVersion]);

  useEffect(() => {
    if (duration <= 0) {
      setStorageEstimate(null);
      return;
    }
    if (storageFetchRef.current) clearTimeout(storageFetchRef.current);
    storageFetchRef.current = setTimeout(() => {
      fetchStorageEstimate(duration, channels, processingOptions.sampleRate, processingOptions.bitDepth).then(setStorageEstimate);
    }, 300);
    return () => { if (storageFetchRef.current) clearTimeout(storageFetchRef.current); };
  }, [duration, channels, processingOptions.sampleRate, processingOptions.bitDepth]);

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
  };

  const paramKeys = Object.keys(paramLabels) as (keyof AIRepairParams)[];

  // 计算当前预估大小
  const currentEstimate = useMemo(() => {
    if (duration <= 0) return null;
    return estimateFileSize(
      duration,
      processingOptions.sampleRate,
      processingOptions.bitDepth,
      channels
    );
  }, [duration, processingOptions.sampleRate, processingOptions.bitDepth, channels]);

  // 计算所有组合的预估大小
  const allEstimates = useMemo(() => {
    if (duration <= 0) return [];
    const estimates: Array<{
      sampleRate: number;
      bitDepth: number;
      size: number;
      sizeMiB: number;
      sizeMB: number;
      isWarning: boolean;
      isRecommended: boolean;
    }> = [];

    for (const sr of sampleRateOptions) {
      for (const bd of bitDepthOptions) {
        const est = estimateFileSize(duration, sr.value, bd.value, channels);
        estimates.push({
          sampleRate: sr.value,
          bitDepth: bd.value,
          ...est,
          isWarning: est.size > WARNING_THRESHOLD_MB,
          isRecommended: isRecommendedCombo(sr.value, bd.value),
        });
      }
    }
    return estimates;
  }, [duration, channels]);

  // 检查当前选择是否警告
  const isCurrentWarning = currentEstimate ? currentEstimate.size > WARNING_THRESHOLD_MB : false;

  // 获取当前选择的详细信息
  const currentCombo = allEstimates.find(
    e => e.sampleRate === processingOptions.sampleRate && e.bitDepth === processingOptions.bitDepth
  );

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

      {availableAlgorithms.length > 0 ? (
        <div className="mb-4 p-3 bg-gradient-to-r from-cyan-900/30 to-purple-900/30 rounded-lg border border-cyan-500/20">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-cyan-400 text-sm font-medium flex items-center gap-1.5 shrink-0">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
              </svg>
              算法版本
            </h4>
            <div className="relative max-w-[200px] sm:max-w-none">
              <select
                value={algorithmVersion}
                onChange={(e) => onAlgorithmChange(e.target.value)}
                disabled={disabled}
                className="appearance-none bg-cyan-500/20 text-white text-sm font-medium py-1.5 pl-3 pr-8 rounded-lg border border-cyan-400/40 focus:outline-none focus:border-cyan-400 cursor-pointer hover:bg-cyan-500/30 transition disabled:opacity-50 disabled:cursor-not-allowed w-full truncate"
              >
                {[...availableAlgorithms].reverse().map((algo) => (
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
      ) : (
        <div className="mb-4 p-3 bg-yellow-900/20 rounded-lg border border-yellow-500/20">
          <p className="text-yellow-400/70 text-xs">当前平台暂无可用算法版本，移动端优化版本开发中...</p>
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
        <h4 className="text-secondary text-sm font-medium mb-3">交付规格</h4>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-gray-400 text-xs mb-2 block flex items-center gap-1">
              目标采样率
              {/* 推荐标记 */}
              {sampleRateOptions.find(o => o.value === processingOptions.sampleRate)?.recommended && (
                <span className="text-emerald-400 text-[10px] bg-emerald-500/20 px-1 rounded">推荐</span>
              )}
            </label>
            <div className="flex gap-1">
              {sampleRateOptions.map((option) => {
                const isSelected = processingOptions.sampleRate === option.value;
                const isRecommended = option.recommended;
                // 检查与当前位深的组合是否推荐
                const comboRecommended = isRecommended && processingOptions.bitDepth === 24;

                return (
                  <button
                    key={option.value}
                    onClick={() => onOptionsChange?.({ ...processingOptions, sampleRate: option.value })}
                    disabled={disabled}
                    className={`flex-1 py-1.5 px-2 rounded-lg text-xs transition-all relative
                      ${isSelected
                        ? 'bg-secondary/30 text-white border border-secondary/50'
                        : isRecommended
                          ? 'bg-primary/30 text-gray-300 border border-emerald-500/30 hover:border-emerald-400/50'
                          : 'bg-primary/30 text-gray-400 border border-gray-700 hover:border-secondary/30'
                      } ${disabled ? 'opacity-50' : ''}
                    `}
                  >
                    {option.label}
                    {/* 推荐小圆点 */}
                    {!isSelected && isRecommended && (
                      <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-emerald-500 rounded-full" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
          <div>
            <label className="text-gray-400 text-xs mb-2 block flex items-center gap-1">
              位深
              {/* 推荐标记 */}
              {processingOptions.bitDepth === 24 && (
                <span className="text-emerald-400 text-[10px] bg-emerald-500/20 px-1 rounded">推荐</span>
              )}
            </label>
            <div className="flex gap-1">
              {bitDepthOptions.map((option) => {
                const isSelected = processingOptions.bitDepth === option.value;
                const isRecommended = option.recommended;
                // 检查与当前采样率的组合是否推荐
                const comboRecommended = isRecommended &&
                  (processingOptions.sampleRate === 44100 || processingOptions.sampleRate === 48000);

                return (
                  <button
                    key={option.value}
                    onClick={() => onOptionsChange?.({ ...processingOptions, bitDepth: option.value })}
                    disabled={disabled}
                    className={`flex-1 py-1.5 px-2 rounded-lg text-xs transition-all relative
                      ${isSelected
                        ? 'bg-secondary/30 text-white border border-secondary/50'
                        : isRecommended
                          ? 'bg-primary/30 text-gray-300 border border-emerald-500/30 hover:border-emerald-400/50'
                          : 'bg-primary/30 text-gray-400 border border-gray-700 hover:border-secondary/30'
                      } ${disabled ? 'opacity-50' : ''}
                    `}
                  >
                    {option.label}
                    {/* 推荐小圆点 */}
                    {!isSelected && isRecommended && (
                      <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-emerald-500 rounded-full" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* 预估输出大小 */}
        {duration > 0 && storageEstimate && (
          <div className="mt-3 p-2.5 rounded-lg border bg-gray-800/50 border-gray-700">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="text-sm font-medium text-gray-300">
                  预估输出大小
                </span>
              </div>
              <span className="text-sm font-bold text-white">
                {storageEstimate.estimated_output_mb} MB
              </span>
            </div>

            {/* 各组合大小参考 */}
            <div className="mt-3 pt-2 border-t border-gray-700/50">
              <div className="text-[10px] text-gray-500 mb-1.5">各组合预估大小参考：</div>
              <div className="grid grid-cols-3 gap-1 text-[10px]">
                {allEstimates.map((est) => {
                  const isCurrent = est.sampleRate === processingOptions.sampleRate && est.bitDepth === processingOptions.bitDepth;
                  return (
                    <div
                      key={`${est.sampleRate}-${est.bitDepth}`}
                      className={`px-1.5 py-1 rounded text-center ${
                        isCurrent
                          ? 'bg-secondary/30 text-white border border-secondary/50'
                          : est.isWarning
                            ? 'bg-red-500/10 text-red-400/70'
                            : est.isRecommended
                              ? 'bg-emerald-500/10 text-emerald-400/70'
                              : 'bg-gray-800/50 text-gray-500'
                      }`}
                    >
                      <div className="font-medium">{est.sampleRate / 1000}k/{est.bitDepth}bit</div>
                      <div>{isMobile ? est.sizeMB.toFixed(0) : est.sizeMiB.toFixed(0)}{isMobile ? 'MB' : 'MiB'}</div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* 服务器内存状态 */}
            {memoryInfo && (
              <div className={`mt-3 pt-2 border-t border-gray-700/50 ${
                memoryInfo.is_sufficient ? '' : (memoryInfo.available_memory_bytes != null && memoryInfo.estimated_memory_bytes > memoryInfo.available_memory_bytes) ? 'text-red-400' : 'text-amber-400'
              }`}>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-400 flex items-center gap-1">
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
                    </svg>
                    服务器内存
                  </span>
                  <span className={memoryInfo.is_sufficient ? 'text-emerald-400' : (memoryInfo.available_memory_bytes != null && memoryInfo.estimated_memory_bytes > memoryInfo.available_memory_bytes) ? 'text-red-400' : 'text-amber-400'}>
                    {memoryInfo.available_memory_bytes != null
                      ? `${(memoryInfo.available_memory_bytes / 1024 / 1024).toFixed(0)} MB 可用`
                      : '未知'}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs mt-1">
                  <span className="text-gray-400 flex items-center gap-1.5">
                    预估处理占用
                    {memoryInfo.memory_saving > 0 && (
                      <span className="inline-flex items-center gap-0.5 text-[10px] bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded-full font-medium">
                        <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                        </svg>
                        -{Math.round(memoryInfo.memory_saving * 100)}%
                      </span>
                    )}
                  </span>
                  <span className={memoryInfo.is_sufficient ? 'text-gray-300' : (memoryInfo.available_memory_bytes != null && memoryInfo.estimated_memory_bytes > memoryInfo.available_memory_bytes) ? 'text-red-400' : 'text-amber-400'}>
                    {(memoryInfo.estimated_memory_bytes / 1024 / 1024).toFixed(0)} MB
                  </span>
                </div>
                {(memoryInfo.has_streaming || memoryInfo.use_float32) && (
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {memoryInfo.has_streaming && (
                      <span className="text-[10px] bg-cyan-500/15 text-cyan-400 px-1.5 py-0.5 rounded">
                        流式分块处理
                      </span>
                    )}
                    {memoryInfo.use_float32 && (
                      <span className="text-[10px] bg-blue-500/15 text-blue-400 px-1.5 py-0.5 rounded">
                        Float32 自动降精度
                      </span>
                    )}
                  </div>
                )}
                {memoryInfo.available_memory_bytes != null && memoryInfo.estimated_memory_bytes > memoryInfo.available_memory_bytes && (
                  <div className="mt-1.5 text-[10px] text-red-400/90">
                    🔴 内存不足！预估占用超出可用内存，处理将失败。请选择低内存算法或缩短音频。
                  </div>
                )}
                {!memoryInfo.is_sufficient && !(memoryInfo.available_memory_bytes != null && memoryInfo.estimated_memory_bytes > memoryInfo.available_memory_bytes) && (
                  <div className="mt-1.5 text-[10px] text-amber-400/90">
                    ⚠️ 服务器可用内存偏低，可能导致处理失败
                  </div>
                )}
                {memoryInfo.total_memory_bytes != null && (
                  <div className="mt-2">
                    <div className="h-2.5 bg-gray-700 rounded-full overflow-hidden flex">
                      {memoryInfo.used_memory_bytes != null && (
                        <div
                          className="h-full bg-gray-500/60 transition-all"
                          style={{
                            width: `${Math.min(100, (memoryInfo.used_memory_bytes / memoryInfo.total_memory_bytes) * 100)}%`,
                          }}
                        />
                      )}
                      <div
                        className={`h-full transition-all ${
                          memoryInfo.is_sufficient ? 'bg-emerald-500' : (memoryInfo.available_memory_bytes != null && memoryInfo.estimated_memory_bytes > memoryInfo.available_memory_bytes) ? 'bg-red-500' : 'bg-amber-500'
                        }`}
                        style={{
                          width: `${Math.min(100, (memoryInfo.estimated_memory_bytes / memoryInfo.total_memory_bytes) * 100)}%`,
                        }}
                      />
                    </div>
                    <div className="flex items-center justify-between text-[9px] text-gray-500 mt-0.5">
                      <div className="flex items-center gap-2">
                        <span className="flex items-center gap-0.5">
                          <span className="inline-block w-1.5 h-1.5 rounded-sm bg-gray-500/60" />
                          已用
                        </span>
                        <span className="flex items-center gap-0.5">
                          <span className={`inline-block w-1.5 h-1.5 rounded-sm ${memoryInfo.is_sufficient ? 'bg-emerald-500' : (memoryInfo.available_memory_bytes != null && memoryInfo.estimated_memory_bytes > memoryInfo.available_memory_bytes) ? 'bg-red-500' : 'bg-amber-500'}`} />
                          预估
                        </span>
                      </div>
                      <span>{(memoryInfo.total_memory_bytes / 1024 / 1024).toFixed(0)} MB</span>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <p className="text-gray-500 text-xs mt-2">交付规格在导出时应用，修改后即时渲染无需重新修复</p>
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

      <div className="mb-3">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={enableBrowserRepair}
            onChange={(e) => onEnableBrowserRepairChange?.(e.target.checked)}
            disabled={disabled}
            className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-cyan-500 focus:ring-cyan-500 focus:ring-offset-0"
          />
          <span className="text-gray-300 text-sm">同时进行浏览器修复</span>
        </label>
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

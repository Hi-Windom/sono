import React, { useState, useMemo, useCallback } from 'react';
import { useDualTrackStore } from '../store/dualTrackStore';
import { useDualTrackProcessor } from '../hooks/useDualTrackProcessor';
import { AIRepairParams } from '../utils/advancedAudioProcessing';
import {
  ProcessingOptions,
  VocalRepairParams,
  InstrumentRepairParams,
  defaultVocalRepairParams,
  defaultInstrumentRepairParams,
  AlgorithmVersion,
} from '../services/backendApi';

interface DualTrackPanelProps {
  params: AIRepairParams;
  processingOptions: ProcessingOptions;
  algorithmVersion: string;
  availableAlgorithms: AlgorithmVersion[];
  onAlgorithmChange: (version: string) => void;
  onParamChange: (key: keyof AIRepairParams, value: number) => void;
}

const sampleRateOptions = [
  { value: 44100, label: '44.1k', recommended: false },
  { value: 48000, label: '48k', recommended: true },
  { value: 96000, label: '96k', recommended: false },
];

const bitDepthOptions: { value: 16 | 24 | 32; label: string; recommended?: boolean }[] = [
  { value: 16, label: '16bit', recommended: false },
  { value: 24, label: '24bit', recommended: true },
  { value: 32, label: '32bit', recommended: false },
];

const WARNING_THRESHOLD_MB = 1000;

function estimateFileSize(
  duration: number,
  sampleRate: number,
  bitDepth: number,
  channels: number
): { size: number; sizeMiB: number; sizeMB: number } {
  const bytes = sampleRate * duration * (bitDepth / 8) * channels;
  const totalBytes = bytes + 44;
  const sizeMiB = totalBytes / (1024 * 1024);
  const sizeMB = totalBytes / (1000 * 1000);
  return { size: sizeMB, sizeMiB, sizeMB };
}

function isRecommendedCombo(sampleRate: number, bitDepth: number): boolean {
  return sampleRate === 48000 && bitDepth === 24;
}

export const DualTrackPanel: React.FC<DualTrackPanelProps> = ({
  params,
  processingOptions,
  algorithmVersion,
  availableAlgorithms,
  onAlgorithmChange,
  onParamChange,
}) => {
  const store = useDualTrackStore();
  const processor = useDualTrackProcessor();

  const [vocalParams, setVocalParams] = useState<VocalRepairParams>(defaultVocalRepairParams);
  const [accompanimentParams, setAccompanimentParams] = useState<InstrumentRepairParams>(defaultInstrumentRepairParams);
  const [mixRatio, setMixRatio] = useState(50);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [pendingVocal, setPendingVocal] = useState<File | null>(null);
  const [pendingAccompaniment, setPendingAccompaniment] = useState<File | null>(null);

  const {
    uploadStatus,
    uploadProgress,
    uploadStep,
    vocalFileName,
    accompanimentFileName,
    vocalInfo,
    accompanimentInfo,
    repairStatus,
    repairProgress,
    repairStep,
    repairError,
    renderStatus,
    renderProgress,
    renderStep,
    renderCaches,
    cacheHit,
    showCacheModal,
  } = store;

  const effectiveDuration = useMemo(() => {
    if (vocalInfo && accompanimentInfo) {
      return Math.max(vocalInfo.duration, accompanimentInfo.duration);
    }
    return 0;
  }, [vocalInfo, accompanimentInfo]);

  const effectiveChannels = useMemo(() => {
    if (vocalInfo && accompanimentInfo) {
      return Math.max(vocalInfo.channels, accompanimentInfo.channels);
    }
    return 2;
  }, [vocalInfo, accompanimentInfo]);

  const filteredAlgorithms = useMemo(() => {
    return availableAlgorithms.filter(
      algo => algo.name === 'v3.0' || algo.name === 'v3.0a' || algo.name === 'v3.1' || algo.name === 'v3.1a'
    );
  }, [availableAlgorithms]);

  const allEstimates = useMemo(() => {
    if (effectiveDuration <= 0) return [];
    return sampleRateOptions.flatMap(sr =>
      bitDepthOptions.map(bd => {
        const est = estimateFileSize(effectiveDuration, sr.value, bd.value, effectiveChannels);
        return {
          sampleRate: sr.value,
          bitDepth: bd.value,
          ...est,
          isWarning: est.size > WARNING_THRESHOLD_MB,
          isRecommended: isRecommendedCombo(sr.value, bd.value),
        };
      })
    );
  }, [effectiveDuration, effectiveChannels]);

  const currentEstimate = useMemo(() => {
    if (effectiveDuration <= 0) return null;
    return estimateFileSize(
      effectiveDuration,
      processingOptions.sampleRate,
      processingOptions.bitDepth,
      effectiveChannels
    );
  }, [effectiveDuration, effectiveChannels, processingOptions.sampleRate, processingOptions.bitDepth]);

  const handleVocalSelect = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setPendingVocal(file);

    if (pendingAccompaniment) {
      try {
        await processor.upload(file, pendingAccompaniment);
        await processor.checkCache(params, processingOptions, algorithmVersion);
      } catch (e) {
        console.error('双轨上传失败:', e);
      }
    }
  }, [processor, params, processingOptions, algorithmVersion, pendingAccompaniment]);

  const handleAccompanimentSelect = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setPendingAccompaniment(file);

    if (pendingVocal) {
      try {
        await processor.upload(pendingVocal, file);
        await processor.checkCache(params, processingOptions, algorithmVersion);
      } catch (e) {
        console.error('双轨上传失败:', e);
      }
    }
  }, [processor, params, processingOptions, algorithmVersion, pendingVocal]);

  const handleRepair = useCallback(async () => {
    try {
      await processor.repair(
        params,
        processingOptions,
        algorithmVersion,
        vocalParams,
        accompanimentParams,
        mixRatio / 100
      );
    } catch (e) {
      console.error('双轨修复失败:', e);
    }
  }, [processor, params, processingOptions, algorithmVersion, vocalParams, accompanimentParams, mixRatio]);

  const handleReset = useCallback(() => {
    processor.reset();
    setVocalParams(defaultVocalRepairParams);
    setAccompanimentParams(defaultInstrumentRepairParams);
    setMixRatio(50);
    setPendingVocal(null);
    setPendingAccompaniment(null);
  }, [processor]);

  const handleUseCache = useCallback(async () => {
    if (cacheHit?.task_id) {
      await processor.useRepairCache(cacheHit.task_id);
    }
  }, [processor, cacheHit]);

  const isProcessing = repairStatus === 'repairing' || renderStatus === 'rendering';
  const hasVocal = !!vocalFileName;
  const hasAccompaniment = !!accompanimentFileName;
  const bothUploaded = hasVocal && hasAccompaniment;
  const canRepair = bothUploaded && repairStatus === 'idle' && !isProcessing;

  const UploadZone = ({
    label,
    icon,
    fileName,
    fileInfo,
    onChange,
    disabled,
  }: {
    label: string;
    icon: string;
    fileName?: string;
    fileInfo?: { duration: number; sample_rate: number; channels: number } | null;
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
    disabled?: boolean;
  }) => (
    <label className={`flex flex-col items-center justify-center w-full h-28 border-2 border-dashed rounded-lg cursor-pointer transition
      ${fileName ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-gray-600 hover:border-secondary/50 bg-black/20'}
      ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
    `}>
      <div className="flex flex-col items-center justify-center py-2 px-3 w-full">
        {fileName ? (
          <div className="w-full">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-lg">{icon}</span>
              <span className="text-xs text-gray-500 uppercase tracking-wider">{label}</span>
            </div>
            <div className="text-sm text-white truncate">{fileName}</div>
            {fileInfo && (
              <div className="text-[10px] text-gray-400 mt-0.5">
                {fileInfo.duration.toFixed(1)}s · {fileInfo.sample_rate / 1000}kHz · {fileInfo.channels}ch
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="text-2xl mb-1">{icon}</div>
            <p className="text-xs text-gray-400">{label}</p>
            <p className="text-[10px] text-gray-500 mt-0.5">点击选择音频文件</p>
          </>
        )}
      </div>
      <input type="file" accept="audio/*" onChange={onChange} className="hidden" disabled={disabled} />
    </label>
  );

  return (
    <div className="bg-gradient-to-br from-primary/80 to-dark/80 rounded-xl p-5 border border-secondary/20">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-white font-bold flex items-center gap-2">
          <svg className="w-5 h-5 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
          双轨修复模式
        </h3>
        {uploadStatus !== 'idle' && (
          <button
            onClick={handleReset}
            className="text-xs text-gray-400 hover:text-white transition"
          >
            重置
          </button>
        )}
      </div>

      {uploadStatus === 'idle' && (
        <div className="grid grid-cols-2 gap-3 mb-4">
          <UploadZone
            label="人声轨"
            icon="🎤"
            onChange={handleVocalSelect}
          />
          <UploadZone
            label="伴奏轨"
            icon="🎹"
            onChange={handleAccompanimentSelect}
          />
        </div>
      )}

      {uploadStatus === 'uploading' && (
        <div className="mb-4">
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>{uploadStep}</span>
            <span>{(uploadProgress * 100).toFixed(0)}%</span>
          </div>
          <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-secondary transition-all duration-300"
              style={{ width: `${uploadProgress * 100}%` }}
            />
          </div>
        </div>
      )}

      {uploadStatus === 'done' && (
        <div className="grid grid-cols-2 gap-3 mb-4">
          <UploadZone
            label="人声轨"
            icon="🎤"
            fileName={vocalFileName}
            fileInfo={vocalInfo}
            onChange={handleVocalSelect}
          />
          <UploadZone
            label="伴奏轨"
            icon="🎹"
            fileName={accompanimentFileName}
            fileInfo={accompanimentInfo}
            onChange={handleAccompanimentSelect}
          />
        </div>
      )}

      {uploadStatus === 'error' && (
        <div className="grid grid-cols-2 gap-3 mb-4">
          <UploadZone
            label="人声轨"
            icon="🎤"
            fileName={vocalFileName}
            onChange={handleVocalSelect}
          />
          <UploadZone
            label="伴奏轨"
            icon="🎹"
            fileName={accompanimentFileName}
            onChange={handleAccompanimentSelect}
          />
        </div>
      )}

      {bothUploaded && (
        <div className="space-y-4">
          <div className="flex gap-2">
            <select
              value={algorithmVersion}
              onChange={(e) => onAlgorithmChange(e.target.value)}
              disabled={isProcessing}
              className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-secondary focus:outline-none"
            >
              {filteredAlgorithms.map((algo) => (
                <option key={algo.name} value={algo.name}>
                  {algo.name} {algo.description}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="w-full py-2 text-left text-sm text-gray-400 hover:text-white transition flex items-center justify-between"
          >
            <span>⚙️ 高级参数</span>
            <span>{showAdvanced ? '▼' : '▶'}</span>
          </button>

          {showAdvanced && (
            <div className="space-y-4">
              <div className="p-3 bg-black/30 rounded-lg">
                <div className="text-xs text-gray-400 mb-2">🎤 人声轨参数</div>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(vocalParams).map(([key, value]) => (
                    <div key={key}>
                      <div className="text-[10px] text-gray-500 mb-1">{key}</div>
                      <input
                        type="range"
                        min="0"
                        max="100"
                        value={value}
                        onChange={(e) => setVocalParams({ ...vocalParams, [key]: parseInt(e.target.value) })}
                        className="w-full h-1.5 bg-gray-700 rounded-full appearance-none cursor-pointer"
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-3 bg-black/30 rounded-lg">
                <div className="text-xs text-gray-400 mb-2">🎹 伴奏轨参数</div>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(accompanimentParams).map(([key, value]) => (
                    <div key={key}>
                      <div className="text-[10px] text-gray-500 mb-1">{key}</div>
                      <input
                        type="range"
                        min="0"
                        max="100"
                        value={value}
                        onChange={(e) => setAccompanimentParams({ ...accompanimentParams, [key]: parseInt(e.target.value) })}
                        className="w-full h-1.5 bg-gray-700 rounded-full appearance-none cursor-pointer"
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-3 bg-black/30 rounded-lg">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-xs text-gray-400">🎚️ 混音比例</span>
                  <span className="text-xs text-white">{mixRatio}% 人声 / {100 - mixRatio}% 伴奏</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={mixRatio}
                  onChange={(e) => setMixRatio(parseInt(e.target.value))}
                  className="w-full h-2 bg-gray-700 rounded-full appearance-none cursor-pointer"
                />
              </div>
            </div>
          )}

          <div className="p-3 bg-black/30 rounded-lg">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-medium text-gray-300">预估输出大小</span>
              <span className="text-sm font-bold text-white">
                {currentEstimate ? `${currentEstimate.sizeMB.toFixed(1)} MB` : '—'}
              </span>
            </div>

            {allEstimates.length > 0 && (
              <div className="mt-2 pt-2 border-t border-gray-700/50">
                <div className="text-[10px] text-gray-500 mb-1.5">各组合预估大小：</div>
                <div className="grid grid-cols-3 gap-1 text-[10px]">
                  {allEstimates.map((est) => {
                    const isCurrent = est.sampleRate === processingOptions.sampleRate && est.bitDepth === processingOptions.bitDepth;
                    const cacheKey = `${est.sampleRate}-${est.bitDepth}`;
                    const renderCachesForSrBd = renderCaches.filter(
                      c => c.sample_rate === est.sampleRate && c.bit_depth === est.bitDepth && c.algorithm_version === algorithmVersion
                    );
                    const renderCache = renderCachesForSrBd.find(c => c.is_merged || c.track_type === 'both') || renderCachesForSrBd[0];
                    const isCached = !!renderCache;
                    return (
                      <div
                        key={cacheKey}
                        className={`px-1.5 py-1 rounded text-center ${
                          isCurrent
                            ? `border border-secondary/50 ${est.isWarning ? 'bg-red-500/10 text-red-400' : est.isRecommended ? 'bg-emerald-500/10 text-emerald-400' : 'bg-gray-800/50 text-white'}`
                            : est.isWarning
                              ? 'bg-red-500/10 text-red-400/70'
                              : est.isRecommended
                                ? 'bg-emerald-500/10 text-emerald-400/70'
                                : 'bg-gray-800/50 text-gray-500'
                        }`}
                      >
                        {isCached && (
                          <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-emerald-400 rounded-full" />
                        )}
                        <div className="font-medium">{est.sampleRate / 1000}k/{est.bitDepth}bit</div>
                        <div>{est.sizeMiB.toFixed(0)} MiB</div>
                        {isCached && <div className="text-[8px] text-emerald-400">可秒下</div>}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {(repairStatus === 'repairing' || renderStatus === 'rendering') && (
            <div className="p-3 bg-black/30 rounded-lg">
              <div className="flex justify-between text-xs text-gray-400 mb-1">
                <span>{repairStep || renderStep}</span>
                <span>{((repairProgress + renderProgress) / 2 * 100).toFixed(0)}%</span>
              </div>
              <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-secondary transition-all duration-300"
                  style={{ width: `${((repairProgress + renderProgress) / 2) * 100}%` }}
                />
              </div>
            </div>
          )}

          {repairError && (
            <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-400">
              ❌ {repairError}
            </div>
          )}

          {uploadStatus === 'done' && repairStatus === 'done' && (
            <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-sm text-emerald-400">
              ✅ 双轨修复完成！
            </div>
          )}

          {canRepair && (
            <button
              onClick={handleRepair}
              disabled={isProcessing}
              className="w-full py-3 bg-gradient-to-r from-secondary to-primary text-white font-medium rounded-lg hover:from-secondary/80 hover:to-primary/80 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              开始双轨修复
            </button>
          )}
        </div>
      )}

      {showCacheModal && cacheHit && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl p-5 max-w-sm w-full">
            <div className="text-lg font-bold text-white mb-3">🗄️ 发现修复缓存</div>
            <div className="text-sm text-gray-400 mb-4">
              检测到相同文件的修复结果，是否直接使用缓存？
            </div>
            <div className="space-y-2 text-xs text-gray-500">
              <div className="flex justify-between">
                <span>缓存任务ID</span>
                <span className="text-gray-300">{cacheHit.task_id?.slice(0, 8)}...</span>
              </div>
              {cacheHit.output_size && (
                <div className="flex justify-between">
                  <span>输出大小</span>
                  <span className="text-gray-300">{(cacheHit.output_size / (1024 * 1024)).toFixed(1)} MiB</span>
                </div>
              )}
            </div>
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => store.setShowCacheModal(false)}
                className="flex-1 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm transition"
              >
                重新修复
              </button>
              <button
                onClick={handleUseCache}
                className="flex-1 py-2 bg-secondary hover:bg-secondary/80 text-white rounded-lg text-sm transition"
              >
                使用缓存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
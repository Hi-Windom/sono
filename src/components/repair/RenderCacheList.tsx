import React, { useState } from 'react';
import { RenderCacheEntry } from '../../services/backendApi';
import { sampleRateOptions, bitDepthOptions, isMobile, estimateFileSize, isRecommendedCombo, WARNING_THRESHOLD_MB } from './shared';

interface RenderCacheListProps {
  renderCaches: RenderCacheEntry[];
  algorithmVersion: string;
  processingOptions: { sampleRate: number; bitDepth: 16 | 24 | 32 };
  effectiveDuration: number;
  effectiveChannels: number;
  isDualTrackMode: boolean;
  onOptionsChange: (options: { sampleRate: number; bitDepth: 16 | 24 | 32 }) => void;
  onInstantDownload?: (cacheEntry: RenderCacheEntry) => void;
  disabled?: boolean;
}

interface EstimateItem {
  sampleRate: number;
  bitDepth: number;
  size: number;
  sizeMiB: number;
  sizeMB: number;
  isWarning: boolean;
  isRecommended: boolean;
}

export function RenderCacheList({
  renderCaches,
  algorithmVersion,
  processingOptions,
  effectiveDuration,
  effectiveChannels,
  isDualTrackMode,
  onOptionsChange,
  onInstantDownload,
  disabled,
}: RenderCacheListProps) {
  const [selectedCache, setSelectedCache] = useState<RenderCacheEntry | null>(null);

  const allEstimates: EstimateItem[] = React.useMemo(() => {
    if (effectiveDuration <= 0) return [];
    const estimates: EstimateItem[] = [];
    for (const sr of sampleRateOptions) {
      for (const bd of bitDepthOptions) {
        const est = estimateFileSize(effectiveDuration, sr.value, bd.value, effectiveChannels);
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
  }, [effectiveDuration, effectiveChannels]);

  const hasContent = allEstimates.length > 0 || isDualTrackMode;
  if (!hasContent) return null;

  return (
    <div className="mt-3 pt-2 border-t border-gray-700/50">
      <div className="text-[10px] text-gray-500 mb-1.5">各组合预估大小参考（🟢 = 可秒下）：</div>
      <div className="grid grid-cols-3 gap-1 text-[10px]">
        {allEstimates.length > 0 ? allEstimates.map((est) => {
          const isCurrent = est.sampleRate === processingOptions.sampleRate && est.bitDepth === processingOptions.bitDepth;
          const cacheKey = `${est.sampleRate}-${est.bitDepth}`;
          const renderCache = renderCaches.find(c => c.sample_rate === est.sampleRate && c.bit_depth === est.bitDepth && c.algorithm_version === algorithmVersion);
          const isCached = !!renderCache;
          return (
            <div
              key={cacheKey}
              onClick={() => {
                if (disabled) return;
                if (isCached && renderCache) {
                  setSelectedCache(renderCache);
                } else {
                  onOptionsChange({
                    sampleRate: est.sampleRate,
                    bitDepth: est.bitDepth as 16 | 24 | 32,
                  });
                }
              }}
              className={`px-1.5 py-1 rounded text-center cursor-pointer transition-all relative ${
                isCurrent
                  ? `border border-secondary/50 ${est.isWarning ? 'bg-red-500/10 text-red-400' : est.isRecommended ? 'bg-emerald-500/10 text-emerald-400' : 'bg-gray-800/50 text-white'}`
                  : est.isWarning
                    ? 'bg-red-500/10 text-red-400/70 hover:bg-red-500/20'
                    : est.isRecommended
                      ? 'bg-emerald-500/10 text-emerald-400/70 hover:bg-emerald-500/20'
                      : 'bg-gray-800/50 text-gray-500 hover:bg-gray-700/50'
              } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              {isCached && (
                <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-emerald-400 rounded-full" title="当前版本有渲染缓存" />
              )}
              <div className="font-medium">{est.sampleRate / 1000}k/{est.bitDepth}bit</div>
              <div>{isMobile ? est.sizeMB.toFixed(0) : est.sizeMiB.toFixed(0)}{isMobile ? 'MB' : 'MiB'}</div>
              {isCached && <div className="text-[8px] text-emerald-400">可秒下</div>}
            </div>
          );
        }) : (
          <>
            {sampleRateOptions.flatMap((sr) =>
              bitDepthOptions.map((bd) => (
                <div
                  key={`${sr.value}-${bd.value}`}
                  className="px-1.5 py-1 rounded text-center bg-gray-800/30 text-gray-600"
                >
                  <div className="font-medium">{sr.value / 1000}k/{bd.value}bit</div>
                  <div>—</div>
                </div>
              ))
            )}
          </>
        )}
      </div>

      {selectedCache && (
        <div className="mt-3 p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg text-[12px]">
          <div className="flex items-center justify-between mb-2">
            <span className="text-emerald-400 font-medium">📦 渲染缓存详情</span>
            <button onClick={() => setSelectedCache(null)} className="text-gray-400 hover:text-white text-lg leading-none">×</button>
          </div>
          <div className="flex justify-between"><span className="text-gray-400">格式</span><span className="text-white">{selectedCache.sample_rate / 1000}kHz / {selectedCache.bit_depth}bit</span></div>
          <div className="flex justify-between"><span className="text-gray-400">文件大小</span><span className="text-white">{(selectedCache.size / (1024 * 1024)).toFixed(1)} MiB</span></div>
          <div className="flex justify-between"><span className="text-gray-400">算法版本</span><span className="text-emerald-400">{selectedCache.algorithm_version || '—'}</span></div>
          <div className="flex justify-between"><span className="text-gray-400">生成时间</span><span className="text-white">{selectedCache.mtime ? new Date(selectedCache.mtime).toLocaleString('zh-CN') : '—'}</span></div>
          <div className="mt-2 flex gap-2">
            <button
              onClick={() => {
                if (onInstantDownload) {
                  onInstantDownload(selectedCache);
                }
              }}
              className="flex-1 py-1 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 rounded text-[11px] transition font-medium"
            >
              ⬇ 秒下
            </button>
            <button
              onClick={() => {
                onOptionsChange({
                  sampleRate: selectedCache.sample_rate,
                  bitDepth: selectedCache.bit_depth as 16 | 24 | 32,
                });
                setSelectedCache(null);
              }}
              className="flex-1 py-1 bg-white/5 hover:bg-white/10 text-gray-400 rounded text-[11px] transition"
            >
              应用此规格
            </button>
            <button
              onClick={() => setSelectedCache(null)}
              className="flex-1 py-1 bg-white/5 hover:bg-white/10 text-gray-400 rounded text-[11px] transition"
            >
              关闭
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

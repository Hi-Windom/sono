import React, { useState, useEffect } from 'react';
import { RenderCacheEntry, fetchRenderCache } from '../services/backendApi';
import { generateExportFilename } from '../hooks/useAudioProcessor';

interface RepairCacheInfo {
  task_id: string;
  output_size: number;
  repair_result?: {
    issues_found?: string[];
    [key: string]: unknown;
  };
  detection_result?: unknown;
  repaired_detection_result?: unknown;
}

export interface CacheHitInfo {
  repair: RepairCacheInfo;
  renderCaches: RenderCacheEntry[];
}

interface RepairCacheModalProps {
  isOpen: boolean;
  cacheHit: CacheHitInfo | null;
  audioFileName?: string;
  algorithmVersion: string;
  onUseRepairCache: (taskId: string) => void;
  onRenderCacheDownload: (cache: RenderCacheEntry, downloadUrl: string, filename: string) => void;
  onReRepair: () => void;
  onClose: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function RepairCacheModal({
  isOpen,
  cacheHit,
  audioFileName,
  algorithmVersion,
  onUseRepairCache,
  onRenderCacheDownload,
  onReRepair,
  onClose,
}: RepairCacheModalProps) {
  if (!isOpen || !cacheHit) return null;

  const { repair, renderCaches } = cacheHit;
  const renderCacheSr = renderCaches[0]?.sample_rate || 48000;
  const renderCacheBd = renderCaches[0]?.bit_depth || 24;

  const handleInstantDownload = (cache: RenderCacheEntry) => {
    const downloadUrl = `/api/v1/download-file/${cache.filename}`;
    const filename = generateExportFilename(
      audioFileName,
      cache.algorithm_version || algorithmVersion,
      cache.sample_rate,
      cache.bit_depth,
    );
    onRenderCacheDownload(cache, downloadUrl, filename);
  };

  const issues = repair.repair_result?.issues_found as string[] | undefined;
  const hasRenderCaches = renderCaches.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative bg-[#0D1117] border border-white/10 rounded-2xl p-5 max-w-md w-full mx-4 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-500/20 to-cyan-500/20 flex items-center justify-center">
              <svg className="w-4.5 h-4.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <div>
              <h2 className="text-white font-bold text-base">检测到已有修复记录</h2>
              <p className="text-gray-500 text-xs">选择使用已有结果或重新修复</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-white/10 rounded-lg text-gray-400 hover:text-white transition"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-3">
          <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3.5">
            <div className="flex items-center gap-2 mb-2.5">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              <span className="text-emerald-400 font-medium text-xs">修复缓存</span>
              <span className="ml-auto text-[10px] text-emerald-400/60">{formatBytes(repair.output_size)}</span>
            </div>
            <div className="text-[11px] text-gray-400 space-y-1 mb-3">
              <div className="flex justify-between">
                <span>任务ID</span>
                <span className="text-gray-300 font-mono text-[10px]">{repair.task_id.slice(0, 12)}...</span>
              </div>
              {issues && issues.length > 0 && (
                <div className="flex justify-between">
                  <span>检测到问题</span>
                  <span className="text-amber-400">{issues.length} 项</span>
                </div>
              )}
            </div>
            <button
              onClick={() => onUseRepairCache(repair.task_id)}
              className="w-full py-2 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/30 rounded-lg text-emerald-400 text-xs font-medium transition"
            >
              ✓ 使用已有修复结果
            </button>
          </div>

          {hasRenderCaches ? (
            <div className="bg-cyan-500/5 border border-cyan-500/20 rounded-lg p-3.5">
              <div className="flex items-center gap-2 mb-2.5">
                <div className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                <span className="text-cyan-400 font-medium text-xs">渲染缓存（可秒下）</span>
                <span className="ml-auto text-[10px] text-cyan-400/60">{renderCaches.length} 个</span>
              </div>
              <div className="space-y-1.5">
                {renderCaches.map((cache, idx) => {
                  const cacheFilename = generateExportFilename(
                    audioFileName,
                    cache.algorithm_version || algorithmVersion,
                    cache.sample_rate,
                    cache.bit_depth,
                  );
                  return (
                    <div key={idx} className="flex items-center gap-2 bg-black/20 rounded-lg p-2">
                      <div className="flex-1 min-w-0">
                        <div className="text-[11px] text-white truncate">{cache.sample_rate / 1000}kHz / {cache.bit_depth}bit</div>
                        <div className="text-[10px] text-gray-500">
                          {formatBytes(cache.size)}
                          {cache.algorithm_version && (
                            <span className="ml-1.5 text-cyan-400/60">{cache.algorithm_version}</span>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={() => handleInstantDownload(cache)}
                        className="px-3 py-1.5 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded text-cyan-400 text-[10px] font-medium transition shrink-0"
                      >
                        ⬇ 秒下
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="bg-gray-800/30 border border-gray-700/30 rounded-lg p-3.5">
              <div className="flex items-center gap-2 mb-1.5">
                <div className="w-1.5 h-1.5 rounded-full bg-gray-500" />
                <span className="text-gray-500 font-medium text-xs">渲染缓存</span>
              </div>
              <div className="text-[11px] text-gray-600">
                暂无渲染缓存（重新修复后将自动生成）
              </div>
            </div>
          )}
        </div>

        <div className="mt-4 pt-3 border-t border-white/5">
          <button
            onClick={onReRepair}
            className="w-full py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-gray-400 hover:text-gray-300 text-xs transition"
          >
            重新执行修复
          </button>
        </div>
      </div>
    </div>
  );
}

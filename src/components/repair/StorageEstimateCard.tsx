import React from 'react';
import { StorageEstimateResult, MemoryInfoResult } from '../../services/backendApi';
import { formatBytes } from './shared';

interface StorageEstimateCardProps {
  currentEstimate: { size: number; sizeMiB: number; sizeMB: number } | null;
  storageEstimate: StorageEstimateResult | null;
  memoryInfo: MemoryInfoResult | null;
  children?: React.ReactNode;
}

export function StorageEstimateCard({ currentEstimate, storageEstimate, memoryInfo, children }: StorageEstimateCardProps) {
  return (
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
          {currentEstimate
            ? `${storageEstimate ? storageEstimate.estimated_output_mb : currentEstimate.sizeMB.toFixed(1)} MB`
            : '—'}
        </span>
      </div>

      {children}

      {storageEstimate && storageEstimate.available_disk_bytes != null ? (
        <div className={`mt-3 pt-2 border-t border-gray-700/50 ${
          storageEstimate.is_sufficient ? '' : 'text-red-400'
        }`}>
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-400 flex items-center gap-1">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
              </svg>
              服务器存储
            </span>
            <span className={storageEstimate.is_sufficient ? 'text-emerald-400' : 'text-red-400'}>
              {formatBytes(storageEstimate.available_disk_bytes)} 可用
            </span>
          </div>
          <div className="flex items-center justify-between text-xs mt-1">
            <span className="text-gray-400">
              预估输出占用
            </span>
            <span className={storageEstimate.is_sufficient ? 'text-gray-300' : 'text-red-400'}>
              {formatBytes(storageEstimate.estimated_output_bytes)}
            </span>
          </div>
          {!storageEstimate.is_sufficient && (
            <div className="mt-1.5 text-[10px] text-red-400/90">
              🔴 存储空间不足！预估输出超出可用磁盘空间。
            </div>
          )}
          {storageEstimate.total_disk_bytes != null && (
            <div className="mt-2">
              <div className="h-2.5 bg-gray-700 rounded-full overflow-hidden flex">
                {storageEstimate.used_disk_bytes != null && (
                  <div
                    className="h-full bg-gray-500/60 transition-all"
                    style={{
                      width: `${Math.min(100, (storageEstimate.used_disk_bytes / storageEstimate.total_disk_bytes) * 100)}%`,
                    }}
                  />
                )}
                <div
                  className={`h-full transition-all ${storageEstimate.is_sufficient ? 'bg-blue-500' : 'bg-red-500'}`}
                  style={{
                    width: `${Math.min(100, (storageEstimate.estimated_output_bytes / storageEstimate.total_disk_bytes) * 100)}%`,
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
                    <span className={`inline-block w-1.5 h-1.5 rounded-sm ${storageEstimate.is_sufficient ? 'bg-blue-500' : 'bg-red-500'}`} />
                    预估
                  </span>
                </div>
                <span>{formatBytes(storageEstimate.total_disk_bytes)}</span>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-3 pt-2 border-t border-gray-700/50 text-center text-gray-500 text-[10px] py-2">
          连接服务器后显示存储信息
        </div>
      )}

      {memoryInfo ? (
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
                ? `${formatBytes(memoryInfo.available_memory_bytes)} 可用`
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
              {formatBytes(memoryInfo.estimated_memory_bytes)}
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
                <span>{formatBytes(memoryInfo.total_memory_bytes)}</span>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-3 pt-2 border-t border-gray-700/50 text-center text-gray-500 text-[10px] py-2">
          连接服务器后显示内存信息
        </div>
      )}
    </div>
  );
}

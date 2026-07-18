import React from 'react';
import { SignalProfile } from '../../services/backendApi';

interface RepairProfileDisplayProps {
  repairProfile: SignalProfile;
}

export function RepairProfileDisplay({ repairProfile }: RepairProfileDisplayProps) {
  return (
    <div className="mb-4 p-3 bg-gradient-to-r from-emerald-900/20 to-cyan-900/20 rounded-lg border border-emerald-500/20">
      <div className="flex items-center gap-1.5 mb-2.5">
        <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
        <h4 className="text-emerald-400 text-sm font-medium">修复诊断画像</h4>
        <span className="text-[10px] text-emerald-400/60 ml-auto">v4.0 分析驱动 · 修复后实测</span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="bg-black/20 rounded px-2 py-1.5">
          <div className="text-gray-500 text-[10px]">信噪比</div>
          <div className={repairProfile.snr_db >= 30 ? 'text-emerald-400' : repairProfile.snr_db >= 20 ? 'text-amber-400' : 'text-red-400'}>
            {repairProfile.snr_db.toFixed(1)} dB
          </div>
        </div>
        <div className="bg-black/20 rounded px-2 py-1.5">
          <div className="text-gray-500 text-[10px]">削波占比</div>
          <div className={repairProfile.clip_density_pct < 0.1 ? 'text-emerald-400' : 'text-amber-400'}>
            {repairProfile.clip_density_pct.toFixed(2)}%
          </div>
        </div>
        <div className="bg-black/20 rounded px-2 py-1.5">
          <div className="text-gray-500 text-[10px]">响度</div>
          <div className="text-white">{repairProfile.lufs.toFixed(1)} LUFS</div>
        </div>
        <div className="bg-black/20 rounded px-2 py-1.5">
          <div className="text-gray-500 text-[10px]">动态范围</div>
          <div className="text-white">{repairProfile.dynamic_range_db.toFixed(1)} dB</div>
        </div>
        <div className="bg-black/20 rounded px-2 py-1.5">
          <div className="text-gray-500 text-[10px]">齿音占比</div>
          <div className={repairProfile.sibilance_pct < 12 ? 'text-emerald-400' : 'text-amber-400'}>
            {repairProfile.sibilance_pct.toFixed(1)}%
          </div>
        </div>
        <div className="bg-black/20 rounded px-2 py-1.5">
          <div className="text-gray-500 text-[10px]">立体声宽度</div>
          <div className="text-white">{repairProfile.stereo_width.toFixed(2)}</div>
        </div>
      </div>
      {repairProfile.detected_issues.length > 0 ? (
        <div className="mt-2">
          <span className="text-amber-400 text-xs">残留问题: </span>
          <span className="text-gray-300 text-xs">{repairProfile.detected_issues.join('、')}</span>
        </div>
      ) : (
        <div className="mt-2 text-emerald-400 text-xs">✓ 未检出残留问题</div>
      )}
    </div>
  );
}

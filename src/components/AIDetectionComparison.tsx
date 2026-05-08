import React from 'react';
import { AISongDetectionResult } from '../utils/aiSongChecker';

interface AIDetectionCardProps {
  title: string;
  result: AISongDetectionResult;
  color: string;
  algorithmVersion?: string;
}

export function AIDetectionCard({ title, result, color, algorithmVersion }: AIDetectionCardProps) {
  const isAI = result.isAI;
  const getSignatureLabel = () => {
    switch (result.signature) {
      case 'human':
        return '人类创作';
      case 'ai':
        return 'AI生成';
      case 'mixed':
        return '混合特征';
      case 'uncertain':
      default:
        return '不确定';
    }
  };
  const getSignatureColor = () => {
    switch (result.signature) {
      case 'human':
        return 'text-green-400';
      case 'ai':
        return 'text-cyan-400';
      case 'mixed':
        return 'text-yellow-400';
      case 'uncertain':
      default:
        return 'text-gray-400';
    }
  };

  return (
    <div className={`bg-gradient-to-br ${color} rounded-xl p-5 border border-white/10`}>
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-white font-medium">{title}</h4>
        <span className={`text-xs font-medium px-2 py-1 rounded-full ${getSignatureColor()} bg-white/10`}>
          {getSignatureLabel()}
        </span>
      </div>

      <div className="relative h-32 flex items-center justify-center mb-4">
        <div className="absolute inset-0 flex items-center justify-center">
          <svg className="w-32 h-32 opacity-20" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="45" fill="none" stroke="currentColor" strokeWidth="2" />
            <circle cx="50" cy="50" r="30" fill="none" stroke="currentColor" strokeWidth="1" />
            <circle cx="50" cy="50" r="15" fill="none" stroke="currentColor" strokeWidth="1" />
            {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => (
              <line
                key={angle}
                x1="50"
                y1="10"
                x2="50"
                y2="15"
                stroke="currentColor"
                strokeWidth="2"
                transform={`rotate(${angle} 50 50)`}
              />
            ))}
          </svg>
        </div>

        <div className="relative text-center">
          <div className={`text-5xl font-bold ${isAI ? 'text-cyan-400' : 'text-green-400'}`}>
            {Math.round(result.humanProbability * 100)}%
          </div>
          <div className="text-gray-400 text-sm mt-1">
            人类创作概率
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="flex justify-between items-center">
          <span className="text-gray-400">置信度</span>
          <span className="text-white font-medium">{Math.round(result.confidence * 100)}%</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-gray-400">频谱平坦度</span>
          <span className="text-white font-medium">{(result.features.spectralFlatness * 100).toFixed(0)}%</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-gray-400">动态范围</span>
          <span className="text-white font-medium">{result.features.dynamicRange.toFixed(0)} dB</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-gray-400">音高变化</span>
          <span className="text-white font-medium">{(result.features.pitchVariability * 100).toFixed(0)}%</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-gray-400">频谱熵</span>
          <span className="text-white font-medium">{(result.features.spectralEntropy * 100).toFixed(0)}%</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-gray-400">MFCC相似度</span>
          <span className="text-white font-medium">{(result.features.mfccSimilarity * 100).toFixed(0)}%</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-gray-400">微节奏一致性</span>
          <span className="text-white font-medium">{(result.features.microRhythmConsistency * 100).toFixed(0)}%</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-gray-400">时域规律性</span>
          <span className="text-white font-medium">{(result.features.temporalRegularity * 100).toFixed(0)}%</span>
        </div>
      </div>

      {result.reasons.length > 0 && (
        <div className="mt-4 pt-4 border-t border-white/10">
          <p className="text-gray-400 text-xs mb-2">检测依据：</p>
          <ul className="space-y-1">
            {result.reasons.map((reason, index) => (
              <li key={index} className="text-gray-300 text-xs flex items-center gap-2">
                <svg className="w-3 h-3 text-secondary" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                {reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {algorithmVersion && (
        <div className="mt-3 pt-2 border-t border-white/5 flex justify-end">
          <span className="text-gray-500 text-[10px]">检测算法 {algorithmVersion}</span>
        </div>
      )}
    </div>
  );
}

interface AIDetectionComparisonProps {
  before: AISongDetectionResult | null;
  backendAfter: AISongDetectionResult | null;
  onDetect?: () => void;
  isProcessing?: boolean;
  detectorVersion?: string;
  onDetectorVersionChange?: (version: string) => void;
  availableDetectors?: { name: string; label: string; description: string }[];
  algorithmVersion?: string;
}

export function AIDetectionComparison({ before, backendAfter, onDetect, isProcessing, detectorVersion, onDetectorVersionChange, availableDetectors, algorithmVersion }: AIDetectionComparisonProps) {
  const [lastDetectedVersion, setLastDetectedVersion] = React.useState<string | null>(null);
  const [showVersionWarning, setShowVersionWarning] = React.useState(false);

  const activeAfter = backendAfter;
  const improvement = before && activeAfter
    ? (activeAfter.humanProbability - before.humanProbability) * 100
    : 0;

  const isImproved = improvement > 3;
  const isNeutral = Math.abs(improvement) <= 3;

  const detectorVersionList = availableDetectors && availableDetectors.length > 0
    ? [...availableDetectors].reverse().map(v => ({ value: v.name, label: v.label }))
    : [
        { value: 'v1.1', label: 'v1.1' },
        { value: 'v1.0', label: 'v1.0' },
      ];

  // 当检测完成时记录版本
  React.useEffect(() => {
    if (before && !isProcessing) {
      setLastDetectedVersion(detectorVersion || 'v1.0');
      setShowVersionWarning(false);
    }
  }, [before, isProcessing, detectorVersion]);

  // 检查版本是否匹配
  const isVersionMismatch = before && lastDetectedVersion && detectorVersion !== lastDetectedVersion;

  return (
    <div className="bg-gradient-to-br from-primary/80 to-dark/80 rounded-xl p-5 border border-secondary/20">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-white font-bold text-lg flex items-center gap-2">
          <svg className="w-5 h-5 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 01-2-2H5a2 2 0 01-2 2v6a2 2 0 012 2h2a2 2 0 012-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 012 2h2a2 2 0 012-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          AI检测分析
        </h3>
        <div className="flex items-center gap-3">
          {detectorVersion && onDetectorVersionChange && (
            <div className="relative">
              <select
                value={detectorVersion}
                onChange={(e) => {
                  const newVersion = e.target.value;
                  if (newVersion !== detectorVersion) {
                    onDetectorVersionChange(newVersion);
                    // 版本切换后，如果已有检测结果，显示警告
                    if (before) {
                      setShowVersionWarning(true);
                    }
                  }
                }}
                className={`appearance-none text-white text-xs font-medium py-1 pl-2 pr-6 rounded-md border cursor-pointer transition ${
                  isVersionMismatch
                    ? 'bg-yellow-500/20 border-yellow-400/40 hover:bg-yellow-500/30'
                    : 'bg-cyan-500/20 border-cyan-400/40 hover:bg-cyan-500/30'
                }`}
                style={{
                  backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%2300D9FF' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`,
                  backgroundPosition: 'right 0.25rem center',
                  backgroundRepeat: 'no-repeat',
                  backgroundSize: '1.5em 1.5em',
                }}
              >
                {detectorVersionList.map(v => (
                  <option key={v.value} value={v.value} className="bg-gray-800">{v.label}</option>
                ))}
              </select>
              {isVersionMismatch && (
                <div className="absolute top-full mt-1 left-0 whitespace-nowrap">
                  <span className="text-yellow-400 text-xs">⚠️ 请重新检测</span>
                </div>
              )}
            </div>
          )}
          {before && activeAfter && (
            <span className={`px-3 py-1 rounded-full text-sm font-medium ${
              isImproved
                ? 'bg-green-500/20 text-green-400'
                : isNeutral
                  ? 'bg-gray-500/20 text-gray-400'
                  : 'bg-red-500/20 text-red-400'
            }`}>
              {isImproved ? '+' : ''}{improvement.toFixed(1)}% {isImproved ? '改善' : isNeutral ? '持平' : '下降'}
            </span>
          )}
          <button
            onClick={onDetect}
            disabled={isProcessing}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
              isProcessing
                ? 'bg-gray-600 text-gray-400 cursor-not-allowed'
                : 'bg-gradient-to-r from-cyan-500 to-purple-500 hover:from-cyan-400 hover:to-purple-400 text-white shadow-lg shadow-cyan-500/20'
            }`}
          >
            {isProcessing ? '检测中...' : before ? '重新检测' : 'AI检测'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {before ? (
          <AIDetectionCard
            title="修复前"
            result={before}
            color="from-red-900/50 to-primary/50"
          />
        ) : (
          <div className="bg-gradient-to-br from-red-900/50 to-primary/50 rounded-xl p-5 border border-white/10 flex items-center justify-center h-64">
            <p className="text-gray-400">等待音频...</p>
          </div>
        )}

        {activeAfter ? (
          <AIDetectionCard
            title="修复后 · 后端处理"
            result={activeAfter}
            color="from-cyan-900/50 to-primary/50"
            algorithmVersion={algorithmVersion}
          />
        ) : (
          <div className="bg-gradient-to-br from-green-900/50 to-primary/50 rounded-xl p-5 border border-white/10 flex items-center justify-center h-64">
            <p className="text-gray-400">处理中...</p>
          </div>
        )}
      </div>

      <div className="mt-4 p-3 bg-black/30 rounded-lg">
        <p className="text-gray-400 text-xs text-center">
          💡 基于音频特征的启发式分析，仅供参考，不作为可靠判断依据
        </p>
      </div>
    </div>
  );
}

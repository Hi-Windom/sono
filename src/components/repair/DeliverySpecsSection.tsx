import React from 'react';
import { ProcessingOptions } from '../../services/backendApi';
import { sampleRateOptions, bitDepthOptions, masteringStyleOptions, getEffectiveMasteringStyle } from './shared';

interface DeliverySpecsSectionProps {
  processingOptions: ProcessingOptions;
  onOptionsChange: (options: ProcessingOptions) => void;
  disabled?: boolean;
  children?: React.ReactNode;
}

export function DeliverySpecsSection({ processingOptions, onOptionsChange, disabled, children }: DeliverySpecsSectionProps) {
  const effectiveStyle = getEffectiveMasteringStyle(processingOptions.masteringStyle);

  return (
    <div className="mb-4 p-3 bg-black/20 rounded-lg">
      <h4 className="text-secondary text-sm font-medium mb-3">交付规格</h4>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-gray-400 text-xs mb-2 block flex items-center gap-1">
            目标采样率
            {sampleRateOptions.find(o => o.value === processingOptions.sampleRate)?.recommended && (
              <span className="text-emerald-400 text-[10px] bg-emerald-500/20 px-1 rounded">推荐</span>
            )}
          </label>
          <div className="flex gap-1">
            {sampleRateOptions.map((option) => {
              const isSelected = processingOptions.sampleRate === option.value;
              const isRecommended = option.recommended;

              return (
                <button
                  key={option.value}
                  onClick={() => onOptionsChange({ ...processingOptions, sampleRate: option.value })}
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
            {processingOptions.bitDepth === 24 && (
              <span className="text-emerald-400 text-[10px] bg-emerald-500/20 px-1 rounded">推荐</span>
            )}
          </label>
          <div className="flex gap-1">
            {bitDepthOptions.map((option) => {
              const isSelected = processingOptions.bitDepth === option.value;
              const isRecommended = option.recommended;

              return (
                <button
                  key={option.value}
                  onClick={() => onOptionsChange({ ...processingOptions, bitDepth: option.value })}
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
                  {!isSelected && isRecommended && (
                    <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-emerald-500 rounded-full" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="mt-3">
        <label className="text-gray-400 text-xs mb-2 block">母带风格</label>
        <div className="flex gap-2">
          {masteringStyleOptions.map((option) => {
            const isSelected = effectiveStyle === option.value;
            return (
              <button
                key={option.value}
                onClick={() => onOptionsChange({ ...processingOptions, masteringStyle: option.value })}
                disabled={disabled}
                className={`flex-1 py-1.5 px-2 rounded-lg text-xs transition-all relative
                  ${isSelected
                    ? 'bg-secondary/30 text-white border border-secondary/50'
                    : option.recommended
                      ? 'bg-primary/30 text-gray-300 border border-emerald-500/30 hover:border-emerald-400/50'
                      : 'bg-primary/30 text-gray-400 border border-gray-700 hover:border-secondary/30'
                  } ${disabled ? 'opacity-50' : ''}
                `}
              >
                {option.label}
                {!isSelected && option.recommended && (
                  <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-emerald-500 rounded-full" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {children}

      <p className="text-gray-500 text-xs mt-2">交付规格在导出时应用，修改后即时渲染无需重新修复</p>
    </div>
  );
}

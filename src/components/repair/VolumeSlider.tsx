import React from 'react';

interface VolumeSliderProps {
  outputVolume: number;
  onChange: (volume: number) => void;
  disabled?: boolean;
}

export function VolumeSlider({ outputVolume, onChange, disabled }: VolumeSliderProps) {
  return (
    <div className="mt-4">
      <div className="flex items-center justify-between mb-2">
        <label className="text-gray-400 text-xs">输出音量</label>
        <span className="text-xs font-mono text-secondary">
          {outputVolume >= 0 ? '+' : ''}{outputVolume.toFixed(1)} dB
        </span>
      </div>
      <input
        type="range"
        min="-12"
        max="6"
        step="0.5"
        value={outputVolume}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        disabled={disabled}
        className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-secondary disabled:opacity-50"
      />
      <div className="flex justify-between text-[10px] text-gray-600 mt-1 relative">
        <span>-12</span>
        <span>-6</span>
        <span>0</span>
        <span>+6 dB</span>
      </div>
    </div>
  );
}

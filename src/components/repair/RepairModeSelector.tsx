import React from 'react';
import { RepairMode } from '../../utils/advancedAudioProcessing';

interface RepairModeSelectorProps {
  modes: RepairMode[];
  selectedMode: string;
  onModeSelect: (mode: RepairMode) => void;
  disabled?: boolean;
}

export function RepairModeSelector({ modes, selectedMode, onModeSelect, disabled }: RepairModeSelectorProps) {
  return (
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
  );
}

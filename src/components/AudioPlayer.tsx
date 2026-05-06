import React from 'react';
import { formatTime } from '../utils/audioUtils';
import { PlayMode } from '../hooks/useAudioProcessor';

interface AudioPlayerProps {
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  playMode: PlayMode;
  hasBrowserResult: boolean;
  hasBackendResult: boolean;
  onPlay: () => void;
  onPause: () => void;
  onSeek?: (time: number) => void;
  onSwitchPlayMode?: (mode: PlayMode) => void;
}

export function AudioPlayer({
  isPlaying,
  currentTime,
  duration,
  playMode,
  hasBrowserResult,
  hasBackendResult,
  onPlay,
  onPause,
  onSeek,
  onSwitchPlayMode,
}: AudioPlayerProps) {
  const hasAnyResult = hasBrowserResult || hasBackendResult;

  const modeLabel: Record<PlayMode, string> = {
    original: '原始',
    browser: '浏览器修复',
    backend: '后端修复',
  };

  return (
    <div className="bg-gradient-to-br from-primary/80 to-dark/80 rounded-2xl p-6 border border-secondary/20">
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-center gap-4">
          {onSwitchPlayMode && hasAnyResult && (
            <div className="flex rounded-lg overflow-hidden border border-secondary/30">
              {(['original', 'browser', 'backend'] as PlayMode[]).map((mode) => {
                const disabled = mode === 'browser' ? !hasBrowserResult : mode === 'backend' ? !hasBackendResult : false;
                const active = playMode === mode;
                return (
                  <button
                    key={mode}
                    onClick={() => !disabled && onSwitchPlayMode(mode)}
                    disabled={disabled}
                    className={`px-3 py-1.5 text-xs font-medium transition ${
                      active
                        ? 'bg-secondary/40 text-secondary'
                        : disabled
                          ? 'bg-transparent text-gray-600 cursor-not-allowed'
                          : 'bg-transparent text-gray-400 hover:bg-secondary/20 hover:text-secondary'
                    }`}
                  >
                    {modeLabel[mode]}
                  </button>
                );
              })}
            </div>
          )}

          <button
            onClick={isPlaying ? onPause : onPlay}
            className="w-16 h-16 rounded-full flex items-center justify-center transition-all bg-gradient-to-r from-secondary to-accent hover:scale-105 shadow-lg shadow-secondary/30"
          >
            {isPlaying ? (
              <svg className="w-7 h-7 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
              </svg>
            ) : (
              <svg className="w-7 h-7 text-white ml-1" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z" />
              </svg>
            )}
          </button>
        </div>

        {duration > 0 && (
          <div className="flex items-center gap-4">
            <span className="text-gray-400 text-sm w-12 text-right">
              {formatTime(currentTime)}
            </span>
            <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-secondary to-accent transition-all duration-100"
                style={{ width: `${(currentTime / duration) * 100}%` }}
              />
            </div>
            <span className="text-gray-400 text-sm w-12">
              {formatTime(duration)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

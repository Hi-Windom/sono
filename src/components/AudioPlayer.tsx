import React from 'react';
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
  playMode,
  hasBrowserResult,
  hasBackendResult,
  onPlay,
  onPause,
  onSwitchPlayMode,
}: AudioPlayerProps) {
  const hasAnyResult = hasBrowserResult || hasBackendResult;

  const modeLabel: Record<PlayMode, string> = {
    original: '原始',
    browser: '浏览器修复',
    backend: '后端修复',
  };

  const modeIcon: Record<PlayMode, React.ReactNode> = {
    original: (
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
      </svg>
    ),
    browser: (
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
      </svg>
    ),
    backend: (
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
      </svg>
    ),
  };

  return (
    <div className="bg-gradient-to-br from-primary/90 to-dark/90 rounded-2xl p-4 border border-secondary/30 shadow-xl shadow-black/20">
      {/* 播放控制区 - 水平排列 */}
      <div className="flex items-center justify-center gap-4">
        {/* 播放/暂停按钮 */}
        <button
          onClick={isPlaying ? onPause : onPlay}
          className="w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200 bg-gradient-to-r from-secondary to-accent hover:scale-110 hover:shadow-lg hover:shadow-secondary/40 active:scale-95"
        >
          {isPlaying ? (
            <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
              <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
            </svg>
          ) : (
            <svg className="w-5 h-5 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>

        {/* 模式切换按钮 */}
        {onSwitchPlayMode && hasAnyResult && (
          <div className="flex items-center gap-1.5">
            {(['original', 'browser', 'backend'] as PlayMode[]).map((mode) => {
              const disabled = mode === 'browser' ? !hasBrowserResult : mode === 'backend' ? !hasBackendResult : false;
              const active = playMode === mode;
              return (
                <button
                  key={mode}
                  onClick={() => !disabled && onSwitchPlayMode(mode)}
                  disabled={disabled}
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 ${
                    active
                      ? 'bg-secondary/30 text-secondary border border-secondary/50 shadow-md shadow-secondary/10'
                      : disabled
                        ? 'bg-gray-800/50 text-gray-600 cursor-not-allowed border border-transparent'
                        : 'bg-gray-800/50 text-gray-400 hover:bg-gray-700/50 hover:text-gray-200 border border-transparent hover:border-gray-600/50'
                  }`}
                >
                  {modeIcon[mode]}
                  <span>{modeLabel[mode]}</span>
                  {active && (
                    <span className="w-1.5 h-1.5 rounded-full bg-secondary animate-pulse" />
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

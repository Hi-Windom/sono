interface StemProcessingPanelProps {
  hasAudio: boolean;
  vocalGain: number;
  instrumentalGain: number;
  onVocalGainChange: (gain: number) => void;
  onInstrumentalGainChange: (gain: number) => void;
  onBalanceChange: (balance: number) => void;
  vocalBalance: number;
}

export function StemProcessingPanel({
  hasAudio,
  vocalGain,
  instrumentalGain,
  onVocalGainChange,
  onInstrumentalGainChange,
  vocalBalance,
  onBalanceChange
}: StemProcessingPanelProps) {
  return (
    <div className="bg-gradient-to-br from-primary/80 to-dark/80 rounded-xl p-5 border border-secondary/20">
      <h3 className="text-white font-bold text-lg flex items-center gap-2 mb-4">
        <svg className="w-5 h-5 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
        </svg>
        分轨混音
      </h3>

      {hasAudio && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 text-sm text-gray-300 mb-2">
            <svg className="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
            <span>智能分离人声和伴奏，分别处理后混音</span>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="bg-gradient-to-br from-cyan-900/30 to-primary/50 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
                <span className="text-white font-medium">人声</span>
              </div>
              
              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-xs text-gray-400 mb-1">
                    <span>音量增益</span>
                    <span>{vocalGain > 0 ? `+${vocalGain.toFixed(1)}` : vocalGain.toFixed(1)} dB</span>
                  </div>
                  <input
                    type="range"
                    min="-6"
                    max="6"
                    step="0.5"
                    value={vocalGain}
                    onChange={(e) => onVocalGainChange(parseFloat(e.target.value))}
                    className="w-full h-1 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                  />
                </div>
              </div>
            </div>

            <div className="bg-gradient-to-br from-purple-900/30 to-primary/50 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <svg className="w-5 h-5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                </svg>
                <span className="text-white font-medium">伴奏</span>
              </div>
              
              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-xs text-gray-400 mb-1">
                    <span>音量增益</span>
                    <span>{instrumentalGain > 0 ? `+${instrumentalGain.toFixed(1)}` : instrumentalGain.toFixed(1)} dB</span>
                  </div>
                  <input
                    type="range"
                    min="-6"
                    max="6"
                    step="0.5"
                    value={instrumentalGain}
                    onChange={(e) => onInstrumentalGainChange(parseFloat(e.target.value))}
                    className="w-full h-1 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-400"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="bg-gradient-to-br from-green-900/30 to-primary/50 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m-15.355-2a8.001 8.001 0 0015.356-2m0 0H15" />
              </svg>
              <span className="text-white font-medium">立体声平衡</span>
            </div>
            <div>
              <div className="flex justify-between text-xs text-gray-400 mb-1">
                <span>左</span>
                <span>{vocalBalance === 0 ? '居中' : vocalBalance < 0 ? '偏左' : '偏右'}</span>
                <span>右</span>
              </div>
              <input
                type="range"
                min="-100"
                max="100"
                step="5"
                value={vocalBalance}
                onChange={(e) => onBalanceChange(parseFloat(e.target.value))}
                className="w-full h-1 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-green-400"
              />
            </div>
          </div>
        </div>
      )}

      {!hasAudio && (
        <div className="text-center py-8 text-gray-400">
          <svg className="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
          </svg>
          <p>请先上传音频文件</p>
        </div>
      )}
    </div>
  );
}
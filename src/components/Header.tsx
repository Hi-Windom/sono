import React from 'react';

interface HeaderProps {
  backendAvailable: boolean;
  isUploading?: boolean;
  isProcessing?: boolean;
  onDiagnose?: () => void;
}

export const Header = ({ backendAvailable, isUploading, isProcessing, onDiagnose }: HeaderProps) => {
  const hasDownstreamActivity = isProcessing;
  const hasUpstreamActivity = isUploading;

  return (
    <header className="border-b border-white/5 bg-gradient-to-b from-primary/30 to-transparent">
      <div className="container mx-auto px-4 py-6 max-w-7xl">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="relative">
              <div className="w-12 h-12 bg-gradient-to-br from-cyan-500 via-purple-500 to-yellow-500 rounded-xl flex items-center justify-center shadow-[0_0_30px_rgba(107,70,193,0.4)]">
                <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
            </div>
            <div>
              <h1 className="text-2xl font-bold bg-gradient-to-r from-cyan-400 via-purple-400 to-yellow-400 bg-clip-text text-transparent">
                AI音乐修复工具
              </h1>
              <p className="text-sm text-gray-400">
                专业音频修复与AI检测分析
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-3 bg-primary/50 border border-white/10 rounded-lg px-4 py-2.5">
              <div className={`w-2.5 h-2.5 rounded-full ${backendAvailable ? 'bg-green-400 animate-pulse' : 'bg-yellow-400'}`} />
              <div className="flex items-center gap-1.5">
                <span className={`text-xs font-medium ${backendAvailable ? 'text-green-400' : 'text-yellow-400'}`}>
                  {backendAvailable ? '已连接' : '未连接'}
                </span>
                <div className="flex items-center gap-1 ml-1">
                  <svg
                    className={`w-3 h-3 transition-colors duration-200 ${hasDownstreamActivity ? 'text-green-400' : 'text-gray-600'}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                  </svg>
                  <svg
                    className={`w-3 h-3 transition-colors duration-200 ${hasUpstreamActivity ? 'text-cyan-400' : 'text-gray-600'}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
                  </svg>
                </div>
              </div>
            </div>
            {onDiagnose && (
              <button
                onClick={onDiagnose}
                className="flex items-center gap-1.5 px-3 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg cursor-pointer transition text-gray-400 hover:text-white text-xs"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                诊断
              </button>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};

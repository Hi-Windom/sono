import React from 'react';

export const Header = () => {
  return (
    <header className="border-b border-white/5 bg-gradient-to-b from-primary/30 to-transparent">
      <div className="container mx-auto px-4 py-6 max-w-7xl">
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
      </div>
    </header>
  );
};

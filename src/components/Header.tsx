import React, { useState } from 'react';
import { useBackend } from '../contexts/BackendContext';

const statusConfig = {
  connected: {
    dotColor: 'bg-green-400 animate-pulse',
    textColor: 'text-green-400',
    label: '已连接',
  },
  unstable: {
    dotColor: 'bg-yellow-400',
    textColor: 'text-yellow-400',
    label: '不稳定',
  },
  disconnected: {
    dotColor: 'bg-red-500',
    textColor: 'text-red-400',
    label: '未连接',
  },
};

export const Header = () => {
  const { connectionStatus, hasUpstreamActivity, hasDownstreamActivity, runBackendDiag, backendDiag } = useBackend();
  const [showDiagModal, setShowDiagModal] = useState(false);
  const config = statusConfig[connectionStatus];

  const handleDiagnose = async () => {
    await runBackendDiag();
    setShowDiagModal(true);
  };

  return (
    <>
      <header className="border-b border-white/5 bg-gradient-to-b from-primary/30 to-transparent">
        <div className="container mx-auto px-4 py-3 md:py-4 max-w-7xl">
          {/* 桌面端：左右布局 */}
          <div className="hidden md:flex items-center justify-between">
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
                <div className={`w-2.5 h-2.5 rounded-full ${config.dotColor}`} />
                <div className="flex items-center gap-1.5">
                  <span className={`text-xs font-medium ${config.textColor}`}>
                    {config.label}
                  </span>
                  <div className="flex items-center gap-1 ml-1">
                    <svg
                      className={`w-3 h-3 transition-all duration-200 ${hasDownstreamActivity ? 'text-cyan-400 scale-125 drop-shadow-[0_0_4px_rgba(34,211,238,0.6)]' : 'text-gray-600'}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                      style={{ transitionTimingFunction: 'cubic-bezier(0.4, 0, 0.2, 1)' }}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                    </svg>
                    <svg
                      className={`w-3 h-3 transition-all duration-200 ${hasUpstreamActivity ? 'text-pink-400 scale-125 drop-shadow-[0_0_4px_rgba(236,72,153,0.6)]' : 'text-gray-600'}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                      style={{ transitionTimingFunction: 'cubic-bezier(0.4, 0, 0.2, 1)' }}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
                    </svg>
                  </div>
                </div>
              </div>
              <button
                onClick={handleDiagnose}
                className="flex items-center gap-1.5 px-3 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg cursor-pointer transition text-gray-400 hover:text-white text-xs"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                诊断
              </button>
            </div>
          </div>

          {/* 移动端：一行布局 - 图标 + 状态 + 诊断 */}
          <div className="md:hidden flex items-center justify-between">
            {/* 左侧：图标 */}
            <div className="w-9 h-9 bg-gradient-to-br from-cyan-500 via-purple-500 to-yellow-500 rounded-xl flex items-center justify-center shadow-[0_0_20px_rgba(107,70,193,0.4)]">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>

            {/* 中间：状态 */}
            <div className="flex items-center gap-2 flex-1 mx-3">
              <div className={`w-2 h-2 rounded-full ${config.dotColor}`} />
              <span className={`text-xs font-medium ${config.textColor}`}>
                {config.label}
              </span>
              <div className="flex items-center gap-1">
                <svg
                  className={`w-3 h-3 transition-all duration-200 ${hasDownstreamActivity ? 'text-cyan-400 scale-125' : 'text-gray-600'}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                </svg>
                <svg
                  className={`w-3 h-3 transition-all duration-200 ${hasUpstreamActivity ? 'text-pink-400 scale-125' : 'text-gray-600'}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
                </svg>
              </div>
            </div>

            {/* 右侧：诊断按钮 */}
            <button
              onClick={handleDiagnose}
              className="flex items-center gap-1 px-2.5 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg cursor-pointer transition text-gray-400 hover:text-white text-xs"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              诊断
            </button>
          </div>
        </div>
      </header>

      {/* 诊断模态框 */}
      {showDiagModal && backendDiag && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowDiagModal(false)}>
          <div className="bg-primary border border-white/10 rounded-xl p-6 max-w-md w-full mx-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-white font-semibold">后端诊断</h3>
              <button onClick={() => setShowDiagModal(false)} className="text-gray-400 hover:text-white">×</button>
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-gray-400">后端服务</span>
                <span className={backendDiag.backend ? 'text-green-400' : 'text-red-400'}>{backendDiag.backend ? '✓' : '✗'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-400">Python</span>
                <span className={backendDiag.python ? 'text-green-400' : 'text-red-400'}>{backendDiag.python ? '✓' : '✗'} {backendDiag.python_version || ''}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-400">FFmpeg</span>
                <span className={backendDiag.ffmpeg ? 'text-green-400' : 'text-red-400'}>{backendDiag.ffmpeg ? '✓' : '✗'} {backendDiag.ffmpeg_version || ''}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-400">内存</span>
                <span className={backendDiag.memory ? 'text-green-400' : 'text-yellow-400'}>{backendDiag.memory ? '✓' : '⚠'} {backendDiag.memory_info ? `${backendDiag.memory_info.available_gb.toFixed(1)}GB` : ''}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-400">存储</span>
                <span className={backendDiag.storage ? 'text-green-400' : 'text-yellow-400'}>{backendDiag.storage ? '✓' : '⚠'} {backendDiag.storage_info ? `${backendDiag.storage_info.available_gb.toFixed(1)}GB` : ''}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-400">GPU</span>
                <span className={backendDiag.gpu ? 'text-green-400' : 'text-gray-400'}>{backendDiag.gpu ? '✓' : '-'} {backendDiag.gpu_info || ''}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

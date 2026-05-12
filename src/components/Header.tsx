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
  const [isDiagLoading, setIsDiagLoading] = useState(false);
  const config = statusConfig[connectionStatus];

  const handleDiagnose = async () => {
    setShowDiagModal(true);
    setIsDiagLoading(true);
    await runBackendDiag();
    setIsDiagLoading(false);
  };

  return (
    <>
      <header className="border-b border-white/5 bg-gradient-to-b from-primary/30 to-transparent">
        <div className="header-container container mx-auto px-4 py-3 md:py-6 max-w-7xl">
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
                      className={`w-3 h-3 transition-all duration-200 ${hasDownstreamActivity ? 'text-cyan-400 scale-125 drop-shadow-[0_0_8px_rgba(34,211,238,0.8)]' : 'text-gray-600'}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                      style={{ transitionTimingFunction: 'cubic-bezier(0.4, 0, 0.2, 1)' }}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                    </svg>
                    <svg
                      className={`w-3 h-3 transition-all duration-200 ${hasUpstreamActivity ? 'text-pink-400 scale-125 drop-shadow-[0_0_8px_rgba(236,72,153,0.8)]' : 'text-gray-600'}`}
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

          {/* 移动端：一行布局 - 左侧标题，右侧状态上诊断下 */}
          <div className="md:hidden flex items-center justify-between h-11">
            {/* 左侧：图标 + 标题（空间不够时自动隐藏） */}
            <div className="flex items-center gap-2 min-w-0 overflow-hidden">
              <div className="w-9 h-9 bg-gradient-to-br from-cyan-500 via-purple-500 to-yellow-500 rounded-xl flex items-center justify-center shadow-[0_0_20px_rgba(107,70,193,0.4)] flex-shrink-0">
                <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              {/* 用容器查询：父容器宽度足够时才显示标题 */}
              <h1 className="header-title text-sm font-bold bg-gradient-to-r from-cyan-400 via-purple-400 to-yellow-400 bg-clip-text text-transparent whitespace-nowrap overflow-hidden text-ellipsis min-w-0">
                AI音乐修复工具
              </h1>
            </div>

            {/* 右侧：状态（上）+ 诊断（下）垂直排列 */}
            <div className="flex flex-col gap-0.5 items-end flex-shrink-0">
              {/* 状态行 */}
              <div className="flex items-center gap-1.5 bg-primary/40 border border-white/10 rounded-md px-2 py-0.5">
                <div className={`w-1.5 h-1.5 rounded-full ${config.dotColor}`} />
                <span className={`text-[10px] font-medium ${config.textColor}`}>
                  {config.label}
                </span>
                <div className="flex items-center gap-0.5">
                  <svg
                    className={`w-2.5 h-2.5 transition-all duration-200 ${hasDownstreamActivity ? 'text-cyan-400 scale-110 drop-shadow-[0_0_6px_rgba(34,211,238,0.8)]' : 'text-gray-600'}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                  </svg>
                  <svg
                    className={`w-2.5 h-2.5 transition-all duration-200 ${hasUpstreamActivity ? 'text-pink-400 scale-110 drop-shadow-[0_0_6px_rgba(236,72,153,0.8)]' : 'text-gray-600'}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
                  </svg>
                </div>
              </div>

              {/* 诊断按钮 */}
              <button
                onClick={handleDiagnose}
                className="flex items-center gap-1 px-2 py-0.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-md cursor-pointer transition text-gray-400 hover:text-white text-[10px]"
              >
                <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                诊断
              </button>
            </div>
          </div>
        </div>
      </header>

      <style>{`
        .header-container {
          container-type: inline-size;
          container-name: header;
        }
        .header-title {
          display: block;
        }
        @container header (max-width: 280px) {
          .header-title {
            display: none;
          }
        }
      `}</style>

      {/* 诊断模态框 */}
      {showDiagModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setShowDiagModal(false)}>
          <div className="bg-[#1a1a2e] border border-white/10 rounded-2xl p-6 max-w-sm w-full mx-4 shadow-2xl shadow-black/40" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500/20 to-purple-500/20 flex items-center justify-center">
                  <svg className="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                </div>
                <h3 className="text-white font-semibold text-base">后端诊断</h3>
              </div>
              <button onClick={() => setShowDiagModal(false)} className="w-7 h-7 flex items-center justify-center rounded-lg text-gray-500 hover:text-white hover:bg-white/10 transition-colors text-lg">×</button>
            </div>

            {isDiagLoading ? (
              <div className="flex flex-col items-center py-8 gap-3">
                <div className="w-8 h-8 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin" />
                <span className="text-gray-400 text-sm">正在检测...</span>
              </div>
            ) : backendDiag ? (
              <div className="space-y-1">
                {[
                  { label: '后端服务', key: 'backend', ok: backendDiag.backend, warn: false },
                  { label: 'Python 环境', key: 'python', ok: backendDiag.python, extra: backendDiag.python_version || '', warn: false },
                  { label: 'FFmpeg 引擎', key: 'ffmpeg', ok: backendDiag.ffmpeg, extra: backendDiag.ffmpeg_version || '', warn: false },
                  { label: '内存', key: 'memory', ok: backendDiag.memory, extra: backendDiag.memory_info ? `${backendDiag.memory_info.available_gb.toFixed(1)} / ${backendDiag.memory_info.total_gb.toFixed(1)} GB` : '', warn: !backendDiag.memory },
                  { label: '磁盘存储', key: 'storage', ok: backendDiag.storage, extra: backendDiag.storage_info ? `${backendDiag.storage_info.available_gb.toFixed(1)} / ${backendDiag.storage_info.total_gb.toFixed(1)} GB` : '', warn: !backendDiag.storage },
                  { label: 'GPU 加速', key: 'gpu', ok: backendDiag.gpu, extra: backendDiag.gpu_info || '', warn: false },
                ].map(item => (
                  <div key={item.key} className={`flex items-center justify-between px-3 py-2.5 rounded-lg ${item.ok ? 'bg-green-500/5' : item.warn ? 'bg-yellow-500/5' : 'bg-red-500/5'}`}>
                    <div className="flex items-center gap-2.5">
                      {item.ok ? (
                        <svg className="w-4 h-4 text-green-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                        </svg>
                      ) : item.warn ? (
                        <svg className="w-4 h-4 text-yellow-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                        </svg>
                      ) : (
                        <svg className="w-4 h-4 text-red-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      )}
                      <span className="text-gray-300 text-sm">{item.label}</span>
                    </div>
                    {item.extra && (
                      <span className={`text-xs font-mono tabular-nums ${item.ok ? 'text-gray-500' : item.warn ? 'text-yellow-400/70' : 'text-red-400/70'}`}>
                        {item.extra}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      )}
    </>
  );
};

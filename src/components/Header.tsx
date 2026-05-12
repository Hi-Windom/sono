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

      {/* 诊断面板 - 终端风格 */}
      {showDiagModal && (
        <div
          className="fixed bottom-0 left-0 right-0 z-50 bg-[#0a0a0f] border-t border-emerald-500/30 max-h-[55vh] overflow-auto"
          style={{ fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace" }}
        >
          {/* 标题栏 */}
          <div className="sticky top-0 bg-[#0a0a0f] flex items-center justify-between px-4 py-2.5 border-b border-white/5">
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-emerald-400 font-semibold text-xs tracking-wider uppercase">Backend Diagnostics</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => { setIsDiagLoading(true); runBackendDiag().then(() => setIsDiagLoading(false)); }}
                disabled={isDiagLoading}
                className="flex items-center gap-1 px-2.5 py-1 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 rounded text-emerald-400 text-[10px] transition-colors disabled:opacity-40 cursor-pointer"
              >
                {isDiagLoading ? (
                  <>
                    <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                    检测中...
                  </>
                ) : '↻ 重新检测'}
              </button>
              <button
                onClick={() => setShowDiagModal(false)}
                className="w-6 h-6 flex items-center justify-center rounded text-gray-500 hover:text-red-400 hover:bg-red-400/10 transition-colors text-sm cursor-pointer"
              >✕</button>
            </div>
          </div>

          {/* 内容区 */}
          <div className="px-4 py-3 text-[11px] leading-relaxed">
            {isDiagLoading ? (
              <div className="flex items-center gap-2 text-emerald-400/60">
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                <span>$ probing backend health...</span>
              </div>
            ) : backendDiag ? (
              <div className="space-y-3">
                {/* 概览行 */}
                <div className="flex items-center gap-2 text-gray-500">
                  <span className="text-gray-600">$</span>
                  <span>diag --check-all</span>
                  <span className="text-emerald-400/60">→ OK</span>
                </div>

                {/* 分隔线 */}
                <div className="border-t border-white/5" />

                {/* 各项检测 */}
                {[
                  {
                    icon: '◆',
                    label: 'BACKEND',
                    name: '后端服务',
                    ok: backendDiag.backend,
                    detail: backendDiag.backend ? 'FastAPI running' : 'Service unreachable',
                  },
                  {
                    icon: '◆',
                    label: 'PYTHON',
                    name: 'Python 环境',
                    ok: backendDiag.python,
                    detail: backendDiag.python_version || 'Not found',
                  },
                  {
                    icon: '◆',
                    label: 'FFMPEG',
                    name: 'FFmpeg 引擎',
                    ok: backendDiag.ffmpeg,
                    detail: backendDiag.ffmpeg_version || 'Not found',
                  },
                  {
                    icon: '◆',
                    label: 'MEMORY',
                    name: '内存',
                    ok: backendDiag.memory,
                    warn: !backendDiag.memory,
                    detail: backendDiag.memory_info
                      ? `${backendDiag.memory_info.available_gb.toFixed(1)}G free / ${backendDiag.memory_info.total_gb.toFixed(1)}G total`
                      : 'Insufficient memory',
                  },
                  {
                    icon: '◆',
                    label: 'STORAGE',
                    name: '磁盘存储',
                    ok: backendDiag.storage,
                    warn: !backendDiag.storage,
                    detail: backendDiag.storage_info
                      ? `${backendDiag.storage_info.available_gb.toFixed(1)}G free / ${backendDiag.storage_info.total_gb.toFixed(1)}G total`
                      : 'Low disk space',
                  },
                  {
                    icon: '◆',
                    label: 'GPU',
                    name: 'GPU 加速',
                    ok: backendDiag.gpu,
                    detail: backendDiag.gpu_info || 'N/A (CPU mode)',
                  },
                ].map(item => (
                  <div key={item.label} className="grid grid-cols-[auto_1fr_auto] gap-x-3 gap-y-0.5">
                    <span className={item.ok ? (item.warn ? 'text-yellow-400' : 'text-emerald-400') : 'text-red-400'}>{item.icon}</span>
                    <span className={item.ok ? 'text-gray-300' : 'text-gray-500'}>
                      <span className="text-gray-600 mr-1.5">[{item.label}]</span>
                      {item.name}
                    </span>
                    <span className={`text-right ${item.ok ? (item.warn ? 'text-yellow-400/70' : 'text-emerald-400/50') : 'text-red-400/50'}`}>
                      {item.ok ? 'OK' : item.warn ? 'WARN' : 'FAIL'}
                    </span>
                    <span />
                    <span className={`pl-4 text-[10px] ${item.ok ? 'text-gray-600' : 'text-gray-700'}`}>{item.detail}</span>
                    <span />
                  </div>
                ))}

                {/* 分隔线 */}
                <div className="border-t border-white/5" />

                {/* 底部时间戳 */}
                <div className="flex items-center gap-2 text-gray-700 text-[10px]">
                  <span>#</span>
                  <span>completed at {new Date().toLocaleTimeString('zh-CN', { hour12: false })}</span>
                </div>
              </div>
            ) : (
              <div className="text-red-400/60">$ error: no response from backend</div>
            )}
          </div>
        </div>
      )}
    </>
  );
};

import React, { useState, useRef, useEffect } from 'react';
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

const formatUptime = (seconds?: number) => {
  if (!seconds) return '-';
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  const parts = [];
  if (days > 0) parts.push(`${days}d`);
  if (hours > 0) parts.push(`${hours}h`);
  if (mins > 0) parts.push(`${mins}m`);
  parts.push(`${secs}s`);
  return parts.join(' ');
};

const Section = ({ title, items }: { title: string; items: Array<{ label: string; name: string; ok?: boolean; warn?: boolean; detail?: string | null; dim?: boolean }> }) => (
  <div>
    <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">{title}</div>
    <div className="space-y-1">
      {items.map(item => (
        <div key={item.label} className={`flex items-center gap-2 ${item.dim ? 'text-gray-500' : ''}`}>
          <span className="w-16 text-gray-600 text-[10px] font-mono shrink-0">{item.label}</span>
          <span className="text-xs">{item.name}</span>
          {item.ok !== undefined && (
            <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded ${item.ok ? 'bg-emerald-500/10 text-emerald-400' : item.warn ? 'bg-yellow-500/10 text-yellow-400' : 'bg-red-500/10 text-red-400'}`}>
              {item.ok ? 'OK' : item.warn ? 'WARN' : 'FAIL'}
            </span>
          )}
          {item.detail && <span className="text-[10px] text-gray-600 ml-2 truncate">{item.detail}</span>}
        </div>
      ))}
    </div>
  </div>
);

export const Header = () => {
  const { connectionStatus, hasUpstreamActivity, hasDownstreamActivity, runBackendDiag, backendDiag } = useBackend();
  const [showDiagModal, setShowDiagModal] = useState(false);
  const [isDiagLoading, setIsDiagLoading] = useState(false);
  const [safePadding, setSafePadding] = useState(0);
  const diagContentRef = useRef<HTMLDivElement>(null);
  const config = statusConfig[connectionStatus];

  useEffect(() => {
    if (!showDiagModal || !diagContentRef.current) return;
    const el = diagContentRef.current;
    const observer = new ResizeObserver(() => {
      setSafePadding(el.scrollHeight * 2);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [showDiagModal]);

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
          className="fixed bottom-0 left-0 right-0 z-50 bg-[#0a0a0f] border-t border-emerald-500/30 flex flex-col"
          style={{ maxHeight: '60vh', fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace" }}
        >
          {/* 标题栏 */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/5 shrink-0">
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-emerald-400 font-semibold text-xs tracking-wider uppercase">Backend Diagnostics</span>
            </div>
            <div className="flex items-center gap-1.5">
              {backendDiag && !isDiagLoading && (
                <button
                  onClick={() => {
                    const lines = [
                      `=== AI音乐修复工具 - 后端诊断报告 ===`,
                      `时间: ${backendDiag.timestamp || new Date().toISOString()}`,
                      ``,
                      `[后端服务]  ${backendDiag.backend ? 'OK' : 'FAIL'}`,
                      `[Python]     ${backendDiag.python ? 'OK' : 'FAIL'}  ${backendDiag.python_version || ''}`,
                      `[FFmpeg]     ${backendDiag.ffmpeg ? 'OK' : 'FAIL'}  ${backendDiag.ffmpeg_version || ''}`,
                      `[内存]       ${backendDiag.memory ? 'OK' : 'WARN'}  ${backendDiag.memory_info ? `${backendDiag.memory_info.available_gb}G / ${backendDiag.memory_info.total_gb}G (${backendDiag.memory_info.used_percent}%使用)` : ''}`,
                      `[磁盘]       ${backendDiag.storage ? 'OK' : 'WARN'}  ${backendDiag.storage_info ? `${backendDiag.storage_info.available_gb}G / ${backendDiag.storage_info.total_gb}G (${backendDiag.storage_info.used_percent}%使用)` : ''}`,
                      `[GPU]        ${backendDiag.gpu ? 'OK' : 'N/A'}   ${backendDiag.gpu_info || ''}`,
                      ``,
                      `--- 系统 ---`,
                      backendDiag.system?.os || '',
                      backendDiag.system?.arch || '',
                      ``,
                      `--- 运行时 ---`,
                      `PID: ${backendDiag.runtime?.pid || ''}  模式: ${backendDiag.runtime?.mobile_mode ? '移动端' : '桌面端'}`,
                      `算法版本: ${(backendDiag.runtime?.algorithm_versions || []).join(', ')}`,
                      `运行时间: ${formatUptime(backendDiag.runtime?.uptime_seconds)}`,
                      ``,
                      `--- 进程资源 ---`,
                      `CPU: ${backendDiag.process?.cpu_percent || '-'}%  内存: ${backendDiag.process?.memory_mb || '-'}MB  线程: ${backendDiag.process?.threads || '-'}`,
                      ``,
                      `--- 目录 ---`,
                      `上传: ${backendDiag.directories?.upload_files ?? '-'} 文件  输出: ${backendDiag.directories?.output_files ?? '-'} 文件  解码: ${backendDiag.directories?.decoded_files ?? '-'} 文件`,
                    ].filter(Boolean).join('\n');
                    navigator.clipboard.writeText(lines);
                  }}
                  className="flex items-center gap-1 px-2 py-1 bg-white/5 hover:bg-white/10 border border-white/10 rounded text-gray-400 hover:text-white text-[10px] transition-colors cursor-pointer"
                  title="复制全部"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                  复制
                </button>
              )}
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
                ) : '↻ 检测'}
              </button>
              <button
                onClick={() => setShowDiagModal(false)}
                className="w-6 h-6 flex items-center justify-center rounded text-gray-500 hover:text-red-400 hover:bg-red-400/10 transition-colors text-sm cursor-pointer"
              >✕</button>
            </div>
          </div>

          {/* 内容区 */}
          <div ref={diagContentRef} className="px-4 py-4 text-xs leading-relaxed overflow-y-auto min-h-0">
            {isDiagLoading ? (
              <div className="flex items-center gap-2 text-emerald-400/60 py-8 justify-center">
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                <span>$ probing backend health...</span>
              </div>
            ) : backendDiag ? (
              <div className="space-y-4">
                {/* 概览 */}
                <div className="flex items-center gap-2 text-gray-500">
                  <span className="text-gray-600">$</span>
                  <span>diag --check-all</span>
                  <span className="text-emerald-400/60">→ OK</span>
                  {backendDiag.timestamp && (
                    <span className="text-gray-700 text-[10px] ml-auto">{new Date(backendDiag.timestamp).toLocaleTimeString('zh-CN', { hour12: false })}</span>
                  )}
                </div>

                <div className="border-t border-white/5" />

                {/* === 核心组件 === */}
                <Section title="核心组件" items={[
                  { label: 'BACKEND', name: '后端服务', ok: backendDiag.backend, detail: 'FastAPI running' },
                  { label: 'PYTHON', name: 'Python 环境', ok: backendDiag.python, detail: backendDiag.python_version },
                  { label: 'FFMPEG', name: 'FFmpeg 引擎', ok: backendDiag.ffmpeg, detail: backendDiag.ffmpeg_version },
                  { label: 'MEMORY', name: '内存', ok: backendDiag.memory, warn: !backendDiag.memory, detail: backendDiag.memory_info ? `${backendDiag.memory_info.available_gb.toFixed(1)}G free / ${backendDiag.memory_info.total_gb.toFixed(1)}G (${backendDiag.memory_info.used_percent}%使用)` : null },
                  { label: 'STORAGE', name: '磁盘存储', ok: backendDiag.storage, warn: !backendDiag.storage, detail: backendDiag.storage_info ? `${backendDiag.storage_info.available_gb.toFixed(1)}G free / ${backendDiag.storage_info.total_gb.toFixed(1)}G (${backendDiag.storage_info.used_percent}%使用)` : null },
                  { label: 'GPU', name: 'GPU 加速', ok: backendDiag.gpu, detail: backendDiag.gpu_info },
                ]} />

                {/* === 系统信息 === */}
                {backendDiag.system && (
                  <>
                    <div className="border-t border-white/5" />
                    <Section title="系统信息" items={[
                      { label: 'OS', name: '操作系统', ok: true, detail: backendDiag.system.os, dim: true },
                      { label: 'ARCH', name: '架构', ok: true, detail: backendDiag.system.arch, dim: true },
                      { label: 'HOST', name: '主机名', ok: true, detail: backendDiag.system.hostname, dim: true },
                    ]} />
                  </>
                )}

                {/* === 运行时 === */}
                {backendDiag.runtime && (
                  <>
                    <div className="border-t border-white/5" />
                    <Section title="运行时" items={[
                      { label: 'PID', name: '进程ID', ok: true, detail: String(backendDiag.runtime.pid), dim: true },
                      { label: 'MODE', name: '运行模式', ok: true, detail: backendDiag.runtime.mobile_mode ? '📱 移动端' : '🖥️ 桌面端', dim: true },
                      { label: 'VER', name: '算法版本', ok: true, detail: (backendDiag.runtime.algorithm_versions || []).join(', '), dim: true },
                      { label: 'UP', name: '运行时长', ok: true, detail: formatUptime(backendDiag.runtime.uptime_seconds), dim: true },
                    ]} />
                  </>
                )}

                {/* === 进程资源 === */}
                {backendDiag.process && (
                  <>
                    <div className="border-t border-white/5" />
                    <Section title="进程资源" items={[
                      { label: 'CPU', name: 'CPU占用', ok: (backendDiag.process.cpu_percent || 0) < 80, warn: (backendDiag.process.cpu_percent || 0) >= 80, detail: `${backendDiag.process.cpu_percent}%`, dim: true },
                      { label: 'RSS', name: '内存占用', ok: (backendDiag.process.memory_mb || 0) < 1024, warn: (backendDiag.process.memory_mb || 0) >= 1024, detail: `${backendDiag.process.memory_mb}MB`, dim: true },
                      { label: 'THR', name: '线程数', ok: true, detail: String(backendDiag.process.threads), dim: true },
                      ...(backendDiag.process.fd_count != null ? [{ label: 'FD', name: '文件描述符', ok: true, detail: String(backendDiag.process.fd_count), dim: true }] : []),
                    ]} />
                  </>
                )}

                {/* === 目录状态 === */}
                {backendDiag.directories && (
                  <>
                    <div className="border-t border-white/5" />
                    <Section title="目录状态" items={[
                      { label: 'UPLOAD', name: '上传目录', ok: true, detail: `${backendDiag.directories.upload_files} 文件`, dim: true },
                      { label: 'OUTPUT', name: '输出目录', ok: true, detail: `${backendDiag.directories.output_files} 文件`, dim: true },
                      { label: 'DECODED', name: '解码缓存', ok: true, detail: `${backendDiag.directories.decoded_files} 文件`, dim: true },
                    ]} />
                  </>
                )}

                <div className="border-t border-white/5" />

                <div className="flex items-center gap-2 text-gray-700 text-[11px]">
                  <span>#</span>
                  <span>completed at {new Date().toLocaleTimeString('zh-CN', { hour12: false })}</span>
                </div>

                {safePadding > 0 && <div style={{ height: safePadding }} aria-hidden="true" />}
              </div>
            ) : (
              <div className="text-red-400/60 py-8">$ error: no response from backend</div>
            )}
          </div>
        </div>
      )}
    </>
  );
};

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';
import { useBackend } from '../contexts/BackendContext';

interface CacheInfo {
  total_size: number;
  upload_size: number;
  output_size: number;
  task_count: number;
  tasks: CacheTask[];
}

interface CacheTask {
  id: string;
  filename: string;
  status: string;
}

export default function LandingPage() {
  const navigate = useNavigate();
  const { backendAvailable } = useBackend();
  const [algorithmVersions, setAlgorithmVersions] = useState<{ name: string; description?: string }[]>([]);
  const [detectorVersions, setDetectorVersions] = useState<{ name: string; description?: string }[]>([]);
  const [deployDays, setDeployDays] = useState<number | null>(null);
  const [cacheTaskCount, setCacheTaskCount] = useState<number>(0);

  const fetchCacheCount = async () => {
    try {
      const res = await fetch('/api/v1/cache/info');
      if (res.ok) {
        const data = await res.json();
        setCacheTaskCount(data.task_count || 0);
      }
    } catch { /* ignore */ }
  };

  const fetchVersions = async () => {
    try {
      const [algRes, detRes, deployRes] = await Promise.all([
        fetch('/api/v1/algorithm-versions'),
        fetch('/api/v1/detector-versions'),
        fetch('/api/v1/deploy-info'),
      ]);
      if (algRes.ok) {
        const algData = await algRes.json();
        setAlgorithmVersions(algData.versions || []);
      }
      if (detRes.ok) {
        const detData = await detRes.json();
        setDetectorVersions(detData.versions || []);
      }
      if (deployRes.ok) {
        const deployData = await deployRes.json();
        setDeployDays(deployData.deploy_days ?? null);
      }
    } catch (err) {
      console.error('获取版本信息失败:', err);
    }
  };

  useEffect(() => {
    fetchCacheCount();
    fetchVersions();
  }, []);

  return (
    <div className="min-h-screen bg-dark">
      <Header />

      <div className="container mx-auto px-4 py-16 max-w-6xl">
        {/* Hero Section */}
        <div className="text-center mb-16">
          <h1 className="text-4xl md:text-5xl font-bold text-white mb-4">
            AI 音乐处理工具
          </h1>
          <p className="text-gray-400 text-lg max-w-2xl mx-auto">
            专业的 AI 音乐修复与检测工具，帮助您识别和优化 AI 生成的音乐内容
          </p>
        </div>

        {/* Feature Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          {/* AI 音乐修复 */}
          <div
            onClick={() => navigate('/repair')}
            className="group bg-primary/50 border border-white/10 rounded-2xl p-8 cursor-pointer
                       hover:border-cyan-400/50 hover:bg-primary/70 transition-all duration-300"
          >
            <div className="w-16 h-16 bg-gradient-to-br from-cyan-500/20 to-purple-500/20 rounded-xl
                            flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
              <svg className="w-8 h-8 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2z" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">AI 音乐修复</h2>
            <p className="text-gray-400 mb-4">
              使用先进的 AI 算法修复和优化 AI 生成的音乐，提升音质，减少失真
            </p>
            <div className="flex items-center text-cyan-400 group-hover:text-cyan-300">
              <span className="text-sm font-medium">开始修复</span>
              <svg className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </div>
          </div>

          {/* AI 训练素材上传 */}
          <div
            onClick={() => navigate('/training-upload')}
            className="group bg-primary/50 border border-white/10 rounded-2xl p-8 cursor-pointer
                       hover:border-purple-400/50 hover:bg-primary/70 transition-all duration-300"
          >
            <div className="w-16 h-16 bg-gradient-to-br from-purple-500/20 to-pink-500/20 rounded-xl
                            flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
              <svg className="w-8 h-8 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">AI 训练素材上传</h2>
            <p className="text-gray-400 mb-4">
              上传 AI 生成的音乐作为训练素材，帮助我们改进检测算法
            </p>
            <div className="flex items-center text-purple-400 group-hover:text-purple-300">
              <span className="text-sm font-medium">上传素材</span>
              <svg className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </div>
          </div>

          {/* 修复参数配置管理 */}
          <div
            onClick={() => navigate('/profile-manager')}
            className="group bg-primary/50 border border-white/10 rounded-2xl p-8 cursor-pointer
                       hover:border-amber-400/50 hover:bg-primary/70 transition-all duration-300"
          >
            <div className="w-16 h-16 bg-gradient-to-br from-amber-500/20 to-orange-500/20 rounded-xl
                            flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
              <svg className="w-8 h-8 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 001.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">修复参数配置</h2>
            <p className="text-gray-400 mb-4">
              保存、管理、导入导出修复参数配置，快速切换预设
            </p>
            <div className="flex items-center text-amber-400 group-hover:text-amber-300">
              <span className="text-sm font-medium">管理配置</span>
              <svg className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </div>
          </div>

          {/* 质量测试 */}
          <div
            onClick={() => navigate('/quality-tests')}
            className="group bg-primary/50 border border-white/10 rounded-2xl p-8 cursor-pointer
                       hover:border-emerald-400/50 hover:bg-primary/70 transition-all duration-300"
          >
            <div className="w-16 h-16 bg-gradient-to-br from-emerald-500/20 to-cyan-500/20 rounded-xl
                            flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
              <svg className="w-8 h-8 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">质量测试</h2>
            <p className="text-gray-400 mb-4">
              自动化测试套件，确保修复算法不引入可闻失真和 AM 伪影
            </p>
            <div className="flex items-center text-emerald-400 group-hover:text-emerald-300">
              <span className="text-sm font-medium">运行测试</span>
              <svg className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </div>
          </div>

          {/* 缓存管理 */}
          <div
            onClick={() => navigate('/cache-manager')}
            className="group bg-primary/50 border border-white/10 rounded-2xl p-8 cursor-pointer
                       hover:border-cyan-400/50 hover:bg-primary/70 transition-all duration-300"
          >
            <div className="w-16 h-16 bg-gradient-to-br from-cyan-500/20 to-purple-500/20 rounded-xl
                            flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
              <svg className="w-8 h-8 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">缓存管理</h2>
            <p className="text-gray-400 mb-4">
              管理后端服务、前端存储和音频解析缓存{cacheTaskCount > 0 ? ` · ${cacheTaskCount} 个任务` : ''}
            </p>
            <div className="flex items-center text-cyan-400 group-hover:text-cyan-300">
              <span className="text-sm font-medium">管理缓存</span>
              <svg className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </div>
          </div>

          {/* 音频 AB 对比 */}
          <div
            onClick={() => navigate('/compare')}
            className="group bg-primary/50 border border-white/10 rounded-2xl p-8 cursor-pointer
                       hover:border-indigo-400/50 hover:bg-primary/70 transition-all duration-300"
          >
            <div className="w-16 h-16 bg-gradient-to-br from-indigo-500/20 to-cyan-500/20 rounded-xl
                            flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
              <svg className="w-8 h-8 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">音频 AB 对比</h2>
            <p className="text-gray-400 mb-4">
              播放服务器缓存的原始与修复后音频，实时切换对比音质差异
            </p>
            <div className="flex items-center text-indigo-400 group-hover:text-indigo-300">
              <span className="text-sm font-medium">开始对比</span>
              <svg className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </div>
          </div>

          {/* AI检测分析 */}
          <div
            onClick={() => navigate('/detect')}
            className="group bg-primary/50 border border-white/10 rounded-2xl p-8 cursor-pointer
                       hover:border-pink-400/50 hover:bg-primary/70 transition-all duration-300"
          >
            <div className="w-16 h-16 bg-gradient-to-br from-pink-500/20 to-purple-500/20 rounded-xl
                            flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
              <svg className="w-8 h-8 text-pink-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M9 19v-6a2 2 0 01-2-2H5a2 2 0 01-2 2v6a2 2 0 012 2h2a2 2 0 012-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 012 2h2a2 2 0 012-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">AI检测分析</h2>
            <p className="text-gray-400 mb-4">
              独立检测任意音频的AI生成概率，支持本地文件和服务端音频对比分析
            </p>
            <div className="flex items-center text-pink-400 group-hover:text-pink-300">
              <span className="text-sm font-medium">开始检测</span>
              <svg className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </div>
          </div>

          {/* 系统流程可视化 */}
          <div
            onClick={() => navigate('/flow')}
            className="group bg-primary/50 border border-white/10 rounded-2xl p-8 cursor-pointer
                       hover:border-cyan-400/50 hover:bg-primary/70 transition-all duration-300"
          >
            <div className="w-16 h-16 bg-gradient-to-br from-cyan-500/20 to-emerald-500/20 rounded-xl
                            flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
              <svg className="w-8 h-8 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white mb-3">系统流程可视化</h2>
            <p className="text-gray-400 mb-4">
              交互式系统架构图，展示前端组件、后端服务与数据流的完整拓扑关系
            </p>
            <div className="flex items-center text-cyan-400 group-hover:text-cyan-300">
              <span className="text-sm font-medium">查看架构</span>
              <svg className="w-5 h-5 ml-2 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </div>
          </div>
        </div>

        {/* Recent Updates Section */}
        <div className="mt-16 max-w-4xl mx-auto">
          <div className="bg-primary/50 border border-white/10 rounded-2xl p-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 bg-gradient-to-br from-pink-500/20 to-cyan-500/20 rounded-xl flex items-center justify-center border border-pink-400/20">
                <svg className="w-6 h-6 text-pink-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div>
                <h3 className="text-white font-bold text-xl">最近更新</h3>
                <p className="text-gray-400 text-sm">功能更新与优化</p>
              </div>
            </div>
            
            <div className="space-y-4">
              <div className="flex items-start gap-4 p-4 bg-black/20 rounded-xl border border-white/5">
                <div className="flex-shrink-0 w-2 h-2 mt-2 rounded-full bg-pink-400"></div>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="text-white font-semibold">AI 检测独立页面 + 浏览器修复移除</h4>
                    <span className="text-gray-500 text-xs">2026-05-11</span>
                  </div>
                  <p className="text-gray-400 text-sm">AI 检测功能独立为专属页面，支持本地文件与服务端音频 A/B 对比分析，检测时间可追溯；后端修复速度和质量已全面超越浏览器，移除浏览器修复通道及 Worker，简化架构。</p>
                </div>
              </div>

              <div className="flex items-start gap-4 p-4 bg-black/20 rounded-xl border border-white/5">
                <div className="flex-shrink-0 w-2 h-2 mt-2 rounded-full bg-cyan-400"></div>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="text-white font-semibold">即时播放 + 频谱优化</h4>
                    <span className="text-gray-500 text-xs">2026-05-10</span>
                  </div>
                  <p className="text-gray-400 text-sm">修复播放闭包过期导致 streaming 播放失效的根因问题，大文件加载后可立即播放；频谱从128段精简至32段并增加频率/分贝坐标刻度，90fps 流畅渲染。</p>
                </div>
              </div>

              <div className="flex items-start gap-4 p-4 bg-black/20 rounded-xl border border-white/5">
                <div className="flex-shrink-0 w-2 h-2 mt-2 rounded-full bg-purple-400"></div>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="text-white font-semibold">服务器数据独立获取</h4>
                    <span className="text-gray-500 text-xs">2026-05-10</span>
                  </div>
                  <p className="text-gray-400 text-sm">修复后端连接后服务器内存/存储信息不显示的问题，移除 duration≤0 阻断，后端连接即获取数据。</p>
                </div>
              </div>

              <div className="flex items-start gap-4 p-4 bg-black/20 rounded-xl border border-white/5">
                <div className="flex-shrink-0 w-2 h-2 mt-2 rounded-full bg-emerald-400"></div>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="text-white font-semibold">解析动画 + 替换文件保护</h4>
                    <span className="text-gray-500 text-xs">2026-05-10</span>
                  </div>
                  <p className="text-gray-400 text-sm">音频卡片解析时顺时针渐变高亮动画；解析中替换文件增加取消令牌保护，避免旧解码结果覆盖新文件状态。</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Stats Section */}
        <div className="mt-16 grid grid-cols-2 md:grid-cols-4 gap-6 max-w-4xl mx-auto">
          <div className="text-center p-4 bg-white/5 rounded-xl">
            <div className="text-3xl font-bold text-cyan-400 mb-1">{deployDays !== null ? `${deployDays}` : '-'}</div>
            <div className="text-sm text-gray-400">已部署天数</div>
          </div>
          <div className="text-center p-4 bg-white/5 rounded-xl">
            <div className="text-3xl font-bold text-purple-400 mb-1">{algorithmVersions.length || '-'}</div>
            <div className="text-sm text-gray-400">修复算法版本</div>
          </div>
          <div className="text-center p-4 bg-white/5 rounded-xl">
            <div className="text-3xl font-bold text-pink-400 mb-1">{detectorVersions.length || '-'}</div>
            <div className="text-sm text-gray-400">检测算法版本</div>
          </div>
          <div className="text-center p-4 bg-white/5 rounded-xl">
            <div className="text-3xl font-bold text-green-400 mb-1">{cacheTaskCount || '-'}</div>
            <div className="text-sm text-gray-400">已处理任务</div>
          </div>
        </div>

        {/* Dev: 下载安卓包 */}
        {import.meta.env.DEV && (
          <div className="mt-8 text-center">
            <a
              href="/release_android.tar.gz"
              download="sono-android.tar.gz"
              className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-emerald-600 to-cyan-600 text-white rounded-xl font-medium hover:from-emerald-500 hover:to-cyan-500 transition shadow-lg shadow-emerald-500/20"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              下载安卓安装包
            </a>
            <p className="text-xs text-gray-500 mt-2">仅开发模式显示 · 包内含后端 + 前端 + 部署脚本</p>
          </div>
        )}
      </div>

      <footer className="mt-12 pb-6 text-center">
        <a
          href="https://github.com/Hi-Windom/sono"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 text-gray-500 hover:text-gray-300 transition text-sm"
        >
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
          GitHub
        </a>
      </footer>
    </div>
  );
}

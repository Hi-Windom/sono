import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';

interface CacheTask {
  id: string;
  filename: string;
  status: string;
  progress: number;
  step: string;
  original_path: string;
  output_path: string;
  original_exists: boolean;
  output_exists: boolean;
  original_size: number;
  output_size: number;
  total_size: number;
  file_hash: string;
  created_at: string;
  updated_at: string;
  error: string;
}

interface CacheInfo {
  total_size: number;
  upload_size: number;
  output_size: number;
  task_count: number;
  invalid_count: number;
  tasks: CacheTask[];
  invalid_tasks: CacheTask[];
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatDateTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes}分钟前`;
  if (hours < 24) return `${hours}小时前`;
  if (days < 7) return `${days}天前`;
  return date.toLocaleDateString();
}

export default function LandingPage() {
  const navigate = useNavigate();
  const [cacheInfo, setCacheInfo] = useState<CacheInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [cleaningStep, setCleaningStep] = useState('');
  const [algorithmVersions, setAlgorithmVersions] = useState<{ name: string; description?: string }[]>([]);
  const [detectorVersions, setDetectorVersions] = useState<{ name: string; description?: string }[]>([]);
  const [deployDays, setDeployDays] = useState<number | null>(null);

  const fetchCacheInfo = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/v1/cache/info');
      if (res.ok) {
        const data = await res.json();
        setCacheInfo(data);
      }
    } catch (err) {
      console.error('获取缓存信息失败:', err);
    } finally {
      setLoading(false);
    }
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
    fetchCacheInfo();
    fetchVersions();
    const interval = setInterval(fetchCacheInfo, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleCleanInvalid = async () => {
    if (!confirm('确定要清理所有无效缓存吗？（包括损坏的文件和错误的任务）')) return;
    
    setCleaning(true);
    setCleaningStep('正在清理无效缓存...');
    
    try {
      const res = await fetch('/api/v1/cache/clean-invalid', { method: 'POST' });
      console.log('清理无效缓存响应状态:', res.status);
      if (res.ok) {
        const result = await res.json();
        console.log('清理无效缓存结果:', result);
        setCleaningStep(`已清理 ${result.cleaned_count} 个无效缓存，释放了 ${formatBytes(result.released_bytes)} 空间`);
        setTimeout(() => {
          setCleaning(false);
          setCleaningStep('');
          fetchCacheInfo();
        }, 1500);
      } else {
        const errorText = await res.text();
        console.error('清理无效缓存失败:', errorText);
        throw new Error(`清理请求失败: ${res.status}`);
      }
    } catch (err) {
      console.error('清理无效缓存异常:', err);
      alert(err instanceof Error ? err.message : '清理失败');
      setCleaning(false);
      setCleaningStep('');
    }
  };

  const handleClearOutput = async () => {
    if (!confirm('确定要清理所有输出缓存吗？这将删除所有修复后的文件，但保留原始上传文件。')) return;
    
    setCleaning(true);
    setCleaningStep('正在清理输出缓存...');
    
    try {
      const res = await fetch('/api/v1/cache/clear-output', { method: 'POST' });
      if (res.ok) {
        const result = await res.json();
        setCleaningStep(`已清理输出缓存，释放了 ${formatBytes(result.released_bytes)} 空间`);
        setTimeout(() => {
          setCleaning(false);
          setCleaningStep('');
          fetchCacheInfo();
        }, 1500);
      } else {
        throw new Error('清理请求失败');
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : '清理失败');
      setCleaning(false);
      setCleaningStep('');
    }
  };

  const handleClearUpload = async () => {
    if (!confirm('确定要清理所有上传缓存吗？这将删除所有原始上传文件，但保留修复后的输出文件。')) return;
    
    setCleaning(true);
    setCleaningStep('正在清理上传缓存...');
    
    try {
      const res = await fetch('/api/v1/cache/clear-upload', { method: 'POST' });
      if (res.ok) {
        const result = await res.json();
        setCleaningStep(`已清理上传缓存，释放了 ${formatBytes(result.released_bytes)} 空间`);
        setTimeout(() => {
          setCleaning(false);
          setCleaningStep('');
          fetchCacheInfo();
        }, 1500);
      } else {
        throw new Error('清理请求失败');
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : '清理失败');
      setCleaning(false);
      setCleaningStep('');
    }
  };

  const handleClearAll = async () => {
    if (!confirm('确定要清空所有缓存吗？此操作不可恢复！')) return;
    
    setCleaning(true);
    setCleaningStep('正在清空全部缓存...');
    
    try {
      const res = await fetch('/api/v1/cache/clear-all', { method: 'POST' });
      if (res.ok) {
        const result = await res.json();
        setCleaningStep(`已清空所有缓存，释放了 ${formatBytes(result.released_bytes)} 空间`);
        setTimeout(() => {
          setCleaning(false);
          setCleaningStep('');
          fetchCacheInfo();
        }, 1500);
      } else {
        throw new Error('清空请求失败');
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : '清空失败');
      setCleaning(false);
      setCleaningStep('');
    }
  };

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

              <div className="flex items-start gap-4 p-4 bg-black/20 rounded-xl border border-white/5">
                <div className="flex-shrink-0 w-2 h-2 mt-2 rounded-full bg-red-400"></div>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="text-white font-semibold">Android 性能优化</h4>
                    <span className="text-gray-500 text-xs">2026-05-10</span>
                  </div>
                  <p className="text-gray-400 text-sm">Python 后端延迟导入（scipy/repair 按需加载）、C 原生 DSP 库（STFT/ISTFT/压缩器/限幅器 ARM NEON 优化）、.pyc 预编译加速启动。</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Cache Manager Section */}
        <div className="mt-16 max-w-4xl mx-auto">
          <div className="bg-primary/50 border border-white/10 rounded-2xl p-8">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 bg-gradient-to-br from-cyan-500/20 to-purple-500/20 rounded-xl flex items-center justify-center border border-cyan-400/20">
                  <svg className="w-6 h-6 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79 8-4" />
                  </svg>
                </div>
                <div>
                  <h3 className="text-white font-bold text-xl">后端缓存管理</h3>
                  <p className="text-gray-400 text-sm">管理上传文件和修复缓存</p>
                </div>
              </div>
              <button
                onClick={fetchCacheInfo}
                disabled={loading || cleaning}
                className="px-4 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-lg text-cyan-400 text-sm transition disabled:opacity-50"
              >
                {loading ? '加载中...' : '刷新'}
              </button>
            </div>

            {cleaning && (
              <div className="mb-6 p-4 bg-cyan-500/10 border border-cyan-500/30 rounded-lg">
                <div className="flex items-center gap-3">
                  <div className="w-5 h-5 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin"></div>
                  <span className="text-cyan-400">{cleaningStep}</span>
                </div>
              </div>
            )}

            {cacheInfo && (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                  <div className="bg-black/20 rounded-lg p-4 text-center">
                    <div className="text-gray-400 text-xs mb-1">总占用</div>
                    <div className="text-white text-xl font-bold">{formatBytes(cacheInfo.total_size)}</div>
                  </div>
                  <div className="bg-black/20 rounded-lg p-4 text-center">
                    <div className="text-gray-400 text-xs mb-1">任务总数</div>
                    <div className="text-white text-xl font-bold">{cacheInfo.task_count}</div>
                  </div>
                  <div className="bg-black/20 rounded-lg p-4 text-center">
                    <div className="text-gray-400 text-xs mb-1">上传文件夹</div>
                    <div className="text-cyan-400 text-lg font-bold">{formatBytes(cacheInfo.upload_size)}</div>
                  </div>
                  <div className="bg-black/20 rounded-lg p-4 text-center">
                    <div className="text-gray-400 text-xs mb-1">输出文件夹</div>
                    <div className="text-purple-400 text-lg font-bold">{formatBytes(cacheInfo.output_size)}</div>
                  </div>
                </div>

                {cacheInfo.invalid_count > 0 && (
                  <div className="mb-6 p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-yellow-400">
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        <span className="font-medium">检测到 {cacheInfo.invalid_count} 个无效缓存</span>
                      </div>
                      <button
                        onClick={handleCleanInvalid}
                        disabled={cleaning}
                        className="px-4 py-2 bg-yellow-500/20 hover:bg-yellow-500/30 border border-yellow-500/30 rounded text-yellow-400 text-sm transition disabled:opacity-50"
                      >
                        清理无效
                      </button>
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <button
                    onClick={handleClearUpload}
                    disabled={cacheInfo.upload_size === 0 || cleaning}
                    className="px-4 py-3 bg-orange-500/20 hover:bg-orange-500/30 border border-orange-500/30 rounded-lg text-orange-400 text-sm transition disabled:opacity-50"
                  >
                    清理上传缓存
                  </button>
                  <button
                    onClick={handleClearOutput}
                    disabled={cacheInfo.output_size === 0 || cleaning}
                    className="px-4 py-3 bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/30 rounded-lg text-purple-400 text-sm transition disabled:opacity-50"
                  >
                    清理输出缓存
                  </button>
                  <button
                    onClick={handleClearAll}
                    disabled={cacheInfo.total_size === 0 || cleaning}
                    className="px-4 py-3 bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 rounded-lg text-red-400 text-sm transition disabled:opacity-50"
                  >
                    清空全部缓存
                  </button>
                </div>

                {cacheInfo.tasks?.length > 0 && (
                  <div className="mt-6">
                    <div className="text-gray-400 text-sm mb-3">最近任务 ({cacheInfo.tasks.length})</div>
                    <div className="max-h-64 overflow-y-auto bg-black/20 rounded-lg border border-white/10">
                      {cacheInfo.tasks.slice(0, 10).map((task) => {
                        const isInvalid = Array.isArray(cacheInfo.invalid_tasks) && cacheInfo.invalid_tasks.some(t => t.id === task.id);
                        return (
                          <div key={task.id} className={`p-3 hover:bg-white/5 ${isInvalid ? 'bg-red-500/5' : ''}`}>
                            <div className="flex items-center justify-between mb-1">
                              <div className="flex items-center gap-2 min-w-0 flex-1">
                                <span className="text-white text-sm font-medium truncate">{task.filename}</span>
                                <span className={`text-xs px-2 py-0.5 rounded flex-shrink-0 ${
                                  task.status === 'completed' ? 'bg-emerald-500/20 text-emerald-400' :
                                  task.status === 'error' || task.status === 'timeout' ? 'bg-red-500/20 text-red-400' :
                                  'bg-yellow-500/20 text-yellow-400'
                                }`}>
                                  {task.status === 'completed' ? '完成' : task.status === 'error' ? '错误' : task.status === 'timeout' ? '超时' : '进行中'}
                                </span>
                                {isInvalid && (
                                  <span className="text-xs text-red-400 bg-red-500/10 px-2 py-0.5 rounded flex-shrink-0">无效</span>
                                )}
                              </div>
                              <span className="text-gray-500 text-xs flex-shrink-0 ml-2">{formatBytes(task.total_size)}</span>
                            </div>
                            <div className="flex items-center justify-between text-xs text-gray-500">
                              <span>{formatDateTime(task.created_at)}</span>
                              {task.error && (
                                <span className="text-red-400 truncate max-w-xs">{task.error}</span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </>
            )}
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
            <div className="text-3xl font-bold text-green-400 mb-1">{cacheInfo?.task_count ?? '-'}</div>
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
    </div>
  );
}

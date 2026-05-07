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

  useEffect(() => {
    fetchCacheInfo();
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
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-4xl mx-auto">
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
                    <h4 className="text-white font-semibold">智能缓存系统重构</h4>
                    <span className="text-gray-500 text-xs">2026-05-07</span>
                  </div>
                  <p className="text-gray-400 text-sm">上传缓存与修复结果缓存解耦：上传层仅按文件 hash 去重，修复结果层按文件+算法+参数三重匹配命中。修复默认算法版本硬编码、Session 持久化不完整等问题。</p>
                </div>
              </div>

              <div className="flex items-start gap-4 p-4 bg-black/20 rounded-xl border border-white/5">
                <div className="flex-shrink-0 w-2 h-2 mt-2 rounded-full bg-red-400"></div>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="text-white font-semibold">任务取消 + 移动端导出修复</h4>
                    <span className="text-gray-500 text-xs">2026-05-07</span>
                  </div>
                  <p className="text-gray-400 text-sm">新增全栈任务取消机制（前端按钮 + 后端 cancel_task）；修复移动端音频导出无反应、文件名异常、浏览器崩溃等问题；Worker 编码超时保护。</p>
                </div>
              </div>

              <div className="flex items-start gap-4 p-4 bg-black/20 rounded-xl border border-white/5">
                <div className="flex-shrink-0 w-2 h-2 mt-2 rounded-full bg-purple-400"></div>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="text-white font-semibold">Python 强制类型检查</h4>
                    <span className="text-gray-500 text-xs">2026-05-07</span>
                  </div>
                  <p className="text-gray-400 text-sm">引入 pyright strict mode，核心基础设施（database/task_manager/ws_manager/file_cache）全量类型注解，算法模块按需降级。</p>
                </div>
              </div>

              <div className="flex items-start gap-4 p-4 bg-black/20 rounded-xl border border-white/5">
                <div className="flex-shrink-0 w-2 h-2 mt-2 rounded-full bg-emerald-400"></div>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <h4 className="text-white font-semibold">检测 v1.2 / 修复 v2.1 支持</h4>
                    <span className="text-gray-500 text-xs">2026-05-07</span>
                  </div>
                  <p className="text-gray-400 text-sm">新增检测 v1.2 和修复 v2.1 算法，整理文件结构（detectors/ 和 repair/ 目录）。</p>
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
            <div className="text-3xl font-bold text-cyan-400 mb-1">v2.0</div>
            <div className="text-sm text-gray-400">最新算法版本</div>
          </div>
          <div className="text-center p-4 bg-white/5 rounded-xl">
            <div className="text-3xl font-bold text-purple-400 mb-1">4</div>
            <div className="text-sm text-gray-400">修复算法版本</div>
          </div>
          <div className="text-center p-4 bg-white/5 rounded-xl">
            <div className="text-3xl font-bold text-pink-400 mb-1">2</div>
            <div className="text-sm text-gray-400">检测算法版本</div>
          </div>
          <div className="text-center p-4 bg-white/5 rounded-xl">
            <div className="text-3xl font-bold text-green-400 mb-1">实时</div>
            <div className="text-sm text-gray-400">浏览器处理</div>
          </div>
        </div>
      </div>
    </div>
  );
}

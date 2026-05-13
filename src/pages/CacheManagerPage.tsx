import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';
import { loadSettings } from '../utils/settingsStorage';
import { fetchDeliveryFiles, deleteDeliveryFile, deleteDeliveryParent } from '../services/backendApi';
import type { DeliveryFile } from '../services/backendApi';

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
  render_caches?: { filename: string; size: number }[];
}

interface CacheInfo {
  total_size: number;
  upload_size: number;
  output_size: number;
  repair_size: number;
  render_size: number;
  upload_count: number;
  output_count: number;
  repair_count: number;
  render_count: number;
  task_count: number;
  invalid_count: number;
  invalid_size: number;
  tasks: CacheTask[];
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

type TabType = 'backend' | 'frontend' | 'analysis' | 'delivery';

export default function CacheManagerPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabType>('backend');

  // 后端缓存
  const [cacheInfo, setCacheInfo] = useState<CacheInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [cleaningStep, setCleaningStep] = useState('');
  const [expandedTask, setExpandedTask] = useState<string | null>(null);

  // 前端缓存
  const [sessionSize, setSessionSize] = useState(0);
  const [settingsSize, setSettingsSize] = useState(0);
  const [settingsCount, setSettingsCount] = useState(0);

  // 解析缓存
  const [analysisEntries, setAnalysisEntries] = useState<Record<string, string | number>[]>([]);
  const [analysisCount, setAnalysisCount] = useState(0);

  // 交付渲染
  const [deliveryFiles, setDeliveryFiles] = useState<DeliveryFile[]>([]);
  const [deliveryLoading, setDeliveryLoading] = useState(false);
  const [deliveryError, setDeliveryError] = useState<string | null>(null);
  const [expandedParent, setExpandedParent] = useState<string | null>(null);

  // 后端缓存操作
  const fetchCacheInfo = useCallback(async () => {
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
  }, []);

  const handleCleanInvalid = async () => {
    if (!confirm('确定要清理所有无效缓存吗？')) return;
    setCleaning(true);
    setCleaningStep('正在清理无效缓存...');
    try {
      const res = await fetch('/api/v1/cache/clean-invalid', { method: 'POST' });
      if (res.ok) {
        const result = await res.json();
        setCleaningStep(`已清理 ${result.cleaned_count} 个，释放 ${formatBytes(result.released_bytes)}`);
        setTimeout(() => { setCleaning(false); setCleaningStep(''); fetchCacheInfo(); }, 1500);
      } else { throw new Error('清理失败'); }
    } catch { setCleaning(false); setCleaningStep(''); }
  };

  const handleClearUpload = async () => {
    if (!confirm('确定清理所有上传缓存？将删除原始上传文件，保留修复输出。')) return;
    setCleaning(true); setCleaningStep('正在清理...');
    try {
      const res = await fetch('/api/v1/cache/clear-upload', { method: 'POST' });
      if (res.ok) {
        const result = await res.json();
        setCleaningStep(`已释放 ${formatBytes(result.released_bytes)}`);
        setTimeout(() => { setCleaning(false); setCleaningStep(''); fetchCacheInfo(); }, 1500);
      }
    } catch { setCleaning(false); setCleaningStep(''); }
  };

  const handleClearRepair = async () => {
    if (!confirm('确定清理修复缓存？将删除修复输出文件，保留原始上传和交付渲染。')) return;
    setCleaning(true); setCleaningStep('正在清理...');
    try {
      const res = await fetch('/api/v1/cache/clear-output', { method: 'POST' });
      if (res.ok) {
        const result = await res.json();
        setCleaningStep(`已释放 ${formatBytes(result.released_bytes)}`);
        setTimeout(() => { setCleaning(false); setCleaningStep(''); fetchCacheInfo(); }, 1500);
      }
    } catch { setCleaning(false); setCleaningStep(''); }
  };

  const handleClearRender = async () => {
    if (!confirm('确定清理所有交付渲染缓存？')) return;
    setCleaning(true); setCleaningStep('正在清理交付渲染...');
    try {
      const res = await fetch('/api/v1/cache/clear-render', { method: 'POST' });
      if (res.ok) {
        const result = await res.json();
        setCleaningStep(`已清理 ${result.cleaned_count} 个渲染文件，释放 ${formatBytes(result.released_bytes)}`);
        setTimeout(() => { setCleaning(false); setCleaningStep(''); fetchCacheInfo(); }, 1500);
      }
    } catch { setCleaning(false); setCleaningStep(''); }
  };

  const handleClearAll = async () => {
    if (!confirm('确定清空所有后端缓存？此操作不可恢复！')) return;
    setCleaning(true); setCleaningStep('正在清空...');
    try {
      const res = await fetch('/api/v1/cache/clear-all', { method: 'POST' });
      if (res.ok) {
        const result = await res.json();
        setCleaningStep(`已释放 ${formatBytes(result.released_bytes)}`);
        setTimeout(() => { setCleaning(false); setCleaningStep(''); fetchCacheInfo(); }, 1500);
      }
    } catch { setCleaning(false); setCleaningStep(''); }
  };

  const handleDeleteTask = async (taskId: string) => {
    if (!confirm('确定删除此任务缓存？')) return;
    try {
      const res = await fetch(`/api/v1/cache/delete/${taskId}`, { method: 'POST' });
      if (res.ok) fetchCacheInfo();
    } catch { /* ignore */ }
  };

  const handleDeleteRenderCache = async (filename: string) => {
    if (!confirm('确定删除此渲染缓存？')) return;
    try {
      const res = await fetch(`/api/v1/render-cache-file/${encodeURIComponent(filename)}`, { method: 'DELETE' });
      if (!res.ok) {
        // 尝试备选路径
        await fetch(`/api/v1/render-cache/${encodeURIComponent(filename)}`, { method: 'DELETE' });
      }
      fetchCacheInfo();
    } catch { /* ignore */ }
  };

  // 前端缓存操作
  const fetchFrontendCacheInfo = useCallback(async () => {
    // 估算 session 大小
    try {
      const db = await indexedDB.open('audio_repair_session');
      const estimate = await navigator.storage?.estimate?.();
      setSessionSize(estimate?.usage ?? 0);
    } catch { setSessionSize(0); }

    // settings 大小
    try {
      const settings = loadSettings();
      const serialized = JSON.stringify(settings);
      setSettingsSize(new Blob([serialized]).size);
      setSettingsCount(settings.savedProfiles?.length ?? 0);
    } catch { setSettingsSize(0); setSettingsCount(0); }
  }, []);

  const handleClearSession = async () => {
    if (!confirm('确定清除当前会话数据？修复页面将恢复初始状态。')) return;
    const { clearSession } = await import('../utils/sessionDB');
    await clearSession();
    fetchFrontendCacheInfo();
  };

  const handleClearSettings = async () => {
    if (!confirm('确定清除所有设置和配置？')) return;
    localStorage.removeItem('ai-music-repair-settings');
    fetchFrontendCacheInfo();
  };

  // 解析缓存操作（后端 API）
  const fetchAnalysisCache = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/analysis-cache-list');
      if (res.ok) {
        const data = await res.json();
        setAnalysisEntries(data.entries || []);
        setAnalysisCount(data.count || 0);
      }
    } catch { /* ignore */ }
  }, []);

  const handleClearAnalysisCache = async () => {
    if (!confirm('确定清除所有音频解析缓存？')) return;
    await fetch('/api/v1/analysis-cache-clear', { method: 'POST' });
    fetchAnalysisCache();
  };

  const handleDeleteAnalysisEntry = async (quickHash: string) => {
    await fetch(`/api/v1/analysis-cache/${encodeURIComponent(quickHash)}`, { method: 'DELETE' });
    fetchAnalysisCache();
  };

  // 交付渲染操作
  const fetchDeliveryList = useCallback(async () => {
    setDeliveryLoading(true);
    setDeliveryError(null);
    try {
      const data = await fetchDeliveryFiles();
      setDeliveryFiles(data.files || []);
    } catch (err) {
      setDeliveryError('获取交付渲染文件失败');
      setDeliveryFiles([]);
    } finally {
      setDeliveryLoading(false);
    }
  }, []);

  const handleDownloadDelivery = (filename: string) => {
    const a = document.createElement('a');
    a.href = '/api/v1/download/' + encodeURIComponent(filename);
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const handleDeleteDeliveryChild = async (filename: string) => {
    if (!confirm('确定删除此交付文件？')) return;
    try {
      await deleteDeliveryFile(filename);
      fetchDeliveryList();
    } catch { /* ignore */ }
  };

  const handleDeleteDeliveryParent = async (filename: string) => {
    if (!confirm(`确定删除"${filename}"及其所有子文件？此操作不可恢复！`)) return;
    try {
      await deleteDeliveryParent(filename);
      fetchDeliveryList();
    } catch { /* ignore */ }
  };

  useEffect(() => {
    fetchCacheInfo();
    fetchFrontendCacheInfo();
    fetchAnalysisCache();
    fetchDeliveryList();
  }, [fetchCacheInfo, fetchFrontendCacheInfo, fetchAnalysisCache, fetchDeliveryList]);

  const tabs: { key: TabType; label: string; icon: string }[] = [
    { key: 'backend', label: '后端缓存', icon: '🖥️' },
    { key: 'frontend', label: '前端缓存', icon: '📱' },
    { key: 'analysis', label: '解析缓存', icon: '🔍' },
    { key: 'delivery', label: '交付渲染', icon: '🎵' },
  ];

  return (
    <div className="min-h-screen bg-dark">
      <Header />

      <div className="container mx-auto px-4 py-8 max-w-5xl">
        {/* 返回按钮 + 标题 */}
        <div className="flex items-center gap-4 mb-6">
          <button
            onClick={() => navigate('/')}
            className="p-2 bg-white/5 hover:bg-white/10 rounded-lg text-gray-400 hover:text-white transition"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div>
            <h1 className="text-2xl font-bold text-white">缓存管理</h1>
            <p className="text-gray-400 text-sm">管理后端服务、前端存储和音频解析缓存</p>
          </div>
        </div>

        {/* Tab 栏 */}
        <div className="flex gap-1 mb-6 bg-black/30 p-1 rounded-lg">
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex-1 py-2.5 px-4 rounded-lg text-sm font-medium transition-all ${
                activeTab === tab.key
                  ? 'bg-gradient-to-r from-cyan-500/20 to-purple-500/20 text-white border border-cyan-500/30'
                  : 'text-gray-400 hover:text-gray-300 hover:bg-white/5'
              }`}
            >
              <span className="mr-1.5">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>

        {/* 清理中提示 */}
        {cleaning && (
          <div className="mb-6 p-4 bg-cyan-500/10 border border-cyan-500/30 rounded-lg">
            <div className="flex items-center gap-3">
              <div className="w-5 h-5 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
              <span className="text-cyan-400">{cleaningStep}</span>
            </div>
          </div>
        )}

        {/* 后端缓存 Tab */}
        {activeTab === 'backend' && cacheInfo && (
          <div className="space-y-6">
            {/* 统计概览 + 对应清理按钮 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-black/20 rounded-lg p-4">
                <div className="text-gray-400 text-xs mb-1 text-center">总占用</div>
                <div className="text-white text-lg font-bold text-center">{formatBytes(cacheInfo.total_size)}</div>
                <div className="text-gray-500 text-[10px] text-center mb-2">{cacheInfo.task_count} 个任务</div>
                <button
                  onClick={handleClearAll}
                  disabled={cacheInfo.total_size === 0 || cleaning}
                  className="w-full py-1.5 bg-red-500/15 hover:bg-red-500/25 border border-red-500/20 rounded text-red-400 text-xs transition disabled:opacity-30"
                >
                  清空全部
                </button>
              </div>
              <div className="bg-black/20 rounded-lg p-4">
                <div className="text-gray-400 text-xs mb-1 text-center">上传文件</div>
                <div className="text-cyan-400 text-lg font-bold text-center">{formatBytes(cacheInfo.upload_size)}</div>
                <div className="text-gray-500 text-[10px] text-center mb-2">{cacheInfo.upload_count} 个</div>
                <button
                  onClick={handleClearUpload}
                  disabled={cacheInfo.upload_size === 0 || cleaning}
                  className="w-full py-1.5 bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/20 rounded text-cyan-400 text-xs transition disabled:opacity-30"
                >
                  清理上传
                </button>
              </div>
              <div className="bg-black/20 rounded-lg p-4">
                <div className="text-gray-400 text-xs mb-1 text-center">修复输出</div>
                <div className="text-purple-400 text-lg font-bold text-center">{formatBytes(cacheInfo.repair_size)}</div>
                <div className="text-gray-500 text-[10px] text-center mb-2">{cacheInfo.repair_count} 个</div>
                <button
                  onClick={handleClearRepair}
                  disabled={cacheInfo.repair_size === 0 || cleaning}
                  className="w-full py-1.5 bg-purple-500/15 hover:bg-purple-500/25 border border-purple-500/20 rounded text-purple-400 text-xs transition disabled:opacity-30"
                >
                  清理修复
                </button>
              </div>
              <div className="bg-black/20 rounded-lg p-4">
                <div className="text-gray-400 text-xs mb-1 text-center">交付渲染</div>
                <div className="text-emerald-400 text-lg font-bold text-center">{formatBytes(cacheInfo.render_size)}</div>
                <div className="text-gray-500 text-[10px] text-center mb-2">{cacheInfo.render_count} 个</div>
                <button
                  onClick={handleClearRender}
                  disabled={cacheInfo.render_size === 0 || cleaning}
                  className="w-full py-1.5 bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/20 rounded text-emerald-400 text-xs transition disabled:opacity-30"
                >
                  清理交付
                </button>
              </div>
            </div>

            {cacheInfo.invalid_count > 0 && (
              <div className="p-4 bg-yellow-500/5 border border-yellow-500/20 rounded-lg">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-yellow-400 text-sm">⚠️</span>
                    <div>
                      <span className="text-yellow-400 text-sm font-medium">无效缓存</span>
                      <span className="text-yellow-400/70 text-xs ml-2">{cacheInfo.invalid_count} 个 · {formatBytes(cacheInfo.invalid_size)}</span>
                    </div>
                  </div>
                  <button
                    onClick={handleCleanInvalid}
                    disabled={cleaning}
                    className="py-1.5 px-4 bg-yellow-500/15 hover:bg-yellow-500/25 border border-yellow-500/20 rounded text-yellow-400 text-xs transition disabled:opacity-30"
                  >
                    清理无效
                  </button>
                </div>
              </div>
            )}

            {/* 任务列表 */}
            {cacheInfo.tasks?.length > 0 && (
              <div>
                <div className="text-gray-400 text-sm mb-3">任务列表 ({cacheInfo.tasks.length})</div>
                <div className="bg-black/20 rounded-lg border border-white/10 divide-y divide-white/5">
                  {cacheInfo.tasks.map((task) => (
                    <div key={task.id}>
                      <div className="p-3 hover:bg-white/5">
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
                            {task.render_caches && task.render_caches.length > 0 && (
                              <span className="text-xs text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded">
                                {task.render_caches.length} 渲染
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                            <span className="text-gray-500 text-xs">{formatBytes(task.total_size)}</span>
                            <button
                              onClick={() => setExpandedTask(expandedTask === task.id ? null : task.id)}
                              className="text-gray-500 hover:text-white text-xs transition"
                            >
                              {expandedTask === task.id ? '▲' : '▼'}
                            </button>
                            <button
                              onClick={() => handleDeleteTask(task.id)}
                              className="text-gray-500 hover:text-red-400 transition p-1"
                              title="删除任务"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          </div>
                        </div>
                        <div className="text-xs text-gray-500">{formatDateTime(task.created_at)}</div>
                      </div>

                      {/* 展开详情：渲染缓存列表 */}
                      {expandedTask === task.id && task.render_caches && task.render_caches.length > 0 && (
                        <div className="px-3 pb-3">
                          <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-3">
                            <div className="text-emerald-400 text-xs font-medium mb-2">交付渲染缓存</div>
                            {task.render_caches.map((rc, idx) => (
                              <div key={idx} className="flex items-center justify-between py-1.5 text-xs">
                                <div className="flex items-center gap-2">
                                  <span className="text-gray-300">{rc.filename}</span>
                                  <span className="text-gray-500">{formatBytes(rc.size)}</span>
                                </div>
                                <button
                                  onClick={() => handleDeleteRenderCache(rc.filename)}
                                  className="text-gray-500 hover:text-red-400 transition"
                                  title="删除渲染缓存"
                                >
                                  ×
                                </button>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'backend' && !cacheInfo && loading && (
          <div className="text-center py-12 text-gray-400">加载中...</div>
        )}

        {/* 前端缓存 Tab */}
        {activeTab === 'frontend' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* 会话数据 */}
              <div className="bg-black/20 rounded-lg p-5 border border-white/5">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-cyan-400 text-lg">💾</span>
                  <div>
                    <h4 className="text-white font-medium">会话数据</h4>
                    <p className="text-gray-500 text-xs">当前修复会话状态 (IndexedDB)</p>
                  </div>
                </div>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-gray-400 text-sm">存储大小</span>
                  <span className="text-white font-medium">{formatBytes(sessionSize)}</span>
                </div>
                <button
                  onClick={handleClearSession}
                  className="w-full py-2 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-lg text-cyan-400 text-sm transition"
                >
                  清除会话数据
                </button>
              </div>

              {/* 设置数据 */}
              <div className="bg-black/20 rounded-lg p-5 border border-white/5">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-purple-400 text-lg">⚙️</span>
                  <div>
                    <h4 className="text-white font-medium">设置 & 配置</h4>
                    <p className="text-gray-500 text-xs">修复参数配置、算法偏好等 (localStorage)</p>
                  </div>
                </div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-gray-400 text-sm">存储大小</span>
                  <span className="text-white font-medium">{formatBytes(settingsSize)}</span>
                </div>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-gray-400 text-sm">配置数量</span>
                  <span className="text-purple-400 font-medium">{settingsCount}</span>
                </div>
                <button
                  onClick={handleClearSettings}
                  className="w-full py-2 bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/30 rounded-lg text-purple-400 text-sm transition"
                >
                  清除所有设置
                </button>
              </div>
            </div>

            <div className="p-4 bg-yellow-500/5 border border-yellow-500/20 rounded-lg text-xs text-yellow-400/80">
              ⚠️ 清除前端缓存不会影响后端服务器的数据，但可能导致当前修复进度丢失或偏好设置重置。
            </div>
          </div>
        )}

        {/* 解析缓存 Tab */}
        {activeTab === 'analysis' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-white font-medium">音频解析缓存</h3>
                <p className="text-gray-500 text-xs">基于文件哈希的 WAV 头信息 & 音频分析结果缓存</p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-gray-400 text-sm">{analysisCount} 条缓存</span>
                <button
                  onClick={fetchAnalysisCache}
                  className="px-3 py-1.5 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-lg text-cyan-400 text-xs transition"
                >
                  刷新
                </button>
                {analysisCount > 0 && (
                  <button
                    onClick={handleClearAnalysisCache}
                    className="px-3 py-1.5 bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 rounded-lg text-red-400 text-xs transition"
                  >
                    清除全部
                  </button>
                )}
              </div>
            </div>

            {analysisEntries.length > 0 ? (
              <div className="bg-black/20 rounded-lg border border-white/10 divide-y divide-white/5">
                {analysisEntries.map((entry) => (
                  <div key={entry.quick_hash as string} className="p-3 hover:bg-white/5">
                    <div className="flex items-center justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-white text-sm font-medium truncate">{entry.file_name as string}</span>
                          <span className="text-gray-500 text-xs">{formatBytes(entry.file_size as number)}</span>
                        </div>
                        <div className="text-gray-500 text-xs">
                          FileHash: {(entry.quick_hash as string).slice(0, 16)}...
                          {' · '}
                          {entry.created_at ? new Date(entry.created_at as string).toLocaleString() : '—'}
                        </div>
                      </div>
                      <button
                        onClick={() => handleDeleteAnalysisEntry(entry.quick_hash as string)}
                        className="text-gray-500 hover:text-red-400 transition p-1.5 flex-shrink-0"
                        title="删除"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12 text-gray-500">
                暂无音频解析缓存<br />
                <span className="text-xs">上传音频文件后会自动缓存解析结果</span>
              </div>
            )}

            <div className="p-4 bg-cyan-500/5 border border-cyan-500/20 rounded-lg text-xs text-cyan-400/80">
              💡 解析缓存基于文件哈希（前1MB+后1MB），同一文件重复加载时可跳过解析直接使用缓存结果，加速页面响应。非WAV文件会自动创建解码WAV缓存，二次加载可跳过慢速解码。
            </div>
          </div>
        )}

        {/* 交付渲染 Tab */}
        {activeTab === 'delivery' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-white font-medium">交付渲染文件</h3>
                <p className="text-gray-500 text-xs">已渲染完成的交付文件，按任务分组管理</p>
              </div>
              <button
                onClick={fetchDeliveryList}
                disabled={deliveryLoading}
                className="px-3 py-1.5 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-lg text-cyan-400 text-xs transition disabled:opacity-50"
              >
                刷新
              </button>
            </div>

            {deliveryLoading && (
              <div className="text-center py-12 text-gray-400">加载中...</div>
            )}

            {deliveryError && !deliveryLoading && (
              <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
                <div className="flex items-center gap-2">
                  <span className="text-red-400 text-sm">⚠️</span>
                  <span className="text-red-400 text-sm">{deliveryError}</span>
                </div>
                <button
                  onClick={fetchDeliveryList}
                  className="mt-2 px-3 py-1 bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 rounded text-red-400 text-xs transition"
                >
                  重试
                </button>
              </div>
            )}

            {!deliveryLoading && !deliveryError && deliveryFiles.length === 0 && (
              <div className="text-center py-12 text-gray-500">
                暂无交付渲染文件<br />
                <span className="text-xs">完成修复并渲染后，交付文件会出现在这里</span>
              </div>
            )}

            {!deliveryLoading && deliveryFiles.length > 0 && (
              <div className="bg-black/20 rounded-lg border border-white/10 divide-y divide-white/5">
                {deliveryFiles.map((file) => (
                  <div key={file.filename}>
                    <div className="p-3 hover:bg-white/5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          {file.is_parent && (
                            <button
                              onClick={() => setExpandedParent(expandedParent === file.filename ? null : file.filename)}
                              className="text-gray-500 hover:text-white text-xs transition flex-shrink-0"
                            >
                              {expandedParent === file.filename ? '▼' : '▶'}
                            </button>
                          )}
                          <span className="text-white text-sm font-medium truncate">{file.filename}</span>
                          <span className="text-gray-500 text-xs">{formatBytes(file.size)}</span>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                          {file.mtime && (
                            <span className="text-gray-500 text-xs">{formatDateTime(file.mtime)}</span>
                          )}
                          <button
                            onClick={() => handleDownloadDelivery(file.filename)}
                            className="text-gray-500 hover:text-cyan-400 transition p-1"
                            title="下载"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                            </svg>
                          </button>
                          {file.is_parent ? (
                            <button
                              onClick={() => handleDeleteDeliveryParent(file.filename)}
                              className="text-gray-500 hover:text-red-400 transition p-1"
                              title="删除整组"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          ) : (
                            <button
                              onClick={() => handleDeleteDeliveryChild(file.filename)}
                              className="text-gray-500 hover:text-red-400 transition p-1"
                              title="删除"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          )}
                        </div>
                      </div>
                      {!file.is_parent && file.track_type && (
                        <div className="mt-1">
                          <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400">
                            {file.track_type === 'vocal' ? '人声轨' : file.track_type === 'accompaniment' ? '伴奏轨' : file.track_type}
                          </span>
                        </div>
                      )}
                    </div>

                    {expandedParent === file.filename && file.children && file.children.length > 0 && (
                      <div className="px-3 pb-3">
                        <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg divide-y divide-emerald-500/10">
                          {file.children.map((child, idx) => (
                            <div key={idx} className="flex items-center justify-between p-2.5 text-xs">
                              <div className="flex items-center gap-2 min-w-0 flex-1">
                                <span className="text-gray-300 truncate">{child.filename}</span>
                                <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 flex-shrink-0">
                                  {child.track_type === 'vocal' ? '人声轨' : child.track_type === 'accompaniment' ? '伴奏轨' : child.track_type || '音频'}
                                </span>
                                <span className="text-gray-500 flex-shrink-0">{formatBytes(child.size)}</span>
                              </div>
                              <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                                <button
                                  onClick={() => handleDownloadDelivery(child.filename)}
                                  className="text-gray-500 hover:text-cyan-400 transition p-1"
                                  title="下载"
                                >
                                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                  </svg>
                                </button>
                                <button
                                  onClick={() => handleDeleteDeliveryChild(child.filename)}
                                  className="text-gray-500 hover:text-red-400 transition p-1"
                                  title="删除"
                                >
                                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                  </svg>
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

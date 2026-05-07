import React, { useState, useCallback, useEffect } from 'react';

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
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'completed': return 'text-emerald-400';
    case 'error':
    case 'timeout': return 'text-red-400';
    case 'pending':
    case 'repairing':
    case 'detecting': return 'text-yellow-400';
    default: return 'text-gray-400';
  }
}

function getStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    completed: '完成',
    error: '错误',
    timeout: '超时',
    pending: '等待中',
    repairing: '修复中',
    detecting: '检测中',
  };
  return labels[status] || status;
}

export function CacheManager() {
  const [cacheInfo, setCacheInfo] = useState<CacheInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [showTasks, setShowTasks] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchCacheInfo = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/v1/cache/info');
      if (!res.ok) {
        throw new Error('获取缓存信息失败');
      }
      const data = await res.json();
      setCacheInfo(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取缓存信息失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCacheInfo();
  }, [fetchCacheInfo]);

  const handleCleanInvalid = useCallback(async () => {
    if (!confirm('确定要清理所有无效缓存吗？')) return;
    
    try {
      const res = await fetch('/api/v1/cache/clean-invalid', { method: 'POST' });
      if (!res.ok) {
        throw new Error('清理失败');
      }
      const result = await res.json();
      alert(`已清理 ${result.cleaned_count} 个无效缓存，释放了 ${formatBytes(result.released_bytes)} 空间`);
      fetchCacheInfo();
    } catch (err) {
      alert(err instanceof Error ? err.message : '清理失败');
    }
  }, [fetchCacheInfo]);

  const handleClearAll = useCallback(async () => {
    if (!confirm('确定要清空所有缓存吗？此操作不可恢复！')) return;
    
    try {
      const res = await fetch('/api/v1/cache/clear-all', { method: 'POST' });
      if (!res.ok) {
        throw new Error('清空失败');
      }
      const result = await res.json();
      alert(`已清空所有缓存，释放了 ${formatBytes(result.released_bytes)} 空间`);
      fetchCacheInfo();
    } catch (err) {
      alert(err instanceof Error ? err.message : '清空失败');
    }
  }, [fetchCacheInfo]);

  const handleDeleteTask = useCallback(async (taskId: string) => {
    if (!confirm('确定要删除此缓存吗？')) return;
    
    try {
      const res = await fetch(`/api/v1/cache/delete/${taskId}`, { method: 'POST' });
      if (!res.ok) {
        throw new Error('删除失败');
      }
      const result = await res.json();
      alert(`已删除，释放了 ${formatBytes(result.released_bytes)} 空间`);
      fetchCacheInfo();
    } catch (err) {
      alert(err instanceof Error ? err.message : '删除失败');
    }
  }, [fetchCacheInfo]);

  return (
    <div className="bg-primary/50 border border-white/10 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-white font-semibold text-lg flex items-center gap-2">
          <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
          </svg>
          后端缓存管理
        </h3>
        <button
          onClick={fetchCacheInfo}
          disabled={loading}
          className="px-3 py-1.5 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-lg text-cyan-400 text-sm transition disabled:opacity-50"
        >
          刷新
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center py-8 text-gray-400">
          加载中...
        </div>
      ) : cacheInfo ? (
        <>
          <div className="grid grid-cols-2 gap-4 mb-4">
            <div className="bg-black/20 rounded-lg p-4">
              <div className="text-gray-400 text-xs mb-1">总占用</div>
              <div className="text-white text-xl font-bold">{formatBytes(cacheInfo.total_size)}</div>
            </div>
            <div className="bg-black/20 rounded-lg p-4">
              <div className="text-gray-400 text-xs mb-1">任务总数</div>
              <div className="text-white text-xl font-bold">{cacheInfo.task_count}</div>
            </div>
            <div className="bg-black/20 rounded-lg p-4">
              <div className="text-gray-400 text-xs mb-1">上传文件夹</div>
              <div className="text-cyan-400 text-lg font-bold">{formatBytes(cacheInfo.upload_size)}</div>
            </div>
            <div className="bg-black/20 rounded-lg p-4">
              <div className="text-gray-400 text-xs mb-1">输出文件夹</div>
              <div className="text-purple-400 text-lg font-bold">{formatBytes(cacheInfo.output_size)}</div>
            </div>
          </div>

          {cacheInfo.invalid_count > 0 && (
            <div className="mb-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-yellow-400">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <span className="font-medium">检测到 {cacheInfo.invalid_count} 个无效缓存</span>
                </div>
                <button
                  onClick={handleCleanInvalid}
                  className="px-3 py-1 bg-yellow-500/20 hover:bg-yellow-500/30 border border-yellow-500/30 rounded text-yellow-400 text-sm transition"
                >
                  清理无效
                </button>
              </div>
            </div>
          )}

          <div className="flex gap-3 mb-4">
            <button
              onClick={handleCleanInvalid}
              disabled={cacheInfo.invalid_count === 0}
              className="flex-1 px-4 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 rounded-lg text-cyan-400 text-sm transition disabled:opacity-50"
            >
              清理无效缓存
            </button>
            <button
              onClick={handleClearAll}
              className="flex-1 px-4 py-2 bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 rounded-lg text-red-400 text-sm transition"
            >
              清空全部缓存
            </button>
          </div>

          <div>
            <button
              onClick={() => setShowTasks(!showTasks)}
              className="flex items-center gap-2 text-gray-400 hover:text-white text-sm mb-2 transition"
            >
              <svg
                className={`w-4 h-4 transition-transform ${showTasks ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
              显示任务列表 ({cacheInfo.tasks.length})
            </button>

            {showTasks && (
              <div className="max-h-80 overflow-y-auto bg-black/20 rounded-lg border border-white/10">
                {cacheInfo.tasks.length === 0 ? (
                  <div className="p-4 text-center text-gray-500 text-sm">
                    暂无缓存
                  </div>
                ) : (
                  <div className="divide-y divide-white/10">
                    {cacheInfo.tasks.map((task) => {
                      const isInvalid = cacheInfo.invalid_tasks.some(t => t.id === task.id);
                      return (
                        <div key={task.id} className={`p-3 hover:bg-white/5 ${isInvalid ? 'bg-red-500/5' : ''}`}>
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-white text-sm font-medium truncate">
                                  {task.filename}
                                </span>
                                <span className={`text-xs ${getStatusColor(task.status)}`}>
                                  {getStatusLabel(task.status)}
                                </span>
                                {isInvalid && (
                                  <span className="text-xs text-red-400 bg-red-500/10 px-1.5 py-0.5 rounded">
                                    无效
                                  </span>
                                )}
                              </div>
                              <div className="text-gray-500 text-xs mb-1">
                                {formatBytes(task.total_size)}
                                {' · '}
                                {new Date(task.created_at).toLocaleString()}
                              </div>
                              {task.error && (
                                <div className="text-red-400 text-xs mt-1 line-clamp-2">
                                  {task.error}
                                </div>
                              )}
                            </div>
                            <button
                              onClick={() => handleDeleteTask(task.id)}
                              className="flex-shrink-0 p-1.5 text-gray-500 hover:text-red-400 hover:bg-red-500/10 rounded transition"
                              title="删除"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

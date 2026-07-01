import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';
import { AlgorithmVersion, fetchAlgorithmVersions, uploadAudio } from '../services/backendApi';

interface DebugResult {
  version: string;
  filename: string | null;
  label: string;
  ok: boolean;
  duration_ms: number;
  rms: number;
  peak: number;
  file_duration_sec?: number;
  error?: string;
}

const TAG_CONFIG: Record<string, { label: string; className: string }> = {
  'mobile':      { label: '移动', className: 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' },
  'desktop':     { label: '桌面', className: 'bg-blue-500/20 text-blue-400 border border-blue-500/30' },
  'stable':      { label: '稳定', className: 'bg-amber-500/20 text-amber-400 border border-amber-500/30' },
  'recommended': { label: '推荐', className: 'bg-purple-500/20 text-purple-400 border border-purple-500/30' },
  'dual-track':  { label: '双轨', className: 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30' },
  'premium':     { label: '精修', className: 'bg-rose-500/20 text-rose-400 border border-rose-500/30' },
};

export default function DebugRepairPage() {
  const navigate = useNavigate();

  const [algorithms, setAlgorithms] = useState<AlgorithmVersion[]>([]);
  const [selectedVersion, setSelectedVersion] = useState('');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [audioFileName, setAudioFileName] = useState('');
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStep, setProgressStep] = useState('');
  const [results, setResults] = useState<DebugResult[] | null>(null);
  const [error, setError] = useState('');

  // 调试页只展示 v3.2 和 v4.0 系列
  const DEBUG_VERSIONS = ['v4.0a+', 'v4.0a', 'v3.2a+', 'v3.2a', 'v3.2+', 'v3.2'];

  useEffect(() => {
    fetchAlgorithmVersions().then(all => {
      const filtered = all.filter(a => DEBUG_VERSIONS.includes(a.name));
      filtered.sort((a, b) => DEBUG_VERSIONS.indexOf(a.name) - DEBUG_VERSIONS.indexOf(b.name));
      setAlgorithms(filtered);
    }).catch(console.error);
  }, []);

  // 默认选中第一个版本
  useEffect(() => {
    if (algorithms.length > 0 && !selectedVersion) {
      setSelectedVersion(algorithms[0]?.name || '');
    }
  }, [algorithms]);

  const handleUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError('');
    setResults(null);
    try {
      const res = await uploadAudio(file, (loaded, total) => {
        setProgress(loaded / total);
        setProgressStep(`上传中 ${((loaded / total) * 100).toFixed(0)}%`);
      });
      setTaskId(res.task_id);
      setAudioFileName(file.name);
      setProgress(0);
      setProgressStep('上传完成');
    } catch (err) {
      setError(err instanceof Error ? err.message : '上传失败');
    } finally {
      setUploading(false);
    }
  }, []);

  const handleRun = useCallback(async () => {
    if (!taskId || !selectedVersion) return;
    setRunning(true);
    setError('');
    setResults(null);
    setProgress(0);
    setProgressStep('运行中...');

    try {
      const resp = await fetch(`/api/v1/repair-debug`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId, algorithm_version: selectedVersion }),
      });
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(txt);
      }
      const data = await resp.json();
      setResults(data.results || []);
      setProgress(100);
      setProgressStep('完成');
    } catch (err) {
      setError(err instanceof Error ? err.message : '运行失败');
    } finally {
      setRunning(false);
    }
  }, [taskId, selectedVersion]);

  return (
    <div className="min-h-screen bg-dark py-6">
      <Header />
      <div className="container mx-auto px-4 max-w-5xl mt-4">
        <button onClick={() => navigate('/')} className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          <span>返回首页</span>
        </button>
      </div>

      <div className="container mx-auto px-4 py-6 max-w-5xl">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 bg-yellow-500/20 rounded-lg flex items-center justify-center border border-yellow-400/20">
            <svg className="w-5 h-5 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">调试修复</h1>
            <p className="text-gray-400 text-sm">使用同一版本、完全一致的参数跑完整管线，保存每个处理阶段的中间结果，逐环节验证逻辑</p>
          </div>
        </div>

        {/* 上传区域 */}
        <div className="bg-primary/50 border border-white/10 rounded-xl p-6 mb-6">
          <div className="flex items-center gap-4 flex-wrap">
            <label className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium transition cursor-pointer
              ${uploading || running ? 'opacity-50 pointer-events-none' : 'bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-400/40 text-cyan-300'}`}>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
              {taskId ? '更换文件' : '选择音频'}
              <input type="file" accept="audio/*" className="hidden" onChange={handleUpload} />
            </label>
            {audioFileName && (
              <div className="flex items-center gap-2 text-sm">
                <span className="text-white font-medium">{audioFileName}</span>
                <span className="text-green-400 text-xs px-1.5 py-0.5 bg-green-500/10 border border-green-500/20 rounded">已上传</span>
              </div>
            )}
          </div>
          {uploading && (
            <div className="mt-3 flex items-center gap-3">
              <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                <div className="h-full bg-gradient-to-r from-cyan-500 to-purple-500 transition-all" style={{ width: `${progress * 100}%` }} />
              </div>
              <span className="text-gray-400 text-xs">{Math.round(progress * 100)}%</span>
            </div>
          )}
        </div>

        {/* 版本选择 —— 单选 */}
        <div className="bg-primary/50 border border-white/10 rounded-xl p-6 mb-6">
          <h2 className="text-sm font-medium text-gray-300 mb-3">选择要调试的算法版本（单选）</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
            {algorithms.map(algo => {
              const checked = selectedVersion === algo.name;
              return (
                <label
                  key={algo.name}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer transition text-sm
                    ${checked
                      ? 'bg-cyan-500/15 border-cyan-400/40 text-cyan-200'
                      : 'bg-white/5 border-white/5 text-gray-400 hover:border-white/15 hover:text-gray-300'
                    }`}
                >
                  <input
                    type="radio"
                    name="debug_version"
                    checked={checked}
                    onChange={() => setSelectedVersion(algo.name)}
                    className="sr-only"
                  />
                  <span className="font-medium">{algo.label}</span>
                  {algo.tags?.map(tag => {
                    const cfg = TAG_CONFIG[tag];
                    if (!cfg) return null;
                    return <span key={tag} className={`text-[9px] px-1 py-0 rounded ${cfg.className}`}>{cfg.label}</span>;
                  })}
                </label>
              );
            })}
          </div>
        </div>

        {/* 运行按钮 */}
        <button
          onClick={handleRun}
          disabled={!taskId || !selectedVersion || running}
          className={`w-full py-3 rounded-xl font-bold text-lg transition mb-6
            ${!taskId || !selectedVersion || running
              ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
              : 'bg-gradient-to-r from-yellow-500/80 to-orange-500/80 hover:from-yellow-500 hover:to-orange-500 text-white'
            }`}
        >
          {running ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              处理中...
            </span>
          ) : (
            `运行调试（${algorithms.find(a => a.name === selectedVersion)?.label || selectedVersion || '请选择版本'}）`
          )}
        </button>

        {/* 进度 */}
        {running && (
          <div className="mb-6 flex items-center gap-3 bg-primary/30 rounded-lg p-3 border border-yellow-500/20">
            <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
              <div className="h-full bg-gradient-to-r from-yellow-500 to-orange-500 transition-all" style={{ width: `${progress}%` }} />
            </div>
            <span className="text-yellow-400 text-xs font-mono w-10 text-right">{Math.round(progress)}%</span>
          </div>
        )}

        {/* 错误 */}
        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
            <div className="flex items-start gap-2">
              <svg className="w-4 h-4 text-red-400 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-red-400 text-sm">{error}</span>
            </div>
          </div>
        )}

        {/* 结果表格 */}
        {results && results.length > 0 && (
          <div className="bg-primary/50 border border-white/10 rounded-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-white/5 flex items-center gap-3">
              <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
              <h2 className="text-sm font-medium text-white">
                管线阶段结果：{results.length} 个中间文件
              </h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/5 text-gray-400 text-xs">
                    <th className="text-left px-4 py-2 font-medium w-12">#</th>
                    <th className="text-left px-4 py-2 font-medium">处理阶段</th>
                    <th className="text-left px-4 py-2 font-medium">文件名</th>
                    <th className="text-center px-4 py-2 font-medium">试听</th>
                    <th className="text-center px-4 py-2 font-medium">下载</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => (
                    <tr key={r.filename || i} className={`border-b border-white/5 ${i % 2 === 0 ? 'bg-white/[0.02]' : ''} ${!r.ok ? 'bg-red-500/5' : ''}`}>
                      <td className="px-4 py-3 text-gray-500 font-mono text-xs">{i + 1}</td>
                      <td className="px-4 py-3">
                        <span className={`font-medium ${r.ok ? 'text-cyan-300' : 'text-red-400'}`}>
                          {r.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-400 font-mono text-xs max-w-[200px] truncate" title={r.filename || ''}>
                        {r.filename || '—'}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {r.ok && r.filename && taskId ? (
                          <audio controls className="h-8 w-[160px]">
                            <source src={`/api/v1/repair-debug/${taskId}/${r.filename}`} type="audio/wav" />
                          </audio>
                        ) : (
                          <span className="text-red-400 text-xs">{r.error || '—'}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {r.ok && r.filename && taskId ? (
                          <a
                            href={`/api/v1/repair-debug/${taskId}/${r.filename}`}
                            download={r.filename}
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-cyan-500/20 border border-white/10 hover:border-cyan-400/40 text-gray-300 hover:text-cyan-300 text-xs transition"
                          >
                            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                            下载
                          </a>
                        ) : (
                          <span className="text-gray-500 text-xs">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

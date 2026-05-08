import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';

interface TestResult {
  name: string;
  status: 'passed' | 'failed' | 'skipped';
  version?: string;
  category?: string;
  metric?: string;
  description?: string;
  error?: string;
}

interface QualityTestResponse {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  summary: string;
  tests: TestResult[];
  baseline: TestResult[];
  per_step: TestResult[];
  iron_rule: TestResult[];
  raw_output: string;
  exit_code: number;
}

const VERSION_COLORS: Record<string, string> = {
  'v2.0': '#06b6d4',
  'v2.1': '#8b5cf6',
  'v2.2': '#f59e0b',
  'v2.2a': '#10b981',
};

const METRIC_ICONS: Record<string, string> = {
  'THD': '∿',
  'Flat-top': '▬',
  'HF Noise': '⟐',
  'SNR': '◈',
  'Finite': '∞',
  'Peak': '▲',
  'DC': '⏚',
  'Length': '⟷',
  'Window': '⊞',
  'Gain CV': '∓',
};

function StatusDot({ status }: { status: string }) {
  if (status === 'passed') return <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]" />;
  if (status === 'failed') return <span className="inline-block w-2.5 h-2.5 rounded-full bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.5)]" />;
  return <span className="inline-block w-2.5 h-2.5 rounded-full bg-yellow-400/60" />;
}

function ProgressBar({ value, max, color }: { value: number; max: number; color: string }) {
  const safeMax = Math.max(max, 1);
  const pct = Math.min(100, (value / safeMax) * 100);
  return (
    <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
      <div className="h-full rounded-full transition-all duration-700 ease-out" style={{ width: `${pct}%`, backgroundColor: color }} />
    </div>
  );
}

function RingChart({ passed, failed, skipped, total }: { passed: number; failed: number; skipped: number; total: number }) {
  if (total === 0) return null;
  const r = 40;
  const c = 2 * Math.PI * r;
  const passedLen = (passed / total) * c;
  const failedLen = (failed / total) * c;
  const skippedLen = (skipped / total) * c;
  const gap = 2;

  return (
    <svg viewBox="0 0 100 100" className="w-28 h-28">
      <circle cx="50" cy="50" r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="8" />
      {passed > 0 && (
        <circle cx="50" cy="50" r={r} fill="none" stroke="#34d399" strokeWidth="8"
          strokeDasharray={`${passedLen - gap} ${c - passedLen + gap}`}
          strokeDashoffset={0} strokeLinecap="round" transform="rotate(-90 50 50)"
          style={{ filter: 'drop-shadow(0 0 4px rgba(52,211,153,0.4))' }} />
      )}
      {failed > 0 && (
        <circle cx="50" cy="50" r={r} fill="none" stroke="#f87171" strokeWidth="8"
          strokeDasharray={`${failedLen - gap} ${c - failedLen + gap}`}
          strokeDashoffset={-(passedLen)} strokeLinecap="round" transform="rotate(-90 50 50)"
          style={{ filter: 'drop-shadow(0 0 4px rgba(248,113,113,0.4))' }} />
      )}
      {skipped > 0 && (
        <circle cx="50" cy="50" r={r} fill="none" stroke="#fbbf24" strokeWidth="8"
          strokeDasharray={`${skippedLen - gap} ${c - skippedLen + gap}`}
          strokeDashoffset={-(passedLen + failedLen)} strokeLinecap="round" transform="rotate(-90 50 50)" />
      )}
      <text x="50" y="46" textAnchor="middle" className="fill-white text-lg font-bold" style={{ fontSize: '18px' }}>
        {total > 0 ? Math.round((passed / total) * 100) : 0}%
      </text>
      <text x="50" y="60" textAnchor="middle" className="fill-gray-400" style={{ fontSize: '8px' }}>
        通过率
      </text>
    </svg>
  );
}

function VersionMatrix({ tests }: { tests: TestResult[] }) {
  const safeTests = Array.isArray(tests) ? tests : [];
  const metrics = useMemo(() => {
    const seen = new Set<string>();
    return safeTests.filter(t => {
      const m = t.metric || '';
      if (!m || seen.has(m)) return false;
      seen.add(m);
      return true;
    }).map(t => t.metric || '');
  }, [safeTests]);

  const versions = useMemo(() => {
    const seen = new Set<string>();
    return safeTests.filter(t => {
      const v = t.version || '';
      if (!v || seen.has(v)) return false;
      seen.add(v);
      return true;
    }).map(t => t.version!);
  }, [safeTests]);

  const getTest = (metric: string, version: string) =>
    safeTests.find(t => t.metric === metric && t.version === version);

  if (metrics.length === 0 || versions.length === 0) {
    return <div className="text-gray-600 text-xs font-mono py-4 text-center">暂无数据</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr>
            <th className="text-left text-gray-500 font-medium pb-3 pr-4 text-xs uppercase tracking-wider">指标</th>
            {versions.map(v => (
              <th key={v} className="text-center pb-3 px-2 text-xs font-medium" style={{ color: VERSION_COLORS[v] || '#9ca3af' }}>
                {v}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map(m => (
            <tr key={m} className="border-t border-white/5">
              <td className="py-2.5 pr-4 text-gray-300 font-mono text-xs">
                <span className="mr-2 opacity-50">{METRIC_ICONS[m] || '·'}</span>
                {m}
              </td>
              {versions.map(v => {
                const t = getTest(m, v);
                if (!t) return <td key={v} className="text-center py-2.5 px-2 text-gray-600">—</td>;
                return (
                  <td key={v} className="text-center py-2.5 px-2">
                    <StatusDot status={t.status} />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function QualityTestPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<QualityTestResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const [liveLines, setLiveLines] = useState<string[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runTests = useCallback(async () => {
    setLoading(true);
    setError(null);
    setData(null);
    setLiveLines([]);

    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    if (pollingRef.current) { clearTimeout(pollingRef.current); pollingRef.current = null; }

    try {
      const startRes = await fetch('/api/v1/quality-tests/start', { method: 'POST' });
      if (!startRes.ok) {
        setError(`启动测试失败: ${startRes.status}`);
        setLoading(false);
        return;
      }
      const { task_id } = await startRes.json();

      const startPolling = () => {
        const poll = async () => {
          try {
            const res = await fetch(`/api/v1/quality-tests/result/${task_id}`);
            if (!res.ok) { setError(`查询失败: ${res.status}`); setLoading(false); return; }
            const json = await res.json();
            if (json.status === 'completed') {
              setData(json);
              setLoading(false);
            } else if (json.status === 'running') {
              pollingRef.current = setTimeout(poll, 2000);
            } else {
              setError(json.error || `未知状态: ${json.status}`);
              setLoading(false);
            }
          } catch (err) {
            setError(`轮询错误: ${err instanceof Error ? err.message : String(err)}`);
            setLoading(false);
          }
        };
        pollingRef.current = setTimeout(poll, 2000);
      };

      try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/${task_id}`;
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;
        let wsOk = false;

        ws.onopen = () => { wsOk = true; };

        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data);
            if (msg.error && !msg.task_id) {
              setError(msg.error);
              setLoading(false);
              return;
            }
            if (msg.quality_test_line) {
              setLiveLines(prev => [...prev.slice(-25), msg.quality_test_line]);
            }
            if (msg.status === 'completed' && msg.total !== undefined) {
              setData({
                total: msg.total || 0, passed: msg.passed || 0, failed: msg.failed || 0, skipped: msg.skipped || 0,
                summary: msg.summary || '', tests: msg.tests || [], baseline: msg.baseline || [],
                per_step: msg.per_step || [], iron_rule: msg.iron_rule || [],
                raw_output: msg.raw_output || '', exit_code: msg.exit_code ?? -1,
              });
              setLoading(false);
              ws.close();
            }
          } catch { /* ignore */ }
        };

        ws.onerror = () => {
          ws.close();
          wsRef.current = null;
          if (!wsOk) startPolling();
        };

        ws.onclose = () => {
          if (wsRef.current === ws) wsRef.current = null;
        };
      } catch {
        startPolling();
      }
    } catch (err) {
      setError(`启动失败: ${err instanceof Error ? err.message : String(err)}`);
      setLoading(false);
    }
  }, []);

  useEffect(() => { runTests(); }, []);

  const allPassed = data && data.failed === 0 && data.total > 0;
  const hasFailure = data && data.failed > 0;

  return (
    <div className="min-h-screen bg-dark">
      <Header />

      <div className="container mx-auto px-4 py-10 max-w-6xl">
        {/* Header */}
        <div className="flex items-start justify-between mb-10 gap-4">
          <div>
            <button onClick={() => navigate('/')} className="text-gray-500 hover:text-gray-300 text-xs mb-3 flex items-center gap-1.5 transition font-mono uppercase tracking-wider">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg>
              Index
            </button>
            <h1 className="text-3xl font-bold text-white tracking-tight">Quality Assurance</h1>
            <p className="text-gray-500 mt-1.5 text-sm font-mono">repair algorithm · automated test suite · 44 checks</p>
          </div>
          <button onClick={runTests} disabled={loading}
            className="px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-gray-300 text-xs font-mono transition disabled:opacity-40 flex items-center gap-2 flex-shrink-0">
            {loading ? (
              <><div className="w-3.5 h-3.5 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />Running...</>
            ) : (
              <><svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>Rerun</>
            )}
          </button>
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="relative w-20 h-20 mb-8">
              <div className="absolute inset-0 border-2 border-white/5 rounded-full" />
              <div className="absolute inset-0 border-2 border-cyan-500/80 border-t-transparent rounded-full animate-spin" />
              <div className="absolute inset-2 border-2 border-purple-500/40 border-b-transparent rounded-full animate-spin" style={{ animationDirection: 'reverse', animationDuration: '1.5s' }} />
            </div>
            <p className="text-gray-400 text-sm font-mono">Running quality tests...</p>
            <p className="text-gray-600 text-xs font-mono mt-1">4 versions × 8 baselines + 12 per-step + 4 iron rules</p>
            {liveLines.length > 0 && (
              <div className="mt-6 w-full max-w-2xl bg-black/30 border border-white/[0.04] rounded-xl p-4 max-h-40 overflow-y-auto">
                {liveLines.map((line, i) => (
                  <div key={i} className={`text-[10px] font-mono leading-relaxed ${
                    line.includes('PASSED') ? 'text-emerald-500/60' :
                    line.includes('FAILED') ? 'text-red-400/60' :
                    'text-gray-600'
                  }`}>{line}</div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Error */}
        {!loading && error && !data && (
          <div className="flex flex-col items-center justify-center py-28">
            <div className="w-16 h-16 bg-red-500/10 rounded-full flex items-center justify-center mb-6">
              <svg className="w-8 h-8 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <p className="text-red-400 text-sm font-mono mb-2">测试运行失败</p>
            <p className="text-gray-500 text-xs font-mono mb-6">{error}</p>
            <button onClick={runTests} className="px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-gray-300 text-xs font-mono transition">
              重试
            </button>
          </div>
        )}

        {data && (
          <div className="space-y-8">
            {/* Summary Row */}
            <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr] gap-6">
              {/* Ring + Stats */}
              <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-6 flex items-center gap-6">
                <RingChart passed={data.passed} failed={data.failed} skipped={data.skipped} total={data.total} />
                <div className="space-y-3 flex-1 min-w-0">
                  <div>
                    <div className="text-xs text-gray-500 font-mono uppercase tracking-wider mb-0.5">Status</div>
                    <div className={`text-lg font-bold ${allPassed ? 'text-emerald-400' : hasFailure ? 'text-red-400' : 'text-gray-400'}`}>
                      {allPassed ? 'ALL PASS' : hasFailure ? `${data.failed} FAIL` : '—'}
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <div className="text-[10px] text-gray-600 font-mono">PASS</div>
                      <div className="text-emerald-400 font-bold text-sm">{data.passed}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-gray-600 font-mono">FAIL</div>
                      <div className={`font-bold text-sm ${data.failed > 0 ? 'text-red-400' : 'text-gray-600'}`}>{data.failed}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-gray-600 font-mono">SKIP</div>
                      <div className="text-yellow-500/60 font-bold text-sm">{data.skipped}</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Version bars */}
              <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-6">
                <div className="text-xs text-gray-500 font-mono uppercase tracking-wider mb-4">Version Coverage</div>
                <div className="space-y-3">
                  {['v2.0', 'v2.1', 'v2.2', 'v2.2a'].map(v => {
                    const vTests = (data.baseline || []).filter(t => t.version === v);
                    const vPassed = vTests.filter(t => t.status === 'passed').length;
                    const color = VERSION_COLORS[v];
                    return (
                      <div key={v}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs font-mono" style={{ color }}>{v}</span>
                          <span className="text-[10px] text-gray-500 font-mono">{vPassed}/{vTests.length}</span>
                        </div>
                        <ProgressBar value={vPassed} max={vTests.length} color={color} />
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Baseline Matrix */}
            <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-6">
              <div className="flex items-center gap-2 mb-5">
                <div className="w-1.5 h-5 bg-cyan-500 rounded-full" />
                <h2 className="text-white font-semibold text-sm tracking-wide">Baseline Matrix</h2>
                <span className="text-gray-600 text-xs font-mono ml-1">8 metrics × 4 versions</span>
              </div>
              <VersionMatrix tests={data.baseline || []} />
            </div>

            {/* Per-Step Quality */}
            <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-6">
              <div className="flex items-center gap-2 mb-5">
                <div className="w-1.5 h-5 bg-purple-500 rounded-full" />
                <h2 className="text-white font-semibold text-sm tracking-wide">v2.2a Per-Step Quality</h2>
                <span className="text-gray-600 text-xs font-mono ml-1">step-by-step SNR regression</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {(data.per_step || []).map((t, i) => (
                  <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-white/[0.02] border border-white/[0.04] hover:border-white/[0.08] transition">
                    <StatusDot status={t.status} />
                    <div className="flex-1 min-w-0">
                      <div className="text-gray-200 text-xs font-medium truncate">{t.description || t.name}</div>
                      <div className="text-gray-600 text-[10px] font-mono mt-0.5">{t.metric}</div>
                    </div>
                    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                      t.status === 'passed' ? 'text-emerald-400/70 bg-emerald-500/10' :
                      t.status === 'failed' ? 'text-red-400/70 bg-red-500/10' :
                      'text-yellow-400/70 bg-yellow-500/10'
                    }`}>
                      {t.status.toUpperCase()}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Iron Rules */}
            <div className="bg-white/[0.02] border border-white/[0.06] rounded-2xl p-6">
              <div className="flex items-center gap-2 mb-5">
                <div className="w-1.5 h-5 bg-red-500 rounded-full" />
                <h2 className="text-white font-semibold text-sm tracking-wide">Iron Rules</h2>
                <span className="text-gray-600 text-xs font-mono ml-1">3 laws from v2.2a incident</span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
                {[
                  { n: '01', title: 'No Hard Clipping', desc: 'np.clip → flat-top → HF harmonics → "呲呲"声。Use tanh soft clip.', rule: 'declip_uses_soft / peak_limit_uses_soft' },
                  { n: '02', title: 'No Time-Varying Gain', desc: '时变增益 = AM 调制 → 边带频率 → 可闻噪声。Use global constant gain.', rule: 'compress_is_global / loudness_norm_is_constant' },
                  { n: '03', title: 'No Large Window Replace', desc: '余弦插值 265 样本 → 误差 119% → 可闻失真。Use single-sample diff clamp.', rule: 'depop_no_large_window' },
                ].map(rule => (
                  <div key={rule.n} className="p-4 rounded-lg bg-red-500/[0.03] border border-red-500/10">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-red-400/60 font-mono text-[10px] font-bold">{rule.n}</span>
                      <span className="text-red-300 text-xs font-semibold">{rule.title}</span>
                    </div>
                    <p className="text-gray-500 text-[11px] leading-relaxed">{rule.desc}</p>
                    <div className="text-gray-600 text-[9px] font-mono mt-2 truncate">{rule.rule}</div>
                  </div>
                ))}
              </div>

              <div className="space-y-1.5">
                {(data.iron_rule || []).map((t, i) => (
                  <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/[0.02] transition">
                    <StatusDot status={t.status} />
                    <span className="text-gray-300 text-xs flex-1">{t.description || t.name}</span>
                    <span className="text-gray-600 text-[10px] font-mono">{t.metric}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Raw Output */}
            <div>
              <button onClick={() => setShowRaw(!showRaw)}
                className="text-gray-600 hover:text-gray-400 text-[10px] font-mono flex items-center gap-1.5 transition mb-2 uppercase tracking-wider">
                <svg className={`w-3 h-3 transition-transform ${showRaw ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
                {showRaw ? 'Hide' : 'Show'} Raw Output
              </button>
              {showRaw && (
                <pre className="bg-black/30 border border-white/[0.04] rounded-xl p-4 text-[10px] text-gray-500 overflow-x-auto max-h-80 overflow-y-auto font-mono leading-relaxed">
                  {data.raw_output || ''}
                </pre>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

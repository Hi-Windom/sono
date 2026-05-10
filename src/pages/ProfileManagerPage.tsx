import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '../components/Header';
import { AIRepairParams, defaultAIRepairParams, repairModes } from '../utils/advancedAudioProcessing';
import {
  getSavedProfiles,
  saveProfileToStorage,
  deleteProfileById,
  renameProfileById,
  applyProfileById,
  loadSettings,
  saveSettings,
  ProfileConfig,
} from '../utils/settingsStorage';

const PARAM_LABELS: Record<keyof AIRepairParams, string> = {
  deClipping: '去削波',
  noiseReduction: '降噪',
  deEssing: '去齿音',
  deCrackle: '去毛刺',
  dePop: '去爆音',
  harmonicEnhance: '谐波增强',
  dynamicRange: '动态范围',
  softness: '柔和处理',
  presenceBoost: '临场增强',
  bassEnhance: '低音增强',
  spatialEnhance: '空间感',
  transientRepair: '瞬态修复',
  warmth: '温暖度',
  clarity: '清晰度',
};

const SAMPLE_RATE_LABELS: Record<number, string> = {
  44100: '44.1k',
  48000: '48k',
  96000: '96k',
};

function paramsSummary(params: AIRepairParams): string[] {
  return (Object.keys(params) as (keyof AIRepairParams)[])
    .filter(k => (params[k] ?? 0) > 0)
    .slice(0, 4)
    .map(k => PARAM_LABELS[k]);
}

export default function ProfileManagerPage() {
  const navigate = useNavigate();
  const [profiles, setProfiles] = useState<ProfileConfig[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');
  const [editingParams, setEditingParams] = useState<{ params: AIRepairParams; sampleRate: number; bitDepth: 16 | 24 | 32 } | null>(null);
  const [showNewDialog, setShowNewDialog] = useState(false);
  const [newName, setNewName] = useState('');
  const [importInputKey, setImportInputKey] = useState(0);

  const refresh = useCallback(() => {
    setProfiles(getSavedProfiles());
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleSaveNew = useCallback(() => {
    const name = newName.trim();
    if (!name) return;
    const settings = loadSettings();
    saveProfileToStorage(name, settings.aiRepairParams, {
      sampleRate: settings.exportOptions.sampleRate,
      bitDepth: settings.exportOptions.bitDepth,
    });
    setNewName('');
    setShowNewDialog(false);
    refresh();
  }, [newName, refresh]);

  const handleDelete = useCallback((id: string, name: string) => {
    if (!confirm(`确定删除配置「${name}」？`)) return;
    deleteProfileById(id);
    refresh();
  }, [refresh]);

  const handleRename = useCallback((id: string) => {
    const name = editingName.trim();
    if (!name) return;
    renameProfileById(id, name);
    setEditingId(null);
    setEditingName('');
    refresh();
  }, [editingName, refresh]);

  const handleApply = useCallback((id: string) => {
    applyProfileById(id);
    navigate('/repair');
  }, [navigate]);

  const handleExport = useCallback((p: ProfileConfig) => {
    const blob = new Blob([JSON.stringify(p, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sono-profile-${p.name.replace(/\s+/g, '_')}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }, []);

  const handleExportAll = useCallback(() => {
    const blob = new Blob([JSON.stringify(profiles, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sono-profiles-all.json';
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }, [profiles]);

  const handleImport = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const data: ProfileConfig | ProfileConfig[] = JSON.parse(reader.result as string);
        const list = Array.isArray(data) ? data : [data];
        const settings = loadSettings();
        const existing = settings.savedProfiles || [];
        const newProfiles = list.map(p => ({
          ...p,
          id: (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : Date.now().toString(36),
          createdAt: p.createdAt || new Date().toISOString(),
        }));
        saveSettings({ savedProfiles: [...existing, ...newProfiles] });
        refresh();
        alert(`已导入 ${list.length} 个配置`);
      } catch {
        alert('导入失败：JSON 格式不正确');
      }
    };
    reader.readAsText(file);
    setImportInputKey(k => k + 1);
  }, [refresh]);

  const openEditParams = useCallback((p: ProfileConfig) => {
    setEditingParams({
      params: { ...p.params },
      sampleRate: p.exportOptions.sampleRate,
      bitDepth: p.exportOptions.bitDepth,
    });
    setEditingId(p.id);
    setEditingName(p.name);
  }, []);

  const saveParamEdit = useCallback(() => {
    if (!editingParams || !editingId) return;
    const settings = loadSettings();
    const updated = (settings.savedProfiles || []).map(p =>
      p.id === editingId ? {
        ...p,
        name: editingName.trim() || p.name,
        params: { ...editingParams.params },
        exportOptions: {
          sampleRate: editingParams.sampleRate,
          bitDepth: editingParams.bitDepth,
        },
      } : p
    );
    saveSettings({ savedProfiles: updated });
    setEditingParams(null);
    setEditingId(null);
    setEditingName('');
    refresh();
  }, [editingParams, editingId, editingName, refresh]);

  const paramSlider = (key: keyof AIRepairParams) => {
    const val = editingParams?.params?.[key] ?? 0;
    return (
      <div key={key as string} className="flex items-center gap-2 py-1">
        <span className="text-xs text-gray-400 w-16 shrink-0">{PARAM_LABELS[key]}</span>
        <input
          type="range"
          min={0}
          max={key === 'warmth' || key === 'clarity' ? 1 : 0.5}
          step={0.01}
          value={val}
          onChange={e => setEditingParams(prev => prev ? {
            ...prev,
            params: { ...prev.params, [key]: parseFloat(e.target.value) },
          } : null)}
          className="flex-1 h-1.5 accent-cyan-400"
        />
        <span className="text-xs text-cyan-400 w-10 text-right tabular-nums">{val.toFixed(2)}</span>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-dark">
      <Header />

      <div className="container mx-auto px-4 py-8 max-w-4xl">
        {/* 标题栏 */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate(-1)}
              className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
            </button>
            <h1 className="text-2xl font-bold text-white">修复参数配置管理</h1>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleExportAll}
              disabled={profiles.length === 0}
              className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-300 text-sm transition disabled:opacity-40"
            >
              导出全部
            </button>
            <label className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-300 text-sm transition cursor-pointer">
              导入配置
              <input
                key={importInputKey}
                type="file"
                accept=".json"
                onChange={handleImport}
                className="hidden"
              />
            </label>
            <button
              onClick={() => { setEditingParams({ params: { ...defaultAIRepairParams }, sampleRate: 48000, bitDepth: 24 }); setEditingId(null); setEditingName(''); setShowNewDialog(true); }}
              className="px-4 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 text-sm font-medium transition"
            >
              + 新增配置
            </button>
          </div>
        </div>

        {/* 内置预设模式 */}
        <div className="mb-6 p-4 bg-white/5 rounded-xl border border-white/10">
          <div className="text-xs text-gray-500 mb-2">内置预设模式（只读）</div>
          <div className="flex gap-2 flex-wrap">
            {repairModes.map(m => (
              <span key={m.name} className="px-3 py-1 rounded-full bg-white/5 text-gray-400 text-xs border border-white/10">
                {m.name}
              </span>
            ))}
          </div>
        </div>

        {/* 配置列表 */}
        {profiles.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            <div className="text-4xl mb-3">📋</div>
            <div>暂无保存的配置</div>
            <div className="text-sm mt-1">在修复页面调整参数后，点击"保存到配置"</div>
          </div>
        ) : (
          <div className="space-y-3">
            {profiles.map(p => (
              <div
                key={p.id}
                className="p-4 bg-white/[0.03] rounded-xl border border-white/10 hover:border-white/20 transition"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    {editingId === p.id && !editingParams ? (
                      <div className="flex items-center gap-2">
                        <input
                          value={editingName}
                          onChange={e => setEditingName(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter') handleRename(p.id);
                            if (e.key === 'Escape') { setEditingId(null); setEditingName(''); }
                          }}
                          autoFocus
                          className="bg-white/10 border border-cyan-400/50 rounded px-2 py-1 text-white text-sm w-48"
                        />
                        <button onClick={() => handleRename(p.id)} className="text-cyan-400 text-xs">保存</button>
                        <button onClick={() => { setEditingId(null); setEditingName(''); }} className="text-gray-500 text-xs">取消</button>
                      </div>
                    ) : (
                      <h3 className="text-white font-medium truncate">{p.name}</h3>
                    )}
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      {paramsSummary(p.params).map(label => (
                        <span key={label} className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400">{label}</span>
                      ))}
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">
                        {SAMPLE_RATE_LABELS[p.exportOptions.sampleRate] || p.exportOptions.sampleRate} / {p.exportOptions.bitDepth}bit
                      </span>
                    </div>
                    <div className="text-[10px] text-gray-500 mt-1">
                      创建于 {new Date(p.createdAt).toLocaleString('zh-CN')}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <button
                      onClick={() => handleApply(p.id)}
                      className="px-3 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 text-xs font-medium transition"
                    >
                      应用
                    </button>
                    <button
                      onClick={() => openEditParams(p)}
                      className="px-2 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 text-xs transition"
                      title="编辑参数"
                    >
                      编辑
                    </button>
                    <button
                      onClick={() => handleExport(p)}
                      className="px-2 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 text-xs transition"
                      title="导出为 JSON"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                    </button>
                    <button
                      onClick={() => { setEditingId(p.id); setEditingName(p.name); }}
                      className="px-2 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 text-xs transition"
                    >
                      重命名
                    </button>
                    <button
                      onClick={() => handleDelete(p.id, p.name)}
                      className="px-2 py-1 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 text-xs transition"
                    >
                      删除
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 新增/编辑参数弹窗 */}
        {(showNewDialog || (editingId && editingParams)) && (
          <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
            <div className="bg-primary border border-white/10 rounded-2xl p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto">
              <h3 className="text-white font-bold text-lg mb-4">
                {editingId ? '编辑参数' : '新增配置'}
              </h3>

              {/* 名称 */}
              <div className="mb-4">
                <label className="text-xs text-gray-400 mb-1 block">配置名称</label>
                <input
                  value={editingName}
                  onChange={e => setEditingName(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') { if (editingId) saveParamEdit(); else handleSaveNew(); } }}
                  placeholder="如：播客人声"
                  autoFocus
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-cyan-400/50"
                />
              </div>

              {/* 参数滑块 */}
              <div className="mb-4">
                <div className="text-xs text-gray-400 mb-2">修复参数</div>
                <div className="max-h-60 overflow-y-auto pr-2">
                  {paramSlider('deClipping')}
                  {paramSlider('noiseReduction')}
                  {paramSlider('deEssing')}
                  {paramSlider('deCrackle')}
                  {paramSlider('dePop')}
                  {paramSlider('harmonicEnhance')}
                  {paramSlider('dynamicRange')}
                  {paramSlider('softness')}
                  {paramSlider('presenceBoost')}
                  {paramSlider('bassEnhance')}
                  {paramSlider('spatialEnhance')}
                  {paramSlider('transientRepair')}
                  {paramSlider('warmth')}
                  {paramSlider('clarity')}
                </div>
              </div>

              {/* 导出规格 */}
              <div className="mb-6">
                <div className="text-xs text-gray-400 mb-2">导出规格</div>
                <div className="flex gap-4">
                  <select
                    value={editingParams?.sampleRate ?? 48000}
                    onChange={e => setEditingParams(prev => prev ? { ...prev, sampleRate: parseInt(e.target.value) } : null)}
                    className="bg-white/5 border border-white/10 rounded px-2 py-1 text-white text-sm"
                  >
                    <option value={44100}>44.1kHz</option>
                    <option value={48000}>48kHz</option>
                    <option value={96000}>96kHz</option>
                  </select>
                  <select
                    value={editingParams?.bitDepth ?? 24}
                    onChange={e => setEditingParams(prev => prev ? { ...prev, bitDepth: parseInt(e.target.value) as 16 | 24 | 32 } : null)}
                    className="bg-white/5 border border-white/10 rounded px-2 py-1 text-white text-sm"
                  >
                    <option value={16}>16bit</option>
                    <option value={24}>24bit</option>
                    <option value={32}>32bit</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-2">
                <button
                  onClick={() => { setShowNewDialog(false); setEditingParams(null); setEditingId(null); setEditingName(''); }}
                  className="px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 text-sm transition"
                >
                  取消
                </button>
                <button
                  onClick={editingId ? saveParamEdit : handleSaveNew}
                  disabled={!editingName?.trim()}
                  className="px-4 py-2 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 text-sm font-medium transition disabled:opacity-40"
                >
                  {editingId ? '保存修改' : '保存'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

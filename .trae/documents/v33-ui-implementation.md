# 实现 v3.3 系列 UI 层计划

## 当前状态分析

v3.3 系列后端已完整实现（v3.3/v3.3+/v3.3a/v3.3a+），`backendApi.ts` 已增加四个新版本到 `ALGORITHM_VERSIONS`。但 UI 层缺少：
1. v3.3 系列专属参数控件（频谱自然化、噪声塑形等 6+ 个滑块）
2. v3.3+ 的 Preset 选择器
3. v3.3a+ 的残差精炼控件
4. 算法版本变化时参数自动切换
5. 后端请求时 v3.3 参数合并

## 文件结构

```
src/
├── services/backendApi.ts          # 修改：增加 v3.3 参数类型
├── components/AIRepairPanel.tsx    # 修改：增加 v3.3 参数控件区域
└── hooks/useAudioProcessor.ts      # 修改：增加 v3.3 参数状态 + 版本切换时自动重置
```

## 实施步骤

### 第 1 步：在 `backendApi.ts` 新增 v3.3 参数类型和默认值

**位置**：`src/services/backendApi.ts`，在 `InstrumentRepairParams` 接口定义之后，约 1743 行之后。

新增接口和常量：

```typescript
export interface V33RepairParams {
  spectralNaturalize: number;
  noiseFloorShape: number;
  harmonicDeregularize: number;
  phaseNaturalize: number;
  transientProtect: number;
  dynamicNaturalize: number;
  loudness: number;
  f0GuidedDepth?: number;
  perceptualWeight?: number;
  preset?: 'none' | 'anti-detect' | 'hifi-pure' | 'vocal';
  residualRefine?: number;
}

export const defaultV33RepairParams: V33RepairParams = {
  spectralNaturalize: 0.6, noiseFloorShape: 0.4, harmonicDeregularize: 0.5,
  phaseNaturalize: 0.3, transientProtect: 0.5, dynamicNaturalize: 0.3, loudness: 0.5,
};

export const defaultV33pRepairParams: V33RepairParams = {
  spectralNaturalize: 0.7, noiseFloorShape: 0.5, harmonicDeregularize: 0.6,
  phaseNaturalize: 0.4, transientProtect: 0.5, dynamicNaturalize: 0.4, loudness: 0.5,
  f0GuidedDepth: 0.3, perceptualWeight: 0.3, preset: 'anti-detect',
};

export const defaultV33aRepairParams: V33RepairParams = {
  spectralNaturalize: 0.5, noiseFloorShape: 0.3, harmonicDeregularize: 0.3,
  phaseNaturalize: 0, transientProtect: 0.4, dynamicNaturalize: 0.2, loudness: 0.5,
};

export const defaultV33apRepairParams: V33RepairParams = {
  spectralNaturalize: 0.5, noiseFloorShape: 0.3, harmonicDeregularize: 0.3,
  phaseNaturalize: 0, transientProtect: 0.4, dynamicNaturalize: 0.2, loudness: 0.5,
  residualRefine: 0.3,
};
```

新增默认参数获取函数：

```typescript
export function getDefaultV33Params(algorithmVersion: string): V33RepairParams {
  if (algorithmVersion === 'v3.3+') return defaultV33pRepairParams;
  if (algorithmVersion === 'v3.3a') return defaultV33aRepairParams;
  if (algorithmVersion === 'v3.3a+') return defaultV33apRepairParams;
  return defaultV33RepairParams;
}
```

新增辅助函数将 v3.3 参数映射为后端请求格式：

```typescript
export function mapV33ParamsToBackend(params: V33RepairParams): Record<string, any> {
  const result: Record<string, any> = {};
  if (params.spectralNaturalize != null) result.spectral_naturalize = params.spectralNaturalize;
  if (params.noiseFloorShape != null) result.noise_floor_shape = params.noiseFloorShape;
  if (params.harmonicDeregularize != null) result.harmonic_deregularize = params.harmonicDeregularize;
  if (params.phaseNaturalize != null) result.phase_naturalize = params.phaseNaturalize;
  if (params.transientProtect != null) result.transient_protect = params.transientProtect;
  if (params.dynamicNaturalize != null) result.dynamic_naturalize = params.dynamicNaturalize;
  if (params.loudness != null) result.loudness = params.loudness;
  if (params.f0GuidedDepth != null) result.f0_guided_depth = params.f0GuidedDepth;
  if (params.perceptualWeight != null) result.perceptual_weight = params.perceptualWeight;
  if (params.preset != null && params.preset !== 'none') result.preset = params.preset;
  if (params.residualRefine != null) result.residual_refine = params.residualRefine;
  return result;
}
```

在 `ALGORITHM_VERSIONS` 数组中已确认包含 v3.3 系列四个版本。

### 第 2 步：在 `useAudioProcessor.ts` 增加 v3.3 参数状态

**位置**：`src/hooks/useAudioProcessor.ts`，约 159 行 `algorithmVersion` state 定义之后。

新增：

```typescript
const [v33Params, setV33Params] = useState<V33RepairParams>(() => {
  const saved = loadSettings();
  const defaults = getDefaultV33Params(saved.algorithmVersion || 'v3.3');
  return { ...defaults, ...saved.v33RepairParams };
});
```

新增 `useEffect` 监听算法版本变化自动切换参数：

```typescript
useEffect(() => {
  if (!algorithmVersion.startsWith('v3.3')) return;
  const defaults = getDefaultV33Params(algorithmVersion);
  setV33Params(prev => ({ ...defaults, ...prev }));
}, [algorithmVersion]);
```

在 `applyAlgorithmVersion` 函数中增加清理逻辑（约 248 行）：

```typescript
if (version.startsWith('v3.3')) {
  const defaults = getDefaultV33Params(version);
  setV33Params(defaults);
}
```

修改返回值（约 1260 行），增加 `v33Params` 和 `setV33Params`：

```typescript
return {
  ...existingFields,
  v33Params,
  setV33Params,
};
```

### 第 3 步：在 `RepairPage.tsx` 中接入 v3.3 参数

**位置**：`src/pages/RepairPage.tsx`

从 `useAudioProcessor()` 解构新增 `v33Params` 和 `setV33Params`（约 22 行之后）：

```typescript
const { ..., v33Params, setV33Params } = useAudioProcessor();
```

在 `AIRepairPanel` 调用处（约 989 行）传入新 props：

```tsx
<AIRepairPanel
  ...
  v33Params={v33Params}
  onV33ParamChange={(key, value) => setV33Params(prev => ({ ...prev, [key]: value }))}
/>
```

确认 `mapParamsToBackend` 函数在调用 `/api/v1/repair` 时合并 v3.3 参数。检查调用点约 398 行：

```typescript
const v33Mapped = mapV33ParamsToBackend(v33Params);
const mainParams = { ...mapParamsToBackend(params, processingOptions, algorithmVersion), ...v33Mapped };
```

### 第 4 步：在 `AIRepairPanel.tsx` 新增 v3.3 参数控件区域

**位置**：`src/components/AIRepairPanel.tsx`，约 1095 行"预设模式"区域之后、"交付规格"之前。

新增 props 接口（约 35 行之后）：

```typescript
interface AIRepairPanelProps {
  ...existingProps
  v33Params?: V33RepairParams | null;
  onV33ParamChange?: (key: keyof V33RepairParams, value: number | string) => void;
}
```

新增参数标签和滑块键列表：

```typescript
const v33ParamConfig: { key: keyof V33RepairParams; label: string; color: string }[] = [
  { key: 'spectralNaturalize', label: '频谱自然化', color: 'cyan' },
  { key: 'noiseFloorShape', label: '噪声地板塑形', color: 'blue' },
  { key: 'harmonicDeregularize', label: '谐波去规整', color: 'purple' },
  { key: 'phaseNaturalize', label: '相位自然化', color: 'green' },
  { key: 'transientProtect', label: '瞬态保护', color: 'amber' },
  { key: 'dynamicNaturalize', label: '动态自然化', color: 'orange' },
];
```

新增折叠状态（约 55 行之后）：

```typescript
const [showV33Params, setShowV33Params] = useState(false);
```

在 JSX 中新增参数区域（在"预设模式"和"交付规格"之间，约 1130 行位置）：

```tsx
{algorithmVersion.startsWith('v3.3') && v33Params && onV33ParamChange && (
  <div className="mb-4">
    <button
      type="button"
      onClick={() => setShowV33Params(!showV33Params)}
      className="w-full flex items-center justify-between p-2 bg-cyan-900/10 rounded-lg border border-cyan-500/20 hover:border-cyan-500/40 transition-all"
    >
      <div className="flex items-center gap-2">
        <span className="text-cyan-400 text-sm font-medium">v3.3 自然化参数</span>
        {algorithmVersion === 'v3.3+' && (
          <span className="text-[10px] bg-violet-500/20 text-violet-400 px-1.5 py-0.5 rounded">增强版</span>
        )}
        {algorithmVersion === 'v3.3a' && (
          <span className="text-[10px] bg-blue-500/20 text-blue-400 px-1.5 py-0.5 rounded">移动精简版</span>
        )}
        {algorithmVersion === 'v3.3a+' && (
          <span className="text-[10px] bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded">移动增强版</span>
        )}
      </div>
      <ChevronDownIcon className={`w-4 h-4 text-cyan-400 transition-transform ${showV33Params ? 'rotate-180' : ''}`} />
    </button>
    
    {showV33Params && (
      <div className="mt-3 p-3 bg-slate-900/50 rounded-lg border border-slate-700/30">
        {/* v3.3+ Preset 选择器 */}
        {algorithmVersion === 'v3.3+' && (
          <div className="mb-3 p-2 bg-gradient-to-r from-violet-900/30 to-fuchsia-900/30 rounded-lg border border-violet-500/20">
            <div className="text-violet-400 text-xs font-medium mb-2">预设模式</div>
            <div className="flex gap-1.5">
              {[
                { value: 'anti-detect', label: '反检测', icon: '🛡️' },
                { value: 'hifi-pure', label: '高保真', icon: '🎵' },
                { value: 'vocal', label: '人声优化', icon: '🎤' },
              ].map(preset => (
                <button
                  key={preset.value}
                  type="button"
                  onClick={() => onV33ParamChange('preset', preset.value)}
                  className={`flex-1 py-1.5 px-2 rounded-md text-xs font-medium transition-all ${
                    v33Params.preset === preset.value
                      ? 'bg-violet-500/30 text-violet-300 border border-violet-400/50'
                      : 'bg-slate-800/50 text-slate-400 border border-slate-700/30 hover:text-slate-300'
                  }`}
                >
                  {preset.icon} {preset.label}
                </button>
              ))}
            </div>
          </div>
        )}
        
        {/* 参数滑块网格 */}
        <div className="grid grid-cols-2 gap-x-4 gap-y-3">
          {v33ParamConfig.map(({ key, label, color }) => (
            <div key={key}>
              <label className={`text-${color}-300 text-xs font-medium flex justify-between`}>
                <span>{label}</span>
                <span className="text-slate-400">{((v33Params[key] ?? 0) * 100).toFixed(0)}%</span>
              </label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={v33Params[key] ?? 0}
                onChange={(e) => onV33ParamChange(key, parseFloat(e.target.value))}
                className={`w-full h-1.5 rounded-full appearance-none cursor-pointer mt-1 bg-${color}-500/30 [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-${color}-400`}
              />
            </div>
          ))}
        </div>
        
        {/* v3.3+ 专属参数 */}
        {algorithmVersion === 'v3.3+' && (
          <div className="grid grid-cols-2 gap-x-4 gap-y-3 mt-3 pt-3 border-t border-slate-700/30">
            <div>
              <label className="text-violet-300 text-xs font-medium flex justify-between">
                <span>F0 引导深度</span>
                <span className="text-slate-400">{((v33Params.f0GuidedDepth ?? 0) * 100).toFixed(0)}%</span>
              </label>
              <input type="range" min="0" max="1" step="0.01" value={v33Params.f0GuidedDepth ?? 0}
                onChange={(e) => onV33ParamChange('f0GuidedDepth', parseFloat(e.target.value))}
                className="w-full h-1.5 rounded-full appearance-none cursor-pointer mt-1 bg-violet-500/30 [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-violet-400" />
            </div>
            <div>
              <label className="text-violet-300 text-xs font-medium flex justify-between">
                <span>感知加权</span>
                <span className="text-slate-400">{((v33Params.perceptualWeight ?? 0) * 100).toFixed(0)}%</span>
              </label>
              <input type="range" min="0" max="1" step="0.01" value={v33Params.perceptualWeight ?? 0}
                onChange={(e) => onV33ParamChange('perceptualWeight', parseFloat(e.target.value))}
                className="w-full h-1.5 rounded-full appearance-none cursor-pointer mt-1 bg-violet-500/30 [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-violet-400" />
            </div>
          </div>
        )}
        
        {/* v3.3a+ 残差精炼 */}
        {algorithmVersion === 'v3.3a+' && (
          <div className="mt-3 pt-3 border-t border-slate-700/30">
            <label className="text-amber-300 text-xs font-medium flex justify-between">
              <span>残差精炼</span>
              <span className="text-slate-400">{((v33Params.residualRefine ?? 0) * 100).toFixed(0)}%</span>
            </label>
            <input type="range" min="0" max="1" step="0.01" value={v33Params.residualRefine ?? 0}
              onChange={(e) => onV33ParamChange('residualRefine', parseFloat(e.target.value))}
              className="w-full h-1.5 rounded-full appearance-none cursor-pointer mt-1 bg-amber-500/30 [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-amber-400" />
          </div>
        )}
      </div>
    )}
  </div>
)}
```

### 第 5 步：更新 `mapParamsToBackend` 以合并 v3.3 参数

确认 `/api/v1/repair` 调用时参数传递正确。检查 `RepairPage.tsx` 约 398 行的调用：

```typescript
const mainParams = mapParamsToBackend(params, processingOptions, algorithmVersion);
```

修改为（当 algorithmVersion.startsWith('v3.3') 时）：

```typescript
let mainParams = mapParamsToBackend(params, processingOptions, algorithmVersion);
if (algorithmVersion.startsWith('v3.3') && v33Params) {
  mainParams = { ...mainParams, ...mapV33ParamsToBackend(v33Params) };
}
```

双轨模式下同样处理（约 547 行）。

### 第 6 步：settingsStorage 更新（可选）

在 `src/utils/settingsStorage.ts` 中新增 `v33RepairParams` 字段，确保参数持久化。

## 测试验证

1. 启动 dev：`bash scripts/start_dev.sh`，用 `OpenPreview` 激活
2. 选择 v3.3 版本，确认参数控件区域正确显示
3. 选择 v3.3+ 版本，确认 Preset 选择器 + F0引导深度 + 感知加权滑块出现
4. 选择 v3.3a 版本，确认移动端精简版参数（无相位自然化）
5. 选择 v3.3a+ 版本，确认残差精炼滑块出现
6. 修改参数后点击"应用"，确认请求发送到后端并处理成功
7. 切换不同版本时参数自动重置为对应默认值
8. 移动端模式下只显示 v3.3a/v3.3a+

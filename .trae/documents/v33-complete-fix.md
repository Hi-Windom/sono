# v3.3 完整修复计划

## 现状问题

### 问题 1：v3.3 没有双轨支持
v3.2/v3.2+/v3.2a/v3.2a+ 都设置了 `"supports_dual_track": True`，但 v3.3/v3.3+/v3.3a/v3.3a+ 全部设置为 `False`。这是遗漏。v3.3 作为 v3.2 的升级版本，必须继承双轨支持。

### 问题 2：UI 层完全没有实现
v3.3 系列参数控件（频谱自然化、噪声塑形等）没有在 `AIRepairPanel.tsx` 中实现。虽然 `backendApi.ts` 增加了版本列表，但前端用户无法调节任何 v3.3 参数，也无法选择 Preset。

### 问题 3：AI 检测率未下降
第三方报告：纯 AI 80%。说明当前算法处理强度不够。

## 实施步骤

### 第 1 步：启用 v3.3 系列双轨支持

**文件**: `backend/services/audio_repair.py`

将所有 4 个 v3.3 版本版本的 `supports_dual_track` 改为 `true`：
- v3.3: `"supports_dual_track": False` → `True`
- v3.3+: `"supports_dual_track": False` → `True`
- v3.3a: `"supports_dual_track": False` → `True`
- v3.3a+: `"supports_dual_track": False` → `True`

### 第 2 步：在 `backendApi.ts` 新增 v3.3 参数类型和默认值

**文件**: `src/services/backendApi.ts`

新增：
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

export function getDefaultV33Params(algorithmVersion: string): V33RepairParams {
  if (algorithmVersion === 'v3.3+') return defaultV33pRepairParams;
  if (algorithmVersion === 'v3.3a') return defaultV33aRepairParams;
  if (algorithmVersion === 'v3.3a+') return defaultV33apRepairParams;
  return defaultV33RepairParams;
}

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

### 第 3 步：在 `useAudioProcessor.ts` 增加 v3.3 参数状态

**文件**: `src/hooks/useAudioProcessor.ts`

1. 导入新增类型和函数
2. 新增 `v33Params` state
3. 监听算法版本变化自动切换参数
4. 在返回值中暴露 `v33Params` 和 `setV33Params`

### 第 4 步：在 `AIRepairPanel.tsx` 新增 v3.3 参数控件区域

**文件**: `src/components/AIRepairPanel.tsx`

1. 新增 props：`v33Params` 和 `onV33ParamChange`
2. 在"预设模式"和"交付规格"之间新增折叠式 v3.3 参数区域：
   - 标题栏：显示 "v3.3 自然化参数" + 版本标签
   - v3.3+ Preset 选择器（反检测/高保真/人声优化）
   - 6 个基础滑块：频谱自然化、噪声地板塑形、谐波去规整、相位自然化、瞬态保护、动态自然化
   - v3.3+ 专属：F0 引导深度、感知加权
   - v3.3a+ 专属：残差精炼

### 第 5 步：在 `RepairPage.tsx` 中接入 v3.3 参数

**文件**: `src/pages/RepairPage.tsx`

1. 从 `useAudioProcessor()` 解构 `v33Params` 和 `setV33Params`
2. 在 `AIRepairPanel` 调用处传入新 props
3. 在调用后端 API 时合并 v3.3 参数（约 398 行和 547 行）

### 第 6 步：提高默认参数强度（针对 AI 检测优化）

**文件**: `backend/services/audio_repair.py`

- v3.3 默认：
  - `spectral_naturalize: 0.6 → 0.8`
  - `noise_floor_shape: 0.4 → 0.6`
  - `harmonic_deregularize: 0.5 → 0.7`
  - `phase_naturalize: 0.3 → 0.5`
  - `transient_protect: 0.5` (保持)
  - `dynamic_naturalize: 0.3 → 0.4`

- v3.3+ 默认：
  - 全部提高 0.1
  - Anti-Detect preset 参数提高

### 第 7 步：v3.3 算法效果增强

**文件**: `backend/services/repair/repair_v3_3/spectral.py`

1. `_harmonic_deregularize`：扰动幅度从 ±0.5% 提升到 ±2%
2. `_noise_floor_shape`：1/f 噪声从 -78~-85dB 提升到 -70~-78dB
3. `_subband_decorrelate`：all-pass 系数增加

**文件**: `backend/services/repair/repair_v3_3/phase.py`

1. `_group_delay_correct`：相位扰动幅度从 0.03 提升到 0.1

## 文件清单

| 文件 | 修改内容 |
|------|----------|
| `backend/services/audio_repair.py` | 双轨支持 + 提高默认参数 |
| `src/services/backendApi.ts` | 新增 v3.3 参数类型和映射函数 |
| `src/hooks/useAudioProcessor.ts` | v3.3 参数状态管理 |
| `src/components/AIRepairPanel.tsx` | v3.3 参数 UI 控件 |
| `src/pages/RepairPage.tsx` | 接入 v3.3 参数 |
| `backend/services/repair/repair_v3_3/spectral.py` | 增强算法效果 |
| `backend/services/repair/repair_v3_3/phase.py` | 增强相位扰动 |

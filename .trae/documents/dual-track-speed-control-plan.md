# 双轨模式速度控制 UI 实现计划

## 目标
为双轨模式（人声轨道 + 伴奏轨道）添加速度控制（speed control）UI，范围 0.5–2.0，步进 0.01，默认值 1.0。

## 涉及文件及修改步骤

### Step 1: `backendApi.ts` — 添加 speed 字段到接口/默认值/映射函数

**1a**: `VocalRepairParams` 接口添加 `speed?: number`
**1b**: `InstrumentRepairParams` 接口添加 `speed?: number`
**1c**: `defaultVocalRepairParams` 添加 `speed: 1.0`
**1d**: `defaultInstrumentRepairParams` 添加 `speed: 1.0`
**1e**: `mapVocalParamsToBackend()` 添加 `speed: params.speed ?? 1.0`
**1f**: `mapInstrumentParamsToBackend()` 添加 `speed: params.speed ?? 1.0`

### Step 2: `settingsStorage.ts` — 添加 speed 字段到接口/默认值（保持类型一致性）

**2a**: `VocalRepairParams` 接口添加 `speed?: number`
**2b**: `InstrumentRepairParams` 接口添加 `speed?: number`
**2c**: `defaultVocalRepairParams` 添加 `speed: 1.0`
**2d**: `defaultInstrumentRepairParams` 添加 `speed: 1.0`

### Step 3: `AIRepairPanel.tsx` — 添加速度滑块 UI

速度滑块与现有参数滑块不同（范围 0.5–2.0 而非 0–1），因此**不加入 grid，而是单独放在 grid 下方**。

**3a**: 在人声参数滑块 grid 下方添加速度滑块
- 标签"速度"，显示值如"1.00x"
- 使用原生 `<input type="range">`，min=0.5, max=2.0, step=0.01
- 样式参考混合比例滑块（全宽 + 标签 + 值显示）

**3b**: 在伴奏参数滑块 grid 下方添加速度滑块
- 同上，但对应 `accompanimentParams` 和 `onAccompanimentParamChange`

### 无需修改的文件
- `RepairPage.tsx` — `handleDualTrackVocalParamChange` 和 `handleDualTrackAccompanimentParamChange` 已是通用 key/value 处理，自动支持 `speed` 字段
- 后端 — 速度参数仅 UI 层添加，暂不在后端使用
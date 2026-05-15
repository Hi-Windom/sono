# v3.3 双轨修复 + 单轨文件名修复 实施计划

## 问题概述

### 问题 1：单轨模式下载文件名包含变速参数
- **位置**: `backend/api/routes.py` L1337-L1339
- **现象**: 单轨模式不支持变速，但下载文件名仍包含 `{speed}x_` 标签
- **修复**: 单轨下载时移除 speed 标签

### 问题 2：v3.3 系列双轨模式实现缺失
- **现状**: v3.3/v3.3+/v3.3a/v3.3a+ 的 `repair_audio` 只处理单轨模式，没有 `processing_mode == "dual"` 的分支
- **参考**: v3.2 的 `repair_audio` 有完整的双轨实现（加载 vocal + accompaniment → 分别处理 → 混音）
- **要求**: 实现 Vocal 轨和 Accompaniment 轨的差异化自然化管线 + Mixback

---

## 实施步骤

### 步骤 1：修复单轨下载文件名（1 个文件修改）

**文件**: `backend/api/routes.py`

**修改点**:
- L1337-L1339: 移除 speed 标签，单轨模式直接使用 `f"{base_name}_repaired.wav"`
- 双轨模式（`/download-file/{filename}`）的 speed 标签逻辑保持不变（L1408-L1410）

**改动量**: 约 3 行

---

### 步骤 2：v3.3 双轨 Vocal 管线（新建文件）

**文件**: `backend/services/repair/repair_v3_3/vocal.py`

**功能**: Vocal 轨专用自然化处理

**包含函数**:
1. `process_vocal_v33(y, sr, params)` — 主入口
2. `_vocal_f0_harmonic_naturalize(y, sr, strength)` — f0-guided 谐波自然化（复用 v3.3+ 的 `_f0_guided_harmonic_process` 逻辑）
3. `_vocal_microtremor_breath(y, sr, strength)` — 微颤音与呼吸自然化（轻微不规则包络注入）
4. `_vocal_emotional_transient_protect(y, sr, strength)` — 情感瞬态保护（onset 区域大幅降低修复强度）
5. `_vocal_de_shimmer(y, sr, strength)` — de-shimmer（高频金属感去除）
6. `_vocal_light_phase_diffuse(y, sr, strength)` — 轻量相位扩散（all-pass）
7. `_vocal_light_noise_floor(y, sr, strength)` — 轻微噪声地板塑形（仅 -80dB 以下）

**处理流程**:
```
f0 谐波自然化 → 微颤音/呼吸 → 情感瞬态保护 → de-shimmer → 轻量相位扩散 → 噪声地板塑形
```

---

### 步骤 3：v3.3 双轨 Inst 管线（新建文件）

**文件**: `backend/services/repair/repair_v3_3/inst.py`

**功能**: Accompaniment 轨专用自然化处理

**包含函数**:
1. `process_inst_v33(y, sr, params)` — 主入口
2. `_inst_aggressive_spectral_naturalize(y, sr, strength)` — 激进谱统计自然化（1/f 粉噪 + 真实残余噪塑形）
3. `_inst_multiband_harmonic_dereg(y, sr, strength)` — 多频段谐波去规整
4. `_inst_spatial_enhance(y, sr, strength)` — 空间感增强（MS 处理 + 高频群延时校正）
5. `_inst_transient_impact_protect(y, sr, strength)` — 鼓点/瞬态冲击保护
6. `_inst_upward_compression(y, sr, strength)` — 多频段慢速 upward compression

**处理流程**:
```
激进谱自然化 → 多频段谐波去规整 → 空间感增强 → 瞬态保护 → upward compression
```

---

### 步骤 4：v3.3 双轨 Mixback（新建文件）

**文件**: `backend/services/repair/repair_v3_3/mixback.py`

**功能**: 混音 + 后处理

**包含函数**:
1. `mixback(vocal, accompaniment, sr, params)` — 主入口
2. `_cross_bleed(vocal, accompaniment, strength)` — 轻量交叉 bleed 模拟
3. `_loudness_match(mixed, sr, target_lufs=-14.0)` — 感知响度匹配（ITU-R BS.1770）
4. `_soft_limit_slow_gain(mixed, sr)` — 全局 soft tanh 限幅 + 慢包络增益
5. `_final_residual_refine(original, processed, strength)` — 最终残差精炼（可选）

**处理流程**:
```
交叉 bleed → 响度匹配 → soft 限幅 + 慢包络 → 残差精炼
```

---

### 步骤 5：修改 v3.3 core.py 支持双轨（修改文件）

**文件**: `backend/services/repair/repair_v3_3/core.py`

**修改点**:
- `repair_audio` 函数增加 `processing_mode` 判断
- 双轨模式：加载 vocal + accompaniment → 分别处理 → mixback → 保存
- 参考 v3.2 的 dual-track 实现模式

**关键逻辑**:
```python
def repair_audio(input_path, output_path, params, progress_callback=None):
    processing_mode = params.get("processing_mode", "single")
    if processing_mode == "single":
        return _repair_single_track(input_path, output_path, params, progress_callback)
    # Dual track
    vocal_path = params.get("vocal_path")
    accompaniment_path = params.get("accompaniment_path")
    # 加载、重采样、处理、混音、保存
```

---

### 步骤 6：修改 v3.3+ core.py 支持双轨（修改文件）

**文件**: `backend/services/repair/repair_v3_3p/core.py`

**修改点**:
- 与 v3.3 类似，增加 dual-track 支持
- Vocal 轨使用增强版管线（含 f0-guided + 感知加权）
- Inst 轨使用 v3.3 的 inst 管线
- Mixback 增加残差精炼后处理

---

### 步骤 7：修改 v3.3a/v3.3a+ core.py 支持双轨（修改文件）

**文件**:
- `backend/services/repair/repair_v3_3a/core.py`
- `backend/services/repair/repair_v3_3ap/core.py`

**修改点**:
- 增加 dual-track 支持
- 使用精简版 vocal/inst 管线
- Mixback 使用精简版

---

### 步骤 8：更新 memory_guard.py（修改文件）

**文件**: `backend/services/memory_guard.py`

**修改点**:
- 确保 v3.3 系列双轨模式的内存估算正确（双轨需要双倍内存估算）

---

### 步骤 9：更新前端参数映射（修改文件）

**文件**: `src/services/backendApi.ts`

**修改点**:
- 确保 v3.3 系列在双轨模式下正确传递 vocal_params / inst_params
- 当前双轨模式使用 `VocalRepairParams` / `InstrumentRepairParams`，v3.3 系列需要映射到 v3.3 自然化参数

---

## 文件变更清单

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `backend/api/routes.py` | 修改 | 修复单轨下载文件名 |
| 2 | `backend/services/repair/repair_v3_3/vocal.py` | 新建 | Vocal 轨管线 |
| 3 | `backend/services/repair/repair_v3_3/inst.py` | 新建 | Inst 轨管线 |
| 4 | `backend/services/repair/repair_v3_3/mixback.py` | 新建 | Mixback 处理 |
| 5 | `backend/services/repair/repair_v3_3/core.py` | 修改 | 增加 dual-track 支持 |
| 6 | `backend/services/repair/repair_v3_3p/core.py` | 修改 | 增加 dual-track 支持 |
| 7 | `backend/services/repair/repair_v3_3a/core.py` | 修改 | 增加 dual-track 支持 |
| 8 | `backend/services/repair/repair_v3_3ap/core.py` | 修改 | 增加 dual-track 支持 |
| 9 | `backend/services/memory_guard.py` | 修改 | 双轨内存估算 |
| 10 | `src/services/backendApi.ts` | 修改 | 前端参数映射 |

---

## 实施顺序

1. **步骤 1**（单轨文件名修复）— 独立、简单，可先做
2. **步骤 2-4**（新建 vocal/inst/mixback 模块）— 核心算法实现
3. **步骤 5**（v3.3 core.py 双轨）— 集成 vocal/inst/mixback
4. **步骤 6**（v3.3+ core.py 双轨）— 增强版集成
5. **步骤 7**（v3.3a/v3.3a+ core.py 双轨）— 移动版集成
6. **步骤 8**（memory_guard.py）— 内存估算
7. **步骤 9**（前端参数映射）— 前端适配

---

## 注意事项

1. **确定性输出**: 所有随机操作使用 `np.random.RandomState(42)` 固定种子
2. **流式处理**: 长音频（>30s）使用 `_streaming_process` 分块处理
3. **内存优化**: 遵循 v2.3 的 4 层内存优化策略
4. **QUALITY_RULES**: 遵守三条铁律（禁止硬削波、禁止逐样本增益调制、禁止大窗口插值修复爆音）
5. **双轨速度**: 双轨模式下 speed 参数由 v3.2 的 `process_vocal_track`/`process_instrument_track` 处理，v3.3 系列暂不支持变速
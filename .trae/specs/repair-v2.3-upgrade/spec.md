# 修复算法 v2.3 + v2.3a 升级方案 Spec

## Why

当前 v2.2（桌面版）和 v2.2a（移动版）存在两个核心问题：
1. **v2.2 桌面版**：`apply_peak_limit_v5` 使用 IIR 增益包络（`_smooth_gain_envelope`），存在 AM 调制伪影风险；`apply_loudness_normalize_v5` 使用逐窗口 RMS 计算增益，也是时变增益
2. **v2.2a 移动版**：处理链过于精简（仅 6 步），缺少频谱降噪、齿音抑制、谐波增强等关键步骤，修复效果与桌面版差距过大

v2.3/v2.3a 的目标是：将 v2.2a 的铁律修复（零 AM 伪影）应用到 v2.2 的完整处理链上，同时保持移动端兼容性。

## What Changes

- 新增 `backend/services/repair/repair_v2_3/` 包：v2.3 桌面版，基于 v2.2 处理链但替换所有 AM 伪影步骤
- 新增 `backend/services/repair/repair_v2_3a/` 包：v2.3a 移动版，基于 v2.2a 扩展处理链
- 修改 `backend/services/audio_repair.py`：注册 v2.3/v2.3a 版本
- 修改 `backend/tests/conftest.py`：ACTIVE_VERSIONS 增加 v2.3/v2.3a
- 修改 `backend/tests/test_repair_quality.py`：增加 v2.3/v2.3a 逐步测试类
- 修改 `backend/api/routes.py`：质量测试 API 的 category_map 增加新测试项

### v2.3 桌面版处理链（基于 v2.2，替换 AM 步骤）

| 步骤 | v2.2 实现 | v2.3 实现 | 变更原因 |
|------|-----------|-----------|----------|
| 削波修复 | `apply_de_clipping_v5` (外部模块) | `_tanh_declip` (内联，tanh软削波) | 铁律1：禁止硬削波 |
| 爆音修复 | `apply_de_pop_v5` (外部模块) | `_diff_clamp_depop` (内联，差分钳制) | 铁律3：禁止大窗口替换 |
| 瞬态修复 | `apply_transient_repair_v7` | 保留（无 AM 风险） | — |
| 响度归一化 | `apply_loudness_normalize_v5` (逐窗口增益) | `_global_loudness_normalize` (全局常量增益) | 铁律2：禁止时变增益 |
| 多段压缩 | `apply_multiband_compression_v5` | `_transparent_multiband_compress` (每子带全局增益) | 铁律2：禁止时变增益 |
| 频谱修复 | `apply_spectral_group_a/b` | 保留（频域操作，无 AM 风险） | — |
| 空间处理 | `apply_spatial_enhance_v6` | 保留（无 AM 风险） | — |
| 音色调整 | presence/bass/warmth/clarity 滤波器 | 保留（FIR/IIR 滤波器，无 AM 风险） | — |
| 峰值限制 | `apply_peak_limit_v5` (IIR增益包络) | `_soft_peak_limit` (tanh软削波) | 铁律1+2：禁止硬削波+时变增益 |

### v2.3a 移动版处理链（基于 v2.2a，扩展步骤）

| 步骤 | v2.2a 实现 | v2.3a 实现 | 变更原因 |
|------|-----------|-----------|----------|
| 削波修复 | `_simple_declip` | 保留 | 已符合铁律 |
| 爆音修复 | `_simple_depop` | 保留 | 已符合铁律 |
| 频谱降噪 | 无 | `_spectral_denoise` (新增，频谱门限降噪) | 补齐关键能力 |
| 齿音抑制 | 无 | `_de_ess` (新增，高频带增益衰减) | 补齐关键能力 |
| 响度归一化 | `_loudness_normalize` | 保留 | 已符合铁律 |
| 动态压缩 | `_transparent_compress` | 保留 | 已符合铁律 |
| DC 移除 | `_remove_dc` | 保留 | — |
| 峰值限制 | `_soft_peak_limit` | 保留 | 已符合铁律 |

## Impact

- Affected specs: 修复算法质量保障体系（`QUALITY_RULES.md`）
- Affected code:
  - `backend/services/repair/repair_v2_3/` (新建)
  - `backend/services/repair/repair_v2_3a/` (新建)
  - `backend/services/audio_repair.py` (修改：注册新版本)
  - `backend/tests/conftest.py` (修改：增加版本)
  - `backend/tests/test_repair_quality.py` (修改：增加测试类)
  - `backend/api/routes.py` (修改：category_map 扩展)

## ADDED Requirements

### Requirement: v2.3 桌面版修复算法

系统 SHALL 提供 v2.3 版本修复算法，继承 v2.2 完整处理链，但将所有 AM 伪影步骤替换为铁律合规实现。

#### Scenario: v2.3 处理链无 AM 伪影
- **WHEN** 用户使用 v2.3 处理任意音频
- **THEN** 所有增益操作使用全局常量增益，所有削波操作使用 tanh 软削波，所有爆音修复使用差分钳制

#### Scenario: v2.3 音质不低于 v2.2
- **WHEN** 对同一音频分别使用 v2.2 和 v2.3 处理
- **THEN** v2.3 的 scale-adjusted SNR 不低于 v2.2 的 80%，且 HF 噪声增长不超过 v2.2 的 1.5 倍

#### Scenario: v2.3 峰值限制无 IIR 增益包络
- **WHEN** 音频峰值超过阈值
- **THEN** 使用 tanh 软削波而非 IIR 增益包络，确保零 AM 伪影

### Requirement: v2.3a 移动版修复算法

系统 SHALL 提供 v2.3a 版本修复算法，在 v2.2a 基础上增加频谱降噪和齿音抑制步骤。

#### Scenario: v2.3a 支持频谱降噪
- **WHEN** 用户设置 `noise_reduction > 0`
- **THEN** 执行频谱门限降噪（STFT → 幅度谱门限 → ISTFT），不引入时变增益

#### Scenario: v2.3a 支持齿音抑制
- **WHEN** 用户设置 `de_essing > 0`
- **THEN** 检测 4-8kHz 高能量区域并衰减，使用全局常量衰减因子

#### Scenario: v2.3a 移动端兼容
- **WHEN** 在移动端运行
- **THEN** 不依赖 librosa/pedalboard，仅使用 numpy + scipy + soundfile

### Requirement: v2.3/v2.3a 质量测试

系统 SHALL 为 v2.3 和 v2.3a 提供完整的质量测试覆盖。

#### Scenario: v2.3 逐步测试
- **WHEN** 运行 `pytest backend/tests/test_repair_quality.py`
- **THEN** `TestV23PerStepQuality` 类验证每个处理步骤的 SNR 和铁律合规

#### Scenario: v2.3a 逐步测试
- **WHEN** 运行 `pytest backend/tests/test_repair_quality.py`
- **THEN** `TestV23aPerStepQuality` 类验证每个处理步骤的 SNR 和铁律合规

### Requirement: 版本注册

系统 SHALL 在 `ALGORITHM_VERSIONS` 中注册 v2.3 和 v2.3a。

#### Scenario: v2.3 桌面版注册
- **WHEN** 系统启动
- **THEN** v2.3 可用，`mobile_compatible: False`，包含 6 个模式（智能/人声/器乐/深度/温和/HiFi）

#### Scenario: v2.3a 移动版注册
- **WHEN** 系统启动
- **THEN** v2.3a 可用，`mobile_compatible: True`，包含 4 个模式（智能/快速/深度/温和）

## MODIFIED Requirements

### Requirement: 质量测试版本覆盖

原要求覆盖 v2.0/v2.1/v2.2/v2.2a，现扩展为 v2.0/v2.1/v2.2/v2.2a/v2.3/v2.3a。

`conftest.py` 中 `ACTIVE_VERSIONS` 列表增加 `"v2.3"` 和 `"v2.3a"`。

## REMOVED Requirements

无移除项。

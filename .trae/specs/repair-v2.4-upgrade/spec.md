# 修复算法 v2.4 + v2.4a 升级方案 Spec

## Why

当前 v2.3/v2.3a 存在四个核心问题：

1. **修复后响度偏低**：`_global_loudness_normalize` 目标 -16 LUFS 过于保守，多段压缩后 makeup gain 仅 0.8×amount（最大 2.4dB），导致修复后音频响度明显低于原始音频
2. **低频增强效果弱**：`apply_bass_enhance_v5` 仅使用低通滤波 + 叠加，无法产生次谐波（sub-harmonic），低频增强量有限且缺乏"厚度感"
3. **高频质感不自然**：`apply_clarity_v2` 和 `apply_presence_boost_v5` 使用带通滤波 + 叠加，增强的高频缺乏自然谐波结构，听感"数码味"重
4. **无法修复 AI 歌唱的"玻璃突刺感"**：v2.3/v2.3a 基于音频特征的修复（频谱降噪、齿音抑制、毛刺修复）本质上无法修复此问题——"玻璃突刺"不是幅度异常或宽频带噪声，而是 AI 模型生成的**不符合谐波规律的窄带频谱尖峰**，当前算法无法识别和修复

## 第三方库调研（截止 2026 年 5 月）

| 库名 | 版本 | 适用性 | 评估 |
|------|------|--------|------|
| noisereduce | v3.0.3 (2025.7) | ✅ 桌面端 | 已在 requirements.txt，v3 移除 librosa 依赖，支持非平稳降噪，可用于 v2.4 增强降噪效果 |
| pedalboard | v0.9.9 (2025.7) | ⚠️ 仅桌面端 | Spotify 出品，Compressor/Limiter 质量高，但需原生二进制，不适合移动端 |
| resemble-enhance | 0.0.1 | ❌ 不适用 | 深度学习方案，依赖 PyTorch+deepspeed，内存和体积不适合本项目 |
| VoiceFixer | — | ❌ 不适用 | 深度学习方案，依赖 PyTorch，不适合本项目 |
| TorchFX | — | ❌ 不适用 | GPU 加速 DSP，依赖 PyTorch，不适合本项目 |

**结论**：v2.4 桌面端可引入 noisereduce v3 的非平稳降噪作为可选增强；v2.4a 移动端仍保持 numpy+scipy+soundfile 纯算法方案。核心改进（响度、低频、高频、玻璃突刺）均通过自研 DSP 算法实现。

## What Changes

- 新增 `backend/services/repair/repair_v2_4/` 包：v2.4 桌面版，基于 v2.3 处理链但升级四个核心模块
- 新增 `backend/services/repair/repair_v2_4a/` 包：v2.4a 移动版，基于 v2.3a 扩展处理链
- 修改 `backend/services/audio_repair.py`：注册 v2.4/v2.4a 版本
- 修改 `backend/tests/conftest.py`：增加 v2.4/v2.4a 测试支持
- 修改 `backend/tests/test_repair_quality.py`：增加 v2.4/v2.4a 逐步测试类
- 修改 `backend/api/routes.py`：质量测试 API 增加 v2.4/v2.4a 测试项
- 修改 `backend/services/memory_guard.py`：增加 v2.4/v2.4a 内存估算

### v2.4 桌面版处理链（基于 v2.3，升级四个核心模块）

| 步骤 | v2.3 实现 | v2.4 实现 | 变更原因 |
|------|-----------|-----------|----------|
| 削波修复 | `_tanh_declip` | 保留 | 已符合铁律 |
| 爆音修复 | `_diff_clamp_depop` | 保留 | 已符合铁律 |
| 瞬态修复 | `_soft_transient_limit` | 保留 | 已符合铁律 |
| 响度归一化 | `_global_loudness_normalize` (目标 -16 LUFS) | `_adaptive_loudness_normalize` (目标 -14 LUFS，自适应增益范围 -15~+9dB) | 修复后响度偏低 |
| 多段压缩 | `_transparent_multiband_compress` (makeup gain 0.8×amount) | `_enhanced_multiband_compress` (makeup gain 1.5×amount，低频子带额外 +2dB) | 修复后响度偏低 + 低频增强 |
| **AI 频谱异常修复** | 无 | **`_spectral_anomaly_repair`** (新增，谐波结构分析 + 窄带异常检测 + 频谱插值修复) | 修复 AI 歌唱"玻璃突刺感" |
| 频谱降噪 | `apply_spectral_group_a` | 保留，新增 noisereduce 非平稳降噪作为可选增强 | — |
| 低频增强 | `apply_bass_enhance_v5` (低通+叠加) | `_harmonic_bass_enhance` (次谐波合成 + 谐波激励，替代 v2.2 的 `apply_bass_enhance_v5`) | 低频增强效果弱 |
| 高频质感 | `apply_clarity_v2` + `apply_presence_boost_v5` (带通+叠加) | `_spectral_highfreq_reconstruct` (频谱高频重建，保留自然谐波结构) | 高频质感不自然 |
| 其他步骤 | 空间/立体声/温暖度/柔化/峰值限制 | 保留 | — |

### v2.4a 移动版处理链（基于 v2.3a，扩展步骤）

| 步骤 | v2.3a 实现 | v2.4a 实现 | 变更原因 |
|------|-----------|-----------|----------|
| 削波修复 | `_simple_declip` | 保留 | 已符合铁律 |
| 爆音修复 | `_simple_depop` | 保留 | 已符合铁律 |
| 频谱降噪 | `_spectral_denoise` | 保留 | — |
| 齿音抑制 | `_de_ess` | 保留 | — |
| **AI 频谱异常修复** | 无 | **`_spectral_anomaly_repair_lite`** (新增，简化版谐波异常检测+修复) | 修复 AI 歌唱"玻璃突刺感" |
| 响度归一化 | `_loudness_normalize` (目标 -16 LUFS) | `_adaptive_loudness_normalize_lite` (目标 -14 LUFS，增益范围 -15~+9dB) | 修复后响度偏低 |
| 动态压缩 | `_transparent_compress` | `_enhanced_compress_lite` (增加 makeup gain) | 修复后响度偏低 |
| **低频增强** | 无 | **`_harmonic_bass_enhance_lite`** (新增，简化版次谐波合成) | 低频增强效果弱 |
| **高频重建** | 无 | **`_spectral_highfreq_reconstruct_lite`** (新增，简化版频谱高频重建) | 高频质感不自然 |
| 直流移除 | `_remove_dc` | 保留 | — |
| 峰值限制 | `_soft_peak_limit` | 保留 | — |

### 核心新算法：`_spectral_anomaly_repair`（AI 歌唱"玻璃突刺"修复）

**问题本质**：AI 歌唱模型（如 So-VITS-SVC、RVC 等）在生成频谱时，会在某些频率点产生不符合谐波规律的窄带高能量尖峰。这些尖峰在听感上表现为"玻璃碎裂"或"金属刺耳"的异常感。

**为什么 v2.3/v2.3a 无法修复**：
- 频谱降噪（`_spectral_denoise`）：基于全局中值门限，只能去除低于门限的噪声，无法识别"高于门限但不符合谐波规律"的异常尖峰
- 齿音抑制（`_de_ess`）：仅针对 4-8kHz 宽频带全局衰减，无法区分正常齿音和异常尖峰
- 毛刺修复（`_fast_de_crackle`）：基于帧能量比检测，只能检测时域能量突变，无法检测频域窄带异常

**v2.4 算法设计**：
1. **谐波结构提取**：对频谱执行自相关分析，提取基频 F0 和谐波序列位置
2. **异常检测**：计算每个频率 bin 的能量与"预期谐波能量"（基于谐波序列插值）的比值，超过阈值的 bin 标记为异常
3. **频谱插值修复**：对异常 bin，用相邻正常 bin 的对数插值替换幅度，保留原始相位
4. **铁律合规**：修复掩码基于全局统计量（非逐帧时变），频谱插值不引入 AM 伪影

### 核心新算法：`_harmonic_bass_enhance`（次谐波低频增强）

**v2.3 问题**：`apply_bass_enhance_v5` 仅使用低通滤波 + 叠加（`y += bass * intensity * gain`），无法产生低于原始基频的次谐波成分，低频增强效果有限。

**v2.4 算法设计**：
1. **次谐波合成**：对低频段（<250Hz）信号进行半频处理（每 2 个采样取平均），生成 1/2 倍频的次谐波
2. **谐波激励**：对低频段信号进行软削波（tanh），生成偶次谐波，增加"温暖感"
3. **混合控制**：次谐波和谐波激励分别乘以 intensity 控制的增益，与原始信号叠加
4. **铁律合规**：所有增益为全局常量，tanh 软削波符合铁律 1

### 核心新算法：`_spectral_highfreq_reconstruct`（频谱高频重建）

**v2.3 问题**：`apply_clarity_v2` 使用带通滤波 + 叠加，增强的高频缺乏自然谐波结构，听感"数码味"重。

**v2.4 算法设计**：
1. **谐波镜像**：从中高频段（2-8kHz）提取能量包络，按谐波比例映射到高频段（8-16kHz）
2. **频谱噪声填充**：对高频段添加与中频能量成比例的微弱噪声，模拟自然高频的"空气感"
3. **相位连续性**：使用原始频谱的相位导数（瞬时频率）外推高频相位，避免相位不连续
4. **铁律合规**：所有增益为全局常量，频域操作固有时频耦合

## Impact

- Affected specs: 修复算法质量保障体系（`QUALITY_RULES.md`）
- Affected code:
  - `backend/services/repair/repair_v2_4/` (新建)
  - `backend/services/repair/repair_v2_4a/` (新建)
  - `backend/services/audio_repair.py` (修改：注册新版本)
  - `backend/services/memory_guard.py` (修改：增加 v2.4/v2.4a 内存估算)
  - `backend/tests/conftest.py` (修改：增加版本)
  - `backend/tests/test_repair_quality.py` (修改：增加测试类)
  - `backend/api/routes.py` (修改：category_map 扩展)

## ADDED Requirements

### Requirement: v2.4 桌面版修复算法

系统 SHALL 提供 v2.4 版本修复算法，继承 v2.3 完整处理链，升级响度归一化、多段压缩、低频增强、高频质感四个核心模块，并新增 AI 频谱异常修复。

#### Scenario: v2.4 修复后响度显著提升
- **WHEN** 用户使用 v2.4 处理任意音频
- **THEN** 修复后音频的 LUFS 不低于 -14 LUFS（v2.3 为 -16 LUFS），增益范围扩展至 -15~+9dB（v2.3 为 -12~+6dB）

#### Scenario: v2.4 低频增强产生次谐波
- **WHEN** 用户设置 `bass_enhance > 0`
- **THEN** `_harmonic_bass_enhance` 生成 1/2 倍频的次谐波成分，低频段（<250Hz）RMS 增长不低于 3dB（相比 v2.3 的 `apply_bass_enhance_v5`）

#### Scenario: v2.4 高频质感自然
- **WHEN** 用户设置 `clarity > 0`
- **THEN** `_spectral_highfreq_reconstruct` 基于谐波镜像重建高频，高频段（8-16kHz）的频谱平坦度不低于 0.3（v2.3 的 `apply_clarity_v2` 低于 0.15）

#### Scenario: v2.4 修复 AI 歌唱"玻璃突刺"
- **WHEN** AI 歌唱音频包含不符合谐波规律的窄带频谱尖峰
- **THEN** `_spectral_anomaly_repair` 检测并修复异常尖峰，修复后异常频谱 bin 的能量降至谐波插值预期的 1.5 倍以内

#### Scenario: v2.4 处理链无 AM 伪影
- **WHEN** 用户使用 v2.4 处理任意音频
- **THEN** 所有新增步骤（`_spectral_anomaly_repair`、`_harmonic_bass_enhance`、`_spectral_highfreq_reconstruct`）使用全局常量增益或频域操作，符合铁律 1/2/3

#### Scenario: v2.4 可选 noisereduce 增强
- **WHEN** 桌面端安装了 noisereduce 且用户设置 `noise_reduction > 0.5`
- **THEN** 频谱降噪步骤优先使用 noisereduce 的非平稳降噪模式；若 noisereduce 不可用则回退到 v2.3 的 `apply_spectral_group_a`

### Requirement: v2.4a 移动版修复算法

系统 SHALL 提供 v2.4a 版本修复算法，在 v2.3a 基础上增加 AI 频谱异常修复、低频增强、高频重建三个步骤，并升级响度归一化和动态压缩。

#### Scenario: v2.4a 修复 AI 歌唱"玻璃突刺"
- **WHEN** AI 歌唱音频包含不符合谐波规律的窄带频谱尖峰
- **THEN** `_spectral_anomaly_repair_lite` 检测并修复异常尖峰（简化版，仅检测 2-12kHz 范围）

#### Scenario: v2.4a 低频增强
- **WHEN** 用户设置 `bass_enhance > 0`
- **THEN** `_harmonic_bass_enhance_lite` 生成次谐波成分

#### Scenario: v2.4a 高频重建
- **WHEN** 用户设置 `clarity > 0`
- **THEN** `_spectral_highfreq_reconstruct_lite` 基于谐波镜像重建高频

#### Scenario: v2.4a 修复后响度提升
- **WHEN** 用户使用 v2.4a 处理任意音频
- **THEN** 修复后音频的 LUFS 不低于 -14 LUFS

#### Scenario: v2.4a 移动端兼容
- **WHEN** 在移动端运行
- **THEN** 不依赖 librosa/pedalboard/noisereduce，仅使用 numpy + scipy + soundfile

### Requirement: v2.4/v2.4a 质量测试

系统 SHALL 为 v2.4 和 v2.4a 提供完整的质量测试覆盖。

#### Scenario: v2.4 逐步测试
- **WHEN** 运行 `pytest backend/tests/test_repair_quality.py`
- **THEN** `TestV24PerStepQuality` 类验证每个新增步骤的 SNR 和铁律合规

#### Scenario: v2.4a 逐步测试
- **WHEN** 运行 `pytest backend/tests/test_repair_quality.py`
- **THEN** `TestV24aPerStepQuality` 类验证每个新增步骤的 SNR 和铁律合规

#### Scenario: AI 频谱异常修复专项测试
- **WHEN** 运行质量测试
- **THEN** 包含模拟"玻璃突刺"频谱异常的测试信号，验证 `_spectral_anomaly_repair` 和 `_spectral_anomaly_repair_lite` 的修复效果

### Requirement: 版本注册

系统 SHALL 在 `ALGORITHM_VERSIONS` 中注册 v2.4 和 v2.4a。

#### Scenario: v2.4 桌面版注册
- **WHEN** 系统启动
- **THEN** v2.4 可用，`mobile_compatible: False`，包含 6 个模式（智能/人声/器乐/深度/温和/HiFi）

#### Scenario: v2.4a 移动版注册
- **WHEN** 系统启动
- **THEN** v2.4a 可用，`mobile_compatible: True`，包含 4 个模式（智能/快速/深度/温和）

### Requirement: 内存估算更新

系统 SHALL 在 `memory_guard.py` 中增加 v2.4/v2.4a 的内存估算。

#### Scenario: v2.4 内存估算
- **WHEN** 系统估算 v2.4 的内存需求
- **THEN** peak_temp 系数与 v2.3 相同（+50%），因为新增步骤均为流式/在线处理，不增加峰值内存

#### Scenario: v2.4a 内存估算
- **WHEN** 系统估算 v2.4a 的内存需求
- **THEN** peak_temp 系数与 v2.3a 相同（+15%），因为新增步骤均为在线处理

## MODIFIED Requirements

### Requirement: 质量测试版本覆盖

原要求覆盖 v2.0/v2.1/v2.2/v2.2a/v2.3/v2.3a，现扩展为 v2.0/v2.1/v2.2/v2.2a/v2.3/v2.3a/v2.4/v2.4a。

`conftest.py` 中 `ACTIVE_VERSIONS` 列表增加 `"v2.4"` 和 `"v2.4a"`。

### Requirement: v2.4/v2.4a 参数语义

v2.4 的 `bass_enhance` 参数从"低通+叠加"变更为"次谐波合成+谐波激励"。v2.4 的 `clarity` 参数从"带通+叠加"变更为"频谱高频重建"。

v2.4a 新增 `bass_enhance` 和 `clarity` 参数（v2.3a 无此参数）。

## REMOVED Requirements

无移除项。

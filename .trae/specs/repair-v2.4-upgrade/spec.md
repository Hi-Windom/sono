# 修复算法 v2.4 + v2.4a 升级方案 Spec

## Why

当前 v2.3/v2.3a 存在四个核心问题：

1. **修复后响度偏低**：`_global_loudness_normalize` 目标 -16 LUFS 过于保守，多段压缩后 makeup gain 仅 0.8×amount（最大 2.4dB），导致修复后音频响度明显低于原始音频
2. **低频增强效果弱**：`apply_bass_enhance_v5` 仅使用低通滤波 + 叠加，无法产生次谐波（sub-harmonic），低频增强量有限且缺乏"厚度感"
3. **高频质感不自然**：`apply_clarity_v2` 和 `apply_presence_boost_v5` 使用带通滤波 + 叠加，增强的高频缺乏自然谐波结构，听感"数码味"重
4. **无法修复 AI 歌唱的"玻璃突刺感"**：Suno v5.5、Sway v5.5 等 AI 歌唱模型生成的音频存在特有的"玻璃突刺"问题，v2.3/v2.3a 的基于音频特征的修复（频谱降噪、齿音抑制、毛刺修复）本质上无法修复此问题

## AI 歌唱"玻璃突刺感"的深度分析

### 问题本质

"玻璃突刺感"不是单一类型的伪影，而是 AI 扩散模型生成音频的**复合频谱缺陷**，包含四个层次：

1. **高频过净（Air 无菌感）**：AI 生成的高频（10kHz+）像玻璃一样透明光滑，缺少真实声学链路的轻微噪声/谐波/衰减，听感"塑料""没有空气颗粒"。这是因为扩散模型从白噪声出发逐步去噪，收敛后的高频过于"完美"
2. **2k-5k 过分锐利（存在感区突刺）**：2-5kHz 是人耳最敏感区域，AI 模型倾向于在此区域过度锐化，产生"贴脸""刺耳""刀割"的听感。这不是幅度异常，而是频谱过于"精确"导致的感知异常
3. **频谱过度平滑（熨斗效应）**：AI 生成的频谱像被熨斗熨过一样平滑，所有段落亮度/清晰度一致，缺乏真实音乐中段落间的"明暗变化"。这种过度平滑本身就是一种伪影——真实人声的频谱有自然的微抖动和随机性
4. **FFT 窗口啁啾（Chirping/Warbling）**：AI 模型内部使用 FFT 窗化处理，在窗口边界处产生频谱泄漏，表现为高频"啁啾声""水泡声""鸟鸣声"（业内称为 chirping、warbling 或 the tweeties），这是 Zynaptiq UNCHIRP 等专业工具专门针对的伪影类型

### 为什么 v2.3/v2.3a 无法修复

| v2.3/v2.3a 算法 | 为什么无法修复"玻璃突刺" |
|-----------------|------------------------|
| `_spectral_denoise`（频谱降噪） | 基于全局中值门限，只能去除**低于门限**的噪声。AI 高频过净是**高于门限但过于完美**，不是噪声 |
| `_de_ess`（齿音抑制） | 仅针对 4-8kHz 宽频带全局衰减，无法区分"正常齿音"和"AI 过度锐化"。且 2-5kHz 的突刺不是齿音问题 |
| `_fast_de_crackle`（毛刺修复） | 基于帧能量比检测时域能量突变，无法检测频域的"过度完美"或 FFT 窗口啁啾 |
| `apply_clarity_v2`（清晰度增强） | 带通+叠加反而加剧了高频的"数码味"，让"玻璃感"更严重 |
| `apply_presence_boost_v5`（临场增强） | 带通+叠加增强了 2-5kHz，反而加剧了"突刺感" |

**根本原因**：v2.3/v2.3a 的所有算法都是"检测异常→修复异常"的思路，但"玻璃突刺"的本质是**频谱过于完美**，不是存在异常。需要的不是"去除异常"，而是**"打破完美"——给 AI 生成的过于精确的频谱注入自然的微不完美**。

### 行业参考

| 工具/方法 | 核心思路 | 可借鉴点 |
|-----------|---------|---------|
| Zynaptiq UNCHIRP | De-chirping（去啁啾）+ Musical Noise Reduction（音乐噪声抑制）+ Transient Synthesis（瞬态合成）| 多分辨率频谱平滑 + 瞬态旁路 |
| Adobe Audition "UnSuno" 预设 | 自适应噪声减少 + 多段压缩 + 频段分离处理 | 针对性频段处理 |
| 卓伊凡"频谱破坏"工作流 | 高频过净→加空气颗粒；2-5k 突刺→宽Q减法；低中频缺肉→加温暖；频谱太平滑→加动态变化 | "打破完美"的整体思路 |
| Undetectr | Spectral Smoothing + Timing Humanization + Pitch Micro-Variation + Dynamic Range Restoration | 频谱平滑 + 微变化注入 |

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

- 新增 `backend/services/repair/repair_v2_4/` 包：v2.4 桌面版，基于 v2.3 处理链但升级核心模块
- 新增 `backend/services/repair/repair_v2_4a/` 包：v2.4a 移动版，基于 v2.3a 扩展处理链
- 修改 `backend/services/audio_repair.py`：注册 v2.4/v2.4a 版本
- 修改 `backend/tests/conftest.py`：增加 v2.4/v2.4a 测试支持
- 修改 `backend/tests/test_repair_quality.py`：增加 v2.4/v2.4a 逐步测试类
- 修改 `backend/api/routes.py`：质量测试 API 增加 v2.4/v2.4a 测试项
- 修改 `backend/services/memory_guard.py`：增加 v2.4/v2.4a 内存估算

### v2.4 桌面版处理链（基于 v2.3，升级核心模块）

| 步骤 | v2.3 实现 | v2.4 实现 | 变更原因 |
|------|-----------|-----------|----------|
| 削波修复 | `_tanh_declip` | 保留 | 已符合铁律 |
| 爆音修复 | `_diff_clamp_depop` | 保留 | 已符合铁律 |
| 瞬态修复 | `_soft_transient_limit` | 保留 | 已符合铁律 |
| 响度归一化 | `_global_loudness_normalize` (目标 -16 LUFS) | `_adaptive_loudness_normalize` (目标 -14 LUFS，自适应增益范围 -15~+9dB) | 修复后响度偏低 |
| 多段压缩 | `_transparent_multiband_compress` (makeup gain 0.8×amount) | `_enhanced_multiband_compress` (makeup gain 1.5×amount，低频子带额外 +2dB) | 修复后响度偏低 + 低频增强 |
| **AI 频谱修复** | 无 | **`_ai_artifact_repair`** (新增，去啁啾 + 频谱去完美化 + 存在感区柔化) | 修复 AI 歌唱"玻璃突刺感" |
| 频谱降噪 | `apply_spectral_group_a` | 保留，新增 noisereduce 非平稳降噪作为可选增强 | — |
| 低频增强 | `apply_bass_enhance_v5` (低通+叠加) | `_harmonic_bass_enhance` (次谐波合成 + 谐波激励，替代 v2.2 的 `apply_bass_enhance_v5`) | 低频增强效果弱 |
| 高频质感 | `apply_clarity_v2` + `apply_presence_boost_v5` (带通+叠加) | `_air_texture_reconstruct` (空气质感重建，替代 `apply_clarity_v2` 和 `apply_presence_boost_v5`) | 高频质感不自然 + AI 高频过净 |
| 其他步骤 | 空间/立体声/温暖度/柔化/峰值限制 | 保留 | — |

### v2.4a 移动版处理链（基于 v2.3a，扩展步骤）

| 步骤 | v2.3a 实现 | v2.4a 实现 | 变更原因 |
|------|-----------|-----------|----------|
| 削波修复 | `_simple_declip` | 保留 | 已符合铁律 |
| 爆音修复 | `_simple_depop` | 保留 | 已符合铁律 |
| 频谱降噪 | `_spectral_denoise` | 保留 | — |
| 齿音抑制 | `_de_ess` | 保留 | — |
| **AI 频谱修复** | 无 | **`_ai_artifact_repair_lite`** (新增，简化版去啁啾 + 频谱去完美化) | 修复 AI 歌唱"玻璃突刺感" |
| 响度归一化 | `_loudness_normalize` (目标 -16 LUFS) | `_adaptive_loudness_normalize_lite` (目标 -14 LUFS，增益范围 -15~+9dB) | 修复后响度偏低 |
| 动态压缩 | `_transparent_compress` | `_enhanced_compress_lite` (增加 makeup gain) | 修复后响度偏低 |
| **低频增强** | 无 | **`_harmonic_bass_enhance_lite`** (新增，简化版次谐波合成) | 低频增强效果弱 |
| **高频重建** | 无 | **`_air_texture_reconstruct_lite`** (新增，简化版空气质感重建) | 高频质感不自然 |
| 直流移除 | `_remove_dc` | 保留 | — |
| 峰值限制 | `_soft_peak_limit` | 保留 | — |

### 核心新算法：`_ai_artifact_repair`（AI 歌唱"玻璃突刺"修复）

**设计理念**：不是"检测异常→修复异常"，而是"打破完美→注入自然"。AI 生成的频谱过于精确/平滑/锐利，需要通过多维度处理将其"拉回"自然听感。

**算法设计（三阶段）**：

**阶段 1：去啁啾（De-chirping）**
- 目标：消除 AI 模型 FFT 窗化处理产生的高频啁啾/水泡/鸟鸣伪影
- 方法：多分辨率频谱平滑——对频谱幅度在时间轴上执行多尺度中值滤波（窗口 3/5/7 帧），取各尺度的最小值作为平滑结果，保留瞬态同时抑制啁啾
- 瞬态旁路：检测瞬态帧（帧间能量差 > 阈值），瞬态帧跳过平滑处理，避免瞬态模糊
- 铁律合规：平滑掩码基于多帧统计量（非单帧时变），不引入 AM 伪影

**阶段 2：频谱去完美化（Spectral De-Perfection）**
- 目标：打破 AI 频谱的"玻璃感"——过于精确、过于平滑、缺乏自然微变化
- 方法：
  1. **频谱微抖动注入**：对频谱幅度添加与信号电平成比例的微弱随机抖动（±0.5~1.5dB），模拟真实声学链路的自然波动
  2. **2-5kHz 存在感区柔化**：对 2-5kHz 频段应用宽 Q（Q=0.7~1.0）动态衰减，衰减量与该频段瞬时能量成正比（能量越高衰减越多），实现"越刺越压"的自适应柔化
  3. **频谱动态变化恢复**：检测音频段落边界（基于长时能量包络的变化点），在段落间引入微弱的频谱亮度差异（±0.5dB），打破"熨斗效应"
- 铁律合规：抖动幅度为全局常量，动态衰减基于频段能量（非逐帧时变增益），段落间差异为全局常量

**阶段 3：空气质感注入（Air Texture Injection）**
- 目标：给 AI 过净的高频（10kHz+）注入自然"空气颗粒感"
- 方法：对 10kHz+ 频段添加与中频（2-8kHz）能量包络成比例的微弱成形噪声（shaped noise），噪声频谱形状模拟真实录音的高频空气衰减特性
- 铁律合规：噪声增益为全局常量，成形噪声与信号能量成比例（非独立时变）

### 核心新算法：`_harmonic_bass_enhance`（次谐波低频增强）

**v2.3 问题**：`apply_bass_enhance_v5` 仅使用低通滤波 + 叠加（`y += bass * intensity * gain`），无法产生低于原始基频的次谐波成分，低频增强效果有限。

**v2.4 算法设计**：
1. **次谐波合成**：对低频段（<250Hz）信号进行半频处理（每 2 个采样取平均），生成 1/2 倍频的次谐波
2. **谐波激励**：对低频段信号进行软削波（tanh），生成偶次谐波，增加"温暖感"
3. **200-500Hz 肉感增强**：对 200-500Hz 频段施加轻微宽 Q 提升（+1~2dB），补充 AI 歌唱常缺的"低中频身体感"
4. **混合控制**：次谐波和谐波激励分别乘以 intensity 控制的增益，与原始信号叠加
5. **铁律合规**：所有增益为全局常量，tanh 软削波符合铁律 1

### 核心新算法：`_air_texture_reconstruct`（空气质感重建）

**v2.3 问题**：`apply_clarity_v2` 使用带通滤波 + 叠加，增强的高频缺乏自然谐波结构，听感"数码味"重。`apply_presence_boost_v5` 增强 2-5kHz 反而加剧突刺感。

**v2.4 算法设计**（替代 `apply_clarity_v2` 和 `apply_presence_boost_v5`）：
1. **谐波镜像**：从中高频段（2-8kHz）提取能量包络，按谐波比例映射到高频段（8-16kHz），保留自然谐波结构
2. **空气质感填充**：对高频段（10kHz+）添加与中频能量成比例的微弱成形噪声，模拟自然高频的"空气颗粒感"
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

系统 SHALL 提供 v2.4 版本修复算法，继承 v2.3 完整处理链，升级响度归一化、多段压缩、低频增强、高频质感四个核心模块，并新增 AI 频谱修复。

#### Scenario: v2.4 修复后响度显著提升
- **WHEN** 用户使用 v2.4 处理任意音频
- **THEN** 修复后音频的 LUFS 不低于 -14 LUFS（v2.3 为 -16 LUFS），增益范围扩展至 -15~+9dB（v2.3 为 -12~+6dB）

#### Scenario: v2.4 低频增强产生次谐波
- **WHEN** 用户设置 `bass_enhance > 0`
- **THEN** `_harmonic_bass_enhance` 生成 1/2 倍频的次谐波成分，低频段（<250Hz）RMS 增长不低于 3dB（相比 v2.3 的 `apply_bass_enhance_v5`）

#### Scenario: v2.4 高频质感自然
- **WHEN** 用户设置 `clarity > 0`
- **THEN** `_air_texture_reconstruct` 基于谐波镜像+空气质感填充重建高频，高频段（8-16kHz）的频谱平坦度不低于 0.3（v2.3 的 `apply_clarity_v2` 低于 0.15）

#### Scenario: v2.4 修复 AI 歌唱"玻璃突刺"——去啁啾
- **WHEN** AI 歌唱音频包含 FFT 窗化产生的高频啁啾/水泡伪影
- **THEN** `_ai_artifact_repair` 阶段 1（去啁啾）通过多分辨率频谱平滑抑制啁啾伪影，瞬态帧不被模糊

#### Scenario: v2.4 修复 AI 歌唱"玻璃突刺"——频谱去完美化
- **WHEN** AI 歌唱音频的高频过于精确/平滑（"玻璃感"），2-5kHz 过度锐利（"突刺感"）
- **THEN** `_ai_artifact_repair` 阶段 2（频谱去完美化）通过微抖动注入 + 存在感区动态柔化 + 段落间动态变化恢复，降低"玻璃突刺感"

#### Scenario: v2.4 修复 AI 歌唱"玻璃突刺"——空气质感注入
- **WHEN** AI 歌唱音频的高频（10kHz+）过于干净/无菌
- **THEN** `_ai_artifact_repair` 阶段 3（空气质感注入）添加与中频能量成比例的成形噪声，恢复自然空气颗粒感

#### Scenario: v2.4 处理链无 AM 伪影
- **WHEN** 用户使用 v2.4 处理任意音频
- **THEN** 所有新增步骤（`_ai_artifact_repair`、`_harmonic_bass_enhance`、`_air_texture_reconstruct`）使用全局常量增益或基于能量的动态处理（非逐帧时变增益），符合铁律 1/2/3

#### Scenario: v2.4 可选 noisereduce 增强
- **WHEN** 桌面端安装了 noisereduce 且用户设置 `noise_reduction > 0.5`
- **THEN** 频谱降噪步骤优先使用 noisereduce 的非平稳降噪模式；若 noisereduce 不可用则回退到 v2.3 的 `apply_spectral_group_a`

### Requirement: v2.4a 移动版修复算法

系统 SHALL 提供 v2.4a 版本修复算法，在 v2.3a 基础上增加 AI 频谱修复、低频增强、高频重建三个步骤，并升级响度归一化和动态压缩。

#### Scenario: v2.4a 修复 AI 歌唱"玻璃突刺"
- **WHEN** AI 歌唱音频包含"玻璃突刺"复合伪影
- **THEN** `_ai_artifact_repair_lite` 执行简化版去啁啾 + 频谱去完美化（仅 2-12kHz 范围，无段落动态变化恢复）

#### Scenario: v2.4a 低频增强
- **WHEN** 用户设置 `bass_enhance > 0`
- **THEN** `_harmonic_bass_enhance_lite` 生成次谐波成分

#### Scenario: v2.4a 高频重建
- **WHEN** 用户设置 `clarity > 0`
- **THEN** `_air_texture_reconstruct_lite` 基于谐波镜像+空气质感填充重建高频

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

#### Scenario: AI 频谱修复专项测试
- **WHEN** 运行质量测试
- **THEN** 包含模拟"玻璃突刺"复合伪影的测试信号（高频过净 + 2-5kHz 突刺 + FFT 啁啾），验证 `_ai_artifact_repair` 和 `_ai_artifact_repair_lite` 的修复效果

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

v2.4 的 `bass_enhance` 参数从"低通+叠加"变更为"次谐波合成+谐波激励"。v2.4 的 `clarity` 参数从"带通+叠加"变更为"空气质感重建"。

v2.4a 新增 `bass_enhance` 和 `clarity` 参数（v2.3a 无此参数）。

## REMOVED Requirements

无移除项。

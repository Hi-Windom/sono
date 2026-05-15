# Sono v3.3 系列算法开发规划 Spec

## Why

当前 v3.2 系列已实现智能压缩、自适应 AI 频谱修复、瞬态感知、共振抑制等算法升级，在 HiFi 音质修复方面表现良好。然而 Suno v5.5（Voices、Custom Models）及同代 AI 模型的典型痕迹（金属感、高频闪烁、谐波规整过度、噪声地板平坦、相位锁定、融合痕迹）需要更强的**统计自然化**处理来消除。同时权威第三方 AI 检测器（authio、ACRCloud、Deezer、Pex 等）的识别率需要通过算法手段显著降低。v3.3 系列专注于**统计自然化**路线，在不违反 QUALITY_RULES.md 三条铁律的前提下，实现 HiFi 音质与反 AI 检测的更好平衡。

## What Changes

### 1. 新增版本体系

| 版本 | 平台 | 定位 | 相对 v3.2 基线 | 内存系数 |
|------|------|------|----------------|----------|
| v3.3 | 桌面 | 基础统计自然化版（推荐主力） | 全新管线 | +40%（新增子带分解 + 谱处理） |
| v3.3+ | 桌面 | 增强版（f0-guided + 感知模块） | 基于 v3.3 | +80%（增加 f0 跟踪 + 感知加权） |
| v3.3a | 移动 | 轻量版（降低计算量） | 全新精简管线 | +20%（减少子带数、简化处理） |
| v3.3a+ | 移动 | 轻量增强版（残差精炼后处理） | 基于 v3.3a | +35%（增加残差扩散后处理） |

**与 v3.2 的哲学差异**：v3.2 是**修复**导向（压缩、激励、齿音抑制、母带），v3.3 是**自然化**导向（统计去规整、谱补全、噪声地板塑形、相位扩散）。两者互补，v3.3 不替代 v3.2，而是提供全新的处理范式。

### 2. 代码目录结构

```
backend/services/repair/
├── repair_v3_3/           # v3.3 桌面标准版（完整管线）
│   ├── __init__.py
│   ├── core.py             # 主入口 repair_v3_3(y, sr, params)
│   ├── spectral.py         # 谱修复、自然化、谐波恢复
│   ├── transient.py        # 瞬态检测与保护
│   ├── phase.py            # 相位/MS 处理
│   ├── dynamic.py          # 动态、响度
│   ├── utils.py            # 辅助函数、软限幅、流式工具
│   ├── config.py           # 参数默认值、Preset
│   └── tests/              # 单元测试
├── repair_v3_3p/          # v3.3+ 桌面增强版
│   ├── __init__.py
│   ├── core.py             # 主入口（继承 v3.3，增加 f0-guided + 感知）
│   └── config.py           # 增强版参数
├── repair_v3_3a/          # v3.3a 移动精简版
│   ├── __init__.py
│   ├── core.py             # 精简管线
│   └── config.py
├── repair_v3_3ap/         # v3.3a+ 移动增强版（残差精炼）
│   ├── __init__.py
│   ├── core.py             # 精简管线 + 残差后处理
│   └── config.py
```

### 3. 核心处理管线（v3.3 主线）

**输入**：音频（任意长度、采样率自适应）
**输出**：修复后 WAV（32-bit float 内部，导出 24-bit/16-bit 可选）

#### 3.1 预分析模块（Pre-analysis）
- **新增** `_pre_analysis(y, sr)` in `spectral.py`:
  - 基频 f0 粗跟踪：简化自相关 / YIN 算法（轻量版，桌面版精确跟踪，移动版简化跟踪）
  - 瞬态/onset 检测：短窗口能量变化率检测起音位置
  - AI 痕迹概率评估：内部参考指标（不影响输出），用于自适应调节强度
  - 子带分解：ERB/Bark 尺度滤波器组，桌面版 24-32 带，移动版 16-20 带
- **复用现有 dsp_utils**，不引入新依赖

#### 3.2 频谱修复与统计自然化（Spectral Naturalization，最优先）
**这是 v3.3 的核心创新，所有操作遵守铁律。**
- **新增** `_spectral_naturalize(y, sr, strength, f0)` in `spectral.py`:
  - **感知驱动谱补全**（`_perceptual_spectral_completion`）：
    - 高频（>8kHz）使用引导滤波 + 谐波梳状增强，仅在 f0 整数倍位置增强
    - 对 AI 模型缺失的高频细节进行统计建模补全
    - 非 f0 整数倍位置保持原始噪声特性
  - **噪声地板塑形**（`_noise_floor_shape`）：
    - 极低幅度 1/f 粉噪注入（-78dB ~ -85dB，相对峰值）
    - 仅针对平坦 AI 噪声区（检测到噪声地板方差 < 阈值时激活）
    - 保留真实残余噪声（不覆盖自然噪声）
  - **谐波统计去规整**（`_harmonic_deregularize`）：
    - 轻微能量扰动 + 泛音不规则性注入（幅度极低，SNR > 50dB 保护）
    - 破坏 AI 模型过度规整的谐波结构
  - **子带选择性去相关**（`_subband_decorrelate`）：
    - 中高频子带轻微相位扰动（all-pass 滤波）
    - 减少 AI 模型的多带相关性痕迹
- **所有随机操作使用固定种子**，确保确定性输出

#### 3.3 瞬态与表达力保护（Transient & Expression Protection）
- **新增** `_transient_protect(y, sr, strength)` in `transient.py`:
  - Onset 区域降低修复强度（<5ms 窗口）
  - 保留/轻微增强微颤音、自然包络波动（v5.5 Voices 情感段）
  - 鼓点/打击乐冲击感保护
  - 复用预分析阶段的瞬态检测结果

#### 3.4 相位与空间自然化（Phase & Spatial）
- **新增** `_phase_naturalize(y, sr, strength)` in `phase.py`:
  - 轻量 all-pass + MS（Mid-Side）扩散处理，增加空气感
  - 高频群延时轻微校正（减少 AI 模型的相位锁定痕迹）
- **复用** v3.2 的 `_vocal_spatial` 基础结构，但参数更保守

#### 3.5 动态与响度处理（Dynamic & Loudness）
- **新增** `_dynamic_naturalize(y, sr, strength)` in `dynamic.py`:
  - 慢速多频段 upward compression（仅低能量区，慢包络 > 50ms）
  - 符合铁律 2：不使用逐样本增益调制，使用全局分频段增益
  - 感知响度匹配（ITU-R BS.1770 / A-weighting，目标 -14 LUFS 可调）

#### 3.6 安全后处理（Safe Post-process）
- **新增** `_safe_postprocess(y, sr, params)` in `utils.py`:
  - Soft tanh 软限幅（符合铁律 1）
  - 全局常量增益（符合铁律 2）
  - 可选残差精炼（v3.3a+）：original - processed 残差极弱感知处理后加回

### 4. 版本差异详情

#### v3.3（桌面标准版）
- 完整管线：预分析 → 频谱自然化 → 瞬态保护 → 相位自然化 → 动态处理 → 安全后处理
- 子带数：24-32（ERB/Bark 尺度）
- f0 跟踪：精确自相关 / YIN
- 默认强度：1.0
- 内存系数：+40%（相对 v3.2）

#### v3.3+（桌面增强版）
- 继承 v3.3 全部管线
- **新增** f0-guided 精细谐波处理：在频谱自然化中使用精确 f0 轨迹引导谐波增强
- **新增** 感知加权模块（Mel/ERB）：根据感知重要性调节各频段处理强度
- **新增** Preset 系统：Anti-Detect / HiFi-Pure / Vocal 三种预设
- 可调参数更丰富（暴露感知加权曲线、去相关深度等）
- 内存系数：+80%

#### v3.3a（移动精简版）
- 精简管线：简化预分析 → 简化频谱自然化 → 简化瞬态保护 → 安全后处理
- 子带数：16-20
- f0 跟踪：简化自相关（不精确跟踪，仅用于子带划分）
- 噪声塑形简化（固定 1/f 参数，不检测 AI 噪声区）
- 关闭相位自然化（all-pass 处理跳过）
- 内存系数：+20%

#### v3.3a+（移动增强版）
- 继承 v3.3a 全部管线
- **新增** 轻量残差扩散后处理：original - processed 残差经极弱感知处理后加回（强度 0.1-0.2）
- 残差处理使用简化频谱自然化（仅一次 all-pass + 1/f 注入）
- 内存系数：+35%

### 5. 后端 API 变更

- **新增** `backend/services/repair/repair_v3_3/core.py`：v3.3 桌面标准版
- **新增** `backend/services/repair/repair_v3_3p/core.py`：v3.3+ 桌面增强版
- **新增** `backend/services/repair/repair_v3_3a/core.py`：v3.3a 移动精简版
- **新增** `backend/services/repair/repair_v3_3ap/core.py`：v3.3a+ 移动增强版
- **修改** `backend/services/audio_repair.py`：注册 v3.3/v3.3+/v3.3a/v3.3a+ 版本
- **修改** `backend/services/memory_guard.py`：增加四个新版本的内存估算
- **新增参数**：
  - `spectral_naturalize: number (0-1)` — 频谱自然化强度
  - `noise_floor_shape: number (0-1)` — 噪声地板塑形强度
  - `harmonic_deregularize: number (0-1)` — 谐波去规整强度
  - `phase_naturalize: number (0-1)` — 相位自然化强度
  - `transient_protect: number (0-1)` — 瞬态保护强度
  - `dynamic_naturalize: number (0-1)` — 动态自然化强度
  - `preset: "anti-detect" | "hifi-pure" | "vocal" | "none"`（仅 v3.3+）
  - `residual_refine: number (0-1)`（仅 v3.3a+）

### 6. 前端变更

- **修改** `src/components/AIRepairPanel.tsx`：
  - v3.3 系列新增频谱自然化、噪声塑形、谐波去规整、相位自然化等控件
  - v3.3+ 增加 Preset 选择器（Anti-Detect / HiFi-Pure / Vocal）
  - v3.3a+ 增加残差精炼强度控件
  - 算法版本选择中 v3.3 作为新推荐版本，标注"自然化"
- **修改** `src/services/backendApi.ts`：
  - 增加 v3.3 系列参数类型
  - ALGORITHM_VERSIONS 包含 v3.3/v3.3+/v3.3a/v3.3a+

### 7. 风险控制

- 每处随机/扰动操作固定种子或确定性实现
- 所有修改幅度从极低开始，逐步提升
- 持续监控 SNR/可听伪影（SNR > 40dB 基线）
- 保留完整中间结果导出（调试频谱/波形）
- 遵守现有缓存、取消、流式机制
- Android 自动降级路径（检测缺失模块 → fallback）

## Impact

- Affected specs: 修复算法质量保障体系
- Affected code:
  - `backend/services/repair/repair_v3_3/`（新建，含 7 个文件）
  - `backend/services/repair/repair_v3_3p/`（新建，含 3 个文件）
  - `backend/services/repair/repair_v3_3a/`（新建，含 3 个文件）
  - `backend/services/repair/repair_v3_3ap/`（新建，含 3 个文件）
  - `backend/services/audio_repair.py`（修改：注册新版本）
  - `backend/services/memory_guard.py`（修改：v3.3 系列内存估算）
  - `src/components/AIRepairPanel.tsx`（修改：v3.3 参数面板）
  - `src/services/backendApi.ts`（修改：v3.3 类型 + 新参数）

## ADDED Requirements

### Requirement: v3.3 桌面标准版算法
The system SHALL provide v3.3 repair algorithm implementing the full statistical naturalization pipeline: pre-analysis, spectral naturalization, transient protection, phase naturalization, dynamic processing, and safe post-processing.

#### Scenario: 频谱自然化
- **WHEN** 用户选择 v3.3 算法并设置 spectral_naturalize > 0
- **THEN** 后端执行感知驱动谱补全（高频引导滤波 + 谐波梳状增强）、噪声地板塑形（极低 1/f 粉噪注入）、谐波统计去规整（轻微能量扰动）、子带选择性去相关（all-pass 相位扰动）

#### Scenario: 瞬态保护
- **WHEN** 用户设置 transient_protect > 0
- **THEN** 后端在 onset 区域（<5ms 窗口）降低修复强度，保留微颤音和打击乐冲击感

#### Scenario: 相位自然化
- **WHEN** 用户设置 phase_naturalize > 0
- **THEN** 后端执行轻量 all-pass + MS 扩散处理，增加空气感

#### Scenario: 动态自然化
- **WHEN** 用户设置 dynamic_naturalize > 0
- **THEN** 后端执行慢速多频段 upward compression + 感知响度匹配

#### Scenario: 安全后处理
- **WHEN** 所有处理步骤完成
- **THEN** 后端应用 soft tanh 软限幅 + 全局常量增益，严格遵守 QUALITY_RULES.md

### Requirement: v3.3+ 桌面增强版
The system SHALL provide v3.3+ algorithm with f0-guided fine harmonic processing, perceptual weighting (Mel/ERB), and preset system (Anti-Detect / HiFi-Pure / Vocal).

#### Scenario: f0-guided 精细谐波
- **WHEN** 用户选择 v3.3+ 算法
- **THEN** 后端使用精确 f0 轨迹引导谐波增强，仅在 f0 整数倍位置操作

#### Scenario: Preset 系统
- **WHEN** 用户选择 preset="anti-detect"
- **THEN** 后端应用最强去相关 + 噪声塑形 + 谐波去规整参数组合
- **WHEN** 用户选择 preset="hifi-pure"
- **THEN** 后端应用保守自然化参数，优先保证音质
- **WHEN** 用户选择 preset="vocal"
- **THEN** 后端优化人声参数（增强瞬态保护 + 减少高频处理）

### Requirement: v3.3a/v3.3a+ 移动版
The system SHALL provide v3.3a (standard) and v3.3a+ (premium) mobile-compatible algorithms with reduced subband count and simplified processing.

#### Scenario: v3.3a 精简处理
- **WHEN** 用户选择 v3.3a 算法
- **THEN** 应用精简管线（16-20 子带、简化 f0、固定噪声塑形、跳过相位自然化）

#### Scenario: v3.3a+ 残差精炼
- **WHEN** 用户选择 v3.3a+ 算法
- **THEN** 在精简管线处理后增加轻量残差扩散后处理（残差经弱感知处理后加回）

### Requirement: 流式处理与内存优化
The system SHALL support streaming processing with overlap-add for arbitrary-length audio, maintaining memory usage ≤4-6GB RAM.

#### Scenario: 长音频处理
- **WHEN** 处理超过 30 分钟的音频
- **THEN** 使用分块流式处理，每块 10s，overlap-add 拼接，内存峰值不超过 6GB

#### Scenario: Android 降级
- **WHEN** 在 Android/Termux 环境运行
- **THEN** 自动检测可用模块，缺失时 fallback 到 v3.3a 精简版

## MODIFIED Requirements

### Requirement: 内存估算（修改）
The system SHALL update memory_guard.py to estimate memory for four new algorithm versions.

**新增估算**：
- v3.3: +40%（子带滤波器组 + 频谱自然化处理，复用现有 STFT）
- v3.3+: +80%（f0 精确跟踪 + 感知加权 + 双倍子带处理）
- v3.3a: +20%（简化子带 + 基础自然化）
- v3.3a+: +35%（子带 + 自然化 + 残差缓冲区）

### Requirement: 算法版本注册（修改）
The system SHALL register v3.3/v3.3+/v3.3a/v3.3a+ in audio_repair.py as selectable algorithm versions.

**新增版本映射**：
- `"v3.3"` → `repair_v3_3.core.repair_audio`
- `"v3.3+"` → `repair_v3_3p.core.repair_audio`
- `"v3.3a"` → `repair_v3_3a.core.repair_audio`
- `"v3.3a+"` → `repair_v3_3ap.core.repair_audio`

## REMOVED Requirements

无
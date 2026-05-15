# 修复算法 v3.2/v3.2a/v3.2+/v3.2a+ 升级 Spec

## Why

当前 v3.1/v3.1a 已实现人声效果器链（激励器、压缩器、空间感、温暖度）和三种母带风格，但人声动态控制、空间感处理、频谱修复精度仍有提升空间。v3.2 引入分频段处理架构和多分辨率频谱修复，显著提升人声清晰度、动态自然度和空间感。v3.2+/v3.2a+ 作为"高画质"变体，允许使用更多内存和处理时间，追求极致音质。

## What Changes

### 1. 新增版本体系

| 版本 | 平台 | 定位 | 相对基线 | 内存系数 |
|------|------|------|----------|----------|
| v3.2 | 桌面 | 标准增强 | 基于 v3.1 | +150% |
| v3.2+ | 桌面 | 高画质（更多内存/时间） | 基于 v3.2 | +250% |
| v3.2a | 移动 | 轻量增强 | 基于 v3.1a | +80% |
| v3.2a+ | 移动 | 高画质轻量（更多内存/时间） | 基于 v3.2a | +120% |

#### v3.2（桌面标准版，相对 v3.1 增强）

- **多频段压缩器**（`_vocal_multiband_compressor`）— 3 频段（低频 20-200Hz、中频 200-4000Hz、高频 4000-20000Hz）独立压缩，每频段独立阈值/比率/attack/release
- **分频段激励器**（`_vocal_multiband_exciter`）— 对中频（1-4kHz）和高频（4-10kHz）分别应用不同强度的谐波激励
- **瞬态增强**（`_transient_enhance`）— 检测并增强人声瞬态（起音），提升清晰度和存在感
- **高级空间感**（`_vocal_spatial_advanced`）— 立体声加宽 + 早期反射模拟 + 扩散混响尾音，支持宽度参数和频率相关延迟
- **自适应母带**（`_mastering_adaptive`）— 分析混音频谱分布，自动调整 EQ 曲线和动态处理，替代固定的三种风格
- **多分辨率 AI 修复**（`_vocal_ai_repair_multi_resolution`）— 结合 N_FFT=1024（高时间分辨率）和 N_FFT=4096（高频率分辨率）的频谱修复结果，取最优
- **共振抑制**（`_resonance_suppress`）— 检测频谱中的突出共振峰并做陷波衰减，消除刺耳音
- **改进压缩器** — v3.1 压缩器升级：增加 look-ahead（前瞻 5ms）、改进 RMS 包络检测精度

#### v3.2+（桌面高画质版，相对 v3.2 增强）

- **两遍处理** — 整个处理管线运行两遍：第一遍粗修，第二遍在粗修基础上精修，参数减半
- **高精度 STFT** — 频谱处理使用 N_FFT=4096，提高频率分辨率
- **前视压缩器**（`_lookahead_compressor`）— 10ms 前视 + 精确 RMS 包络 + 软膝曲线，更自然
- **四频段多频段处理** — 分 4 频段独立压缩/激励
- **动态均衡器**（`_dynamic_eq`）— 实时检测问题频率并做动态衰减
- **高级混响** — 更长衰减时间、扩散网络模拟、早期反射 + 混响尾音分离

#### v3.2a（移动标准版，相对 v3.1a 增强）

- **多频段压缩器精简版**（`_vocal_multiband_compressor_lite`）— 2 频段（低频 20-300Hz、高频 300-20000Hz）压缩
- **分频段激励器精简版**（`_vocal_multiband_exciter_lite`）— 中高频（2-6kHz）单频段激励
- **瞬态增强精简版**（`_transient_enhance_lite`）— 简化瞬态检测 + 增益提升
- **空间感增强精简版**（`_vocal_spatial_lite`）— 简单的立体声加宽 + 短混响
- **多分辨率 AI 修复精简版**（`_vocal_ai_repair_multi_res_lite`）— N_FFT=1024 + N_FFT=2048 双分辨率融合
- **共振抑制精简版**（`_resonance_suppress_lite`）— 简化的共振峰检测 + 衰减
- **改进母带精简版** — EQ 曲线优化，增加瞬态保护

#### v3.2a+（移动高画质版，相对 v3.2a 增强）

- **两遍轻量处理** — 轻量管线运行两遍
- **AI 修复高分辨率** — 使用 N_FFT=2048 全分辨率
- **压缩器前视**（5ms look-ahead）
- **三频段多频段压缩**
- **更高质量混响** — 更长衰减、更好扩散

### 2. 后端算法 — 新增文件

- **新增** `backend/services/repair/repair_v3_2/core.py`：v3.2 桌面标准版
- **新增** `backend/services/repair/repair_v3_2p/core.py`：v3.2+ 桌面高画质版
- **新增** `backend/services/repair/repair_v3_2a/core.py`：v3.2a 移动标准版
- **新增** `backend/services/repair/repair_v3_2ap/core.py`：v3.2a+ 移动高画质版
- **修改** `backend/services/audio_repair.py`：注册 v3.2/v3.2+/v3.2a/v3.2a+ 版本
- **修改** `backend/services/memory_guard.py`：增加四个新版本的内存估算

### 3. 后端 API — 新增参数

- **修改** `VocalRepairParams` 增加：
  - `multiband_compressor: number (0-1)` — 多频段压缩强度
  - `multiband_exciter: number (0-1)` — 多频段激励强度
  - `transient_enhance: number (0-1)` — 瞬态增强强度
  - `spatial_advanced: number (0-1)` — 高级空间感强度
  - `resonance_suppress: number (0-1)` — 共振抑制强度
  - `ai_repair_multi_res: number (0-1)` — 多分辨率 AI 修复强度
  - `mastering_mode: "adaptive" | "standard" | "powerful" | "warm"` — 新增自适应母带模式
- **修改** `ProcessingOptions` 增加：
  - `quality_mode: "standard" | "premium"` — 标准/高画质模式（对应 + 版本）
  - `multi_pass: boolean` — 是否启用多遍处理

### 4. 前端 — 修复页面 v3.2/v3.2a

- **修改** `src/components/AIRepairPanel.tsx`：
  - v3.2/v3.2+ 人声参数面板增加：多频段压缩器、多频段激励器、瞬态增强、高级空间感、共振抑制、多分辨率 AI 修复
  - v3.2a/v3.2a+ 人声参数面板增加对应精简版控件
  - 合并输出区域增加母带模式选择器（标准/强劲/温暖/自适应）
  - v3.2+/v3.2a+ 面板增加"高画质模式"开关提示
- **修改** `src/services/backendApi.ts`：
  - 增加 v3.2 系列参数类型
  - ALGORITHM_VERSIONS 包含 v3.2/v3.2+/v3.2a/v3.2a+
  - 增加 quality_mode/multi_pass 参数

### 5. 前端 — 算法版本选择

- **修改** `src/components/AIRepairPanel.tsx`：
  - 双轨模式下 v3.2/v3.2a 作为新推荐版本
  - v3.2+ 标注为"高画质"标签，v3.2a+ 标注为"移动高画质"
  - 选择 + 版本时显示提示：将使用更多内存和处理时间

## Impact

- Affected specs: 修复算法质量保障体系
- Affected code:
  - `backend/services/repair/repair_v3_2/` (新建)
  - `backend/services/repair/repair_v3_2p/` (新建)
  - `backend/services/repair/repair_v3_2a/` (新建)
  - `backend/services/repair/repair_v3_2ap/` (新建)
  - `backend/services/audio_repair.py` (修改：注册新版本)
  - `backend/services/memory_guard.py` (修改：v3.2 系列内存估算)
  - `src/components/AIRepairPanel.tsx` (修改：v3.2 参数面板)
  - `src/services/backendApi.ts` (修改：v3.2 类型 + 新参数)
  - `src/hooks/useAudioProcessor.ts` (修改：quality_mode 参数传递)

## ADDED Requirements

### Requirement: v3.2 桌面标准版算法
The system SHALL provide v3.2 repair algorithm for desktop with multiband processing, transient enhancement, advanced spatial, and adaptive mastering.

#### Scenario: 多频段压缩器
- **WHEN** 用户选择 v3.2 算法并设置 multiband_compressor > 0
- **THEN** 后端将人声分为 3 频段（低/中/高）分别应用独立压缩，频段间交叉渐变防伪影

#### Scenario: 分频段激励器
- **WHEN** 用户设置 multiband_exciter > 0
- **THEN** 后端对中频（1-4kHz）和高频（4-10kHz）分别应用不同驱动量的谐波激励

#### Scenario: 瞬态增强
- **WHEN** 用户设置 transient_enhance > 0
- **THEN** 后端检测人声瞬态起音并做增益提升，提升清晰度和存在感

#### Scenario: 高级空间感
- **WHEN** 用户设置 spatial_advanced > 0
- **THEN** 后端应用立体声加宽 + 早期反射模拟 + 扩散混响尾音

#### Scenario: 自适应母带
- **WHEN** 用户选择 mastering_mode="adaptive"
- **THEN** 后端分析混音频谱分布，自动计算 EQ 曲线和动态处理参数

#### Scenario: 多分辨率 AI 修复
- **WHEN** 用户设置 ai_repair_multi_res > 0
- **THEN** 后端结合 N_FFT=1024 和 N_FFT=4096 的频谱修复结果，融合最优部分

#### Scenario: 共振抑制
- **WHEN** 用户设置 resonance_suppress > 0
- **THEN** 后端检测频谱突出共振峰并做动态陷波衰减

### Requirement: v3.2+ 桌面高画质版
The system SHALL provide v3.2+ algorithm with premium quality using multi-pass processing and higher precision.

#### Scenario: 两遍处理
- **WHEN** 用户选择 v3.2+ 算法
- **THEN** 整个处理管线运行两遍：第一遍参数按 0.7 系数，第二遍按 0.3 系数精细调整

#### Scenario: 高精度 STFT
- **WHEN** 频谱处理步骤执行
- **THEN** 使用 N_FFT=4096 提高频率分辨率

#### Scenario: 前视压缩器
- **WHEN** 压缩步骤执行
- **THEN** 使用 10ms 前视 + 精确 RMS 包络

### Requirement: v3.2a/v3.2a+ 移动版
The system SHALL provide v3.2a (standard) and v3.2a+ (premium) mobile-compatible algorithms.

#### Scenario: v3.2a 精简处理
- **WHEN** 用户选择 v3.2a 算法
- **THEN** 应用 2 频段压缩、单频段激励、简化瞬态增强、简化空间感和双分辨率 AI 修复

#### Scenario: v3.2a+ 高画质
- **WHEN** 用户选择 v3.2a+ 算法
- **THEN** 轻量管线运行两遍、AI 修复使用全分辨率 N_FFT=2048、压缩器带 5ms 前视

## MODIFIED Requirements

### Requirement: 内存估算（修改）
The system SHALL update memory_guard.py to estimate memory for four new algorithm versions.

**修改前**：仅支持 v3.1 (+120%) 和 v3.1a (+60%)
**修改后**：
- v3.2: +150%（多频段处理增加临时缓冲区）
- v3.2+: +250%（两遍处理 + 高精度 STFT + 前视缓冲区）
- v3.2a: +80%（多频段 + 双分辨率处理）
- v3.2a+: +120%（两遍处理 + 高分辨率 + 前视）

## REMOVED Requirements

无
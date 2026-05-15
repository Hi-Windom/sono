# 修复算法 v3.2/v3.2a/v3.2+/v3.2a+ 升级 Spec

## Why

当前 v3.1/v3.1a 已实现人声效果器链（激励器、压缩器、空间感、温暖度）和三种母带风格，但算法精度和智能程度仍有提升空间。v3.2 系列专注于**低内存增长的智能算法升级**，通过改进阈值策略、包络检测、自适应参数等计算方式的优化来提升音质，而非增加内存密集型处理。v3.2+ 作为"精修"变体，允许适度增加内存和处理时间，追求更精细的修复效果。v3.2a+ 作为"移动增强"变体，在移动端基础上提供更强的处理能力。

## What Changes

### 1. 新增版本体系

| 版本 | 平台 | 定位 | 相对基线 | 内存系数 |
|------|------|------|----------|----------|
| v3.2 | 桌面 | 标准智能升级 | 基于 v3.1 | +30%（最小内存增长） |
| v3.2+ | 桌面 | 精修（适度更多内存/时间） | 基于 v3.2 | +60% |
| v3.2a | 移动 | 轻量智能升级 | 基于 v3.1a | +20% |
| v3.2a+ | 移动 | 移动增强（适度更多内存/时间） | 基于 v3.2a | +40% |

#### v3.2（桌面标准版，相对 v3.1 增强）

**原则：不增加额外大缓冲区，所有改进复用现有 STFT 数据或使用极小额外内存。**

- **智能压缩器**（`_vocal_smart_compressor`）— 替换 v3.1 `_vocal_compressor`：
  - 自适应 release 时间：根据音频内容动态调整 release（安静段快释放、响亮段慢释放），减少 pumping 效应
  - 改进 RMS 包络：使用滑动窗口 RMS + 峰值跟踪混合，响应更自然
  - 相同内存占用，仅改进计算逻辑
- **自适应 AI 频谱修复**（`_vocal_ai_repair_adaptive`）— 替换 v3.1 `_vocal_ai_repair_enhanced`：
  - 动态噪声本底跟踪：逐帧更新噪声本底估计，而非使用全局中位数
  - 频域自适应阈值：高频段使用更宽松阈值（减少高频衰减），低频段使用更严格阈值
  - 复用现有 STFT 数据，不新增缓冲区
- **瞬态感知处理**（`_transient_aware_process`）— 新增处理步骤：
  - 瞬态检测：基于帧间频谱变化检测起音位置（仅需 2 帧历史缓冲区 ~6KB）
  - 瞬态保护：在压缩/激励步骤中识别瞬态帧，降低处理强度以保留起音清晰度
- **自适应母带**（`_mastering_adaptive`）— 新增母带模式，与 standard/powerful/warm 并列：
  - 频谱分析：对混音结果做快速频谱分析（复用 STFT）
  - 自动 EQ：根据频谱能量分布自动计算 EQ 提升/衰减曲线
  - 智能响度：根据内容类型自动选择目标响度
- **共振抑制**（`_resonance_suppress`）— 新增处理步骤：
  - 基于 STFT 幅值检测异常突出的频点（共振峰）
  - 对该频点施加动态陷波衰减
  - 完全复用现有 STFT 数据，零额外内存
- **改进激励器**（`_vocal_exciter_improved`）— 替换 v3.1 `_vocal_exciter`：
  - 多阶谐波生成（二次 + 三次谐波混合），非对称饱和曲线
  - 频段交叉渐变，减少谐波失真
- **改进齿音抑制**（`_de_esser_improved`）— 替换 v3.1 `_vocal_de_esser_advanced`：
  - 自适应阈值：根据整体齿音能量水平动态调整检测阈值
  - 频率跟踪：检测齿音中心频率偏移，做更精准的衰减

**处理管线变化**（v3.1 管线基础上）：
- 替换：`_vocal_compressor` → `_vocal_smart_compressor`
- 替换：`_vocal_ai_repair_enhanced` → `_vocal_ai_repair_adaptive`
- 替换：`_vocal_exciter` → `_vocal_exciter_improved`
- 替换：`_vocal_de_esser_advanced` → `_de_esser_improved`
- 新增：`_transient_aware_process`（在压缩器之后、激励器之前）
- 新增：`_resonance_suppress`（在 AI 修复之后、激励器之前）
- 新增：母带模式 `adaptive`

#### v3.2+（桌面精修版，相对 v3.2 增强）

**适度增加内存，换取更优效果。**

- **两遍轻量处理** — 管线运行两遍：第一遍全参数处理，第二遍以 0.3 系数精细微调。第二遍仅运行核心步骤（smart_compressor + exciter + transient_aware），跳过已处理步骤
- **前视压缩器**（`_lookahead_compressor`）— 替换 `_vocal_smart_compressor`：
  - 5ms look-ahead 缓冲区（~240 样本 @48kHz，极小内存）
  - 前视 + RMS 混合包络检测，起音更自然
- **双分辨率 AI 修复** — 替换 `_vocal_ai_repair_adaptive`：
  - 主处理使用 N_FFT=2048（标准），额外用 N_FFT=1024 做瞬态保护
  - 瞬态帧使用高时间分辨率结果，平稳帧使用高频率分辨率结果
  - 额外 STFT 计算 ~5MB 临时内存（流式下可忽略）
- **增强共振抑制** — 替换 `_resonance_suppress`：
  - 增加时域平滑，避免陷波引入可闻伪影
  - 频域 + 时域双域检测，提高共振检测准确率
- **增强空间感**（`_vocal_spatial_enhanced`）— 替换 `_vocal_spatial_advanced`：
  - 早期反射 + 扩散混响尾音（约 50ms 额外缓冲区）
  - 频率相关立体声加宽

#### v3.2a（移动标准版，相对 v3.1a 增强）

**同样遵循最小内存增长原则。**

- **智能压缩器精简版**（`_vocal_smart_compressor_lite`）— 替换 `_vocal_compressor_lite`：
  - 自适应 release 时间（与桌面版相同算法，更保守的参数范围）
- **自适应 AI 修复精简版**（`_vocal_ai_repair_adaptive_lite`）— 替换 `_vocal_ai_repair_enhanced_lite`：
  - 动态噪声本底跟踪 + 频域自适应阈值
  - 使用 N_FFT=1024（与 v3.1a 相同，不增加内存）
- **瞬态感知处理精简版**（`_transient_aware_process_lite`）— 新增：
  - 简化瞬态检测（仅基于时域能量变化）
  - 瞬态保护逻辑
- **共振抑制精简版**（`_resonance_suppress_lite`）— 新增：
  - 简化共振峰检测 + 衰减
- **自适应母带精简版**（`_mastering_adaptive_lite`）— 新增母带模式
- **改进激励器精简版** — 替换 `_vocal_exciter_lite`：
  - 更好的谐波混合比例

#### v3.2a+（移动增强版，相对 v3.2a 增强）

- **两遍轻量处理** — 精简管线运行两遍
- **前视压缩器精简版** — 3ms look-ahead（~144 样本）
- **AI 修复全分辨率** — 使用 N_FFT=2048
- **增强空间感精简版** — 简单早期反射 + 短混响尾音

### 2. 后端算法 — 新增文件

- **新增** `backend/services/repair/repair_v3_2/core.py`：v3.2 桌面标准版
- **新增** `backend/services/repair/repair_v3_2p/core.py`：v3.2+ 桌面精修版
- **新增** `backend/services/repair/repair_v3_2a/core.py`：v3.2a 移动标准版
- **新增** `backend/services/repair/repair_v3_2ap/core.py`：v3.2a+ 移动增强版
- **修改** `backend/services/audio_repair.py`：注册 v3.2/v3.2+/v3.2a/v3.2a+ 版本
- **修改** `backend/services/memory_guard.py`：增加四个新版本的内存估算

### 3. 后端 API — 新增参数

- **修改** `VocalRepairParams` 增加：
  - `smart_compressor: number (0-1)` — 智能压缩强度（替换 compressor）
  - `transient_aware: number (0-1)` — 瞬态感知处理强度
  - `resonance_suppress: number (0-1)` — 共振抑制强度
  - `ai_repair_adaptive: number (0-1)` — 自适应 AI 修复强度（替换 ai_repair_enhanced）
  - `exciter_improved: number (0-1)` — 改进激励器强度（替换 exciter）
  - `de_esser_improved: number (0-1)` — 改进齿音抑制强度（替换 de_esser_advanced）
  - `mastering_mode: "adaptive" | "standard" | "powerful" | "warm"` — 新增自适应母带模式
- **修改** `ProcessingOptions` 增加：
  - `quality_mode: "standard" | "fine"` — 标准/精修模式（+ 版本使用精修模式）

### 4. 前端 — 修复页面 v3.2/v3.2a

- **修改** `src/components/AIRepairPanel.tsx`：
  - v3.2/v3.2+ 人声参数面板：替换压缩器/激励器/齿音抑制控件为改进版，新增瞬态感知、共振抑制控件
  - v3.2a/v3.2a+ 人声参数面板：对应精简版控件更新
  - 合并输出区域增加母带模式选择器（标准/强劲/温暖/自适应）
  - v3.2+/v3.2a+ 面板增加"精修模式"标签提示
- **修改** `src/services/backendApi.ts`：
  - 增加 v3.2 系列参数类型
  - ALGORITHM_VERSIONS 包含 v3.2/v3.2+/v3.2a/v3.2a+
  - 增加 quality_mode 参数

### 5. 前端 — 算法版本选择

- **修改** `src/components/AIRepairPanel.tsx`：
  - 双轨模式下 v3.2/v3.2a 作为新推荐版本
  - v3.2+ 标注为"精修"标签，v3.2a+ 标注为"增强"标签
  - 选择 + 版本时显示提示：将使用稍多内存和处理时间，换取更精细的修复效果

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
The system SHALL provide v3.2 repair algorithm for desktop with smart compressor, adaptive AI repair, transient-aware processing, adaptive mastering, and resonance suppression — all with minimal memory increase.

#### Scenario: 智能压缩器
- **WHEN** 用户选择 v3.2 算法并设置 smart_compressor > 0
- **THEN** 后端使用自适应 release 时间（安静段快释放、响亮段慢释放）+ 滑动窗口 RMS + 峰值跟踪混合包络检测

#### Scenario: 自适应 AI 频谱修复
- **WHEN** 用户设置 ai_repair_adaptive > 0
- **THEN** 后端使用动态噪声本底跟踪（逐帧更新）和频域自适应阈值（高频宽松、低频严格），复用现有 STFT 数据

#### Scenario: 瞬态感知处理
- **WHEN** 用户设置 transient_aware > 0
- **THEN** 后端检测瞬态起音位置，在压缩/激励步骤中对瞬态帧降低处理强度以保留起音清晰度

#### Scenario: 自适应母带
- **WHEN** 用户选择 mastering_mode="adaptive"
- **THEN** 后端对混音做频谱分析，自动计算 EQ 提升/衰减曲线和目标响度

#### Scenario: 共振抑制
- **WHEN** 用户设置 resonance_suppress > 0
- **THEN** 后端基于 STFT 幅值检测异常突出频点，施加动态陷波衰减

#### Scenario: 改进激励器
- **WHEN** 用户设置 exciter_improved > 0
- **THEN** 后端使用多阶谐波生成（二次 + 三次谐波混合）和非对称饱和曲线

#### Scenario: 改进齿音抑制
- **WHEN** 用户设置 de_esser_improved > 0
- **THEN** 后端使用自适应阈值和频率跟踪进行更精准的齿音衰减

### Requirement: v3.2+ 桌面精修版
The system SHALL provide v3.2+ algorithm with premium quality using two-pass processing, look-ahead compressor, and dual-resolution AI repair.

#### Scenario: 两遍轻量处理
- **WHEN** 用户选择 v3.2+ 算法
- **THEN** 管线运行两遍：第一遍全参数处理，第二遍仅核心步骤以 0.3 系数精细微调

#### Scenario: 前视压缩器
- **WHEN** 压缩步骤执行
- **THEN** 使用 5ms look-ahead + RMS 混合包络检测

#### Scenario: 双分辨率 AI 修复
- **WHEN** AI 修复步骤执行
- **THEN** 瞬态帧使用 N_FFT=1024 高时间分辨率，平稳帧使用 N_FFT=2048 高频率分辨率

### Requirement: v3.2a/v3.2a+ 移动版
The system SHALL provide v3.2a (standard) and v3.2a+ (premium) mobile-compatible algorithms with minimal memory increase.

#### Scenario: v3.2a 精简处理
- **WHEN** 用户选择 v3.2a 算法
- **THEN** 应用智能压缩精简版、自适应 AI 修复精简版、瞬态感知精简版、共振抑制精简版、自适应母带精简版

#### Scenario: v3.2a+ 增强
- **WHEN** 用户选择 v3.2a+ 算法
- **THEN** 轻量管线运行两遍、AI 修复使用全分辨率 N_FFT=2048、压缩器带 3ms look-ahead

## MODIFIED Requirements

### Requirement: 内存估算（修改）
The system SHALL update memory_guard.py to estimate memory for four new algorithm versions.

**修改前**：v3.1 (+120%)、v3.1a (+60%)
**修改后**：
- v3.2: +30%（改进算法逻辑，复用现有缓冲区，极小额外内存）
- v3.2+: +60%（两遍处理 + look-ahead 缓冲区 + 双分辨率 STFT）
- v3.2a: +20%（精简版算法改进）
- v3.2a+: +40%（两遍处理 + look-ahead + 全分辨率 AI）

## REMOVED Requirements

无
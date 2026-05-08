# AI 检测算法 v1.2 优化 + AI 修复算法 v2.1 音质优化 Spec

## Why

### AI 检测算法 v1.2 问题
当前 v1.2 检测算法在 `/backend/storage/training` 目录的 **AI 音乐素材** 上检测效果不佳。这些素材是 AI 生成的音乐，应当被正确识别为 AI。

**目标**：所有 AI 音乐素材用 v1.2 检测算法的 **AI 生成概率应当高于 70%**（即人类创作概率低于 30%）。

### AI 修复算法 v2.1 问题
v2.1 已存在（基于 v2.0 架构），但最终音质存在问题：
- 过度处理导致的 artifacts
- 频谱处理不够平滑
- 响度归一化有 pumping 效应

需要在保持性能的同时提升音质保真度。

## What Changes

### AI 检测算法 v1.2 优化
- **优化目标**：提高对高质量 AI 音乐素材的检出率（AI 概率 > 70%）
- **素材特点**：制作精良、听感逼真的 AI 音乐，AI 纯音乐无明显瑕疵，AI 歌唱有明显瑕疵
- **方法**：基于 `/backend/storage/training` 目录的 AI 音乐素材重新校准评分权重和阈值
- **策略**：识别高质量 AI 的隐性特征（微观规律、过度完美、缺乏人类变化）
- **保持**：对人类创作音频的低误判率

### AI 修复算法 v2.1 音质优化
- **优化现有** `backend/services/repair/repair_v2_1/` 模块
- **改进**：
  - 减少过度处理导致的 artifacts
  - 优化频谱处理组的平滑度
  - 改进响度归一化算法，减少 pumping
  - 优化谐波增强的自然度

## Impact

- 后端：`backend/services/detectors/ai_detector_v1_2.py`（修改）
- 后端：`backend/services/repair/repair_v2_1/*.py`（优化）
- 后端：`backend/services/audio_repair.py`（如有参数变更）
- 训练：`backend/training/analyze_features.py`（用于检测算法校准）

## ADDED Requirements

### Requirement: AI 检测算法 v1.2 优化

系统 SHALL 优化 v1.2 检测算法，确保 AI 音乐素材的 AI 生成概率 > 70%。

#### 校准流程
1. 提取 `/backend/storage/training` 所有 AI 音乐素材的特征
2. 分析当前 v1.2 在这些素材上的 AI 概率分布
3. 针对高质量 AI 音乐（制作精良、听感逼真）调整检测策略：
   - **AI 纯音乐**：无明显瑕疵，需识别微观规律
     - `spectral_correlation`：检测频谱层面的过度规律
     - `spectral_entropy`：检测频谱信息熵的异常分布
     - `chroma_var`：检测音高特征的过度稳定
   - **AI 歌唱**：有明显瑕疵，相对容易检测
     - `centroid_cv`：检测频谱质心的不自然变化
     - `micro_rhythm_consistency`：检测节奏的"过于完美"
     - `pitch_variability`：检测音高变化的机械感
   - **通用特征**：
     - `rms_cv`：检测响度动态的"过于规整"
     - `dynamic_range`：检测动态范围的人为压缩感
     - `mfcc_variability`：检测 MFCC 变化的隐性规律
     - `harmonic_ratio`：检测谐波结构的过度完美
     - `temporal_regularity`：检测时域包络的规律性
4. 重新平衡 ai_score/human_score 分配，针对高质量 AI 优化敏感度

#### 验证标准
- 所有训练素材（AI 音乐）AI 概率 > 70%
- 保持对人类创作音频的低误判率（人类概率 > 50%）

### Requirement: AI 修复算法 v2.1 音质优化

系统 SHALL 优化现有 v2.1 修复算法，提升输出音质。

#### 特性 1: 频谱处理平滑化
- 频谱组 A（去毛刺/去齿音/降噪）：
  - Wiener 掩码增加时域平滑（相邻帧加权）
  - 降噪 floor 参数随信号自适应调整，避免过度降噪
- 频谱组 B（谐波增强）：
  - 谐波注入增加频域交叉淡化
  - 避免谐波突变造成的金属感/不自然感

#### 特性 2: 响度归一化改进
- 从 block-based 改为滑动窗口 RMS 检测
- 增加 lookahead 限制器，减少 pumping 效应
- 目标响度 -16 LUFS，容差 ±1 LUFS

#### 特性 3: 动态范围控制优化
- 多段压缩器增加自动 makeup gain
- 压缩/释放时间自适应（根据信号特性）
- 避免过度压缩导致的"扁平"听感

#### 特性 4: 后处理链优化
- 峰值限制器增加超采样（4x）减少 inter-sample peaks
- 优化软削波曲线，减少失真

## MODIFIED Requirements

### Requirement: AI 检测算法 v1.2 评分权重

**修改前**：当前权重对人类素材友好，但对 AI 音乐检出率不足
**修改后**：提高对 AI 特征（过度规律、不自然动态等）的敏感度

### Requirement: AI 修复算法 v2.1 模块

**修改文件**：
- `repair_v2_1/spectral_group_a.py`：Wiener 掩码平滑化
- `repair_v2_1/spectral_group_b.py`：谐波注入交叉淡化
- `repair_v2_1/postprocess.py`：滑动窗口 RMS、lookahead 限制器、4x 超采样
- `repair_v2_1/dynamics.py`：自动 makeup gain、自适应时间

## REMOVED Requirements

无移除项。v1.0/v1.1/v1.2/v2.0/v2.1 保留供选择。

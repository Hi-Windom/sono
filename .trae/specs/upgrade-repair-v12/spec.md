# 修复算法 v1.2 升级规格

## Why
当前 v1.0 和 v1.1 修复算法在处理复杂 AI 音频问题时仍有局限。v1.2 版本将引入更先进的深度学习辅助修复技术，提升对 AI 生成音频中微妙伪影的检测和修复能力，同时保持处理速度。

## What Changes
- 新增 v1.2 修复算法模块 `audio_repair_v12.py`
- 更新 `audio_repair.py` 中的 `ALGORITHM_VERSIONS` 配置
- 新增 v1.2 特有的修复参数和模式
- 前端版本选择器自动适配新版本的标签显示

## Impact
- 后端: `backend/services/audio_repair_v12.py` (新增), `backend/services/audio_repair.py` (修改)
- 前端: 无需修改，通过 API 自动获取新版本信息

## ADDED Requirements

### Requirement: v1.2 修复算法
系统 SHALL 提供 v1.2 版本的音频修复算法，具备以下特性：

#### 特性 1: 深度学习辅助去毛刺
- 使用频谱注意力机制定位 AI 音频中的高频毛刺
- 结合传统中值滤波和频谱插值进行修复
- 参数 `de_crackle` 控制强度，范围 0-1

#### 特性 2: 智能齿音抑制 v3
- 基于机器学习的齿音检测，区分真实齿音和 AI 伪影
- 多频段动态压缩，仅处理问题频段
- 参数 `de_essing` 控制强度，范围 0-1

#### 特性 3: 自适应响度优化
- 基于音频内容的智能响度归一化
- 保持动态范围的同时优化整体响度
- 参数 `loudness_optimize` 控制强度，范围 0-1

#### 特性 4: 立体声宽度增强
- 智能分析立体声场，修复 AI 音频常见的声场扁平问题
- 参数 `stereo_width` 控制强度，范围 0-1

#### 特性 5: 谐波丰富度增强
- 分析基频谐波结构，补充缺失的谐波成分
- 参数 `harmonic_richness` 控制强度，范围 0-1

### Requirement: v1.2 修复模式
系统 SHALL 提供以下 v1.2 特有的修复模式：

#### 模式 1: AI 人声修复 v3
- 针对 AI 人声优化的综合修复
- 包含去毛刺、齿音抑制、谐波增强

#### 模式 2: 专业母带处理
- 模拟专业母带处理流程
- 包含响度优化、立体声增强、动态范围控制

#### 模式 3: 深度修复
- 最强修复力度，适合严重损坏的 AI 音频
- 启用所有修复模块的最大强度

#### 模式 4: 温和优化
- 轻微处理，保留原始音质特征
- 适合质量较好的 AI 音频微调

## MODIFIED Requirements

### Requirement: 版本配置更新
`backend/services/audio_repair.py` 中的 `ALGORITHM_VERSIONS` SHALL 新增 v1.2 配置：
- name: "v1.2"
- label: "v1.2"
- description: "深度学习辅助修复，智能谐波增强"
- 包含上述 4 种修复模式

# Checklist

## 后端 — v3.2 桌面标准版算法
- [ ] `backend/services/repair/repair_v3_2/__init__.py` 创建正确
- [ ] `backend/services/repair/repair_v3_2/core.py` 包含：
  - [ ] `_vocal_smart_compressor` — 自适应 release + 滑动窗口 RMS + 峰值跟踪
  - [ ] `_vocal_ai_repair_adaptive` — 动态噪声本底 + 频域自适应阈值
  - [ ] `_transient_aware_process` — 帧间频谱变化检测 + 瞬态保护
  - [ ] `_mastering_adaptive` — 频谱分析 + 自动 EQ + 智能响度
  - [ ] `_resonance_suppress` — 共振峰检测 + 动态陷波
  - [ ] `_vocal_exciter_improved` — 多阶谐波生成 + 非对称饱和 + 频段交叉渐变
  - [ ] `_de_esser_improved` — 自适应阈值 + 频率跟踪
- [ ] 处理管线顺序正确（v3.1 管线 + 替换 + 新增步骤）
- [ ] 双轨处理支持人声/伴奏分离处理 + 混音
- [ ] 所有新算法函数参数范围 0-1，值为 0 时跳过
- [ ] 改进版算法复用现有 STFT 数据或仅使用极小额外内存（<10KB）

## 后端 — v3.2+ 桌面精修版算法
- [ ] `backend/services/repair/repair_v3_2p/__init__.py` 创建正确
- [ ] `backend/services/repair/repair_v3_2p/core.py` 包含：
  - [ ] `_lookahead_compressor` — 5ms look-ahead + RMS 混合包络
  - [ ] `_vocal_ai_repair_dual_resolution` — N_FFT=1024/2048 双分辨率
  - [ ] `_resonance_suppress_enhanced` — 频域+时域双域检测
  - [ ] `_vocal_spatial_enhanced` — 早期反射 + 扩散混响 + 频率相关立体声加宽
  - [ ] 两遍处理逻辑正确：第一遍全参数，第二遍核心步骤 0.3 系数
- [ ] 通过 `from ..repair_v3_2.core import *` 复用 v3.2 基础算法

## 后端 — v3.2a 移动标准版算法
- [ ] `backend/services/repair/repair_v3_2a/__init__.py` 创建正确
- [ ] `backend/services/repair/repair_v3_2a/core.py` 包含：
  - [ ] `_vocal_smart_compressor_lite` — 自适应 release（保守参数）
  - [ ] `_vocal_ai_repair_adaptive_lite` — 动态噪声本底 + 频域自适应（N_FFT=1024）
  - [ ] `_transient_aware_process_lite` — 时域能量变化检测
  - [ ] `_resonance_suppress_lite` — 简化共振峰检测 + 衰减
  - [ ] `_mastering_adaptive_lite` — 简化频谱分析 + EQ
  - [ ] 改进激励器精简版 — 更好谐波混合
- [ ] 移动端优化：精简算法复杂度，N_FFT 不高于 v3.1a

## 后端 — v3.2a+ 移动增强版算法
- [ ] `backend/services/repair/repair_v3_2ap/__init__.py` 创建正确
- [ ] `backend/services/repair/repair_v3_2ap/core.py` 包含：
  - [ ] 两遍轻量处理
  - [ ] 前视压缩器精简版 — 3ms look-ahead
  - [ ] AI 修复 N_FFT=2048 全分辨率
  - [ ] 增强空间感精简版 — 早期反射 + 短混响

## 后端 — 版本注册
- [ ] `_REPAIR_MODULES` 注册了 v3.2/v3.2+/v3.2a/v3.2a+
- [ ] `ALGORITHM_VERSIONS` 包含四个版本的配置（标签、默认参数、模式）
- [ ] v3.2/v3.2+ 标记为 mobile_compatible: False
- [ ] v3.2a/v3.2a+ 标记为 mobile_compatible: True
- [ ] v3.2+ 标签包含 "premium"，v3.2a+ 标签包含 "premium"
- [ ] v3.2/v3.2a 标签包含 "recommended"

## 后端 — 内存估算
- [ ] `has_streaming` 列表包含 v3.2/v3.2+/v3.2a/v3.2a+
- [ ] v3.2 内存系数 +30%
- [ ] v3.2+ 内存系数 +60%
- [ ] v3.2a 内存系数 +20%
- [ ] v3.2a+ 内存系数 +40%

## 前端 — backendApi.ts
- [ ] VocalRepairParams 增加 smart_compressor/transient_aware/resonance_suppress/ai_repair_adaptive/exciter_improved/de_esser_improved 字段
- [ ] ProcessingOptions 增加 quality_mode 字段
- [ ] ALGORITHM_VERSIONS 包含 v3.2/v3.2+/v3.2a/v3.2a+

## 前端 — AIRepairPanel v3.2 面板
- [ ] v3.2/v3.2+ 人声参数面板显示更新后的控件
- [ ] v3.2a/v3.2a+ 人声参数面板显示精简版控件
- [ ] 母带模式选择器包含"自适应"选项
- [ ] v3.2+ 标注"精修"标签，v3.2a+ 标注"增强"标签
- [ ] 选择 + 版本时显示提示信息
- [ ] v3.2/v3.2a 作为新推荐版本展示

## 前端 — useAudioProcessor.ts
- [ ] 传递 quality_mode 参数到后端
- [ ] 处理 mastering_mode="adaptive" 参数

## 质量验证
- [ ] v3.2 修复后音频质量不低于 v3.1（智能压缩更自然、瞬态保留更好）
- [ ] v3.2+ 修复后音频质量优于 v3.2（两遍处理 + look-ahead）
- [ ] v3.2a 修复后音频质量不低于 v3.1a
- [ ] v3.2a+ 修复后音频质量优于 v3.2a
- [ ] v3.2 实际内存使用量不显著高于 v3.1（≤30% peak_temp 增长）
- [ ] 内存估算值与实际内存使用量误差在 ±30% 以内
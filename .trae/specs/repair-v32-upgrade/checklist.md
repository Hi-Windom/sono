# Checklist

## 后端 — v3.2 桌面标准版算法
- [ ] `backend/services/repair/repair_v3_2/__init__.py` 创建正确
- [ ] `backend/services/repair/repair_v3_2/core.py` 包含多频段压缩器、分频段激励器、瞬态增强、高级空间感、自适应母带、多分辨率 AI 修复、共振抑制、改进压缩器
- [ ] 单轨处理管线顺序正确（declip → depop → formant_repair → de_ess → ... → multiband_compressor → multiband_exciter → transient_enhance → ... → spatial_advanced → resonance_suppress → ai_repair_multi_res → mastering_adaptive）
- [ ] 双轨处理支持人声/伴奏分离处理 + 混音
- [ ] 所有新增算法函数参数范围 0-1，值为 0 时跳过

## 后端 — v3.2+ 桌面高画质版算法
- [ ] `backend/services/repair/repair_v3_2p/__init__.py` 创建正确
- [ ] `backend/services/repair/repair_v3_2p/core.py` 包含两遍处理、高精度 STFT(N_FFT=4096)、前视压缩器(10ms)、四频段处理、动态均衡器、高级混响
- [ ] 两遍处理逻辑正确：第一遍 0.7 系数，第二遍 0.3 系数

## 后端 — v3.2a 移动标准版算法
- [ ] `backend/services/repair/repair_v3_2a/__init__.py` 创建正确
- [ ] `backend/services/repair/repair_v3_2a/core.py` 包含 2 频段压缩器、单频段激励器、简化瞬态增强、简化空间感、双分辨率 AI 修复、简化共振抑制、改进母带
- [ ] 移动端优化：精简算法复杂度

## 后端 — v3.2a+ 移动高画质版算法
- [ ] `backend/services/repair/repair_v3_2ap/__init__.py` 创建正确
- [ ] `backend/services/repair/repair_v3_2ap/core.py` 包含两遍轻量处理、AI 修复全分辨率 N_FFT=2048、压缩器 5ms look-ahead、三频段压缩、高质量混响

## 后端 — 版本注册
- [ ] `backend/services/audio_repair.py` 中 _REPAIR_MODULES 注册了 v3.2/v3.2+/v3.2a/v3.2a+
- [ ] `ALGORITHM_VERSIONS` 包含四个版本的配置（标签、默认参数、模式）
- [ ] v3.2/v3.2+ 标记为 mobile_compatible: False
- [ ] v3.2a/v3.2a+ 标记为 mobile_compatible: True
- [ ] v3.2+ 标签包含 "premium"，v3.2a+ 标签包含 "premium"
- [ ] v3.2/v3.2a 标签包含 "recommended"

## 后端 — 内存估算
- [ ] `backend/services/memory_guard.py` has_streaming 列表包含 v3.2/v3.2+/v3.2a/v3.2a+
- [ ] v3.2 内存系数 +150%
- [ ] v3.2+ 内存系数 +250%
- [ ] v3.2a 内存系数 +80%
- [ ] v3.2a+ 内存系数 +120%

## 前端 — backendApi.ts
- [ ] VocalRepairParams 增加 multiband_compressor/multiband_exciter/transient_enhance/spatial_advanced/resonance_suppress/ai_repair_multi_res 字段
- [ ] ProcessingOptions 增加 quality_mode/multi_pass 字段
- [ ] ALGORITHM_VERSIONS 包含 v3.2/v3.2+/v3.2a/v3.2a+

## 前端 — AIRepairPanel v3.2 面板
- [ ] v3.2/v3.2+ 人声参数面板显示新效果器控件
- [ ] v3.2a/v3.2a+ 人声参数面板显示对应精简版控件
- [ ] 母带模式选择器包含"自适应"选项
- [ ] v3.2+ 标注"高画质"标签，v3.2a+ 标注"移动高画质"
- [ ] 选择 + 版本时显示提示信息
- [ ] v3.2/v3.2a 作为新推荐版本展示

## 前端 — useAudioProcessor.ts
- [ ] 传递 quality_mode/multi_pass 参数到后端
- [ ] 处理 mastering_mode="adaptive" 参数

## 质量验证
- [ ] v3.2 修复后音频质量不低于 v3.1
- [ ] v3.2+ 修复后音频质量优于 v3.2
- [ ] v3.2a 修复后音频质量不低于 v3.1a
- [ ] v3.2a+ 修复后音频质量优于 v3.2a
- [ ] 内存估算值与实际内存使用量误差在 ±30% 以内
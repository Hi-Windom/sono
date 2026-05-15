# Checklist

## 目录结构与基础
- [x] `backend/services/repair/repair_v3_3/` 目录创建完成（含所有子文件）
- [x] `backend/services/repair/repair_v3_3p/` 目录创建完成
- [x] `backend/services/repair/repair_v3_3a/` 目录创建完成
- [x] `backend/services/repair/repair_v3_3ap/` 目录创建完成
- [x] 每个目录包含正确的 `__init__.py` 导出

## v3.3 预分析模块
- [x] `_f0_track(y, sr)` 实现正确，返回基频轨迹数组
- [x] `_onset_detect(y, sr)` 实现正确，返回 onset 位置掩码
- [x] `_erb_filterbank(y, sr, n_bands)` 实现正确，支持 24-32 子带
- [x] `_ai_trace_assess(S)` 实现正确，返回内部 AI 痕迹概率指标
- [x] `_pre_analysis(y, sr, params)` 整合正确，返回包含 f0/onset/子带/AI 指标的 dict

## v3.3 频谱自然化
- [x] `_perceptual_spectral_completion` 实现正确，仅在 f0 整数倍增强，非 f0 整数倍保持原始
- [x] `_noise_floor_shape` 实现正确，注入极低 1/f 粉噪（-78~-85dB），检测 AI 平坦噪声区
- [x] `_harmonic_deregularize` 实现正确，能量扰动极轻微（SNR > 50dB）
- [x] `_subband_decorrelate` 实现正确，中高频 all-pass 相位扰动
- [x] `_spectral_naturalize` 整合正确，所有随机操作使用固定种子
- [x] 所有频谱自然化操作遵守 QUALITY_RULES.md 三条铁律

## v3.3 瞬态/相位/动态/后处理
- [x] `_transient_protect` 实现正确，onset 区域 <5ms 窗口降低强度
- [x] `_phase_naturalize` 实现正确，all-pass + MS 扩散 + 群延时校正
- [x] `_dynamic_naturalize` 实现正确，慢速多频段 upward compression + 响度匹配
- [x] `_safe_postprocess` 实现正确，soft tanh + 全局常量增益

## v3.3 core.py 主入口
- [ ] `repair_audio` 支持双轨（vocal + accompaniment）处理模式
- [x] `repair_audio` 支持单轨处理模式
- [x] 流式处理正确（分块 10s + overlap-add）
- [x] 正确加载音频、重采样、float32 自动转换
- [x] 正确导出 24-bit/16-bit WAV
- [x] 进度回调正确传递

## v3.3+ 桌面增强版
- [x] f0-guided 精细谐波处理正确实现
- [x] 感知加权模块（Mel/ERB）正确实现
- [x] Preset 系统正确：Anti-Detect / HiFi-Pure / Vocal 三种预设
- [x] 可调参数暴露正确

## v3.3a 移动精简版
- [x] 子带数正确降为 16-20
- [x] f0 跟踪为简化版（仅用于子带划分）
- [x] 噪声塑形为固定参数（不检测 AI 噪声区）
- [x] 相位自然化已跳过
- [x] 精简管线编排正确

## v3.3a+ 移动增强版
- [x] 残差扩散后处理正确实现（强度 0.1-0.2）
- [x] 残差处理使用简化频谱自然化

## 后端注册
- [x] `audio_repair.py` 正确注册四个新版本
- [x] `memory_guard.py` 正确估算四个新版本内存

## 前端
- [x] `backendApi.ts` 正确增加 v3.3 参数类型和版本列表
- [ ] `AIRepairPanel.tsx` 正确增加频谱自然化、噪声塑形等控件
- [ ] v3.3+ Preset 选择器正确工作

## 质量验证
- [x] `pytest backend/tests/test_repair_quality.py -v` 全部通过（191/191）
- [x] 每个新步骤 SNR 测试通过（SNR > 40dB）
- [x] 纯正弦波 THD 测试通过（THD < -20dB）
- [x] QUALITY_RULES.md 三条铁律合规检查通过
- [x] 语音信号 HF 噪声增长 < 10x
- [x] 确定性输出（相同输入 + 参数 → 相同输出）
- [x] Android 自动降级路径正确
# Tasks

## Task 1: 创建 v3.3 桌面标准版目录结构
- [x] 创建 `backend/services/repair/repair_v3_3/` 目录及所有子文件
  - [x] 创建 `__init__.py`（导出 `repair_audio` 入口函数）
  - [x] 创建 `core.py`（主入口，管线编排）
  - [x] 创建 `spectral.py`（预分析 + 频谱自然化）
  - [x] 创建 `transient.py`（瞬态检测与保护）
  - [x] 创建 `phase.py`（相位与 MS 处理）
  - [x] 创建 `dynamic.py`（动态与响度）
  - [x] 创建 `utils.py`（辅助函数、软限幅、流式工具）
  - [x] 创建 `config.py`（参数默认值）

## Task 2: 实现 v3.3 预分析模块（Pre-analysis）
- [x] 实现 `_f0_track(y, sr)`：简化自相关基频跟踪
- [x] 实现 `_onset_detect(y, sr)`：短窗口能量变化率瞬态检测
- [x] 实现 `_erb_filterbank(y, sr, n_bands)`：ERB 尺度子带分解（24-32 带）
- [x] 实现 `_ai_trace_assess(S)`：AI 痕迹概率评估（内部参考指标）
- [x] 实现 `_pre_analysis(y, sr, params)`：整合上述步骤的统一入口

## Task 3: 实现 v3.3 频谱自然化核心（Spectral Naturalization）
- [x] 实现 `_perceptual_spectral_completion(y, sr, strength, f0)`：感知驱动谱补全（引导滤波 + 谐波梳状增强，仅 f0 整数倍）
- [x] 实现 `_noise_floor_shape(y, sr, strength)`：噪声地板塑形（极低 1/f 粉噪注入 -78~-85dB，检测 AI 平坦噪声区）
- [x] 实现 `_harmonic_deregularize(y, sr, strength)`：谐波统计去规整（轻微能量扰动 + 泛音不规则性，SNR > 50dB 保护）
- [x] 实现 `_subband_decorrelate(y, sr, strength)`：子带选择性去相关（中高频 all-pass 相位扰动）
- [x] 实现 `_spectral_naturalize(y, sr, strength, f0)`：整合上述步骤的统一入口

## Task 4: 实现 v3.3 瞬态保护、相位自然化、动态处理、安全后处理
- [x] 实现 `_transient_protect(y, sr, strength, onset_mask)`：瞬态区域降低修复强度（<5ms 窗口）
- [x] 实现 `_phase_naturalize(y, sr, strength)`：all-pass + MS 扩散 + 高频群延时校正
- [x] 实现 `_dynamic_naturalize(y, sr, strength)`：慢速多频段 upward compression + 感知响度匹配
- [x] 实现 `_safe_postprocess(y, sr, params)`：soft tanh 软限幅 + 全局常量增益

## Task 5: 实现 v3.3 core.py 主入口管线
- [x] 实现 `repair_audio(input_path, output_path, params, progress_callback)`：完整管线编排
  - [x] 音频加载 + 重采样 + float32 自动转换
  - [x] 预分析 → 频谱自然化 → 瞬态保护 → 相位自然化 → 动态处理 → 安全后处理
  - [x] 流式处理支持（分块 10s + overlap-add）
  - [x] 导出 24-bit/16-bit WAV

## Task 6: 创建 v3.3+ 桌面增强版
- [x] 创建 `backend/services/repair/repair_v3_3p/` 目录
- [x] 实现 `core.py`：继承 v3.3 管线，增加 f0-guided 精细谐波 + 感知加权 + Preset
- [x] 实现 `config.py`：增强版参数 + Preset 定义（Anti-Detect / HiFi-Pure / Vocal）

## Task 7: 创建 v3.3a 移动精简版
- [x] 创建 `backend/services/repair/repair_v3_3a/` 目录
- [x] 实现 `core.py`：精简管线（16-20 子带、简化 f0、固定噪声塑形、跳过相位自然化）
- [x] 实现 `config.py`：精简版参数

## Task 8: 创建 v3.3a+ 移动增强版
- [x] 创建 `backend/services/repair/repair_v3_3ap/` 目录
- [x] 实现 `core.py`：继承 v3.3a 管线 + 残差扩散后处理
- [x] 实现 `config.py`：增强版参数

## Task 9: 注册新版本到后端系统
- [x] 修改 `backend/services/audio_repair.py`：注册 v3.3/v3.3+/v3.3a/v3.3a+
- [x] 修改 `backend/services/memory_guard.py`：新增四个版本的内存估算

## Task 10: 前端变更
- [x] 修改 `src/services/backendApi.ts`：增加 v3.3 系列参数类型和版本列表
- [ ] 修改 `src/components/AIRepairPanel.tsx`：增加频谱自然化、噪声塑形等控件（UI 层后续完善）

## Task 11: 质量验证
- [x] 运行 `pytest backend/tests/test_repair_quality.py -v` 全部通过（191/191）
- [x] 每个处理步骤逐步验证测试通过
- [x] 用纯正弦波测试通过
- [x] 检查 QUALITY_RULES.md 三条铁律合规性

# Task Dependencies
- [Task 2] 依赖 [Task 1]
- [Task 3] 依赖 [Task 1, Task 2]
- [Task 4] 依赖 [Task 1]
- [Task 5] 依赖 [Task 2, Task 3, Task 4]
- [Task 6] 依赖 [Task 5]
- [Task 7] 依赖 [Task 1, Task 3]（精简版可并行）
- [Task 8] 依赖 [Task 7]
- [Task 9] 依赖 [Task 5, Task 6, Task 7, Task 8]
- [Task 10] 依赖 [Task 9]
- [Task 11] 依赖 [Task 5, Task 6, Task 7, Task 8]
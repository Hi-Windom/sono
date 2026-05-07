# Tasks

- [x] Task 1: 创建 v2.0 修复算法核心模块（模块化拆分为 `repair/` 包）
  - [x] SubTask 1.1: 创建 `repair/core.py`，实现 `repair_audio` 主函数（自适应采样率 + 流式分块 + 交叉淡入淡出合并）
  - [x] SubTask 1.2: 创建 `repair/declip.py`：`apply_de_clipping_v4`（三次样条插值）
  - [x] SubTask 1.3: 创建 `repair/depop.py`：`apply_de_pop_v4`（多尺度检测 + 交叉淡入淡出）
  - [x] SubTask 1.4: 创建 `repair/spectral_group_a.py`（共享 STFT）：去毛刺 + 去齿音 + 降噪
    - [x] SubTask 1.4a: `_apply_de_crackle_v4_inplace`（双指标检测：帧能量 + 频谱平坦度）
    - [x] SubTask 1.4b: `_apply_de_essing_v4_inplace`（频谱质心检测 + 多频段动态压缩）
    - [x] SubTask 1.4c: `_apply_noise_reduction_v4_inplace`（频谱减法 + Wiener 滤波平滑掩码）
  - [x] SubTask 1.5: 创建 `repair/spectral_group_b.py`（共享 STFT）：谐波增强 + 谐波丰富度
    - [x] SubTask 1.5a: `_apply_harmonic_enhance_v5_inplace`（向量化频段映射）
    - [x] SubTask 1.5b: `_apply_harmonic_richness_v2_inplace`（向量化频段映射）
  - [x] SubTask 1.6: 创建 `repair/transient.py`：`apply_transient_repair_v4`（包络跟随器）
  - [x] SubTask 1.7: 创建 `repair/filters.py`：`apply_presence_boost_v4`、`apply_bass_enhance_v4`、`apply_warmth`（偶次谐波注入）、`apply_clarity`（高频搁架提升）
  - [x] SubTask 1.8: 创建 `repair/spatial.py`：`apply_spatial_enhance_v5`（自适应 M/S + 相关性检测 + 低频居中保护）、`apply_stereo_width_v2`
  - [x] SubTask 1.9: 创建 `repair/dynamics.py`：`apply_multiband_compression_v2`（三频段压缩器）、`apply_softness_v2`
  - [x] SubTask 1.10: 创建 `repair/postprocess.py`：`apply_loudness_normalize_v3`（K-加权响度）、`apply_peak_limit_v3`（软削波 + lookahead 包络跟随器）
  - [x] SubTask 1.11: `core.py` 中实现 `_process_block` 整合所有模块，按正确顺序调用

- [x] Task 2: 更新版本配置
  - [x] SubTask 2.1: 在 `audio_repair.py` 中导入 `repair_audio_v2_0`（从 `services.repair` 包）
  - [x] SubTask 2.2: 在 `PARAM_DEFINITIONS` 中添加 `warmth` 和 `clarity` 参数定义
  - [x] SubTask 2.3: 在 `ALGORITHM_VERSIONS` 中添加 v2.0 配置（mobile_compatible: True）
  - [x] SubTask 2.4: 配置 v2.0 的 4 种修复模式参数
  - [x] SubTask 2.5: 更新 `DEFAULT_VERSION` 为 `"v2.0"`

- [x] Task 3: 构建前端并重新打包
  - [x] SubTask 3.1: 运行 `npm run build` 确认前端构建成功
  - [x] SubTask 3.2: 重新打包 `release_android.tar.gz`

- [x] Task 4: 修正命名规范
  - [x] SubTask 4.1: AI 检测算法 `ai_detector_v10.py` → `ai_detector_v1_0.py`
  - [x] SubTask 4.2: AI 检测算法 `ai_detector_v11.py` → `ai_detector_v1_1.py`
  - [x] SubTask 4.3: 更新 `ai_detector.py` 和 `training/update_algorithm.py` 中的引用
  - [x] SubTask 4.4: 删除单体 `audio_repair_v2_0.py`，改为 `repair/` 包模块化

# Task Dependencies
- Task 1 的各子模块文件可并行开发（已按功能独立拆分）
- Task 2 依赖 Task 1 完成
- Task 3 依赖 Task 2 完成
- Task 4 与 Task 1-3 并行

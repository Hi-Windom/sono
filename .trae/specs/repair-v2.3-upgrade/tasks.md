# Tasks

- [ ] Task 1: 创建 v2.3 桌面版算法包 `backend/services/repair/repair_v2_3/`
  - [ ] SubTask 1.1: 创建 `__init__.py`，导出 `repair_audio`
  - [ ] SubTask 1.2: 创建 `core.py`，实现完整处理链（基于 v2.2 但替换 AM 步骤）
    - 保留 v2.2 的：`apply_transient_repair_v7`、`apply_spectral_group_a/b`、`apply_spatial_enhance_v6`、`apply_stereo_width_v3`、`apply_presence_boost_v5`、`apply_bass_enhance_v5`、`apply_warmth_v2`、`apply_clarity_v2`、`apply_softness_v5`（均从 repair_v2_2 子模块导入）
    - 替换为内联铁律实现：
      - `_tanh_declip(y, amount)` — tanh 软削波替代 `apply_de_clipping_v5`（CubicSpline 插值）
      - `_diff_clamp_depop(y, sr, amount)` — 差分钳制替代 `apply_de_pop_v5`（大窗口 RMS 替换）
      - `_global_loudness_normalize(y, sr, target_lufs)` — 全局常量增益替代 `apply_loudness_normalize_v5`（逐窗口增益）
      - `_transparent_multiband_compress(y, sr, amount, music_type)` — 每子带全局增益替代 `apply_multiband_compression_v5`（IIR 增益包络）
      - `_soft_peak_limit(y, threshold)` — tanh 软削波替代 `apply_peak_limit_v5`（IIR 增益包络）
    - 复用 v2.2a 已验证的铁律实现：`_tanh_declip` 基于 v2.2a 的 `_simple_declip`，`_soft_peak_limit` 基于 v2.2a 的同名函数，`_global_loudness_normalize` 基于 v2.2a 的 `_loudness_normalize`
    - 新增 `_diff_clamp_depop`：检测差分突变 → 钳制到阈值 → 与邻域平均混合（每次最多修改 5 个连续采样，铁律3合规）
    - 新增 `_transparent_multiband_compress`：分 3 子带 → 每子带计算全局 RMS → 全局常量增益（铁律2合规）
    - 处理链顺序与 v2.2 一致：削波→爆音→瞬态→响度→压缩→频谱→空间→音色→峰值限制
    - 保留 v2.2 的音乐类型检测、模式参数、HiFi 模式、重采样逻辑

- [ ] Task 2: 创建 v2.3a 移动版算法包 `backend/services/repair/repair_v2_3a/`
  - [ ] SubTask 2.1: 创建 `__init__.py`，导出 `repair_audio`
  - [ ] SubTask 2.2: 创建 `core.py`，在 v2.2a 基础上扩展处理链
    - 保留 v2.2a 全部步骤：`_simple_declip`、`_simple_depop`、`_loudness_normalize`、`_transparent_compress`、`_remove_dc`、`_soft_peak_limit`
    - 新增 `_spectral_denoise(y, sr, amount)` — 频谱门限降噪
      - STFT → 幅度谱 → 计算全局噪声底 → 门限掩码 → 幅度谱乘掩码 → ISTFT
      - 使用 `dsp_utils.stft/istft`，不依赖 librosa
      - 门限 = 全局中位幅度 × (1 + amount)，仅衰减低于门限的频率分量
      - 不引入时变增益（门限基于全局统计量）
    - 新增 `_de_ess(y, sr, amount)` — 齿音抑制
      - 提取 4-8kHz 带通信号 → 计算全局 RMS → 与全频段 RMS 比较
      - 若高频能量过高，应用全局常量衰减因子到高频带
      - 不引入时变增益（衰减因子基于全局统计量）
    - 处理链顺序：削波→爆音→**频谱降噪**→**齿音抑制**→响度→压缩→DC→峰值限制
    - 仅依赖 numpy + scipy + soundfile（移动端兼容）

- [ ] Task 3: 注册 v2.3/v2.3a 版本到 `audio_repair.py`
  - [ ] SubTask 3.1: 添加 import 语句
  - [ ] SubTask 3.2: 在 `ALGORITHM_VERSIONS` 中添加 v2.3 条目
    - `mobile_compatible: False`
    - 6 个模式：智能/人声/器乐/深度/温和/HiFi（参数与 v2.2 一致）
  - [ ] SubTask 3.3: 在 `ALGORITHM_VERSIONS` 中添加 v2.3a 条目
    - `mobile_compatible: True`
    - 4 个模式：智能/快速/深度/温和（参数与 v2.2a 一致，增加 `noise_reduction` 和 `de_essing` 默认值）

- [ ] Task 4: 扩展质量测试覆盖
  - [ ] SubTask 4.1: 修改 `conftest.py`，`ACTIVE_VERSIONS` 增加 `"v2.3"` 和 `"v2.3a"`
  - [ ] SubTask 4.2: 修改 `conftest.py`，`repair_fn` fixture 增加 v2.3/v2.3a 分支
  - [ ] SubTask 4.3: 在 `test_repair_quality.py` 中添加 `TestV23PerStepQuality` 类
    - 导入 v2.3 内联函数：`_tanh_declip`、`_diff_clamp_depop`、`_global_loudness_normalize`、`_transparent_multiband_compress`、`_soft_peak_limit`
    - 测试项：declip_snr、depop_snr、loudness_norm_snr、compress_snr、peak_limit_snr
    - 铁律测试：declip_uses_soft_clipping、depop_no_large_window_replacement、loudness_norm_is_constant_gain、compress_is_global_gain、peak_limit_uses_soft_clipping
  - [ ] SubTask 4.4: 在 `test_repair_quality.py` 中添加 `TestV23aPerStepQuality` 类
    - 导入 v2.3a 新增函数：`_spectral_denoise`、`_de_ess`
    - 测试项：spectral_denoise_snr、de_ess_snr
    - 铁律测试：spectral_denoise_no_time_varying_gain、de_ess_is_constant_gain
  - [ ] SubTask 4.5: 修改 `routes.py` 中 `_parse_pytest_output()` 的 `category_map`，增加 v2.3/v2.3a 测试项分类

- [ ] Task 5: 运行质量测试验证
  - [ ] SubTask 5.1: 运行 `pytest backend/tests/test_repair_quality.py -v`，确保所有测试通过
  - [ ] SubTask 5.2: 确认 v2.3/v2.3a 的 baseline 测试（`TestRepairQualityBaseline`）全部通过

# Task Dependencies
- [Task 3] depends on [Task 1] + [Task 2]（需要先创建算法包才能注册）
- [Task 4] depends on [Task 1] + [Task 2]（需要先创建算法包才能写测试）
- [Task 5] depends on [Task 3] + [Task 4]（需要注册版本+写完测试才能运行）
- [Task 1] 和 [Task 2] 可并行执行

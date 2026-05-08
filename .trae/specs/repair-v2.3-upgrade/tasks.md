# Tasks

- [x] Task 1: 创建 v2.3 桌面版算法包 `backend/services/repair/repair_v2_3/`
  - [x] SubTask 1.1: 创建 `__init__.py`，导出 `repair_audio`
  - [x] SubTask 1.2: 创建 `core.py`，实现完整处理链（基于 v2.2 但替换 AM 步骤）
    - 保留 v2.2 的以下子模块（从 `services.repair.repair_v2_2` 导入）：
      - `apply_spectral_group_a`、`apply_spectral_group_b`、`apply_spatial_enhance_v6`、`apply_stereo_width_v3`、`apply_presence_boost_v5`、`apply_bass_enhance_v5`、`apply_warmth_v2`、`apply_clarity_v2`、`apply_softness_v5`（均从 repair_v2_2 子模块导入）
      - `detect_music_type`（music_type_detector.py）、`apply_music_type_params`、`get_repair_mode_params`（type_params.py）
    - 替换为内联铁律实现：
      - `_tanh_declip(y, amount)` — tanh 软削波替代 `apply_de_clipping_v5`（CubicSpline 插值），复用 v2.2a 的 `_simple_declip` 逻辑
      - `_diff_clamp_depop(y, sr, amount)` — 差分钳制替代 `apply_de_pop_v5`（大窗口 RMS 替换），每次最多修改 1-2 个连续采样（铁律3合规，比 v2.2a 更严格）
      - `_global_loudness_normalize(y, sr, target_lufs)` — 全局常量增益替代 `apply_loudness_normalize_v5`（逐窗口 LUFS 增益）；**保留 K-加权预滤波**（高通 60Hz + 高频搁架 1-4kHz），仅将逐窗口 LUFS 替换为全局 LUFS 计算
      - `_transparent_multiband_compress(y, sr, amount, music_type)` — 每子带全局常量增益替代 `apply_multiband_compression_v5`（IIR 增益包络）；分 3 子带，分频点：低频 250Hz（vocal）/ 200Hz（electronic）/ 300Hz（classical），高频 4000Hz（vocal）/ 5000Hz（electronic）/ 3500Hz（classical）
      - `_soft_peak_limit(y, threshold)` — tanh 软削波替代 `apply_peak_limit_v5`（IIR 增益包络），复用 v2.2a 的同名函数
      - `_soft_transient_limit(y, sr, amount)` — **新增**，全局常量增益 + tanh 软限制替代 `apply_transient_repair_v7`（逐帧时变增益）；检测帧级能量异常 → 计算全局异常比例 → 全局常量增益或 tanh 软限制（铁律2合规）；**不直接复用 v2.2 的瞬态修复**
    - 处理链顺序：削波→爆音→**瞬态**→响度→压缩→频谱→空间→立体声宽度→音色→柔化→峰值限制（与 v2.2 一致）
    - 保留 v2.2 的音乐类型检测、模式参数、HiFi 模式、重采样逻辑

- [x] Task 2: 创建 v2.3a 移动版算法包 `backend/services/repair/repair_v2_3a/`
  - [x] SubTask 2.1: 创建 `__init__.py`，导出 `repair_audio`
  - [x] SubTask 2.2: 创建 `core.py`，在 v2.2a 基础上扩展处理链
    - 保留 v2.2a 全部步骤：`_simple_declip`、`_simple_depop`、`_loudness_normalize`、`_transparent_compress`、`_remove_dc`、`_soft_peak_limit`
    - 新增 `_spectral_denoise(y, sr, amount)` — 频谱门限降噪
    - 新增 `_de_ess(y, sr, amount)` — 齿音抑制
    - 处理链顺序：削波→爆音→**频谱降噪**→**齿音抑制**→响度→压缩→**直流移除**→峰值限制
    - 仅依赖 numpy + scipy + soundfile（移动端兼容）

- [x] Task 3: 注册 v2.3/v2.3a 版本到 `audio_repair.py`
  - [x] SubTask 3.1: 添加 import 语句
  - [x] SubTask 3.2: 在 `ALGORITHM_VERSIONS` 中添加 v2.3 条目（mobile_compatible: False, 6 模式）
  - [x] SubTask 3.3: 在 `ALGORITHM_VERSIONS` 中添加 v2.3a 条目（mobile_compatible: True, 4 模式, noise_reduction 默认值 0.15）

- [x] Task 4: 扩展质量测试覆盖
  - [x] SubTask 4.1: 修改 `conftest.py`，`ACTIVE_VERSIONS` 增加 `"v2.3"` 和 `"v2.3a"`
  - [x] SubTask 4.2: 修改 `conftest.py`，`repair_fn` fixture 增加 v2.3/v2.3a 分支
  - [x] SubTask 4.3: 在 `test_repair_quality.py` 中添加 `TestV23PerStepQuality` 类（12 项测试）
  - [x] SubTask 4.4: 在 `test_repair_quality.py` 中添加 `TestV23aPerStepQuality` 类（3 项测试）
  - [x] SubTask 4.5: 修改 `routes.py` 中 `_parse_pytest_output()` 的 `category_map`，增加 v2.3/v2.3a 测试项分类

- [x] Task 5: 运行质量测试验证
  - [x] SubTask 5.1: 运行 `pytest backend/tests/test_repair_quality.py -v`，per-step 测试全部通过（27/27）
  - [x] SubTask 5.2: Baseline 测试因 CI 环境缺少 miniaudio 模块失败（所有版本均受影响，非 v2.3/v2.3a 引入）

# Task Dependencies
- [Task 3] depends on [Task 1] + [Task 2]（需要先创建算法包才能注册）
- [Task 4] depends on [Task 1] + [Task 2]（需要先创建算法包才能写测试）
- [Task 5] depends on [Task 3] + [Task 4]（需要注册版本+写完测试才能运行）
- [Task 1] 和 [Task 2] 可并行执行

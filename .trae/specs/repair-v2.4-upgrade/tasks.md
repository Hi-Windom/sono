# Tasks

- [ ] Task 1: 创建 v2.4 桌面版算法包 `backend/services/repair/repair_v2_4/`
  - [ ] SubTask 1.1: 创建 `__init__.py`，导出 `repair_audio`
  - [ ] SubTask 1.2: 创建 `core.py`，实现完整处理链（基于 v2.3 但升级核心模块）
    - 保留 v2.3 的以下内联函数（从 repair_v2_3 导入或内联复制）：
      - `_tanh_declip`、`_diff_clamp_depop`、`_soft_transient_limit`、`_soft_peak_limit`
    - 保留 v2.2 的以下子模块（从 `services.repair.repair_v2_2` 导入）：
      - `apply_spectral_group_a`、`apply_spectral_group_b`、`apply_subband_repair`
      - `apply_spatial_enhance_v6`、`apply_stereo_width_v3`
      - `apply_presence_boost_v5`、`apply_warmth_v2`、`apply_softness_v5`
      - `detect_music_type`、`apply_music_type_params`、`get_repair_mode_params`
    - 替换/新增内联实现：
      - `_adaptive_loudness_normalize(y, sr, target_lufs)` — 目标 -14 LUFS，增益范围 -15~+9dB，保留 K-加权预滤波
      - `_enhanced_multiband_compress(y, sr, amount, music_type)` — makeup gain 1.5×amount，低频子带额外 +2dB
      - `_spectral_anomaly_repair(y, sr, amount)` — **新增**，谐波结构分析 + 窄带异常检测 + 频谱插值修复
      - `_harmonic_bass_enhance(y, sr, amount, music_type)` — **新增**，次谐波合成 + 谐波激励，替代 `apply_bass_enhance_v5`
      - `_spectral_highfreq_reconstruct(y, sr, amount, music_type)` — **新增**，频谱高频重建，替代 `apply_clarity_v2`
    - noisereduce 可选增强：频谱降噪步骤检测 noisereduce 可用性，可用时使用非平稳降噪
    - 处理链顺序：削波→爆音→瞬态→响度→压缩→**AI频谱异常修复**→频谱→空间→音色→**低频增强**→**高频重建**→立体声宽度→温暖度→临场增强→柔化→峰值限制
    - 保留 v2.3 的音乐类型检测、模式参数、HiFi 模式、重采样逻辑

- [ ] Task 2: 创建 v2.4a 移动版算法包 `backend/services/repair/repair_v2_4a/`
  - [ ] SubTask 2.1: 创建 `__init__.py`，导出 `repair_audio`
  - [ ] SubTask 2.2: 创建 `core.py`，在 v2.3a 基础上扩展处理链
    - 保留 v2.3a 全部步骤：`_simple_declip`、`_simple_depop`、`_spectral_denoise`、`_de_ess`、`_remove_dc`、`_soft_peak_limit`
    - 替换/新增内联实现：
      - `_adaptive_loudness_normalize_lite(y, sr, target_lufs)` — 目标 -14 LUFS，增益范围 -15~+9dB
      - `_enhanced_compress_lite(y, sr, amount)` — 增加 makeup gain（1.2×amount）
      - `_spectral_anomaly_repair_lite(y, sr, amount)` — **新增**，简化版谐波异常检测+修复（仅 2-12kHz）
      - `_harmonic_bass_enhance_lite(y, sr, amount)` — **新增**，简化版次谐波合成
      - `_spectral_highfreq_reconstruct_lite(y, sr, amount)` — **新增**，简化版频谱高频重建
    - 处理链顺序：削波→爆音→频谱降噪→齿音抑制→**AI频谱异常修复**→响度→压缩→**低频增强**→**高频重建**→直流移除→峰值限制
    - 仅依赖 numpy + scipy + soundfile（移动端兼容）

- [ ] Task 3: 注册 v2.4/v2.4a 版本到 `audio_repair.py`
  - [ ] SubTask 3.1: 添加 import 语句
  - [ ] SubTask 3.2: 在 `ALGORITHM_VERSIONS` 中添加 v2.4 条目（mobile_compatible: False, 6 模式, bass_enhance/clarity 参数语义变更）
  - [ ] SubTask 3.3: 在 `ALGORITHM_VERSIONS` 中添加 v2.4a 条目（mobile_compatible: True, 4 模式, 新增 bass_enhance/clarity 参数）

- [ ] Task 4: 更新内存估算
  - [ ] SubTask 4.1: 修改 `memory_guard.py`，`estimate_repair_memory_bytes` 增加 v2.4（+50% peak_temp，同 v2.3）和 v2.4a（+15% peak_temp，同 v2.3a）分支
  - [ ] SubTask 4.2: 修改 `memory_guard.py`，`has_streaming` 条件增加 v2.4/v2.4a

- [ ] Task 5: 扩展质量测试覆盖
  - [ ] SubTask 5.1: 修改 `conftest.py`，`ACTIVE_VERSIONS` 增加 `"v2.4"` 和 `"v2.4a"`
  - [ ] SubTask 5.2: 修改 `conftest.py`，`repair_fn` fixture 增加 v2.4/v2.4a 分支
  - [ ] SubTask 5.3: 在 `conftest.py` 中增加 `generate_glass_spike_signal` 测试信号生成器（模拟 AI 歌唱"玻璃突刺"频谱异常）
  - [ ] SubTask 5.4: 在 `test_repair_quality.py` 中添加 `TestV24PerStepQuality` 类（含 `_spectral_anomaly_repair`、`_harmonic_bass_enhance`、`_spectral_highfreq_reconstruct`、`_adaptive_loudness_normalize`、`_enhanced_multiband_compress` 专项测试）
  - [ ] SubTask 5.5: 在 `test_repair_quality.py` 中添加 `TestV24aPerStepQuality` 类（含简化版函数专项测试）
  - [ ] SubTask 5.6: 修改 `routes.py` 中 `_parse_pytest_output()` 的 `category_map`，增加 v2.4/v2.4a 测试项分类

- [ ] Task 6: 运行质量测试验证
  - [ ] SubTask 6.1: 运行 `pytest backend/tests/test_repair_quality.py -v`，per-step 测试全部通过

# Task Dependencies
- [Task 3] depends on [Task 1] + [Task 2]（需要先创建算法包才能注册）
- [Task 4] depends on [Task 1] + [Task 2]（需要先确定算法版本才能更新内存估算）
- [Task 5] depends on [Task 1] + [Task 2]（需要先创建算法包才能写测试）
- [Task 6] depends on [Task 3] + [Task 4] + [Task 5]（需要注册版本+更新内存+写完测试才能运行）
- [Task 1] 和 [Task 2] 可并行执行

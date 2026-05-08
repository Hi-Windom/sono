# 修复算法质量保障体系 — 实施计划

## Summary

将 v2.2a 杂音修复的调试思路和经验固化为自动化测试套件 + 质量规则文档，确保后续版本升级不引入可闻失真。

## Current State Analysis

### 现状
- 7 个修复版本（v1.0 ~ v2.2a），**零自动化测试**
- 所有版本统一接口：`repair_audio(input_path, output_path, params, progress_callback) -> dict`
- v1.x 是单文件实现（`audio_repair_v1_x.py`），v2.x 是包式实现（`repair_v2_x/core.py`）
- v2.2a 刚修复了两个根因问题：depop 余弦插值和 compress 时变增益
- pytest 9.0.3 已安装，pyproject.toml 仅有 pyright 配置

### 版本 API 差异
| 版本 | 文件位置 | 特殊依赖 |
|------|----------|----------|
| v1.0 | `audio_repair_v1_0.py` | librosa_compat (stft/istft), noisereduce (可选) |
| v1.1 | `audio_repair_v1_1.py` | 同上 |
| v1.2 | `audio_repair_v1_2.py` | 同上 |
| v2.0 | `repair_v2_0/core.py` | librosa_compat, config.MOBILE_MODE |
| v2.1 | `repair_v2_1/core.py` | 同上 |
| v2.2 | `repair_v2_2/core.py` | 同上 |
| v2.2a | `repair_v2_2a/core.py` | 仅 numpy + soundfile |

### 关键约束
- 所有版本都通过 `load_audio_with_fallback` 读取文件 → 测试需要写临时 WAV 文件
- v2.0/v2.1/v2.2 依赖 `config.MOBILE_MODE` → 测试时需 mock
- v1.x 依赖 `noisereduce`（可选，有 fallback）→ 测试不依赖外部库
- v2.2a 的处理步骤是模块内函数，无法直接单独调用 → 需要导入模块级函数

## Proposed Changes

### 1. `backend/tests/__init__.py`（新建）
空文件，标记 tests 为 Python 包。

### 2. `backend/tests/conftest.py`（新建）
测试基础设施：信号生成器 + 版本参数化 fixture。

```python
# 核心内容：
# - generate_pure_sine(sr, freq, duration, amplitude) -> np.ndarray
# - generate_multi_tone(sr, duration) -> np.ndarray
# - generate_with_pops(sr, duration) -> np.ndarray (带爆音)
# - generate_with_clipping(sr, duration) -> np.ndarray (带削波)
# - generate_speech_like(sr, duration) -> np.ndarray (带包络调制)
# - write_temp_wav(y, sr, tmp_path) -> str (写临时WAV)
# - compute_thd(signal, sr, fundamental_freq) -> float
# - compute_scale_adjusted_snr(original, processed) -> float
# - compute_hf_noise(signal, sr, low_hz, high_hz) -> float
# - count_flat_top_samples(signal, threshold=1e-8) -> int
# - compute_per_step_snr(input_signal, step_fn, *args) -> float
# - @pytest.fixture(params=["v2.0", "v2.1", "v2.2", "v2.2a"]) repair_version
# - @pytest.fixture repair_fn(repair_version) -> 调用函数
# - @pytest.fixture default_params(repair_version) -> 默认参数
```

### 3. `backend/tests/test_repair_quality.py`（新建）
质量基线测试 + 逐步回归测试。

**TestRepairQualityBaseline**（全流程质量门限）：
- `test_pure_sine_no_artifacts`：纯正弦波输入 → THD < -40dB（有损操作允许更高失真）
- `test_no_hard_clipping`：输出无 flat-top 样本
- `test_no_high_frequency_noise`：5-16kHz HF 噪声 < 输入的 2 倍
- `test_scale_adjusted_snr`：全流程 SNR > 20dB（有损修复允许较低 SNR）
- `test_output_finite`：输出无 NaN/Inf

**TestV22aPerStepQuality**（v2.2a 逐步回归，直接调用模块函数）：
- `test_declip_snr`：declip 步骤 SNR > 40dB
- `test_depop_snr`：depop 步骤 SNR > 40dB
- `test_compress_snr`：compress 步骤 SNR > 40dB（全局常量增益 = 纯线性）
- `test_peak_limit_snr`：peak_limit 步骤 SNR > 40dB
- `test_loudness_norm_snr`：loudness_norm 步骤 SNR > 60dB
- `test_depop_no_large_window_replacement`：depop 不替换超过 3 个连续样本
- `test_compress_is_global_gain`：compress 输出是输入的常数倍

### 4. `backend/services/repair/QUALITY_RULES.md`（新建）
精简版质量规则，放在代码目录中，开发时直接参考。

内容：
- 3 条铁律（禁止硬削波、禁止逐样本增益调制、禁止大窗口替换）
- 每条规则附带反例和正例代码片段
- 新版本开发 checklist

### 5. `.trae/documents/repair_quality_guide.md`（新建）
完整经验文档，包含：
- 调试方法论（逐步 SNR、频谱分析、THD 测试、flat-top 检测）
- v2.2a 修复完整案例分析（4 次错误尝试 → 数据驱动诊断 → 根因定位）
- 诊断脚本模板（可直接复制使用）
- 版本升级流程

### 6. `pyproject.toml`（修改）
添加 pytest 配置段：

```toml
[tool.pytest.ini_options]
testpaths = ["backend/tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
```

## Assumptions & Decisions

1. **测试信号用合成信号**，不依赖真实音频文件，确保可重复
2. **v1.x 版本暂不纳入逐步测试**：v1.x 是单文件实现，内部函数不可直接导入测试；但纳入全流程基线测试
3. **SNR 阈值设定**：基于实际诊断数据，全流程允许较低 SNR（有损修复不可避免），逐步测试要求更严格
4. **v2.2a 逐步测试直接导入模块函数**：`from services.repair.repair_v2_2a.core import _simple_declip, _simple_depop, ...`
5. **CI 集成**：暂不配置，但测试应能在 `cd /workspace && python -m pytest backend/tests/ -v` 一键运行
6. **文档语言**：中文
7. **conftest.py 中 mock config.MOBILE_MODE**：v2.0/v2.1/v2.2 的 core.py 导入了 `from config import MOBILE_MODE`，需要在测试前 mock

## Verification Steps

1. `cd /workspace && python -m pytest backend/tests/test_repair_quality.py -v` 全部通过
2. 手动验证：修改 v2.2a compress 引入时变增益，test_compress_is_global_gain 应失败
3. 文档内容完整，包含本次修复的全部经验

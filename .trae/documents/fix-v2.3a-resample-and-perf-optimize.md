# 修复 v2.3a 重采样 Bug + 性能优化计划

## 摘要

1. **Bug 修复**：v2.3a 的 `repair_audio` 缺少重采样逻辑——既没有上采样到工作采样率，也没有输出重采样到 `params["sample_rate"]`。需补齐上采样到 48kHz + 输出重采样。
2. **v2.3 工作采样率升级**：将 v2.3 桌面版工作采样率从 48kHz 提升到 96kHz，补充更多处理细节。
3. **性能优化**：在绝不降低音质的前提下，优化 v2.3 和 v2.3a 的处理速度，用量化测试验证优化前后音质不变。

## 现状分析

### Bug：v2.3a 缺少重采样

| 版本 | 上采样到工作采样率 | 输出重采样到 target_sr |
|------|---------------------|------------------------|
| v2.0 | ✅ | ✅ |
| v2.1 | ✅ | ✅ |
| v2.2 | ✅ 48kHz | ✅ |
| v2.2a | ❌ 无 | ❌ 无（历史遗留，不修改） |
| v2.3 | ✅ 48kHz → **升级到 96kHz** | ✅ |
| **v2.3a** | **❌ 无 → 补齐 48kHz** | **❌ 无 → 补齐** |

### 性能瓶颈分析

#### 全局优化（dsp_utils.py）
1. **`istft` 使用 Python for 循环逐帧叠加**（n_frames 可能上万） → 向量化 overlap-add，循环次数从 n_frames 降到 n_fft

#### v2.3a 优化机会
1. **`_spectral_denoise_1d` 中 `from services.dsp_utils import stft, istft` 在函数内部每次调用时执行** → 移到模块顶层
2. **`_de_ess_1d` 每次调用 `butter` 设计滤波器** → 使用 `lru_cache` 缓存 SOS 系数
3. **`_simple_depop_1d` 中 Python for 循环逐样本处理** → 向量化
4. **多处 `gc.collect()` 调用** → 仅在频谱降噪后保留，其余移除

#### v2.3 优化机会
1. **`_global_loudness_normalize` 使用 `filtfilt` + `butter` 的 `b,a` 格式** → 改用 `sosfiltfilt` + `sos` 格式（数值更稳定）
2. **`_transparent_multiband_compress` 每次调用 `butter` 设计 4 个滤波器** → 使用 `lru_cache` 缓存
3. **`_soft_transient_limit` 中 Python for 循环遍历异常帧** → 向量化
4. **输出重采样中 `filtfilt(b, a)` → `sosfiltfilt(sos)`**：数值更稳定
5. **多处 `gc.collect()`** → 减少

## 提议变更

### 变更 1：v2.3 工作采样率升级到 96kHz

**文件**：`backend/services/repair/repair_v2_3/core.py`

- 将 `DESKTOP_WORKING_SR = 48000` 改为 `DESKTOP_WORKING_SR = 96000`
- 输出重采样逻辑保持不变（会自动从 96kHz 重采样到 target_sr）
- 上采样到 96kHz 后，频谱分辨率翻倍，滤波器截止频率更精确，处理细节更丰富

### 变更 2：修复 v2.3a 重采样 Bug

**文件**：`backend/services/repair/repair_v2_3a/core.py`

在 `repair_audio` 函数中：

1. 添加 `MOBILE_WORKING_SR = 48000` 常量
2. 添加 `from scipy.signal import resample_poly` 导入
3. 在 load_audio 之后添加上采样逻辑：
```python
original_sr = sr
target_sr = params.get("sample_rate", sr)

working_sr = min(MOBILE_WORKING_SR, sr) if sr > MOBILE_WORKING_SR else sr
if sr != working_sr:
    if progress_callback:
        progress_callback(0.02, f"v2.3a 重采样到 {working_sr//1000}kHz...")
    target_len = int(y.shape[1] * working_sr / sr)
    y_new = np.zeros((y.shape[0], target_len))
    for ch in range(y.shape[0]):
        resampled = resample_poly(y[ch], working_sr, sr)
        y_new[ch, :len(resampled)] = resampled[:target_len]
    y = y_new
    sr = working_sr
    gc.collect()
```
4. 在峰值限制之后、导出之前添加输出重采样：
```python
if target_sr != sr:
    if progress_callback:
        progress_callback(0.88, f"v2.3a 重采样到 {target_sr//1000}kHz...")
    if target_sr < sr:
        nyquist = target_sr / 2
        cutoff = nyquist * 0.95
        sos = butter(6, cutoff / (sr / 2), btype='low', output='sos')
        for ch in range(y.shape[0]):
            y[ch] = sosfiltfilt(sos, y[ch])
    y_resampled = np.zeros((y.shape[0], int(y.shape[1] * target_sr / sr)))
    for ch in range(y.shape[0]):
        resampled = resample_poly(y[ch], target_sr, sr)
        y_resampled[ch, :len(resampled)] = resampled[:y_resampled.shape[1]]
    y = y_resampled
    sr = target_sr
    gc.collect()
```
5. 更新返回值 `output_sample_rate` 为 `sr`（已经是）

### 变更 3：优化 `dsp_utils.py` 的 `istft`（全局优化）

**文件**：`backend/services/dsp_utils.py`

将 `istft` 中的 Python for 循环 overlap-add 向量化。原代码逐帧循环（n_frames 次），改为逐采样点循环（n_fft 次），n_fft=2048 远小于 n_frames：

```python
def istft(S, hop_length=512, length=None, window='hann'):
    n_fft = 2 * (S.shape[0] - 1)
    fft_window = get_window(window, n_fft, fftbins=True)
    n_frames = S.shape[1]
    expected_signal_len = n_fft + hop_length * (n_frames - 1)
    y = np.zeros(expected_signal_len)
    window_sum = np.zeros(expected_signal_len)
    frames = np.fft.irfft(S.T, n=n_fft, axis=1)
    windowed = frames * fft_window[np.newaxis, :]
    win_sq = fft_window ** 2
    frame_starts = np.arange(n_frames) * hop_length
    for i in range(n_fft):
        y[frame_starts + i] += windowed[:, i]
        window_sum[frame_starts + i] += win_sq[i]
    nonzero = window_sum > 1e-10
    y[nonzero] /= window_sum[nonzero]
    pad_length = n_fft // 2
    y = y[pad_length:]
    if length is not None:
        y = y[:length]
    return y
```

数学结果完全等价，仅循环结构不同。

### 变更 4：v2.3a 函数级性能优化

**文件**：`backend/services/repair/repair_v2_3a/core.py`

1. **将 `from services.dsp_utils import stft, istft` 移到模块顶层**：避免每次调用 `_spectral_denoise_1d` 时的重复导入开销
2. **向量化 `_simple_depop_1d`**：用 numpy 向量化操作替代 Python for 循环
3. **缓存 `_de_ess` 的带通滤波器 SOS**：使用 `functools.lru_cache` 缓存 `butter` 结果
4. **精简 `gc.collect()`**：仅在 `_spectral_denoise` 后保留，移除其余 5 处

### 变更 5：v2.3 函数级性能优化

**文件**：`backend/services/repair/repair_v2_3/core.py`

1. **`_global_loudness_normalize` 改用 `sosfiltfilt`**：替换 `filtfilt(b, a)` 为 `sosfiltfilt(sos)`，数值更稳定
2. **缓存 `_transparent_multiband_compress` 的滤波器 SOS**：使用 `lru_cache` 缓存 `butter` 结果
3. **向量化 `_soft_transient_limit` 中的异常帧处理**：用 numpy 批量操作替代 for 循环
4. **输出重采样 `filtfilt(b, a)` → `sosfiltfilt(sos)`**
5. **精简 `gc.collect()`**：仅在重采样和频谱操作后保留

### 变更 6：添加性能基准测试

**文件**：`backend/tests/test_repair_quality.py`

新增 `TestV23Performance` 和 `TestV23aPerformance` 类：
- 测量各处理函数的执行时间（使用 `time.perf_counter`）
- 断言优化后执行时间不超过基线的 1.5 倍（防止性能回退）
- 对比优化前后 SNR，断言音质不降低（SNR 差异 < 0.5 dB）

**文件**：`backend/tests/conftest.py`

添加 `benchmark_step` 辅助函数。

### 变更 7：添加重采样正确性测试

**文件**：`backend/tests/test_repair_quality.py`

新增 `TestV23aResample` 类：
- 测试 v2.3a 上采样到 48kHz 后输出采样率正确
- 测试 v2.3a 输出重采样到指定采样率正确
- 测试 v2.3 上采样到 96kHz 后输出采样率正确

## 假设与决策

1. **v2.3a 上采样到 48kHz**：移动版也上采样到 48kHz 工作采样率处理，输出时重采样到目标采样率。这比直接在原始低采样率处理质量更高。
2. **v2.3 工作采样率升级到 96kHz**：桌面端上采样到 96kHz 补充更多细节，输出时重采样到目标采样率。
3. **v2.2a 不修改**：v2.2a 是历史版本，不在本次修改范围内。
4. **优化不改变算法语义**：所有优化必须保持相同的数学结果（向量化 = 原循环的等价变换），SNR 差异 < 0.5 dB 视为数值等价。
5. **`istft` 向量化是全局优化**：所有使用 `dsp_utils.istft` 的版本都会受益。
6. **重采样统一使用 `sosfiltfilt`**：比 `filtfilt(b, a)` 数值更稳定，避免高阶滤波器的数值误差。

## 验证步骤

1. **Bug 修复验证**：
   - 构造 44.1kHz 输入，验证 v2.3a 上采样到 48kHz 处理
   - 构造 `sample_rate=22050` 参数，验证 v2.3a 输出为 22050Hz
   - 构造 44.1kHz 输入，验证 v2.3 上采样到 96kHz 处理
   - 验证返回值 `output_sample_rate` 正确

2. **音质回归验证**：
   - 运行 `pytest backend/tests/test_repair_quality.py -v`，所有 per-step SNR 和铁律测试必须通过
   - 对比优化前后各函数的 SNR，差异 < 0.5 dB

3. **性能验证**：
   - 新增性能测试测量各函数执行时间
   - istft 向量化预期 2-5x 提速
   - 函数级优化预期 10-30% 提速

4. **完整测试**：
   - `pytest backend/tests/test_repair_quality.py -v` 全部通过

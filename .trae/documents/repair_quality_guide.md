# 修复算法质量保障 — 完整经验指南

## 一、调试方法论

### 1.1 逐步 SNR 测试

**核心思想**：对每个处理步骤单独测量 scale-adjusted SNR，找出引入失真的步骤。

**Scale-adjusted SNR 定义**：
```
SNR = 20 * log10(RMS(input) / RMS(noise))
noise = output - input * scale
scale = dot(output, input) / dot(input, input)
```
其中 `scale` 因子排除了纯幅度变化（如 loudness_normalize 只改音量不引入噪声）。

**操作步骤**：
1. 导入每个处理步骤的函数
2. 用同一输入信号依次通过每个步骤
3. 计算每个步骤的 scale-adjusted SNR
4. SNR 显著低于其他步骤的就是噪声源

**诊断标准**：
- 纯线性操作（增益、DC 移除）：SNR > 80dB
- 有损但正确操作（declip、depop）：SNR > 40dB
- **SNR < 30dB**：严重问题，该步骤在引入可闻失真

### 1.2 频谱噪声分析

**核心思想**：测量残差在 5-10kHz、10-16kHz 频段的能量，"呲呲"声主要集中在此。

**操作步骤**：
1. 对输入和输出分别做带通滤波（5-10kHz, 10-16kHz）
2. 计算各频段 RMS 能量
3. 比较输入/输出在各频段的能量比

**诊断标准**：
- 正常步骤：HF 能量比 < 2x
- **HF 能量比 > 10x**：该步骤在添加高频噪声
- **HF 能量比 > 100x**：严重 AM 伪影

### 1.3 THD 测试

**核心思想**：用纯净正弦波输入，测量输出总谐波失真。

**操作步骤**：
1. 生成 440Hz 纯正弦波
2. 通过处理链
3. 对输出做 FFT，测量基波与各次谐波的功率比

**诊断标准**：
- 纯线性操作：THD < -80dB
- 有损操作：THD < -40dB
- **THD > -20dB**：硬削波或其他严重非线性

### 1.4 Flat-top 检测

**核心思想**：统计输出中 `|diff| < 1e-8` 的连续样本数，检测硬削波。

**诊断标准**：
- 正常音频：flat-top 比例 < 0.1%
- **flat-top 比例 > 1%**：存在硬削波

---

## 二、v2.2a 修复案例分析

### 2.1 问题现象

v2.2a 修复后音频出现明显"呲呲"杂音，下载到本地播放同样存在，确认是处理效果本身的问题。

### 2.2 错误尝试历程

| 尝试 | 修改内容 | 结果 | 失败原因 |
|------|----------|------|----------|
| 1 | 替换 `_smooth_compress` 为 `_transparent_compress`（逐帧增益） | 杂音依旧 | 逐帧增益 = AM 调制 |
| 2 | 替换 `_peak_limit` 为 `_peak_limit_smooth`（IIR 增益包络） | 杂音依旧 | IIR 增益包络 = AM 调制 |
| 3 | 替换为 `_soft_peak_limit`（tanh 软削波）+ 修复 depop 2D bug | 杂音依旧 | 只修了 peak_limit，没修 compress 和 depop |
| 4 | 误判为前端 AnalyserNode 重复连接 | 被用户纠正 | 杂音在文件本身，不是播放问题 |

### 2.3 数据驱动诊断

**关键转折**：停止猜测，用数据说话。

```python
# 逐步 SNR 测试结果（使用真实音频）
步骤              SNR(dB)   残差(%)   HF噪声(5-10kHz)
declip            100+      0.00      1:1
depop             19.3      11.9      1.15/0.43
compress          10.2      4.71      3.13e+01/1.09e+01
loudness_norm     100+      0.00      1:1
peak_limit        100+      0.00      1:1
```

**结论**：depop 和 compress 是两个噪声源。

### 2.4 根因与修复

**depop 根因**：余弦插值替换 265 样本窗口，误差 119%
- 修复：单样本差分钳制 + 邻居平均，阈值从 `median*(30+40*amount)` 提高到 `median*(80+120*amount)`

**compress 根因**：时变增益 = AM 调制，5-16kHz 噪声 3.13e+01
- 修复：全局常量增益（基于全局 RMS 计算单一增益因子）

**修复后验证**：
```
所有步骤残差: 0.00%
HF 噪声: 3.13e+01 → 4.88e-06 (降低 640 万倍)
```

### 2.5 核心教训

1. **不要猜，要测**：人耳无法判断噪声来自哪个步骤，必须用数据量化
2. **AM 伪影是隐形杀手**：任何时变增益都会产生边带频率，即使增益变化很缓慢
3. **大窗口替换是陷阱**：看起来"平滑"的余弦插值，实际误差可达 119%
4. **硬削波无处不在**：`np.clip` 是最常见的"简单修复"，但也是最常见的高频噪声源

---

## 三、诊断脚本模板

### 3.1 逐步 SNR 诊断

```python
import numpy as np
from services.audio_loader import load_audio_with_fallback

def diagnose_per_step(input_path, version="v2.2a"):
    """逐步测量每个处理步骤的 SNR"""
    y, sr = load_audio_with_fallback(input_path, sr=None, mono=False)
    if y.ndim == 1:
        y = y.reshape(1, -1)

    # 导入步骤函数（以 v2.2a 为例）
    from services.repair.repair_v2_2a.core import (
        _simple_declip, _simple_depop, _transparent_compress,
        _soft_peak_limit, _loudness_normalize, _remove_dc,
    )

    steps = [
        ("declip", lambda y: _simple_declip(y, 0.5)),
        ("depop", lambda y: _simple_depop(y, sr, 0.5)),
        ("loudness_norm", lambda y: _loudness_normalize(y, sr, -16.0)),
        ("compress", lambda y: _transparent_compress(y, sr, 0.5)),
        ("dc_remove", lambda y: _remove_dc(y, sr)),
        ("peak_limit", lambda y: _soft_peak_limit(y, 0.9)),
    ]

    current = y.copy()
    for name, step_fn in steps:
        prev = current.copy()
        current = step_fn(current)
        snr = compute_scale_adjusted_snr(prev, current)
        hf_in = compute_hf_noise(prev, sr, 5000, 10000)
        hf_out = compute_hf_noise(current, sr, 5000, 10000)
        print(f"{name:15s}  SNR={snr:6.1f}dB  HF={hf_out:.2e}/{hf_in:.2e}")

def compute_scale_adjusted_snr(original, processed):
    orig = original.astype(np.float64).flatten()
    proc = processed.astype(np.float64).flatten()
    min_len = min(len(orig), len(proc))
    orig, proc = orig[:min_len], proc[:min_len]
    scale = np.dot(proc, orig) / (np.dot(orig, orig) + 1e-20)
    noise = proc - orig * scale
    orig_rms = np.sqrt(np.mean(orig ** 2))
    noise_rms = np.sqrt(np.mean(noise ** 2))
    if noise_rms < 1e-10:
        return 100.0
    return 20 * np.log10(orig_rms / noise_rms)

def compute_hf_noise(signal, sr, low_hz, high_hz):
    from scipy.signal import butter, sosfilt
    y = signal.astype(np.float64).flatten()
    nyq = sr / 2
    sos = butter(4, [low_hz/nyq, high_hz/nyq], btype="band", output="sos")
    return np.sqrt(np.mean(sosfilt(sos, y) ** 2))
```

### 3.2 THD 快速检测

```python
def quick_thd_check(version="v2.2a"):
    """用纯正弦波检测 THD"""
    sr = 44100
    t = np.arange(int(sr * 2)) / sr
    y = 0.5 * np.sin(2 * np.pi * 440 * t)

    # 通过处理链...
    # （需要写临时文件并调用 repair_audio）

    # 测量 THD
    spectrum = np.abs(np.fft.rfft(y_out * np.hanning(len(y_out))))
    freqs = np.fft.rfftfreq(len(y_out), 1/sr)
    fund_idx = np.argmin(np.abs(freqs - 440))
    fund_power = np.max(spectrum[fund_idx-5:fund_idx+5]) ** 2
    harmonic_power = 0
    for h in range(2, 6):
        h_idx = np.argmin(np.abs(freqs - 440*h))
        harmonic_power += np.max(spectrum[h_idx-5:h_idx+5]) ** 2
    thd_db = 10 * np.log10(harmonic_power / fund_power + 1e-20)
    print(f"THD: {thd_db:.1f} dB")
```

---

## 四、版本升级流程

### 4.1 开发新版本时

1. **复制最新版本目录**，修改处理链
2. **在 `audio_repair.py` 注册新版本**，添加到 `ALGORITHM_VERSIONS`
3. **运行基线测试**：`pytest backend/tests/test_repair_quality.py::TestRepairQualityBaseline -v -k v2_3`
4. **为新步骤编写逐步测试**（参考 `TestV22aPerStepQuality`）
5. **用真实音频试听**，确认无杂音
6. **提交代码**

### 4.2 修改现有版本时

1. **先运行现有测试**，确认当前状态
2. **修改处理步骤**
3. **再次运行测试**，确认无回归
4. **如果测试失败**：
   - SNR 下降 → 检查是否引入了 AM 伪影或硬削波
   - HF 噪声上升 → 检查是否有时变增益或大窗口替换
   - flat-top 增加 → 检查是否有 `np.clip` 做削波
5. **用逐步 SNR 诊断脚本定位问题步骤**
6. **修复后重新测试**

### 4.3 添加新测试信号时

在 `conftest.py` 中添加新的 `generate_*` 函数，并在 `test_repair_quality.py` 中编写对应的测试用例。

---

## 五、质量指标参考值

| 指标 | 纯线性操作 | 有损但正确 | 严重问题 |
|------|-----------|-----------|---------|
| Scale-adjusted SNR | > 80 dB | > 40 dB | < 30 dB |
| THD（纯正弦输入） | < -60 dB | < -20 dB | > -10 dB |
| HF 噪声增长比 | < 1.5x | < 5x | > 10x |
| Flat-top 样本比例 | < 0.01% | < 0.1% | > 1% |
| 增益变异系数 (CV) | < 0.001 | < 0.01 | > 0.05 |

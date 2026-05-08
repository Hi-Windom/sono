# 修复算法质量规则

## 三条铁律

### 铁律 1：禁止硬削波

**定义**：不允许使用 `np.clip(y, -threshold, threshold)` 或任何截平波形的操作。

**原因**：硬削波产生 flat-top 样本，引入大量高频谐波，听感为"呲呲"杂音。

**反例**：
```python
# ❌ 硬削波 — 产生 flat-top 样本 + 高频谐波
y = np.clip(y, -0.95, 0.95)
```

**正例**：
```python
# ✅ tanh 软削波 — 阈值以下完全线性，阈值以上平滑压缩
def _soft_peak_limit_1d(data, threshold):
    abs_data = np.abs(data)
    mask = abs_data > threshold
    if not np.any(mask):
        return data
    headroom = 1.0 - threshold
    over = abs_data[mask] - threshold
    scale = headroom * 0.98
    data[mask] = np.sign(data[mask]) * (threshold + scale * np.tanh(over / scale))
    return data
```

---

### 铁律 2：禁止逐样本增益调制

**定义**：不允许增益随时间逐帧/逐样本变化。任何 `gain[i]` 随 `i` 变化的操作都是 AM 调制。

**原因**：时变增益 = AM 调制 = 产生边带频率 = 可闻"呲呲"杂音（5-16kHz 尤其严重）。

**反例**：
```python
# ❌ 逐帧增益 — AM 调制产生边带噪声
frame_rms = compute_per_frame_rms(y)
gain_curve = target_rms / (frame_rms + 1e-10)
gain_interp = np.interp(np.arange(len(y)), frame_centers, gain_curve)
y = y * gain_interp  # 时变增益 = AM 伪影
```

**正例**：
```python
# ✅ 全局常量增益 — 纯线性操作，零 AM 伪影
global_rms = np.sqrt(np.mean(y ** 2))
if global_rms > threshold_lin:
    target_rms = threshold_lin + (global_rms - threshold_lin) / ratio
    global_gain = target_rms / global_rms
    y = y * global_gain  # 常量增益 = 零失真
```

---

### 铁律 3：禁止大窗口替换

**定义**：修复爆音/毛刺时，不允许用插值替换超过 5 个连续样本。

**原因**：大窗口插值（如余弦/线性插值替换 265 个样本）误差可达 119%，产生可闻失真。

**反例**：
```python
# ❌ 余弦插值替换 265 样本窗口 — 误差 119%
window = 0.5 * (1 - np.cos(2 * np.pi * np.arange(265) / 264))
y[start:start+265] = y[start:start+265] * (1 - window) + interp * window
```

**正例**：
```python
# ✅ 单样本差分钳制 — 只修正异常样本，不替换窗口
diff = np.diff(data)
abs_diff = np.abs(diff)
threshold = median_diff * (80 + 120 * amount)
pop_mask = np.concatenate(([False], abs_diff > threshold))
for idx in np.where(pop_mask)[0]:
    if idx > 0 and idx < len(data) - 1:
        prev = data[idx - 1]
        next_val = data[idx + 1]
        actual_diff = data[idx] - prev
        if abs(actual_diff) > threshold:
            clamped = prev + np.sign(actual_diff) * threshold
            data[idx] = 0.5 * (clamped + next_val)
```

---

## 新版本开发 Checklist

- [ ] 所有处理步骤通过 `test_repair_quality.py` 基线测试
- [ ] 每个新步骤编写逐步 SNR 测试（SNR > 40dB）
- [ ] 检查是否使用了 `np.clip` 做削波 → 替换为 tanh 软削波
- [ ] 检查是否有逐帧/逐样本增益变化 → 替换为全局常量增益
- [ ] 检查爆音修复是否替换超过 5 个连续样本 → 替换为单样本钳制
- [ ] 用纯正弦波输入测试 THD < -20dB
- [ ] 用语音风格信号测试 HF 噪声增长 < 10x
- [ ] 运行 `pytest backend/tests/test_repair_quality.py -v` 全部通过

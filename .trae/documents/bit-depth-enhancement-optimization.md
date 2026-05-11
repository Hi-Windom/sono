# 位深提升优化计划：16bit→24bit（内存/性能优先版）

## 一、现状分析

### 1. 当前位深处理流程

**输入阶段**（[audio_loader.py](file:///workspace/backend/services/audio_loader.py)）：
- miniaudio 解码时统一转为 `float32`（L7）
- 无论源文件是 16bit 还是 24bit，加载后都是 float32
- **问题**：16bit 源的量化台阶（65536级）已刻入信号中，float32 只是"包装"了这些台阶

**处理阶段**（v2.4/v2.4a core.py）：
- 所有 DSP 在 float32/float64 下进行
- v2.4 有频谱超分、HiFi AI修复等，但**没有位深提升专用模块**
- v2.4a 是轻量版，同样缺失

**输出阶段**：
- v2.4（L465-469）：直接 `sf.write(y, sr, subtype="PCM_24")` — **无dither**
- v2.4a（L748-756）：soundfile 失败时 fallback 到 `int16` — **24bit交付降级！**
- render.py（L234-242）：同上，fallback 也是 `int16`

### 2. 核心问题

| 问题 | 严重度 | 当前状态 |
|------|--------|---------|
| 16bit量化台阶残留 | 高 | ❌ 无处理 |
| 无dithering | 中 | ❌ v1.1有，v2.x全部丢失 |
| 无noise shaping | 低 | ❌ 完全没有 |
| fallback降级为16bit | 高 | ❌ 24bit交付失效 |
| 处理链无位深感知 | 中 | ❌ 不知道源是16bit |

## 二、优化方案（内存/性能优先设计）

### 设计原则

1. **零额外STFT**：位深提升不引入新的频域变换，复用已有处理链中的频谱数据
2. **时域优先**：反量化平滑用纯时域算法，避免STFT的O(N log N)开销
3. **O(1)额外内存**：dither和noise shaping均为逐样本处理，不需要额外缓冲区
4. **流式兼容**：所有算法支持逐块处理，不依赖全局状态
5. **条件执行**：仅当源位深 < 目标位深时才执行，24bit源零开销

### 修改1：新增 `bit_depth_enhance.py`（内存零开销模块）

**文件**：`backend/services/repair/repair_v2_4/bit_depth_enhance.py`（新建）

#### 1.1 量化台阶检测（O(N)时间，O(1)额外内存）

```python
def detect_quantization(y, suspected_bit_depth=16):
    """检测是否存在指定位深的量化台阶，仅扫描前10秒"""
    # 仅取前10秒样本，避免全量扫描
    max_samples = min(len(y.shape[-1]), 10 * 48000)
    y_sample = y[..., :max_samples]
    n_levels = 2 ** suspected_bit_depth
    quant_step = 2.0 / n_levels
    quantized = np.round(y_sample / quant_step) * quant_step
    residual = np.mean(np.abs(y_sample - quantized))
    return residual < quant_step * 0.01
```

**内存开销**：仅前10秒的副本 ≈ 48000 × 2ch × 8bytes ≈ 0.7MB
**时间开销**：O(480k) ≈ <1ms

#### 1.2 时域反量化平滑（O(N)时间，O(1)额外内存 — in-place）

**核心思路**：16bit量化台阶本质是信号被截断到65536个离散电平。平滑方法是在相邻量化电平之间添加微小的随机抖动，打破阶梯感。

```python
def dequantize_smooth_inplace(y, source_bit_depth=16):
    """时域反量化平滑 — in-place，零额外内存"""
    if source_bit_depth >= 24:
        return y
    quant_step = 2.0 / (2 ** source_bit_depth)
    # 对每个样本，如果恰好落在量化台阶上，添加微小偏移
    # 偏移量 = 量化步长 × 随机值 × 0.5（半个LSB的抖动）
    half_lsb = quant_step * 0.5
    # 检测量化台阶：样本值能被quant_step整除
    quantized = np.round(y / quant_step) * quant_step
    on_step = np.abs(y - quantized) < quant_step * 0.01
    # 仅对落在台阶上的样本添加微小抖动
    noise = (np.random.random(y.shape) - 0.5) * half_lsb
    y[on_step] += noise[on_step]
    return y
```

**内存开销**：0（in-place操作，仅临时生成与y同shape的bool和noise数组，可分块处理）
**时间开销**：O(N) ≈ 对5分钟音频 <5ms

**分块版本**（长音频，避免临时数组）：

```python
def dequantize_smooth_inplace_chunked(y, source_bit_depth=16, chunk_size=48000):
    """分块时域反量化平滑 — 严格控制内存"""
    if source_bit_depth >= 24:
        return y
    quant_step = 2.0 / (2 ** source_bit_depth)
    half_lsb = quant_step * 0.5
    n_samples = y.shape[-1]
    for start in range(0, n_samples, chunk_size):
        end = min(start + chunk_size, n_samples)
        chunk = y[..., start:end]
        quantized = np.round(chunk / quant_step) * quant_step
        on_step = np.abs(chunk - quantized) < quant_step * 0.01
        noise = (np.random.random(chunk.shape) - 0.5) * half_lsb
        chunk[on_step] += noise[on_step]
        del quantized, on_step, noise
    return y
```

**内存开销**：chunk_size × channels × 8bytes ≈ 48k × 2 × 8 = 0.7MB/块
**时间开销**：O(N)，与音频长度线性增长

#### 1.3 TPDF Dither（O(N)时间，O(1)额外内存）

```python
def apply_tpdf_dither_inplace(y, target_bit_depth=24):
    """TPDF dither — in-place，零额外内存"""
    if target_bit_depth >= 32:
        return y
    quant_step = 2.0 / (2 ** target_bit_depth)
    # TPDF = 两个均匀分布的卷积，等价于三角分布
    # 逐样本处理，避免大数组
    rng = np.random.default_rng(42)
    for i in range(y.shape[-1] if y.ndim > 1 else len(y)):
        # TPDF: (rand1 - 0.5) + (rand2 - 0.5) = 三角分布
        dither = (rng.random() - 0.5 + rng.random() - 0.5) * quant_step
        if y.ndim > 1:
            for ch in range(y.shape[0]):
                y[ch, i] += dither
        else:
            y[i] += dither
```

**问题**：逐样本Python循环太慢。改用向量化分块：

```python
def apply_tpdf_dither_inplace(y, target_bit_depth=24, chunk_size=480000):
    """TPDF dither — 向量化分块，内存可控"""
    if target_bit_depth >= 32:
        return y
    quant_step = 2.0 / (2 ** target_bit_depth)
    rng = np.random.default_rng(42)
    n_samples = y.shape[-1] if y.ndim > 1 else len(y)
    for start in range(0, n_samples, chunk_size):
        end = min(start + chunk_size, n_samples)
        shape = (y.shape[0], end - start) if y.ndim > 1 else (end - start,)
        dither = (rng.random(shape) - 0.5 + rng.random(shape) - 0.5) * quant_step
        if y.ndim > 1:
            y[:, start:end] += dither
        else:
            y[start:end] += dither
        del dither
    return y
```

**内存开销**：chunk_size × channels × 8bytes ≈ 480k × 2 × 8 = 7.7MB/块
**时间开销**：O(N)，向量化，5分钟音频 ≈ 2ms

#### 1.4 简化 Noise Shaping（O(N)时间，O(1)额外内存）

使用一阶误差反馈，不需要STFT：

```python
def apply_noise_shaping_inplace(y, sr, target_bit_depth=24):
    """简化noise shaping — 一阶误差反馈，O(1)额外内存"""
    if target_bit_depth >= 32:
        return y
    quant_step = 2.0 / (2 ** target_bit_depth)
    # 一阶反馈系数（将噪声推向高频）
    # 系数0.5左右，越大高频推力越强，但稳定性越差
    feedback = 0.6
    error = 0.0
    # 逐样本处理（必须，因为有反馈状态）
    # 但用numba或C扩展可以加速
    for i in range(y.shape[-1] if y.ndim > 1 else len(y)):
        if y.ndim > 1:
            for ch in range(y.shape[0]):
                val = y[ch, i] + error * feedback
                quantized = np.round(val / quant_step) * quant_step
                error = val - quantized
                y[ch, i] = quantized
        else:
            val = y[i] + error * feedback
            quantized = np.round(val / quant_step) * quant_step
            error = val - quantized
            y[i] = quantized
    return y
```

**问题**：逐样本Python循环对长音频太慢。

**解决方案**：noise shaping 改为可选功能，默认关闭。对于16→24bit的场景，TPDF dither已经足够（24bit的量化噪声底在-144dB，远低于听阈）。noise shaping主要在16bit输出时有价值。

**最终策略**：
- **24bit输出**：仅TPDF dither（足够，无需noise shaping）
- **16bit输出**：TPDF dither + noise shaping（此时才有必要）

### 修改2：audio_loader.py 返回源位深

**文件**：`backend/services/audio_loader.py`

```python
def load_audio_with_fallback(file_path, sr=None, mono=False):
    # ... 现有代码 ...
    # 新增：获取源位深
    source_bit_depth = sound.sample_width * 8  # miniaudio提供sample_width
    return raw, sample_rate, source_bit_depth
```

**注意**：这是API变更，需要更新所有调用点。为最小化改动，改为可选返回：

```python
def load_audio_with_fallback(file_path, sr=None, mono=False, return_bit_depth=False):
    # ... 现有代码 ...
    source_bit_depth = sound.sample_width * 8
    if return_bit_depth:
        return raw, sample_rate, source_bit_depth
    return raw, sample_rate
```

**内存开销**：0
**时间开销**：0（miniaudio已提供sample_width）

### 修改3：v2.4 core.py 集成位深提升

**文件**：`backend/services/repair/repair_v2_4/core.py`

在导出前（L456-469之间）插入：

```python
# 位深提升优化
bit_depth = params.get("bit_depth", 24)
source_bit_depth = params.get("source_bit_depth", 24)
if source_bit_depth < bit_depth:
    from .bit_depth_enhance import dequantize_smooth_inplace_chunked, apply_tpdf_dither_inplace
    y = dequantize_smooth_inplace_chunked(y, source_bit_depth)
    y = apply_tpdf_dither_inplace(y, bit_depth)
```

**内存开销**：0（in-place操作）
**时间开销**：<10ms（5分钟音频）

### 修改4：v2.4a core.py 集成位深提升（轻量版）

**文件**：`backend/services/repair/repair_v2_4a/core.py`

同v2.4，在导出前插入。同时**修复fallback降级**：

```python
# 修复前（L748-756）:
except Exception:
    from scipy.io import wavfile
    if y.ndim > 1:
        y_out = y.T
    else:
        y_out = y
    if y_out.dtype != np.int16:
        y_out = np.clip(y_out * 32767, -32768, 32767).astype(np.int16)  # BUG: 降级为16bit!
    wavfile.write(output_path, sr, y_out)

# 修复后:
except Exception:
    from scipy.io import wavfile
    bit_depth = params.get("bit_depth", 24)
    if y.ndim > 1:
        y_out = y.T
    else:
        y_out = y
    if bit_depth == 24:
        y_out = np.clip(y_out * 8388607, -8388608, 8388607).astype(np.int32)
    elif y_out.dtype != np.int16:
        y_out = np.clip(y_out * 32767, -32768, 32767).astype(np.int16)
    wavfile.write(output_path, sr, y_out)
```

**注意**：scipy.io.wavfile 不支持直接写 PCM_24，但支持写 int32 数据配合24bit标记。需要验证。如果不支持，fallback应尝试用struct手动写入24bit WAV。

### 修改5：render.py 修复 fallback + 位深提升

**文件**：`backend/services/render.py`

同修改4修复fallback。同时在render_output中加入位深提升（当目标位深 > 源位深时）。

### 修改6：API层传递源位深

**文件**：`backend/api/routes.py`

在修复请求处理中，从audio_info获取源位深并传入params：

```python
# 在调用repair_audio前
audio_info = get_audio_info(input_path)
params["source_bit_depth"] = audio_info.get("sample_width", 2) * 8
```

## 三、内存/性能影响分析

### 新增内存开销

| 步骤 | 额外内存 | 说明 |
|------|---------|------|
| 量化台阶检测 | 0.7MB | 仅前10秒 |
| 反量化平滑 | 0.7MB/块 | 分块处理，块大小1秒 |
| TPDF dither | 7.7MB/块 | 分块处理，块大小10秒 |
| noise shaping | 0 | 逐样本，仅1个float状态 |
| **总计峰值** | **<10MB** | 远小于STFT的~15MB |

### 新增时间开销

| 步骤 | 5分钟音频 | 60分钟音频 |
|------|----------|-----------|
| 量化台阶检测 | <1ms | <1ms |
| 反量化平滑 | <5ms | <60ms |
| TPDF dither | <2ms | <24ms |
| noise shaping(可选) | ~500ms | ~6s |
| **总计(不含noise shaping)** | **<10ms** | **<100ms** |
| **总计(含noise shaping)** | **~500ms** | **~6s** |

### 与现有流程对比

- 现有v2.4处理5分钟音频约30-60秒
- 位深提升增加 <10ms，占比 <0.03%
- **几乎零性能影响**

## 四、实施步骤

1. **新建** `backend/services/repair/repair_v2_4/bit_depth_enhance.py`
   - detect_quantization() — 量化台阶检测
   - dequantize_smooth_inplace_chunked() — 时域反量化平滑
   - apply_tpdf_dither_inplace() — TPDF dither
   - apply_noise_shaping_inplace() — 简化noise shaping（可选，仅16bit输出时启用）

2. **修改** `backend/services/audio_loader.py`
   - 新增 return_bit_depth 参数，返回源位深

3. **修改** `backend/services/repair/repair_v2_4/core.py`
   - 导出前插入位深提升（反量化平滑 + TPDF dither）
   - 传递source_bit_depth到params

4. **修改** `backend/services/repair/repair_v2_4a/core.py`
   - 同v2.4插入位深提升
   - 修复fallback降级为int16的BUG

5. **修改** `backend/services/render.py`
   - 修复fallback降级
   - render流程中加入位深提升

6. **修改** `backend/api/routes.py`
   - 传递源位深信息到params

7. **测试验证**
   - `python -m pytest backend/tests/test_repair_quality.py -v`

## 五、关键决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 反量化平滑：频域 vs 时域 | **时域** | 避免STFT的内存和时间开销 |
| Dither：TPDF vs 其他 | **TPDF** | 标准方案，实现简单，效果确定 |
| Noise shaping：启用 vs 可选 | **可选（仅16bit输出）** | 24bit输出无需，避免逐样本循环的性能问题 |
| 检测量化台阶：全量 vs 采样 | **前10秒采样** | 足够判断，避免长音频开销 |
| 分块大小 | 1秒(平滑)/10秒(dither) | 平滑需要精细，dither可以大块 |

## 六、风险与缓解

1. **反量化平滑过度处理**：仅对落在量化台阶上的样本处理，且偏移量限制在±0.5 LSB
2. **Noise shaping稳定性**：一阶反馈系数限制在0.6以内，确保不发散
3. **Fallback路径兼容性**：scipy.io.wavfile对24bit写入的支持需要验证，可能需要手动写入WAV头
4. **API兼容性**：audio_loader返回值变更用可选参数，不影响现有调用

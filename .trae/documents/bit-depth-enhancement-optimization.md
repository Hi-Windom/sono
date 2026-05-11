# 位深提升优化分析计划：16bit→24bit

## 一、现状分析

### 1. 当前位深处理流程

**输入阶段**（[audio_loader.py](file:///workspace/backend/services/audio_loader.py)）：
- miniaudio 解码时统一转为 `float32`（L7: `output_format=miniaudio.SampleFormat.FLOAT32`）
- 无论源文件是 16bit 还是 24bit，加载后都是 float32 浮点数
- **问题**：16bit 源的量化台阶（65536级）已刻入信号中，float32 只是"包装"了这些台阶

**处理阶段**（v2.4 [core.py](file:///workspace/backend/services/repair/repair_v2_4/core.py) / v2.4a [core.py](file:///workspace/backend/services/repair/repair_v2_4a/core.py)）：
- 所有 DSP 处理在 float32/float64 下进行，精度足够
- v2.4 有频谱超分（`spectral_superres`）、HiFi AI修复、细节增强等模块
- v2.4a 是轻量版，无频谱超分
- **关键缺失**：没有任何模块专门处理"16bit量化台阶→24bit平滑"的位深提升问题

**输出阶段**：
- v2.4（L465-469）：直接 `sf.write(output_path, y, sr, subtype="PCM_24")`
- v2.4a（L742-756）：同上，soundfile 失败时 fallback 到 `int16`（**降级为16bit！**）
- render.py（L229-242）：同上，fallback 也是 `int16`
- **关键缺失**：无 dithering、无 noise shaping、无量化台阶平滑

### 2. 历史对比：v1.1 有 dither，v2.x 全部丢失

- v1.1（[audio_repair_v1_1.py:687-702](file:///workspace/backend/services/repair/audio_repair_v1_1.py#L687-L702)）有 `_apply_dither()` 函数
  - 使用 TPDF（三角概率密度函数）dither
  - 在导出前应用：`y = _apply_dither(y, bit_depth)`
- **v2.0/v2.1/v2.2/v2.2a/v2.3/v2.3a/v2.4/v2.4a 全部没有 dither**
- 这意味着从 v2.0 开始，位深转换的 dither 就丢失了

### 3. 核心问题诊断

16bit→24bit 的位深提升，存在以下问题：

| 问题 | 严重程度 | 当前状态 |
|------|---------|---------|
| **16bit量化台阶残留** | 高 | ❌ 无处理。16bit源只有65536个离散电平，直接写24bit只是"零填充"低位，听感上台阶感仍在安静段落可闻 |
| **无dithering** | 中 | ❌ v2.x全部缺失。虽然16→24是升位深（理论上不需要dither），但处理过程中产生的信号在24bit量化时仍需dither |
| **无noise shaping** | 中 | ❌ 完全没有。noise shaping可将量化噪声推到人耳不敏感的高频区 |
| **fallback降级为16bit** | 高 | ❌ v2.4a/render.py的soundfile失败时直接输出int16，24bit交付完全失效 |
| **处理链无位深感知** | 中 | ❌ 处理模块不知道源是16bit，无法针对性优化 |

### 4. 16bit→24bit 位深提升的专业要求

专业音频工程中，16bit→24bit提升需要：
1. **量化台阶平滑（De-quantization）**：用插值/oversampling消除16bit的阶梯感
2. **Dithering**：虽然升位深不严格需要，但处理链中重量化时需要
3. **Noise Shaping**：将量化噪声移至不敏感频段
4. **动态范围扩展**：利用24bit的144dB动态范围，优化低电平细节

## 二、优化方案

### 方案概览

在 v2.4/v2.4a 的修复流程中，新增 **位深提升优化模块**，包含4个子功能：

### 修改1：新增位深感知模块 `bit_depth_enhance.py`

**文件**：`backend/services/repair/repair_v2_4/bit_depth_enhance.py`（新建）

功能：
1. **量化台阶检测**：分析源音频是否存在16bit量化台阶
2. **反量化平滑（De-quantization Smoothing）**：
   - 对存在量化台阶的信号，使用多项式插值平滑阶梯
   - 在频域检测量化噪声特征（谐波状的量化失真），进行抑制
   - 方法：STFT域中对低幅度信号的量化台阶进行频谱平滑
3. **TPDF Dithering**：
   - 在24bit输出前应用TPDF dither
   - 消除处理链中引入的量化相关失真
4. **Noise Shaping**：
   - 使用改进的F-weighted noise shaping曲线
   - 将量化噪声推到>15kHz的高频区
   - 利用24bit的低底噪优势

### 修改2：v2.4 core.py 集成位深提升

**文件**：`backend/services/repair/repair_v2_4/core.py`

在修复流程中，于"响度归一化"之后、"动态处理"之前，插入位深提升步骤：
- 读取源文件位深信息（需要从params传入或从音频分析）
- 如果源位深 < 目标位深，执行位深提升优化

### 修改3：v2.4a core.py 集成位深提升（轻量版）

**文件**：`backend/services/repair/repair_v2_4a/core.py`

轻量版位深提升：仅包含TPDF dither + 简化noise shaping，不做频域平滑（节省内存）

### 修改4：修复 fallback 降级问题

**文件**：
- `backend/services/repair/repair_v2_4a/core.py`（L748-756）
- `backend/services/render.py`（L234-242）

将 fallback 从 `int16` 改为 `int24`/`int32`，确保24bit交付不降级。

### 修改5：源位深信息传递

**文件**：
- `backend/services/audio_loader.py`：返回源位深信息
- `backend/api/routes.py`：在params中传递源位深
- 修复入口处检测源位深并传入params

### 修改6：render.py 位深提升

**文件**：`backend/services/render.py`

在render_output中，当目标位深 > 源位深时，应用位深提升优化。

## 三、技术细节

### 3.1 量化台阶检测算法

```python
def detect_quantization_steps(y, suspected_bit_depth=16):
    """检测音频是否存在指定位深的量化台阶"""
    n_levels = 2 ** suspected_bit_depth
    quant_step = 2.0 / n_levels
    # 检查样本值是否落在量化台阶上
    quantized = np.round(y / quant_step) * quant_step
    residual = y - quantized
    # 如果残差极小，说明存在量化台阶
    ratio = np.mean(np.abs(residual)) / (quant_step + 1e-10)
    return ratio < 0.01  # 阈值：残差小于1%量化步长
```

### 3.2 反量化平滑算法

```python
def dequantize_smooth(y, sr, source_bit_depth=16):
    """消除低位深量化台阶，平滑到高位深"""
    if source_bit_depth >= 24:
        return y
    # 方法1：频域平滑 - 抑制量化噪声的谐波特征
    S = stft(y, n_fft=2048, hop_length=512)
    mag = np.abs(S)
    # 量化噪声在频域表现为均匀底噪上的周期性尖峰
    # 使用频谱门限低于信号但高于量化噪声的阈值
    # ... 频谱平滑处理
    # 方法2：时域多项式插值
    # 对相邻量化台阶之间的样本进行三次样条插值
```

### 3.3 TPDF Dither + Noise Shaping

```python
def apply_tpdf_dither(y, target_bit_depth=24):
    """TPDF dither + noise shaping"""
    quant_step = 2.0 / (2 ** target_bit_depth)
    # TPDF: 两个均匀分布之差
    noise = (np.random.random(y.shape) - 0.5) + (np.random.random(y.shape) - 0.5)
    noise *= quant_step
    y_dithered = y + noise
    return y_dithered

def apply_noise_shaping(y, sr, target_bit_depth=24):
    """F-weighted noise shaping"""
    # 将量化误差反馈到后续样本
    # 使用人耳等响曲线的逆作为shaping滤波器
    # 简化版：二阶IIR高通，将噪声推向高频
```

### 3.4 Fallback修复

```python
# 修复前（v2.4a L754-755）:
if y_out.dtype != np.int16:
    y_out = np.clip(y_out * 32767, -32768, 32767).astype(np.int16)

# 修复后:
if bit_depth == 24:
    y_out = np.clip(y_out * 8388607, -8388608, 8388607).astype(np.int32)
    # soundfile可以写int32的PCM_24
elif bit_depth == 16:
    y_out = np.clip(y_out * 32767, -32768, 32767).astype(np.int16)
```

## 四、实施步骤

1. **新建** `backend/services/repair/repair_v2_4/bit_depth_enhance.py`
   - 实现量化台阶检测
   - 实现反量化平滑
   - 实现TPDF dither
   - 实现noise shaping

2. **修改** `backend/services/audio_loader.py`
   - 返回源位深信息（从miniaudio或文件头获取）

3. **修改** `backend/services/repair/repair_v2_4/core.py`
   - 在响度归一化后插入位深提升步骤
   - 在导出前应用dither+noise shaping

4. **修改** `backend/services/repair/repair_v2_4a/core.py`
   - 插入轻量版位深提升
   - 修复fallback降级为int16的问题

5. **修改** `backend/services/render.py`
   - 修复fallback降级问题
   - 在render流程中加入位深提升

6. **修改** `backend/api/routes.py`
   - 传递源位深信息到params

7. **测试验证**
   - 运行 `python -m pytest backend/tests/test_repair_quality.py -v`
   - 手动测试16bit源→24bit输出的音质

## 五、预期效果

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 安静段落台阶感 | 可闻（16bit量化残留） | 不可闻（平滑处理） |
| 量化噪声分布 | 均匀分布（白噪特性） | 高频集中（noise shaping） |
| 低电平细节 | 受16bit底噪限制 | 利用24bit动态范围 |
| fallback输出 | 降级为16bit | 保持24bit |
| 动态范围 | ~96dB（16bit残留） | ~144dB（24bit完整） |

## 六、风险与注意事项

1. **反量化平滑的过度处理风险**：如果源本身就是24bit，不应执行平滑。必须先检测源位深。
2. **Noise shaping的稳定性**：IIR反馈回路可能导致不稳定，需要限制反馈系数。
3. **内存开销**：频域平滑需要STFT，对长音频需使用streaming模式。
4. **兼容性**：soundfile的PCM_24写入在不同平台上行为一致，但fallback路径需要验证。

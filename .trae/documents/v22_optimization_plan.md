# v2.2 音频修复性能优化计划

## 用户决策确认

基于用户反馈，确定以下优化方向：
- **方案**: 混合方案（C 扩展 + ONNX 模型）
- **依赖**: 完全接受 PyTorch/ONNX Runtime
- **优先级**: 音质优先，保持 HiFi 品质

## 当前性能瓶颈分析

### 1. 频谱修复 (spectral_group_a.py)
**当前问题**:
- 每通道循环处理
- 多层嵌套循环（频段×帧）
- 使用 `gaussian_filter1d` 和 `medfilt`（较慢）
- STFT/ISTFT 每通道重复计算

**耗时估算**: 占总处理时间 30-40%

### 2. 谐波增强 (spectral_group_b.py)
**当前问题**:
- 双重嵌套循环（谐波数 × 基频数 × 帧数）
- 每帧调用 `gaussian_filter1d`
- 频谱质心计算耗时

**耗时估算**: 占总处理时间 25-35%

### 3. 瞬态修复 (transient.py)
**当前问题**:
- aubio onset 检测后仍有 Python 循环修复
- 逐 onset 处理，无法向量化

**耗时估算**: 占总处理时间 15-20%

### 4. 动态处理 (dynamics.py)
**当前问题**:
- 每通道 4 次 SOS 滤波
- 增益平滑使用循环

**耗时估算**: 占总处理时间 10-15%

## 优化方案设计

### 第一阶段：ONNX 模型集成（预期 10-50x 提速）

#### 1.1 DeepFilterNet 降噪替换频谱修复

**实现文件**: `backend/services/repair/repair_v2_2/spectral_group_a_v2.py`

**技术方案**:
```python
import onnxruntime as ort
import numpy as np

class DeepFilterNetONNX:
    def __init__(self, model_path: str):
        # 使用 ONNX Runtime 推理
        self.session = ort.InferenceSession(
            model_path,
            providers=['CPUExecutionProvider']
        )
    
    def process(self, audio: np.ndarray, sr: int) -> np.ndarray:
        # 重采样到 48kHz（DeepFilterNet 要求）
        # ONNX 推理
        # 返回降噪后的音频
```

**模型选择**:
- DeepFilterNet2 ONNX (约 2MB)
- 下载地址: https://github.com/Rikorose/DeepFilterNet/releases

**集成方式**:
- 替换 `_fast_noise_reduction` 函数
- 保留去齿音和毛刺修复的简化逻辑
- 预期提速: 降噪部分 20-50x

#### 1.2 DTLN 降噪备选方案

**实现文件**: `backend/services/repair/repair_v2_2/dtln_denoiser.py`

**技术方案**:
- 使用 DTLN 的 ONNX/TFLite 模型
- 200x 实时因子，适合移动端
- 模型大小: 1-2MB

### 第二阶段：C/Cython 扩展（预期 5-20x 提速）

#### 2.1 STFT/ISTFT C 扩展

**实现文件**: `backend/services/repair/repair_v2_2/_stft.c` / `_stft.pyx`

**优化点**:
- 使用 FFTW 或 Intel MKL
- 批处理多通道
- 减少 Python 循环开销

**关键函数**:
```c
// _stft.c
void batch_stft(float** input, int n_channels, int n_samples,
                complex float** output, int n_fft, int hop_length);

void batch_istft(complex float** input, int n_channels, int n_frames,
                 float** output, int n_fft, int hop_length, int length);
```

#### 2.2 快速中值滤波 C 扩展

**实现文件**: `backend/services/repair/repair_v2_2/_fast_filters.c`

**优化点**:
- 替换 `scipy.signal.medfilt`
- 使用快速选择算法（O(n) 中值）
- SIMD 优化（SSE/AVX）

#### 2.3 谐波增强 C 扩展

**实现文件**: `backend/services/repair/repair_v2_2/_harmonic.c`

**优化点**:
- 将双重嵌套循环移至 C
- 使用 OpenMP 并行化
- 预计算频谱映射表

### 第三阶段：算法重构（预期 2-5x 提速）

#### 3.1 向量化频谱处理

**修改文件**: `backend/services/repair/repair_v2_2/spectral_group_a.py`

**优化策略**:
```python
# 当前：循环处理
for i in range(1, n_frames):
    gain[:, i] = alpha * gain[:, i-1] + (1 - alpha) * gain[:, i]

# 优化：使用 scipy.signal.lfilter（C 实现）
from scipy.signal import lfilter
gain = lfilter([1-alpha], [1, -alpha], gain, axis=1)
```

#### 3.2 批处理通道

**修改文件**: `backend/services/repair/repair_v2_2/core.py`

**优化策略**:
- 当前：逐通道处理
- 优化：批处理所有通道，减少函数调用开销

#### 3.3 减少 STFT/ISTFT 次数

**当前流程**:
1. spectral_group_a: STFT → 处理 → ISTFT
2. spectral_group_b: STFT → 处理 → ISTFT

**优化流程**:
1. 单次 STFT
2. group_a 处理
3. group_b 处理
4. 单次 ISTFT

## 实施计划

### 任务 1: ONNX 模型集成（优先级：高）

**文件变更**:
- 新增: `backend/services/repair/repair_v2_2/onnx_denoiser.py`
- 修改: `backend/services/repair/repair_v2_2/spectral_group_a.py`
- 修改: `backend/requirements.txt`（添加 onnxruntime）

**步骤**:
1. 下载 DeepFilterNet2 ONNX 模型
2. 实现 ONNX 推理封装类
3. 修改 spectral_group_a 集成 ONNX 降噪
4. 添加降级逻辑（ONNX 失败时回退到 Wiener）
5. 测试效果和性能

**预期效果**:
- 降噪部分提速: 20-50x
- 整体频谱修复提速: 5-10x

### 任务 2: C 扩展开发（优先级：中）

**文件变更**:
- 新增: `backend/services/repair/repair_v2_2/_fast_filters.c`
- 新增: `backend/services/repair/repair_v2_2/_fast_filters.pyx`
- 新增: `setup.py`（C 扩展构建配置）
- 修改: `backend/services/repair/repair_v2_2/spectral_group_b.py`

**步骤**:
1. 实现快速中值滤波 C 扩展
2. 实现谐波增强 C 扩展
3. 添加 setup.py 构建配置
4. 修改 spectral_group_b 使用 C 扩展
5. 测试和性能对比

**预期效果**:
- 谐波增强提速: 5-10x
- 滤波操作提速: 3-5x

### 任务 3: 算法向量化优化（优先级：高）

**文件变更**:
- 修改: `backend/services/repair/repair_v2_2/spectral_group_a.py`
- 修改: `backend/services/repair/repair_v2_2/spectral_group_b.py`
- 修改: `backend/services/repair/repair_v2_2/dynamics.py`
- 修改: `backend/services/repair/repair_v2_2/core.py`

**步骤**:
1. 使用 `scipy.signal.lfilter` 替换手动平滑循环
2. 合并 group_a 和 group_b 的 STFT/ISTFT
3. 批处理多通道
4. 优化内存分配（预分配数组）

**预期效果**:
- 频谱处理提速: 2-3x
- 动态处理提速: 2x

### 任务 4: 瞬态修复优化（优先级：中）

**文件变更**:
- 修改: `backend/services/repair/repair_v2_2/transient.py`
- 新增: `backend/services/repair/repair_v2_2/_transient.c`

**步骤**:
1. 使用 aubio 的更多功能（已部分集成）
2. 实现 C 扩展的瞬态修复
3. 向量化修复过程

**预期效果**:
- 瞬态修复提速: 3-5x

### 任务 5: 性能测试和调优（优先级：高）

**文件变更**:
- 新增: `backend/tests/test_performance_v22.py`

**测试内容**:
1. 各模块单独性能测试
2. 端到端处理时间对比
3. 音质指标对比（SNR、THD 等）
4. 移动端性能测试

**验收标准**:
- 频谱修复: 3x+ 提速
- 瞬态修复: 3x+ 提速
- 整体处理: 5x+ 提速
- 音质: 保持或提升

### 任务 6: Android 打包（优先级：高）

**文件变更**:
- 修改: `scripts/build_android_release.sh`
- 修改: `backend/requirements.txt`

**步骤**:
1. 确保 ONNX Runtime 支持 Android
2. 更新依赖配置
3. 重新打包 Android 发布包
4. 移动端测试

## 技术细节

### ONNX Runtime 配置

```python
import onnxruntime as ort

# 优化配置
sess_options = ort.SessionOptions()
sess_options.inter_op_num_threads = 4
sess_options.intra_op_num_threads = 4
sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

# 加载模型
session = ort.InferenceSession(
    model_path,
    sess_options=sess_options,
    providers=['CPUExecutionProvider']
)
```

### C 扩展构建配置

```python
# setup.py
from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy

extensions = [
    Extension(
        "repair_v2_2._fast_filters",
        ["backend/services/repair/repair_v2_2/_fast_filters.pyx"],
        include_dirs=[numpy.get_include()],
        extra_compile_args=["-O3", "-fopenmp"],
        extra_link_args=["-fopenmp"],
    )
]

setup(
    ext_modules=cythonize(extensions),
)
```

### 降级策略

```python
def apply_spectral_group_a(y, sr, params, ...):
    try:
        # 尝试使用 ONNX 降噪
        if ONNX_AVAILABLE:
            return _apply_with_onnx(y, sr, params, ...)
    except Exception as e:
        logger.warning(f"ONNX failed, falling back: {e}")
    
    # 回退到优化后的 Wiener 滤波
    return _apply_wiener_optimized(y, sr, params, ...)
```

## 风险评估

### 技术风险

1. **ONNX Runtime 移动端兼容性**
   - 风险: ONNX Runtime 在 Android/Termux 上可能有问题
   - 缓解: 准备 TFLite 备选方案

2. **C 扩展构建复杂性**
   - 风险: 不同平台编译问题
   - 缓解: 提供纯 Python 降级方案

3. **模型加载内存占用**
   - 风险: DeepFilterNet 模型占用 2-5MB 内存
   - 缓解: 延迟加载，使用 INT8 量化模型

### 效果风险

1. **深度学习模型过度处理**
   - 风险: 降噪过度导致音质损失
   - 缓解: 提供强度调节参数，默认保守设置

2. **C 扩展数值精度**
   - 风险: C 扩展与 Python 结果不一致
   - 缓解: 严格测试，确保误差 < 0.1dB

## 预期效果

| 模块 | 当前耗时占比 | 预期提速 | 优化后耗时占比 |
|------|-------------|---------|---------------|
| 频谱修复 | 35% | 10x | 5% |
| 谐波增强 | 30% | 5x | 8% |
| 瞬态修复 | 18% | 3x | 7% |
| 动态处理 | 12% | 2x | 7% |
| 其他 | 5% | 1x | 5% |
| **整体** | 100% | **5-8x** | **32%** |

## 验证标准

1. **性能验证**
   - 处理 1 分钟音频时间 < 10 秒（当前约 50-60 秒）
   - 频谱修复和瞬态修复各提速 3x+

2. **音质验证**
   - SNR 提升或保持
   - THD+N < -60dB
   - 主观听感无退化

3. **稳定性验证**
   - 100 次连续处理无崩溃
   - 内存使用稳定，无泄漏

## 时间线

| 阶段 | 任务 | 预计时间 |
|------|------|---------|
| 第 1 周 | ONNX 模型集成 | 2-3 天 |
| 第 1 周 | 算法向量化优化 | 2-3 天 |
| 第 2 周 | C 扩展开发 | 3-4 天 |
| 第 2 周 | 瞬态修复优化 | 1-2 天 |
| 第 3 周 | 性能测试和调优 | 2-3 天 |
| 第 3 周 | Android 打包 | 1-2 天 |

**总计**: 2-3 周完成全部优化

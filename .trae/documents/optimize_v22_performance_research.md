# v2.2 极致性能优化研究计划

## 用户反馈
- 当前优化提升有限，需要提速 3x 以上
- 瓶颈：STFT/ISTFT、滤波器运算、Python 循环、内存分配
- 环境：Termux，可安装轻量 C 库，内存 <2GB
- 目标：速度提升 5x+，保持 90% 音质

## 领域最新发展调研

### 1. 音频处理算法趋势

#### 深度学习降噪（2023-2024）
- **RNNoise/PercepNet**: 轻量级 RNN 降噪，实时性能
- **DTLN/DTLN+**: 双信号变换 LSTM 网络，低延迟
- **FullSubNet+**: 频谱子带网络，轻量高效
- **问题**: 模型较大（1-10MB），Termux 加载慢

#### 传统算法优化
- **Wiener 滤波**: 频域最优线性滤波
- **MMSE-STSA**: 最小均方误差短时谱估计
- **OM-LSA**: 最优改进对数谱幅度估计
- **优势**: 计算量可控，适合移动端

### 2. 高性能计算方案

#### FFT 加速库
- **FFTW**: 最快的 FFT 实现，支持 SIMD
- **Kiss FFT**: 轻量级，适合嵌入式
- **PocketFFT**: NumPy 默认，性能一般
- **方案**: 通过 ctypes 调用 libfftw3

#### 信号处理加速
- **libsndfile**: 音频 I/O 优化
- **libsamplerate**: 高质量重采样
- **libsoxr**: 优化的重采样库

#### BLAS/LAPACK
- **OpenBLAS**: 优化的矩阵运算
- **NumPy 自动使用**: 已集成

### 3. Python 性能优化

#### Numba（Termux 不可用）
- JIT 编译 Python 代码
- 需要 LLVM，Termux 安装困难

#### Cython（Termux 不可用）
- 需要编译 C 扩展
- Termux 缺少编译工具链

#### ctypes + C 库（可行）
- 调用预编译的 .so 库
- 无需编译，直接加载
- **推荐方案**

### 4. 算法级优化策略

#### 减少 STFT/ISTFT 次数
- 当前：每个频谱处理步骤一次 STFT/ISTFT
- 优化：合并所有频谱处理到一次变换
- **预期提升**: 3-5x

#### 降低 FFT 尺寸
- 当前：n_fft=2048
- 优化：n_fft=1024 或 512
- **预期提升**: 2-4x
- **音质影响**: 高频分辨率降低，可接受

#### 重叠相加优化
- 当前：hop_length=512 (75% 重叠)
- 优化：hop_length=1024 (50% 重叠)
- **预期提升**: 2x
- **音质影响**: 时间分辨率降低

#### 滤波器优化
- 当前：sosfiltfilt 4阶滤波器
- 优化：
  1. 降低阶数到 2阶
  2. 使用 IIR 直接型替代 SOS
  3. 批量处理多通道
- **预期提升**: 2-3x

## 重新设计方案

### 方案 A: 极致简化（推荐）

#### 核心思想
- 只保留最关键处理步骤
- 大幅降低算法复杂度
- 使用最简单的实现

#### 处理流程
1. **时域修复**（削波、爆音）- 保留
2. **单次 STFT** - 合并所有频谱处理
3. **简化降噪** - 频谱减法，无平滑
4. **简化去齿音** - 固定频段衰减
5. **ISTFT** - 单次逆变换
6. **简单压缩** - 单段压缩，无分频
7. **响度归一化** - 保留

#### 性能预期
- **速度提升**: 8-10x
- **音质保持**: 85-90%
- **复杂度**: O(N) 每采样点

### 方案 B: C 库加速

#### 核心思想
- 保留现有算法
- 关键路径用 C 实现
- Python 只做流程控制

#### C 库实现
1. **stft.c** - 优化的 STFT/ISTFT
2. **compressor.c** - 向量化压缩器
3. **filter.c** - 优化的滤波器组

#### 性能预期
- **速度提升**: 5-8x
- **音质保持**: 95%+
- **复杂度**: 中等

### 方案 C: 混合方案（推荐）

#### 核心思想
- 算法简化 + C 库加速
- 平衡速度和音质

#### 实现
1. 简化处理流程（类似方案 A）
2. 关键计算用 C 库（STFT、滤波）
3. 保留核心音质处理

#### 性能预期
- **速度提升**: 6-8x
- **音质保持**: 90-95%
- **复杂度**: 中等

## 具体实施计划

### Phase 1: 算法简化（立即实施）

#### 1.1 合并频谱处理
**文件**: `spectral_group_a.py`
- 合并降噪、去齿音、毛刺修复为单次 STFT/ISTFT
- 简化算法，移除平滑操作
- 使用固定参数，减少计算

#### 1.2 简化压缩器
**文件**: `dynamics.py`
- 多段压缩 → 单段压缩
- 移除频段分割
- 简化包络检测

#### 1.3 降低 FFT 尺寸
**文件**: `core.py`
- n_fft: 2048 → 1024
- hop_length: 512 → 1024
- 减少 50% 计算量

### Phase 2: C 库开发（1-2 天）

#### 2.1 开发 libsono_dsp.so
**文件**: `backend/services/dsp_native/`

```c
// 核心函数
void stft_float(const float* input, int n_samples, 
                float* output_real, float* output_imag,
                int n_fft, int hop_length);

void istft_float(const float* input_real, const float* input_imag,
                 float* output, int n_samples,
                 int n_fft, int hop_length);

void compressor_float(const float* input, float* output, int n_samples,
                      float threshold, float ratio, 
                      float attack_ms, float release_ms, int sr);

void filter_band_float(const float* input, float* output, int n_samples,
                       float low_freq, float high_freq, int sr);
```

#### 2.2 Python 封装
**文件**: `backend/services/dsp_native/__init__.py`
- ctypes 加载 .so 库
- 提供 Python 接口
- 失败时回退到 NumPy 实现

### Phase 3: 集成测试（半天）

#### 3.1 功能测试
- 验证所有处理步骤正常
- 对比音质变化

#### 3.2 性能测试
- 测量处理时间
- 对比优化前后

#### 3.3 Termux 兼容性测试
- 验证 C 库加载
- 测试内存使用

## 文件修改清单

### 修改文件
1. `backend/services/repair/repair_v2_2/core.py`
   - 降低 FFT 参数
   - 调整处理流程

2. `backend/services/repair/repair_v2_2/spectral_group_a.py`
   - 合并频谱处理
   - 简化算法

3. `backend/services/repair/repair_v2_2/dynamics.py`
   - 简化压缩器
   - 单段处理

4. `backend/services/repair/repair_v2_2/transient.py`
   - 进一步简化或移除

### 新增文件
1. `backend/services/dsp_native/stft.c`
2. `backend/services/dsp_native/compressor.c`
3. `backend/services/dsp_native/filter.c`
4. `backend/services/dsp_native/Makefile`

## 验证标准

### 性能目标
- [ ] 处理速度提升 5x 以上
- [ ] 内存使用 < 500MB
- [ ] 支持实时处理（< 1x 音频时长）

### 音质目标
- [ ] 主观听感评分 > 4/5
- [ ] THD+N < 0.5%
- [ ] 动态范围保留 > 80%

### 兼容性目标
- [ ] Termux 正常运行
- [ ] C 库加载失败时自动回退
- [ ] 支持 ARM64 架构

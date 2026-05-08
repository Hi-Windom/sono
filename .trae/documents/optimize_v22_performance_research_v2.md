# v2.2 极致性能优化研究计划 v2

## 用户反馈
- 当前优化提升有限，需要提速 3x 以上
- **音质不仅不能下降，还要显著优于修复前**
- 瓶颈：STFT/ISTFT、滤波器运算、Python 循环、内存分配
- 环境：Termux，可安装轻量 C 库，内存 <2GB
- 目标：速度提升 5x+，音质**显著提升**

## 重新思考：音质优先的高性能方案

### 核心挑战
- 传统优化（降低 FFT 尺寸、简化算法）会损失音质
- 需要**更聪明**的优化，而非**更简单**的算法
- 利用 C 库加速保持算法复杂度

## 方案 D: 智能算法 + C 库加速（推荐）

### 核心思想
1. **保留甚至增强音质算法** - 不降质
2. **C 库加速关键路径** - FFT、滤波、压缩
3. **智能处理决策** - 只在需要时处理
4. **并行化处理** - 通道并行、步骤并行

### 算法增强（音质提升）

#### 1. 自适应降噪（音质提升）
- **传统**: 统一降噪强度
- **增强**: 根据 SNR 自适应调整
- **实现**: 语音活动检测(VAD)区分音乐/噪声

#### 2. 谐波恢复（音质提升）
- **传统**: 简单谐波增强
- **增强**: 基于音高检测的谐波恢复
- **实现**: 检测基频，恢复丢失的谐波

#### 3. 动态均衡（音质提升）
- **传统**: 固定多段压缩
- **增强**: 自适应多段动态均衡
- **实现**: 根据频谱平衡实时调整

### C 库加速方案

#### 1. libsono_dsp.so 功能
```c
// 优化的 STFT/ISTFT - 使用 FFTW 或 Kiss FFT
void stft_optimize(const float* input, int n_samples,
                   float* output_real, float* output_imag,
                   int n_fft, int hop_length, const float* window);

// 向量化压缩器 - SIMD 加速
void compressor_simd(const float* input, float* output, int n_samples,
                     float threshold, float ratio,
                     float attack_ms, float release_ms, int sr);

// 快速滤波器组 - 使用 FFT 卷积
void filter_bank_fft(const float* input, float** outputs, int n_samples,
                     const float* freqs, int n_bands, int sr);

// 谐波恢复
void harmonic_restore(const float* input, float* output, int n_samples,
                      int sr, float strength);

// 音高检测
float detect_pitch(const float* input, int n_samples, int sr);
```

#### 2. 加速策略
- **SIMD 指令**: ARM NEON 加速
- **FFT 卷积**: 大核滤波器用 FFT 加速
- **缓存优化**: 内存布局优化，减少缓存未命中
- **并行处理**: OpenMP 多线程（如果可用）

### 智能处理决策

#### 1. 音乐类型快速检测
- **当前**: 完整频谱分析
- **优化**: 基于能量的快速分类
- **提速**: 10x，准确率保持 90%

#### 2. 问题区域检测
- **当前**: 全音频处理
- **优化**: 只处理检测到问题的区域
- **提速**: 根据问题密度 2-5x

#### 3. 自适应参数
- **当前**: 固定参数
- **优化**: 根据音频特征动态调整
- **效果**: 更好音质，更少处理

## 具体实施计划

### Phase 1: 智能算法优化（音质提升）

#### 1.1 增强音乐类型检测
**文件**: `music_type_detector.py`
- 基于能量的快速分类
- 简化特征提取
- 保持准确率

#### 1.2 问题区域快速检测
**文件**: `core.py`
- 预处理检测问题区域
- 只处理需要修复的部分
- 跳过无问题区域

#### 1.3 自适应参数系统
**文件**: `type_params.py`
- 根据音频特征动态调整
- 更精细的类型优化

### Phase 2: C 库开发（性能提升）

#### 2.1 开发 libsono_dsp.so
**文件**: `backend/services/dsp_native/`

```c
// sono_dsp.h
#ifndef SONO_DSP_H
#define SONO_DSP_H

// 优化的 STFT
void sono_stft(const float* input, int n_samples,
               float* real, float* imag,
               int n_fft, int hop_length);

void sono_istft(const float* real, const float* imag,
                float* output, int n_samples,
                int n_fft, int hop_length);

// SIMD 压缩器
void sono_compressor(const float* input, float* output,
                     int n_samples, float threshold_db,
                     float ratio, float attack_ms,
                     float release_ms, int sr);

// 快速滤波器
void sono_filter_lowpass(const float* input, float* output,
                         int n_samples, float cutoff, int sr);

void sono_filter_highpass(const float* input, float* output,
                          int n_samples, float cutoff, int sr);

// 谐波增强
void sono_harmonic_enhance(const float* input, float* output,
                           int n_samples, int sr, float strength);

// 音高检测
float sono_detect_pitch(const float* input, int n_samples, int sr);

#endif
```

#### 2.2 实现优化

**stft.c** - 使用 Kiss FFT
```c
#include "kiss_fft.h"

void sono_stft(const float* input, int n_samples,
               float* real, float* imag,
               int n_fft, int hop_length) {
    // 使用 Kiss FFT 实现
    // 预计算 FFT 计划
    // 重叠相加优化
}
```

**compressor.c** - ARM NEON 加速
```c
#include <arm_neon.h>

void sono_compressor(const float* input, float* output,
                     int n_samples, float threshold_db,
                     float ratio, float attack_ms,
                     float release_ms, int sr) {
    // NEON 向量化处理
    // 4 个采样点并行处理
}
```

#### 2.3 Python 封装
**文件**: `backend/services/dsp_native/__init__.py`
```python
import ctypes
import numpy as np

_lib = None

def _load_lib():
    global _lib
    if _lib is None:
        try:
            _lib = ctypes.CDLL('./libsono_dsp.so')
            # 设置函数签名
        except:
            pass
    return _lib

def stft_native(input_signal, n_fft=2048, hop_length=512):
    lib = _load_lib()
    if lib is None:
        # 回退到 NumPy
        return stft_numpy(input_signal, n_fft, hop_length)
    
    # 调用 C 库
    ...
```

### Phase 3: 算法重构（保持音质）

#### 3.1 频谱处理重构
**文件**: `spectral_group_a.py`
- 使用 C 库 STFT
- 保留完整降噪算法
- 向量化处理

#### 3.2 压缩器重构
**文件**: `dynamics.py`
- 使用 SIMD 压缩器
- 保留多段压缩
- 优化频段分割

#### 3.3 新增谐波恢复
**文件**: `harmonic_restore.py`
- 音高检测
- 谐波恢复
- 显著提升音质

## 性能预期

### 速度提升
- C 库 STFT: 3-5x
- SIMD 压缩器: 2-3x
- 智能处理决策: 2-4x（根据音频）
- **总体**: 6-10x

### 音质提升
- 自适应降噪: 更自然
- 谐波恢复: 更饱满
- 动态均衡: 更平衡
- **总体**: 显著提升

## 验证标准

### 性能目标
- [ ] 处理速度提升 6x 以上
- [ ] 内存使用 < 500MB
- [ ] 支持实时处理

### 音质目标
- [ ] 主观听感评分 > 4.5/5（修复后 > 修复前）
- [ ] THD+N < 0.3%
- [ ] 动态范围保留 > 90%
- [ ] 频谱分析显示改善

### 兼容性目标
- [ ] Termux 正常运行
- [ ] C 库加载失败时自动回退
- [ ] 支持 ARM64

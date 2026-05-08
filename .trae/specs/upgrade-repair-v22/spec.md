# AI 修复算法 v2.2 升级 Spec

## Why

当前 v2.1 修复算法虽然已在移动端可用，但存在以下问题：
1. **音质问题**：不同类型音乐（人声、器乐、电子、古典）处理效果不够精细
2. **性能瓶颈**：纯 Python/NumPy 实现，在移动端 Termux 环境下处理长音频仍有性能压力
3. **缺乏音乐类型感知**：使用统一参数处理所有类型音乐，无法针对性优化

v2.2 采用**桌面端与移动端隔离实现**策略：
- **桌面端 (v2.2)**：最佳效果，音质显著提升，不追求极致速度
- **移动端 (v2.2a)**：速度优先，确保音质不下降，精简处理流程

## 领域最新发展调研 (2024-2025)

### 1. Apollo - Band-sequence Modeling (Tencent 2024)
- **核心创新**: 显式频带分割模块，将频谱图划分为多个子带分别处理
- **技术亮点**: 
  - Roformer + TCN 捕获频率和时间特征
  - 低频保留 + 中高频重建的分离策略
  - GAN 框架平衡感知质量和失真
- **对 v2.2 的启发**: 采用子带处理策略，针对不同频段使用不同算法参数

### 2. AudioSR - Latent Diffusion Audio Super-Resolution
- **核心创新**: 基于扩散模型的通用音频超分辨率（任意输入 → 48kHz）
- **技术亮点**:
  - 替换式后处理保留原始低频信息
  - 多任务学习获得通用音频特征表示
  - 支持音乐、语音、环境音效全类型
- **对 v2.2 的启发**: 谐波重建时可参考扩散模型的迭代精化思想

### 3. BABE-2 - Diffusion-based Generative Equalizer (Aalto 2024)
- **核心创新**: 扩散模型用于生成式均衡，同时估计滤波器退化响应和重建音频
- **技术亮点**:
  - 生成式均衡概念：合成缺失频谱成分以达到目标频谱轮廓
  - 适用于历史音乐录音修复
  - 优化算法利用扩散模型先验
- **对 v2.2 的启发**: AI 音乐修复中的频谱均衡可采用生成式方法

### 4. AEROMamba - State Space Model for Audio SR
- **核心创新**: 用 Mamba (SSM) 替代 Attention 和 LSTM
- **技术亮点**:
  - 训练内存减少 2-4x
  - 推理速度提升 14x
  - 常数内存占用（不随序列长度增长）
- **对 v2.2 的启发**: 后续版本可考虑 SSM 架构替代 Transformer

### 5. 神经音频编解码器 artifact 去除 (2024)
- **关键发现**: 神经编解码器产生的 artifact 具有特定模式（音调伪影、周期性伪影）
- **技术趋势**: 
  - Improved RVQGAN: 8kbps 压缩 44.1kHz 音频，90倍压缩比
  - HILCodec: 轻量化实时流式编解码器
  - 码本崩溃问题的解决方案
- **对 v2.2 的启发**: AI 生成音频的 artifact 检测需要针对特定模式设计

## What Changes

### 版本区分
- **v2.2**: 桌面端完整版，`mobile_compatible: False`
- **v2.2a**: 移动端精简版，`mobile_compatible: True`

### 桌面端 v2.2 特性
- 新增 `backend/services/repair/repair_v2_2/` 目录
- 完整音乐类型检测模块
- C 原生库加速（可选）
- **子带分离处理**（借鉴 Apollo）：低频保留 + 中高频修复分离策略
- 完整频谱处理（Wiener 滤波、自适应去齿音、毛刺修复）
- **生成式谐波重建**（借鉴 BABE-2）：智能重建缺失谐波
- 多段动态压缩
- **AI Artifact 模式检测**（针对神经编解码器 artifact 优化）

### 移动端 v2.2a 特性
- 新增 `backend/services/repair/repair_v2_2a/` 目录
- 简化音乐类型检测
- 极速频谱处理（频谱减法替代 Wiener）
- 单段压缩替代多段压缩
- 确保 5x+ 速度提升

## v2.2 桌面端核心架构

### 1. 音乐类型自动检测
- 基于频谱特征、节奏特征、谐波结构自动识别音乐类型
- 支持类型：人声主导、纯器乐、电子音乐、古典音乐、流行音乐
- 检测结果影响后续处理参数选择

### 2. C 原生库加速（可选）
- 核心 DSP 运算（STFT/ISTFT、滤波、压缩）使用 C 实现
- 通过 ctypes 调用，无需额外依赖
- 提供纯 Python 回退方案

### 3. 子带分离处理（Apollo-inspired）
```
输入音频 → QMF 滤波器组 → 子带分离
    ├── 低频子带 (0-500Hz): 直接保留，最小处理
    ├── 中频子带 (500-4000Hz): Wiener 滤波 + 动态均衡
    └── 高频子带 (4000Hz+): 谐波重建 + 去齿音
              ↓
         子带重建 → 输出
```
- **低频保留策略**: 避免过度处理导致低频浑浊
- **中频修复策略**: 重点修复 AI 生成音频的频谱不连续性
- **高频重建策略**: 智能重建缺失谐波，增强空气感

### 4. 类型优化处理管线

| 音乐类型 | 优化重点 | 特殊处理 |
|---------|---------|---------|
| 人声主导 | 齿音抑制、气息自然度 | 增强去齿音，保护气音 |
| 纯器乐 | 谐波丰富度、空间感 | 增强谐波，优化混响感 |
| 电子音乐 | 低频控制、动态范围 | 收紧低频，增强冲击力 |
| 古典音乐 | 动态保护、细节保留 | 最小化处理，保护动态 |
| 流行音乐 | 平衡处理、响度优化 | 综合优化，适度增强 |

## v2.2a 移动端核心架构

**1. 简化类型检测**
- 基于能量分布快速分类
- 减少计算量，保持准确率

**2. 极速频谱处理**
- 单次 STFT/ISTFT
- 简化降噪算法
- 固定频段去齿音

**3. 单段压缩**
- 替代多段压缩
- 简化包络检测
- 全频段统一处理

## Impact

- 后端: `backend/services/repair/repair_v2_2/` (桌面端完整版)
- 后端: `backend/services/repair/repair_v2_2a/` (移动端精简版)
- 后端: `backend/services/audio_repair.py` (注册 v2.2 和 v2.2a)
- 后端: `backend/services/dsp_native/` (C 原生库，可选)

## 第三方库调研

### 1. 信号处理库
| 库名 | 用途 | Termux 兼容性 | 建议 |
|-----|------|--------------|------|
| **PyFFTW** | FFT 加速 | ✓ | 桌面端首选，需 FFTW3 C 库 |
| **mkl-fft** | Intel MKL FFT | ✗ | 仅 x86，移动端不可用 |
| **cupy** | GPU 加速 | ✗ | Termux 不支持 CUDA |
| **numba** | JIT 编译 | ✓ | 移动端可用，加速效果显著 |
| **scipy.signal** | 滤波/处理 | ✓ | 基础依赖，已集成 |

### 2. 音频处理专用库
| 库名 | 用途 | Termux 兼容性 | 建议 |
|-----|------|--------------|------|
| **pedalboard** | 音频效果 | ✓ | 桌面端高质量效果器 |
| **sox** | 音频处理 | ✓ | 命令行工具，可绑定 |
| **rubberband** | 时间拉伸 | ✓ | 高质量音高/速度调整 |
| **aubio** | 音频分析 | ✓ | 节拍/音高检测 |

### 3. 深度学习相关
| 库名 | 用途 | Termux 兼容性 | 建议 |
|-----|------|--------------|------|
| **onnxruntime** | 模型推理 | ✓ | 轻量级，移动端可用 |
| **tflite** | 移动推理 | ✓ | Android 原生支持 |
| **ncnn** | 移动端推理 | ✓ | 腾讯开源，Termux 可用 |

## ADDED Requirements

### Requirement: v2.2 桌面端修复算法

系统 SHALL 提供 v2.2 桌面端版本的音频修复算法，具备以下特性：

#### 特性 1: 音乐类型自动检测
- 基于频谱质心、带宽、零交叉率、谐波结构检测
- 检测置信度 > 0.7 时启用类型优化
- 检测维度：vocal_ratio, harmonic_complexity, rhythmic_regularity, spectral_contrast

#### 特性 2: 子带分离处理
- **QMF 滤波器组**: 完美重构子带分离
- **低频保留**: 0-500Hz 直接通过，避免浑浊
- **中频修复**: 500-4000Hz Wiener 滤波 + 动态均衡
- **高频重建**: 4000Hz+ 谐波重建 + 自适应去齿音

#### 特性 3: 生成式谐波重建 (BABE-2 inspired)
- **谐波检测**: 识别缺失或弱化的谐波成分
- **智能重建**: 基于音乐类型生成自然谐波
- **相位保持**: 维持原始相位关系，避免失真
- **自适应强度**: 根据检测到的音乐类型调整重建强度

#### 特性 4: 多段动态压缩
- 3 段压缩（低/中/高频）
- 自适应阈值
- 保留动态范围

#### 特性 5: AI Artifact 模式检测
- **周期性伪影检测**: 检测神经编解码器产生的音调伪影
- **频谱不连续性检测**: 识别 AI 生成的频谱跳变
- **瞬态失真检测**: 定位瞬态信号的处理异常
- **针对性修复**: 根据检测到的 artifact 类型应用对应修复算法

## 算法实现参考

### 1. 子带分离实现 (Apollo-inspired)
```python
# QMF 滤波器组实现
from scipy.signal import firwin, lfilter

def create_qmf_bank(num_bands=4, filter_len=128):
    """创建 QMF 滤波器组实现完美重构"""
    # 原型低通滤波器
    prototype = firwin(filter_len, 1.0 / num_bands)
    # 调制生成各子带滤波器
    filters = []
    for k in range(num_bands):
        modulation = np.cos(np.pi * (k + 0.5) * np.arange(filter_len))
        filters.append(prototype * modulation)
    return filters

def subband_process(audio, filters, process_fn):
    """子带分离处理"""
    subbands = [lfilter(f, 1, audio) for f in filters]
    processed = [process_fn(sb, i) for i, sb in enumerate(subbands)]
    return sum(processed)  # 重建
```

### 2. 生成式谐波重建 (BABE-2 inspired)
```python
def harmonic_reconstruction(audio, sr, music_type):
    """
    智能谐波重建
    - 检测基频和谐波结构
    - 基于音乐类型决定重建策略
    - 保持相位连续性
    """
    # 1. 基频检测 (YIN 算法或自相关)
    f0 = detect_f0(audio, sr)
    
    # 2. 谐波检测
    harmonics = detect_harmonics(audio, sr, f0)
    
    # 3. 缺失谐波重建
    reconstructed = np.zeros_like(audio)
    for h in range(1, 20):  # 前20次谐波
        harmonic_freq = f0 * h
        if harmonic_freq > sr / 2:
            break
        
        # 检查该谐波是否存在
        if not harmonics[h]['present']:
            # 基于音乐类型生成谐波
            amplitude = estimate_harmonic_amplitude(h, music_type, harmonics)
            phase = estimate_harmonic_phase(h, harmonics)
            reconstructed += generate_sine(harmonic_freq, amplitude, phase, len(audio))
    
    return audio + reconstructed * 0.3  # 混合比例可调
```

### 3. AI Artifact 检测
```python
def detect_ai_artifacts(audio, sr):
    """
    检测 AI 生成音频的 artifact
    """
    artifacts = {
        'periodic': [],      # 周期性伪影
        'spectral_gaps': [], # 频谱间隙
        'transient_distortion': []  # 瞬态失真
    }
    
    # 1. 周期性伪影检测 (神经编解码器常见)
    stft = np.abs(librosa.stft(audio))
    # 检测频谱中的周期性模式
    for freq_bin in range(stft.shape[0]):
        autocorr = np.correlate(stft[freq_bin], stft[freq_bin], mode='full')
        peaks = find_peaks(autocorr[autocorr.size//2:])
        if len(peaks) > 0 and peaks[0] < 10:  # 短周期 = 伪影
            artifacts['periodic'].append(freq_bin)
    
    # 2. 频谱不连续性检测
    spectral_diff = np.diff(stft, axis=1)
    discontinuities = np.where(np.abs(spectral_diff) > threshold)
    artifacts['spectral_gaps'] = list(zip(discontinuities[0], discontinuities[1]))
    
    return artifacts
```

### 4. 推荐技术栈

#### 桌面端 v2.2
| 组件 | 推荐方案 | 备选方案 |
|-----|---------|---------|
| FFT | PyFFTW | scipy.fft |
| 滤波 | scipy.signal.sosfilt | C 实现 |
| 效果器 | pedalboard | 自研 |
| 分析 | librosa (仅训练) | 自研 DSP |

#### 移动端 v2.2a
| 组件 | 推荐方案 | 优化策略 |
|-----|---------|---------|
| FFT | numpy.fft | 固定长度缓存 |
| 滤波 | scipy.signal.lfilter | 降采样处理 |
| 效果器 | 自研简化版 | 查表法 |
| 分析 | 能量检测 | 避免复杂特征 |

### Requirement: v2.2a 移动端修复算法

系统 SHALL 提供 v2.2a 移动端版本的音频修复算法，具备以下特性：

#### 特性 1: 简化类型检测
- 基于能量快速分类
- 减少计算量

#### 特性 2: 极速频谱处理
- 单次 STFT/ISTFT
- 频谱减法降噪（简化）
- 固定频段去齿音

#### 特性 3: 单段压缩
- 全频段统一处理
- 简化包络检测

#### 特性 4: 性能目标
- 速度提升 5x+
- 内存 < 300MB
- 音质不下降

### Requirement: 修复模式

v2.2 和 v2.2a SHALL 提供以下修复模式：

#### 模式 1: 智能修复（默认）
- 自动检测音乐类型
- 应用类型优化的处理参数

#### 模式 2: 人声修复
- 针对人声优化
- 重点：去齿音、气息自然度、清晰度

#### 模式 3: 器乐修复
- 针对器乐优化
- 重点：谐波丰富度、空间感

#### 模式 4: 深度修复
- 最强修复力度
- 适合严重损坏的 AI 音频

#### 模式 5: 温和优化
- 轻微处理，保留原始音质

#### 模式 6: HiFi 模式（仅桌面端）
- 最小处理，最高音质保真度

## MODIFIED Requirements

### Requirement: 版本配置更新

`backend/services/audio_repair.py` 中的 `ALGORITHM_VERSIONS` SHALL 新增：

**v2.2 桌面端配置：**
- name: "v2.2"
- label: "v2.2 桌面版"
- description: "最佳音质，完整处理"
- mobile_compatible: False
- repair_fn: repair_audio_v2_2

**v2.2a 移动端配置：**
- name: "v2.2a"
- label: "v2.2a 移动版"
- description: "速度优先，精简处理"
- mobile_compatible: True
- repair_fn: repair_audio_v2_2a

## REMOVED Requirements

无移除项。v1.0/v1.1/v1.2/v2.0/v2.1/v2.2/v2.2a 保留供选择。

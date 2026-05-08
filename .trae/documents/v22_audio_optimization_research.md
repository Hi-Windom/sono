# v2.2 音频处理性能优化研究报告

## 用户反馈
- 问题：瞬态修复和频谱修复耗时过长，需要提速 3 倍以上
- 优化策略：使用 C/C++ 原生库
- 依赖接受度：完全接受 PyTorch、ONNX Runtime 等深度学习框架

## 领域最新发展调研

### 1. 深度学习音频处理模型（2024-2025）

#### 1.1 DeepFilterNet
- **GitHub**: https://github.com/Rikorose/DeepFilterNet
- **Stars**: 4.1k
- **特点**: 实时语音增强，使用深度滤波技术
- **性能**: 实时因子 0.02（比实时快 50 倍）
- **模型大小**: 约 2-5MB
- **支持格式**: PyTorch, ONNX, TFLite
- **适用场景**: 降噪、语音增强

#### 1.2 DTLN (Dual-Signal Transformation LSTM Network)
- **GitHub**: https://github.com/breizhn/DTLN
- **Stars**: 713
- **特点**: 实时语音去噪，TensorFlow 2.x 实现
- **性能**: 实时因子 0.005（比实时快 200 倍）
- **模型大小**: 约 1-2MB
- **支持格式**: TF-Lite, ONNX
- **适用场景**: 实时降噪、移动设备

#### 1.3 ClearerVoice-Studio
- **GitHub**: https://github.com/modelscope/ClearerVoice-Studio
- **Stars**: 4.1k
- **特点**: 阿里开源，支持语音增强、分离、目标说话人提取
- **性能**: 实时处理
- **模型大小**: 5-20MB
- **支持格式**: PyTorch
- **适用场景**: 语音增强、人声分离

#### 1.4 denoisers (PyTorch)
- **GitHub**: https://github.com/will-rice/denoisers
- **特点**: WaveUNet + UNet1D 架构
- **性能**: 高效实时处理
- **适用场景**: 音频降噪

### 2. 瞬态检测算法发展

#### 2.1 librosa onset detection
- 基于频谱变化的瞬态检测
- 多种 onset strength 计算方法
- 性能：中等，纯 Python

#### 2.2 aubio
- C 语言实现的音频分析库
- 实时 onset 检测
- Python 绑定可用
- 性能：高

#### 2.3 传统算法优化方向
- 能量差分法
- 频谱通量法
- 相位偏差法

### 3. C/C++ 高性能音频处理库

#### 3.1 RNNoise
- **GitHub**: https://github.com/xiph/rnnoise
- **特点**: Mozilla 开源，基于 RNN 的降噪
- **性能**: 极快，纯 C 实现
- **模型大小**: 约 50KB
- **适用场景**: 实时降噪

#### 3.2 JAXdsp
- **GitHub**: https://github.com/cifkao/jax-spectral
- **特点**: 基于 JAX 的可微分音频处理
- **性能**: GPU 加速，自动微分
- **适用场景**: 研究、可微分 DSP

## 优化方案设计

### 方案 A: 集成 DeepFilterNet（推荐）

#### 优势
1. **速度**: 比实时快 50 倍，完全满足 3x 提速要求
2. **效果**: SOTA 降噪效果，音质损失小
3. **部署**: 支持 ONNX，移动端友好
4. **维护**: 活跃开源项目，持续更新

#### 实现步骤
1. 下载 DeepFilterNet ONNX 模型（约 2MB）
2. 使用 ONNX Runtime 进行推理
3. 替换现有频谱修复模块
4. 保持 API 兼容

#### 代码示例
```python
import onnxruntime as ort
import numpy as np

class DeepFilterNetDenoiser:
    def __init__(self, model_path):
        self.session = ort.InferenceSession(model_path)
        
    def process(self, audio, sr):
        # 预处理
        # ONNX 推理
        # 后处理
        return denoised_audio
```

### 方案 B: 使用 RNNoise

#### 优势
1. **速度**: 极快，纯 C 实现
2. **大小**: 模型仅 50KB
3. **无依赖**: 不需要 PyTorch/ONNX
4. **成熟**: Mozilla 出品，稳定可靠

#### 劣势
1. 效果略逊于 DeepFilterNet
2. 仅支持降噪，不支持瞬态修复

### 方案 C: C/C++ 重写关键算法

#### 重写模块
1. **STFT/ISTFT**: 使用 FFTW 或 Intel MKL
2. **降噪**: Wiener 滤波 C 实现
3. **瞬态检测**: 能量差分法 C 实现

#### 优势
1. **速度**: 5-20 倍加速
2. **控制**: 完全控制算法细节
3. **无模型**: 不依赖预训练模型

#### 劣势
1. 开发周期长
2. 维护成本高
3. 效果不如深度学习模型

## 推荐方案

### 第一阶段：集成 DeepFilterNet
- 使用 ONNX Runtime 推理
- 替换频谱修复模块
- 预期提速: 10-50 倍

### 第二阶段：优化瞬态检测
- 使用 aubio 或简化算法
- 或集成轻量级 onset 检测模型
- 预期提速: 3-5 倍

### 第三阶段（可选）: C/C++ 优化
- 对剩余瓶颈进行 C/C++ 重写
- 使用 SIMD 指令优化

## 实施计划

### 任务 1: 集成 DeepFilterNet
- 下载 ONNX 模型
- 封装 ONNX Runtime 推理类
- 替换 spectral_group_a.py
- 测试效果和性能

### 任务 2: 优化瞬态修复
- 调研 aubio 集成方案
- 或使用简化 onset 检测算法
- 替换 transient.py

### 任务 3: 性能测试
- 对比优化前后处理时间
- 验证音质指标
- 移动端性能测试

### 任务 4: 打包发布
- 包含 ONNX 模型
- 更新依赖配置
- 重新打包 Android 发布包

## 风险评估

### 技术风险
1. **模型兼容性**: ONNX Runtime 在移动端的支持
2. **内存占用**: 模型加载后的内存使用
3. **效果退化**: 深度学习模型可能过度处理

### 缓解措施
1. 使用 TFLite 作为移动端备选
2. 模型量化（INT8）减少内存
3. 提供强度调节参数

## 预期效果

- **频谱修复**: 提速 10-50 倍
- **瞬态修复**: 提速 3-5 倍
- **整体处理**: 提速 5-10 倍
- **音质**: 保持或提升

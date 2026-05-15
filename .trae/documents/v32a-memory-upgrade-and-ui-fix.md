# v3.2a+ 内存扩容 + 算法选择器对齐 实施计划

## 变更 1：算法选择下拉框右对齐

### 问题
`AlgorithmSelector` 的下拉列表容器使用 `left-0 right-0` 定位，导致下拉框相对按钮左边缘对齐。当按钮位于页面右侧时，下拉框会向左溢出，视觉上不协调。

### 修改
**文件**: `src/components/AlgorithmSelector.tsx` 第 114 行

将：
```tsx
className="absolute z-50 mt-1 left-0 right-0 min-w-[280px] ..."
```
改为：
```tsx
className="absolute z-50 mt-1 right-0 min-w-[280px] ..."
```

移除 `left-0`，保留 `right-0`，使下拉框容器始终从右边缘向左展开，与页面右侧对齐。

---

## 变更 2：v3.2a+ 内存系数提升至 +300%

### 问题
当前 v3.2a+ 内存系数为 +40%（`peak_temp += upsampled_samples * elem_size * 0.4`），限制了移动增强版的能力。提升至 +300% 后可以启用更多处理步骤。

### 2.1 更新内存估算

**文件**: `backend/services/memory_guard.py` 第 76-77 行

将：
```python
elif algorithm_version == "v3.2a+":
    peak_temp += upsampled_samples * elem_size * 0.4
```
改为：
```python
elif algorithm_version == "v3.2a+":
    peak_temp += upsampled_samples * elem_size * 3.0
```

### 2.2 增强 v3.2a+ 核心算法

**文件**: `backend/services/repair/repair_v3_2ap/core.py`

利用 300% 内存空间，增加以下处理能力：

| 增强项 | 当前实现 | 增强后 |
|--------|---------|--------|
| AI 修复分辨率 | N_FFT=2048 | N_FFT=4096（更高频率分辨率） |
| 前视压缩器 | 3ms look-ahead | 10ms look-ahead + 软膝曲线 |
| 空间感 | 1 tap 早期反射 + 50ms 混响 | 3 tap 早期反射 + 100ms 混响 + 频率相关立体声加宽 |
| 共振抑制 | 基础版（来自 v3.2a） | 增强版：频域+时域双域检测 + 帧间平滑 |
| 两遍处理 | 仅 3 个核心步骤 | 全步骤两遍（第一遍 1.0 系数，第二遍 0.3 系数） |
| 多频段压缩 | 无 | 3 频段压缩器（低频 20-300Hz、中频 300-4000Hz、高频 4000-20000Hz） |

具体修改：

#### 2.2.1 升级 `_lookahead_compressor_lite`
- lookahead 从 3ms 提升到 10ms
- 从硬膝改为软膝曲线（与桌面版 v3.2 smart_compressor 相同的 knee 逻辑）
- 增加 RMS + 峰值混合包络检测

#### 2.2.2 升级 `_vocal_ai_repair_adaptive_lite`
- N_FFT 从 2048 提升到 4096
- 增加频域自适应阈值分段（3 段：0-2kHz, 2-8kHz, 8-20kHz）

#### 2.2.3 升级 `_vocal_spatial_lite_enhanced`
- 早期反射从 1 tap 增加到 3 tap（5ms, 10ms, 15ms）
- 混响尾音从 50ms 增加到 100ms
- 增加频率相关立体声加宽（低于 200Hz 为单声道）

#### 2.2.4 新增 `_resonance_suppress_enhanced_lite`
- 从 v3.2a 的 `_resonance_suppress_lite` 升级
- 增加时域平滑（帧间一阶低通滤波）
- 频域 + 时域双域检测

#### 2.2.5 新增 `_vocal_multiband_compressor_lite`
- 3 频段压缩：低频 20-300Hz、中频 300-4000Hz、高频 4000-20000Hz
- 每频段独立阈值/比率
- 频段间交叉渐变防伪影

#### 2.2.6 升级两遍处理
- 第二遍从仅 3 个步骤扩展到全步骤
- 第二遍系数保持 0.3

#### 2.2.7 更新 `process_vocal_track` 管线
- 替换 `_lookahead_compressor_lite` 为升级版
- 替换 `_vocal_ai_repair_adaptive_lite` 为升级版
- 替换 `_vocal_spatial_lite_enhanced` 为升级版
- 替换 `_resonance_suppress_lite` 为 `_resonance_suppress_enhanced_lite`
- 新增 `_vocal_multiband_compressor_lite` 步骤（在 `_transparent_compress` 之前）

---

## 实施顺序

1. **修改 AlgorithmSelector.tsx** — 下拉框右对齐（单文件修改，无依赖）
2. **修改 memory_guard.py** — v3.2a+ 内存系数 +300%（单文件修改，无依赖）
3. **增强 repair_v3_2ap/core.py** — 利用 300% 内存增加处理能力（依赖步骤 2）

步骤 1 和 2 可并行执行，步骤 3 在步骤 2 之后执行。
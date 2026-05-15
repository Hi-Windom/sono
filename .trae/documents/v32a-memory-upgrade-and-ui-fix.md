# v3.2a+ 内存扩容 + 算法选择器对齐 + 移除两遍处理 实施计划

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

## 变更 2：移除现有的两遍处理实现

### 问题
v3.2+ 和 v3.2a+ 当前实现了两遍处理（`repair_audio` 中先调用父版本处理，再对结果做第二遍微调）。两遍处理不合理，应移除。

### 2.1 移除 v3.2+ 两遍处理

**文件**: `backend/services/repair/repair_v3_2p/core.py`

- 删除 `repair_audio` 函数中的两遍处理逻辑
- 改为直接委托给 v3.2 的 `repair_audio`（即 `_v3_2_repair_audio`）
- 保留 v3.2+ 特有的算法函数（`_lookahead_compressor`、`_vocal_ai_repair_dual_resolution`、`_resonance_suppress_enhanced`、`_vocal_spatial_enhanced`）
- `process_vocal_track` 和 `_repair_single_track` 保持使用 v3.2+ 特有函数（单遍处理）

### 2.2 移除 v3.2a+ 两遍处理

**文件**: `backend/services/repair/repair_v3_2ap/core.py`

- 删除 `repair_audio` 函数中的两遍处理逻辑
- 改为直接委托给 v3.2a 的 `repair_audio`（即 `_v3_2a_repair_audio`）
- 保留 v3.2a+ 特有的算法函数
- `process_vocal_track` 保持使用 v3.2a+ 特有函数（单遍处理）

---

## 变更 3：v3.2a+ 内存系数提升至 +300%

### 问题
当前 v3.2a+ 内存系数为 +40%（`peak_temp += upsampled_samples * elem_size * 0.4`），限制了移动增强版的能力。提升至 +300% 后可以启用更多处理步骤。

### 3.1 更新内存估算

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

### 3.2 增强 v3.2a+ 核心算法

**文件**: `backend/services/repair/repair_v3_2ap/core.py`

利用 300% 内存空间，增加以下处理能力：

| 增强项 | 当前实现 | 增强后 |
|--------|---------|--------|
| AI 修复分辨率 | N_FFT=2048 | N_FFT=4096（更高频率分辨率） |
| 前视压缩器 | 3ms look-ahead | 10ms look-ahead + 软膝曲线 |
| 空间感 | 1 tap 早期反射 + 50ms 混响 | 3 tap 早期反射 + 100ms 混响 + 频率相关立体声加宽 |
| 共振抑制 | 基础版（来自 v3.2a） | 增强版：频域+时域双域检测 + 帧间平滑 |
| 多频段压缩 | 无 | 3 频段压缩器（低频 20-300Hz、中频 300-4000Hz、高频 4000-20000Hz） |

具体修改：

#### 3.2.1 升级 `_lookahead_compressor_lite`
- lookahead 从 3ms 提升到 10ms
- 从硬膝改为软膝曲线（与桌面版 v3.2 smart_compressor 相同的 knee 逻辑）
- 增加 RMS + 峰值混合包络检测

#### 3.2.2 升级 `_vocal_ai_repair_adaptive_lite`
- N_FFT 从 2048 提升到 4096
- 增加频域自适应阈值分段（3 段：0-2kHz, 2-8kHz, 8-20kHz）

#### 3.2.3 升级 `_vocal_spatial_lite_enhanced`
- 早期反射从 1 tap 增加到 3 tap（5ms, 10ms, 15ms）
- 混响尾音从 50ms 增加到 100ms
- 增加频率相关立体声加宽（低于 200Hz 为单声道）

#### 3.2.4 新增 `_resonance_suppress_enhanced_lite`
- 从 v3.2a 的 `_resonance_suppress_lite` 升级
- 增加时域平滑（帧间一阶低通滤波）
- 频域 + 时域双域检测

#### 3.2.5 新增 `_vocal_multiband_compressor_lite`
- 3 频段压缩：低频 20-300Hz、中频 300-4000Hz、高频 4000-20000Hz
- 每频段独立阈值/比率
- 频段间交叉渐变防伪影

#### 3.2.6 更新 `process_vocal_track` 管线
- 替换 `_lookahead_compressor_lite` 为升级版
- 替换 `_vocal_ai_repair_adaptive_lite` 为升级版
- 替换 `_vocal_spatial_lite_enhanced` 为升级版
- 替换 `_resonance_suppress_lite` 为 `_resonance_suppress_enhanced_lite`
- 新增 `_vocal_multiband_compressor_lite` 步骤（在 `_transparent_compress` 之前）

---

## 实施顺序

1. **修改 AlgorithmSelector.tsx** — 下拉框右对齐（单文件修改，无依赖）
2. **修改 memory_guard.py** — v3.2a+ 内存系数 +300%（单文件修改，无依赖）
3. **移除 v3.2+ 两遍处理** — 修改 repair_v3_2p/core.py（无依赖）
4. **移除 v3.2a+ 两遍处理** — 修改 repair_v3_2ap/core.py（无依赖）
5. **增强 repair_v3_2ap/core.py** — 利用 300% 内存增加处理能力（依赖步骤 2、4）

步骤 1、2、3、4 可并行执行，步骤 5 在步骤 2 和 4 之后执行。
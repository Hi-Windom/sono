# v3.3 双轨 Bug 修复 + 进度通知细化 实施计划

## 问题 1：`original_dtype` 未定义错误

### 根因分析
- **位置**: `backend/services/repair/repair_v3_3/mixback.py` L157
- **函数**: `_residual_refine_1d(original, processed, strength)`
- **原因**: 函数末尾 `return np.clip(result, -1.0, 1.0).astype(original_dtype)` 使用了未定义的变量 `original_dtype`
- **触发条件**: v3.3+ / v3.3a+ 双轨模式下 `residual_refine > 0` 时调用此函数

### 修复方案
- 将 `original_dtype` 改为 `processed.dtype`（processed 是函数参数，始终可用）
- 同时检查 mixback.py 中其他函数是否有类似问题

### 涉及文件
| 文件 | 修改 |
|------|------|
| `backend/services/repair/repair_v3_3/mixback.py` | L157: `original_dtype` → `processed.dtype` |

---

## 问题 2：细化前端进度通知颗粒度

### 现状分析
当前双轨进度步骤（v3.3 `_repair_dual_track`）：
```
0.05 加载双轨音频
0.15 双轨预分析
0.25 处理人声轨
0.50 处理伴奏轨
0.70 混音
0.85 导出
1.0 完成
```

**问题**: Vocal 轨处理（0.25→0.50）和 Inst 轨处理（0.50→0.70）内部有多个子阶段，但没有任何中间进度更新，导致进度条跳跃。

### 改进方案

#### 步骤 2a：vocal.py 增加 progress_callback 支持
- `process_vocal_v33(y, sr, params, progress_callback=None, progress_start=0.0, progress_end=1.0)`
- 每个子阶段（f0_harmonic → microtremor_breath → transient_protect → de_shimmer → phase_diffuse → noise_floor）报告进度
- 将子阶段进度映射到 `[progress_start, progress_end]` 区间

#### 步骤 2b：inst.py 增加 progress_callback 支持
- `process_inst_v33(y, sr, params, progress_callback=None, progress_start=0.0, progress_end=1.0)`
- 每个子阶段（spectral_naturalize → harmonic_deregularize → spatial_enhance → transient_protect → upward_compression）报告进度

#### 步骤 2c：mixback.py 增加 progress_callback 支持
- `mixback(vocal, accompaniment, sr, params, progress_callback=None, progress_start=0.0, progress_end=1.0)`
- 每个子阶段（cross_bleed → loudness_match → soft_limit → residual_refine）报告进度

#### 步骤 2d：更新 v3.3 core.py `_repair_dual_track`
- 将 `progress_callback` 传递给 `process_vocal_v33`、`process_inst_v33`、`mixback`
- 映射进度区间：
  - Vocal 处理: 0.25 → 0.50
  - Inst 处理: 0.50 → 0.70
  - Mixback: 0.70 → 0.85

#### 步骤 2e：更新 v3.3+ core.py `_repair_dual_track`
- 同上，将 progress_callback 传递给 vocal/inst/mixback

#### 步骤 2f：更新 v3.3a core.py `_repair_dual_track`
- 同上，移动版精简管线

#### 步骤 2g：更新 v3.3a+ core.py `_repair_dual_track`
- 同上，移动增强版

---

## 实施顺序

1. **步骤 1**（修复 `original_dtype`）— 1 行修改，立即解决崩溃
2. **步骤 2a**（vocal.py 进度回调）— 核心改动
3. **步骤 2b**（inst.py 进度回调）— 核心改动
4. **步骤 2c**（mixback.py 进度回调）— 核心改动
5. **步骤 2d**（v3.3 core.py 传递进度）— 集成
6. **步骤 2e**（v3.3+ core.py 传递进度）— 集成
7. **步骤 2f**（v3.3a core.py 传递进度）— 集成
8. **步骤 2g**（v3.3a+ core.py 传递进度）— 集成

---

## 文件变更清单

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `backend/services/repair/repair_v3_3/mixback.py` | 修改 | 修复 `original_dtype` 错误 |
| 2 | `backend/services/repair/repair_v3_3/vocal.py` | 修改 | 增加 progress_callback 参数 |
| 3 | `backend/services/repair/repair_v3_3/inst.py` | 修改 | 增加 progress_callback 参数 |
| 4 | `backend/services/repair/repair_v3_3/mixback.py` | 修改 | 增加 progress_callback 参数 |
| 5 | `backend/services/repair/repair_v3_3/core.py` | 修改 | 传递 progress_callback |
| 6 | `backend/services/repair/repair_v3_3p/core.py` | 修改 | 传递 progress_callback |
| 7 | `backend/services/repair/repair_v3_3a/core.py` | 修改 | 传递 progress_callback |
| 8 | `backend/services/repair/repair_v3_3ap/core.py` | 修改 | 传递 progress_callback |

---

## 注意事项

1. `progress_callback` 签名统一为 `(progress: float, step: str)`，progress 范围 0.0~1.0
2. 子阶段进度映射使用线性插值：`p = start + (end - start) * (sub_progress / total_steps)`
3. 当 `progress_callback` 为 None 时跳过，保持向后兼容
4. 单轨模式不受影响（不传递 progress_callback）
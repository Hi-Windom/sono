# v3.3 UI 层修复与 AI 检测审计计划

## 问题 1：移动端双轨算法列表没有 v3.3a/v3.3a+

### 根因分析
在 `AIRepairPanel.tsx` 第 169-173 行：
```typescript
const filteredAlgorithms = useMemo(() => {
  if (isDualTrackMode) {
    return availableAlgorithms.filter(a => a.supportsDualTrack === true);
  }
  return availableAlgorithms;
}, [isDualTrackMode, availableAlgorithms]);
```

双轨模式下只显示 `supportsDualTrack === true` 的算法。v3.3a/v3.3a+ 在 `audio_repair.py` 中 `supports_dual_track: false`。

### 修复方案
移动端双轨模式下，需要同时显示支持双轨的算法和移动端兼容的算法：

```typescript
const filteredAlgorithms = useMemo(() => {
  if (isDualTrackMode) {
    // 双轨模式：显示支持双轨的算法 + 移动端兼容的单轨算法
    return availableAlgorithms.filter(a => 
      a.supportsDualTrack === true || 
      (a.mobile_compatible !== false && a.tags && a.tags.includes('mobile'))
    );
  }
  // 非双轨移动端：只显示移动端兼容的
  if (isMobile) {
    return availableAlgorithms.filter(a => a.mobile_compatible !== false);
  }
  return availableAlgorithms;
}, [isDualTrackMode, availableAlgorithms, isMobile]);
```

但双轨需要的是人声+伴奏分别处理的能力。v3.3a/v3.3a+ 是单轨处理算法。在双轨模式下，v3.3a/v3.3a+ 实际上可以作为**单轨处理替代方案**使用（用户分别处理人声和伴奏）。

**实际决策**：v3.3a/v3.3a+ 在双轨模式下应该可以显示，因为双轨 UI 允许用户为人声和伴奏选择不同的算法。需要在 `audio_repair.py` 中检查双轨模式下是否真的需要特殊支持。

检查双轨 API 端点（`/api/v1/repair-dual`）：它分别对人声和伴奏调用不同的修复模块。v3.3a/v3.3a+ 的 `repair_audio` 函数接受单轨输入，可以被双轨 API 调用。

**修改**：在 `audio_repair.py` 中将 v3.3a/v3.3a+ 的 `supports_dual_track` 改为 `true`，因为它们可以分别处理人声和伴奏。

## 问题 2：第三方 AI 检测报告下降未实现

### 根因分析
第三方报告显示：
- Spectral analysis: 纯AI 80%（最有可能）
- Temporal analysis: 纯AI 不太可能 21%，混合模式 78%

这意味着 v3.3 的**统计自然化**算法虽然实现了，但：
1. **频谱特征**仍然被检测为纯 AI（80%）——说明谐波规整、频谱补全等处理强度不够或方向不对
2. **时间特征**有一定改善（混合模式 78%）——说明瞬态保护有一定效果

### 需要审计的代码路径

#### A. v3.3 后端算法实现审计
需要检查以下文件是否正确实现了预期功能：

1. `repair_v3_3/spectral.py`：
   - `_perceptual_spectral_completion`：引导滤波 + 谐波梳状增强是否真正在 f0 整数倍操作？
   - `_noise_floor_shape`：1/f 粉噪注入强度是否足够（-78~-85dB 可能太弱）？
   - `_harmonic_deregularize`：能量扰动是否真正破坏了 AI 谐波规整？
   - `_subband_decorrelate`：all-pass 相位扰动是否有效？

2. `repair_v3_3/phase.py`：
   - `_phase_naturalize`：MS 扩散和群延时校正是否生效？
   - `_group_delay_correct`：STFT 相位扰动幅度是否足够？

3. `repair_v3_3/dynamic.py`：
   - `_dynamic_naturalize`：上行压缩是否真正改变了动态特征？

#### B. 默认参数强度审计
检查 `ALGORITHM_VERSIONS` 中 v3.3 系列的默认参数值：
- `spectral_naturalize: 0.6` — 可能不够强
- `noise_floor_shape: 0.4` — 可能不够强
- `harmonic_deregularize: 0.5` — 可能不够强
- `phase_naturalize: 0.3` — 可能不够强

#### C. Preset 参数审计（v3.3+）
Anti-Detect preset 的参数是否真的针对 AI 检测器优化？

### 实施步骤

#### 第 1 步：修复移动端双轨算法列表

**文件**: `backend/services/audio_repair.py`
- 将 v3.3a/v3.3a+ 的 `supports_dual_track` 改为 `true`
- 原因：双轨 API 分别处理人声和伴奏，v3.3a/v3.3a+ 的单轨处理能力完全满足需求

**文件**: `src/components/AIRepairPanel.tsx`
- 修改 `filteredAlgorithms` 逻辑，移动端显示 `mobile_compatible !== false` 的所有算法
- 双轨模式下也显示移动端兼容的算法

#### 第 2 步：v3.3 算法强度调优

**文件**: `backend/services/audio_repair.py`
- 提高 v3.3/v3.3+ 默认参数强度：
  - `spectral_naturalize: 0.6 → 0.8`
  - `noise_floor_shape: 0.4 → 0.6`
  - `harmonic_deregularize: 0.5 → 0.7`
  - `phase_naturalize: 0.3 → 0.5`

**文件**: `backend/services/repair/repair_v3_3p/config.py`
- 提高 Anti-Detect preset 强度

#### 第 3 步：v3.3 算法效果增强

需要针对 AI 检测器的关键特征进行更有针对性的处理：

1. **频谱规整检测**（Spectral regularity）：
   - AI 生成的音频谐波幅度比过于规律
   - 需要更强的谐波不规则性注入
   - 修改 `_harmonic_deregularize`：增加扰动幅度从 ±0.5% 到 ±2-3%

2. **噪声地板检测**（Noise floor analysis）：
   - AI 模型噪声地板过于平坦
   - 需要更强的 1/f 噪声注入
   - 修改 `_noise_floor_shape`：从 -78~-85dB 提升到 -70~-78dB

3. **相位锁定检测**（Phase coherence）：
   - AI 模型相位过于一致
   - 需要更强的相位扰动
   - 修改 `_group_delay_correct`：增加相位扰动幅度

4. **子带相关性检测**（Cross-band correlation）：
   - AI 模型多带之间相关性过高
   - 修改 `_subband_decorrelate`：增加去相关强度

#### 第 4 步：验证测试

1. 使用相同的测试音频运行 v3.3 处理
2. 提交到第三方检测器验证 AI 率是否下降
3. 对比处理前后的频谱图差异

## 文件清单

需要修改的文件：
1. `backend/services/audio_repair.py` — v3.3a/v3.3a+ 支持双轨 + 提高默认参数强度
2. `src/components/AIRepairPanel.tsx` — 修改算法过滤逻辑
3. `backend/services/repair/repair_v3_3/spectral.py` — 增强自然化强度
4. `backend/services/repair/repair_v3_3/phase.py` — 增强相位扰动
5. `backend/services/repair/repair_v3_3p/config.py` — 调整 Anti-Detect preset

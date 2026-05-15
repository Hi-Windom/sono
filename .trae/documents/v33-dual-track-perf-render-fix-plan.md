# v3.3 双轨性能优化 + 渲染交付修复 v2

## 问题 1：伴奏谐波去规整性能瓶颈（卡住 85 秒）

### 根因分析

当前 `_inst_multiband_harmonic_dereg` 函数有三个性能瓶颈：

**瓶颈 A（最大）：大随机数组分配**
- L87-L95：`rng.uniform(-X, X, size=(n_sub_bins, n_frames))` 创建形状为 (子带bin数, 全部帧数) 的随机数组
- 对于 5 分钟音频（n_frames ≈ 51680），三个子带的随机数组总大小 ≈ 51M 个 float64 元素 ≈ 408 MB
- 对于 30 分钟音频，总大小 ≈ 245M 元素 ≈ 1.96 GB
- 分配和填充这些大数组是主要耗时来源

**瓶颈 B：内层峰值对循环的 rng.uniform 调用**
- L108：每个峰值对调用一次 `rng.uniform` 生成单个随机数
- 约 200 帧 × 100 峰值对 = 20,000 次调用，每次调用有固定开销

**瓶颈 C：逐 bin 插值循环**
- L113-L116：`for b in range(n_bins)` 循环，对 1025 个 bin 分别执行 `np.interp`
- 虽然已稀疏化到 ~200 帧，但 1025 次 `np.interp` 调用仍有累积开销

### 优化方案

#### 步骤 1a：随机数组广播化（解决瓶颈 A）
- 将 `rng.uniform(-X, X, size=(n_sub_bins, n_frames))` 改为 `rng.uniform(-X, X, size=(n_sub_bins, 1))`
- 利用 numpy 广播机制，每个 bin 的随机扰动值在所有帧上保持一致
- 对于谐波去规整算法，逐 bin 扰动（而非逐 bin 逐帧）已足够实现统计去规整效果
- 内存从 O(n_bins × n_frames) 降至 O(n_bins)

#### 步骤 1b：预生成随机值（解决瓶颈 B）
- 在循环前预生成所有需要的随机值：`all_ratio_noise = rng.uniform(-0.1 * strength, 0.1 * strength, size=max_pairs)`
- 内层循环通过索引访问，避免每次调用 `rng.uniform`

#### 步骤 1c：向量化插值（解决瓶颈 C）
- 使用 `np.interp` 的向量化形式，一次性对所有 bin 进行插值
- 或使用 `scipy.interpolate.interp1d` 批量处理

### 涉及文件
| 文件 | 修改 |
|------|------|
| `backend/services/repair/repair_v3_3/inst.py` | `_inst_multiband_harmonic_dereg` 三重优化 |

---

## 问题 2：双轨修复后未进入渲染交付流程

### 根因分析

**核心缺陷**：双轨 `onComplete` 回调（`RepairPage.tsx` L187-L215）在 `renderAndDownload` 成功后**没有调用 `setShowDownloadModal(true)`**。

对比单轨流程（`useAudioProcessor.ts` L1347-L1355）：
```typescript
// 单轨：renderAndDownload 成功后显示下载弹窗
renderAndDownload(currentOpts, effectiveAlgorithmVersion).then(result => {
    if (result?.downloadUrl) {
        setRenderDownloadUrl(result.downloadUrl);
    }
    setShowDownloadModal(true);  // ✅ 单轨有这行
}).catch(err => {
    setShowDownloadModal(true);  // ✅ 即使失败也显示
});
```

```typescript
// 双轨：renderAndDownload 成功后只调了 setCacheTriggerKey
const result = await renderAndDownload(undefined, algorithmVersion);
// ...
setCacheTriggerKey(k => k + 1);  // ❌ 没有 setShowDownloadModal(true)
```

**后果**：
1. `renderAndDownload` 成功执行并设置了 `autoRenderInfo`
2. 但 `showDownloadModal` 始终为 false
3. 下载弹窗（L1095）条件 `showDownloadModal && instantDownloadInfo` 不满足
4. 用户界面停留在"准备渲染交付..."后无任何反应
5. 前后端均无报错，因为代码执行成功，只是 UI 状态未更新

### 修复方案

#### 步骤 2a：双轨 onComplete 增加下载弹窗触发
- `renderAndDownload` 成功后：捕获 result，设置 `setRenderDownloadUrl`，调用 `setShowDownloadModal(true)`
- `renderAndDownload` 失败时：设置 `backendError`，但仍调用 `setShowDownloadModal(true)` 让用户看到错误信息

#### 步骤 2b：后端 _repair_dual_track 增加文件存在性检查
- 在 `sf.write` 之后，检查输出文件是否存在且大小 > 0
- 如果文件缺失，记录警告日志但继续执行（不阻断流程）

#### 步骤 2c：增加前端错误日志
- 在双轨 `onComplete` 的关键步骤增加 `console.log` / `console.error`
- 方便未来调试

### 涉及文件
| 文件 | 修改 |
|------|------|
| `src/pages/RepairPage.tsx` | `startDualTrackPolling` 的 `onComplete` 增加下载弹窗触发 |
| `backend/services/repair/repair_v3_3/core.py` | `_repair_dual_track` 增加文件存在性检查 |

---

## 实施顺序

1. **步骤 1a**（随机数组广播化）— 最核心的性能优化，解决 85 秒卡顿
2. **步骤 1b**（预生成随机值）— 进一步减少内层循环开销
3. **步骤 1c**（向量化插值）— 减少插值开销
4. **步骤 2a**（双轨 onComplete 增加下载弹窗）— 解决渲染不触发问题
5. **步骤 2b**（后端文件存在性检查）— 后端稳健性
6. **步骤 2c**（前端错误日志）— 调试辅助

---

## 文件变更清单

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `backend/services/repair/repair_v3_3/inst.py` | 修改 | 三重性能优化 |
| 2 | `src/pages/RepairPage.tsx` | 修改 | onComplete 增加下载弹窗 |
| 3 | `backend/services/repair/repair_v3_3/core.py` | 修改 | 后端文件检查 |

---

## 注意事项
1. 随机数组广播化后，每个 bin 的扰动值在时间轴上恒定，但不同 bin 之间仍不同 — 这保持了谐波去规整的统计特性
2. 确定性输出：所有随机操作仍使用固定种子 42
3. 下载弹窗在 `renderAndDownload` 失败时也应显示，让用户看到错误信息而非空白界面
4. 后端文件检查不阻断流程，仅记录警告
# v3.3 双轨性能优化 + 渲染交付修复 v2

## 问题 1：伴奏谐波去规整性能瓶颈（卡住 85 秒）

### 根因分析

`_inst_multiband_harmonic_dereg`（`inst.py` L87-L95）创建形状为 `(子带bin数, 全部帧数)` 的大随机数组：

```python
low_perturb = rng.uniform(-0.01, 0.01, size=(n_low_bins, n_frames))   # ~200 × 51680
mid_perturb = rng.uniform(-0.03, 0.03, size=(n_mid_bins, n_frames))   # ~500 × 51680
high_perturb = rng.uniform(-0.06, 0.06, size=(n_high_bins, n_frames)) # ~325 × 51680
```

- 5 分钟音频：51M float64 ≈ **408 MB** 随机数组分配
- 30 分钟音频：245M float64 ≈ **1.96 GB**
- 分配+填充是主要耗时（85 秒）
- 此外内层循环逐峰值对调 `rng.uniform` 也有累积开销

### 优化方案

#### 步骤 1a：随机数组广播化（核心）
`size=(n_sub_bins, n_frames)` → `size=(n_sub_bins, 1)`，numpy 广播
- 每个 bin 的扰动值在时间轴上恒定
- 内存从 **O(n_bins × n_frames)** 降至 **O(n_bins)**
- 谐波去规整只需统计扰动，逐 bin 足够

#### 步骤 1b：预生成内层随机值
循环前一次性生成所有 `ratio_noise`，避免逐峰值对调用 `rng.uniform`

### 涉及文件
| 文件 | 修改 |
|------|------|
| `backend/services/repair/repair_v3_3/inst.py` | `_inst_multiband_harmonic_dereg` 优化 |

---

## 问题 2：双轨修复后渲染流程未启动

### 根因分析

双轨修复完成后，`onComplete` 回调（`RepairPage.tsx` L187-L215）存在 **3 个问题**，且 `handleUseDualCache`（L510-L538）存在 **相同问题**：

#### 问题 A：`loadAudioFromUrl` 阻塞渲染流程
```typescript
// L193：先下载修复结果 → 可能失败或超时
const buffer = await loadAudioFromUrl(downloadUrl, ...);
```
- 下载 URL 可能不可用（后端 `/download/{task_id}` 依赖 `task.output_path`，双轨任务的 output_path 可能未正确设置）
- 如果下载失败（404/超时），错误被 catch 但执行继续
- **如果下载挂起（60s 超时）**，`renderAndDownload` 被阻塞，用户看到"准备渲染交付..."后无响应
- 且 `loadAudioFromUrl` 不属于渲染流程，仅用于预览，不应阻塞渲染

#### 问题 B：未设置 `forceRenderRef.current = true`
```typescript
// L203：直接调 renderAndDownload
const result = await renderAndDownload(undefined, algorithmVersion);
```
对比单轨（`useAudioProcessor.ts` L1342）：
```typescript
forceRenderRef.current = true;  // 单轨强制跳过缓存
renderAndDownload(currentOpts, ...).then(...)
```
- 双轨未设 `forceRenderRef`，`renderAndDownload` 会先查渲染缓存
- 如果有过期缓存条目，返回 stale 结果而不触发实际渲染

#### 问题 C：错误被静默吞噬
```typescript
} catch (e) {
    setBackendError(e instanceof Error ? e.message : '渲染交付失败');
    setIsProcessing(false);  // 关闭处理状态
    return;
}
```
- `setIsProcessing(false)` 让 UI 退出处理状态
- 没有 `console.error` 日志，无法调试
- 用户看不到错误详情

#### 问题 D：`handleUseDualCache` 有相同问题
L510-L538 的缓存命中处理函数有完全相同的 3 个问题：
- L523：`loadAudioFromUrl(previewUrl, ...)` 阻塞
- L534：未设 `forceRenderRef`
- L535-537：仅 `console.error`，无用户可见错误

### 修复方案

#### 步骤 2a：重构 onComplete 流程
- **移除** `loadAudioFromUrl` 调用（渲染完成后由其他机制加载预览）
- 直接进入渲染流程

#### 步骤 2b：设置 forceRenderRef
- 调 `renderAndDownload` 前设 `forceRenderRef.current = true`

#### 步骤 2c：增强错误冒泡和日志
- `renderAndDownload` 返回 null 时：`console.error('[双轨] renderAndDownload 返回 null')` + `setBackendError`
- 异常捕获时：`console.error('[双轨] 渲染失败:', e)` + `setBackendError`
- 不依赖 `setIsProcessing(false)` 后的 UI 状态

#### 步骤 2d：修复 handleUseDualCache
- 相同修复：移除 `loadAudioFromUrl`、设 `forceRenderRef`、增强错误日志

### 涉及文件
| 文件 | 修改 |
|------|------|
| `src/pages/RepairPage.tsx` | `onComplete` + `handleUseDualCache` 重构 |

---

## 问题 3：后端双轨任务下载可能不可用

### 根因分析

`/download/{task_id}` 端点（`routes.py` L1325）依赖 `task.get("output_path")`：
```python
output_path = task.get("output_path")
if not output_path or not os.path.exists(output_path):
    raise HTTPException(status_code=404, detail="修复后的音频不存在")
```

双轨修复的 `_repair_dual_track` 写入 `output_path`（混音结果），但需要确认：
1. 任务管理器是否正确设置了 `task.output_path`
2. 文件是否确实写入成功
3. 下载端点是否能正确 serve 双轨的混音结果

### 修复方案

#### 步骤 3a：后端 _repair_dual_track 增加文件存在性检查
- `sf.write` 后检查文件是否存在且 > 0 bytes
- 如果缺失，记录 error 日志

#### 步骤 3b：后端下载端点增加双轨支持日志
- 下载时如果 `output_path` 不存在，记录 task params 中的 `vocal_output_path` 和 `accompaniment_output_path` 用于调试

### 涉及文件
| 文件 | 修改 |
|------|------|
| `backend/services/repair/repair_v3_3/core.py` | `_repair_dual_track` 文件检查 |
| `backend/api/routes.py` | `/download/{task_id}` 增加调试日志 |

---

## 实施顺序

1. **步骤 1a**（随机数组广播化）— 最核心的性能优化
2. **步骤 1b**（预生成随机值）— 减少内层循环开销
3. **步骤 2a**（重构 onComplete）— 移除阻塞的 loadAudioFromUrl
4. **步骤 2b**（设 forceRenderRef）— 确保触发实际渲染
5. **步骤 2c**（增强错误日志）— 让错误可见
6. **步骤 2d**（修复 handleUseDualCache）— 缓存命中路径修复
7. **步骤 3a**（后端文件检查）— 后端稳健性
8. **步骤 3b**（下载端点日志）— 调试辅助

---

## 文件变更清单

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `backend/services/repair/repair_v3_3/inst.py` | 修改 | 随机数组广播化 + 预生成随机值 |
| 2 | `src/pages/RepairPage.tsx` | 修改 | onComplete + handleUseDualCache 重构 |
| 3 | `backend/services/repair/repair_v3_3/core.py` | 修改 | 后端文件存在性检查 |
| 4 | `backend/api/routes.py` | 修改 | 下载端点增加调试日志 |

---

## 注意事项
1. 随机数组广播化后每个 bin 扰动值在时间轴上恒定，不同 bin 间不同 — 保持谐波去规整的统计特性
2. 确定性输出：所有随机操作仍使用固定种子 42
3. `forceRenderRef.current = true` 确保跳过过期渲染缓存
4. 后端文件检查不阻断流程，仅记录警告/错误日志
5. 修复后验证：双轨修复完成 → 自动进入渲染 → 渲染完成后可下载
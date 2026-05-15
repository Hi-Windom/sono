# v3.3 双轨性能优化 + 渲染交付修复 实施计划

## 问题 1：伴奏谐波去规整性能瓶颈

### 根因分析
- **位置**: `backend/services/repair/repair_v3_3/inst.py` L96-L110
- **函数**: `_inst_multiband_harmonic_dereg`
- **瓶颈**: 双重 Python for 循环处理每一帧（n_frames 可达 10000+）：
  1. 外层 `for j in range(n_frames)` — 逐帧迭代
  2. 内层 `for b in range(1, n_bins - 1)` — 逐 bin 峰值检测
  3. 峰值间的谐波比率调整也是 Python 循环
- **复杂度**: O(n_frames × n_bins) = O(10000 × 1025) ≈ 1000 万次 Python 循环

### 优化方案

#### 步骤 1a：向量化峰值检测
- 使用 numpy 广播替代内层 `for b` 循环
- `is_peak = (col[1:-1] > col[:-2]) & (col[1:-1] > col[2:]) & (col[1:-1] > np.mean(col) * 1.5)`
- 配合 `np.where` 获取峰值索引

#### 步骤 1b：稀疏化谐波比率调整
- 谐波去规整是统计性扰动，无需逐帧处理
- 改为每隔 `max(1, n_frames // 200)` 帧处理一次（约 200 帧）
- 中间帧使用插值平滑

#### 步骤 1c：跳过 SNR 保护（可选）
- L117-L123 的 SNR 保护计算在长音频下额外开销大
- 仅当 `strength > 0.5` 时才执行

### 涉及文件
| 文件 | 修改 |
|------|------|
| `backend/services/repair/repair_v3_3/inst.py` | `_inst_multiband_harmonic_dereg` 性能优化 |

---

## 问题 2：修复后未进入渲染交付流程

### 根因分析
- **位置**: `src/pages/RepairPage.tsx` L187-L207（`startDualTrackPolling` 的 `onComplete`）
- **核心缺陷**: `onComplete` 回调中所有错误都被 `catch` 并仅 `console.error`，**没有任何用户可见的错误提示**
- **可能原因链**：
  1. `loadAudioFromUrl` 加载修复结果失败 → 静默吞噬
  2. `renderAndDownload` 内部错误 → 双重 `catch` 静默吞噬
  3. 用户界面停留在"准备渲染交付..."后悄然消失

### 修复方案

#### 步骤 2a：前端 onComplete 增加用户可见错误处理
- `loadAudioFromUrl` 失败时：设置 `backendError` 状态，显示用户可见错误
- `renderAndDownload` 失败时：设置 `backendError` 状态，显示用户可见错误
- 移除 `onComplete` 外层的 `try-catch`，让错误自然冒泡到 `onError`

#### 步骤 2b：确保 taskIdRef 同步更新
- 在 `onComplete` 中 `setTaskId(taskId)` 后，增加 `taskIdRef.current = taskId` 显式赋值
- 避免 React 异步状态更新导致 ref 未及时同步

#### 步骤 2c：renderAndDownload 增加错误冒泡
- 修改 `renderAndDownload` 内部，错误时不静默 return null
- 改为 throw，让外层可以捕获并展示

#### 步骤 2d：后端增加错误检查和日志
- `_repair_dual_track` 中关键步骤增加异常捕获
- 确保 `output_path` 文件确实已写入
- 修复完成时确认所有文件存在

### 涉及文件
| 文件 | 修改 |
|------|------|
| `src/pages/RepairPage.tsx` | `onComplete` 错误处理增强 |
| `src/hooks/useAudioProcessor.ts` | `renderAndDownload` 错误冒泡 |
| `backend/services/repair/repair_v3_3/core.py` | 后端文件存在性检查 |

---

## 实施顺序

1. **步骤 1a**（向量化峰值检测）— 最核心的性能优化
2. **步骤 1b**（稀疏化谐波比率调整）— 进一步加速
3. **步骤 2a**（前端错误处理）— 解决渲染不触发问题
4. **步骤 2b**（taskIdRef 同步）— 确保 ref 正确
5. **步骤 2c**（renderAndDownload 错误冒泡）— 错误可见
6. **步骤 2d**（后端文件检查）— 后端稳健性

---

## 文件变更清单

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `backend/services/repair/repair_v3_3/inst.py` | 修改 | 谐波去规整向量化 + 稀疏化 |
| 2 | `src/pages/RepairPage.tsx` | 修改 | onComplete 错误处理 |
| 3 | `src/hooks/useAudioProcessor.ts` | 修改 | renderAndDownload 错误冒泡 |
| 4 | `backend/services/repair/repair_v3_3/core.py` | 修改 | 后端文件检查 |

---

## 注意事项
1. 向量化后保持与原算法行为一致（固定种子 42，确定性输出）
2. 稀疏化处理后 SNR 保护阈值保持 45dB
3. 前端错误状态使用现有的 `backendError` / `setBackendError` 机制
4. 错误信息中英文统一使用中文（用户语言）
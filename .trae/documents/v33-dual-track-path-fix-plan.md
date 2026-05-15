# v3.3 双轨路径修复 + 秒下机制修复 v2

## 问题 1：双轨"修复结果不存在"

### 根因：路径不匹配

`_repair_dual_track`（`core.py` L202-L205）**自行计算**输出路径：

```python
vocal_output = os.path.join(output_dir, f"{base_name}_vocal.wav")       # {task_id}_repaired_vocal.wav
inst_output = os.path.join(output_dir, f"{base_name}_accompaniment.wav") # {task_id}_repaired_accompaniment.wav
```

但修复端点（`routes.py` L771-L775）在 `params` 中**存储了不同的路径**：

```python
params["vocal_output_path"] = os.path.join(OUTPUT_DIR, f"{vocal_task_id}_repaired.wav")
params["accompaniment_output_path"] = os.path.join(OUTPUT_DIR, f"{accompaniment_task_id}_repaired.wav")
```

**后果**：
- 实际文件写入：`{task_id}_repaired_vocal.wav`
- 渲染端点查找：`{vocal_task_id}_repaired.wav`
- 文件不存在 → 返回 400 "修复结果不存在"

### 修复

#### 步骤 1a：`_repair_dual_track` 使用 params 中的路径
`core.py` L202-L205：从 `params` 读取 `vocal_output_path` 和 `accompaniment_output_path`

#### 步骤 1b：返回值增加路径字段
`_repair_dual_track` 返回值增加 `vocal_output_path` 和 `accompaniment_output_path`，让 `task_manager.py` 能正确更新子任务

---

## 问题 2：秒下（Instant Download）弹窗状态残留

### 根因：旧状态未清理

渲染完成后设置下载弹窗时，**没有先清理残留的旧状态**：

**单轨**（`useAudioProcessor.ts` L1347-L1355）：
```typescript
renderAndDownload(currentOpts, ...).then(result => {
    if (result?.downloadUrl) {
        setRenderDownloadUrl(result.downloadUrl);  // 直接覆盖，但旧值可能还在
    }
    setShowDownloadModal(true);  // 直接设为 true，但 instantDownloadInfo 还是旧的
    // ❌ 没有先清理旧状态
    // ❌ 没有设置 instantDownloadInfo
});
```

**双轨**（`RepairPage.tsx` L187-L215，之前已修复）：
```typescript
const result = await renderAndDownload(undefined, algorithmVersion, true);
// ✅ 渲染成功
// ❌ 没有清理旧状态
// ❌ 没有设置 renderDownloadUrl
// ❌ 没有设置 instantDownloadInfo
// ❌ 没有设置 showDownloadModal
```

**后果**：
- 残留的 `instantDownloadInfo` 指向旧渲染结果
- 新渲染完成后弹窗显示旧数据
- 用户看到错误的文件信息

### 修复方案

所有渲染完成后的回调（单轨 `applySettings`、双轨 `onComplete`、双轨 `handleUseDualCache`）统一执行：

```typescript
// 1. 先清理旧状态
setInstantDownloadInfo(null);
setShowDownloadModal(false);
setRenderDownloadUrl('');

// 2. 再设置新状态
setRenderDownloadUrl(result.downloadUrl);
setInstantDownloadInfo({
    filename: result.fileName,
    fileSize: '计算中...',
    sampleRate: `${result.renderInfo.output_sample_rate / 1000} kHz`,
    bitDepth: result.renderInfo.output_bit_depth,
    channels: result.renderInfo.channels,
});
setShowDownloadModal(true);
```

#### 步骤 2a：单轨 `applySettings` 增加清理 + 秒下设置
`useAudioProcessor.ts` L1347-L1355

由于 `setInstantDownloadInfo` 在 `RepairPage.tsx` 中定义，`applySettings` 无法直接调用。
**方案**：在 `RepairPage.tsx` 中添加 `useEffect`，监听 `autoRenderInfo` 变化，自动执行清理 + 设置：

```typescript
useEffect(() => {
    if (autoRenderInfo && renderDownloadUrl) {
        setInstantDownloadInfo(null);  // 先清理
        setShowDownloadModal(false);
        // 再设置
        setInstantDownloadInfo({
            filename: generateExportFilename(...),
            fileSize: '计算中...',
            sampleRate: `${autoRenderInfo.output_sample_rate / 1000} kHz`,
            bitDepth: autoRenderInfo.output_bit_depth,
            channels: autoRenderInfo.channels,
        });
        setShowDownloadModal(true);
    }
}, [autoRenderInfo]);
```

#### 步骤 2b：双轨 `onComplete` 增加清理 + 秒下设置
`RepairPage.tsx` L187-L215：`renderAndDownload` 成功后先清理旧状态，再设置新状态

#### 步骤 2c：双轨 `handleUseDualCache` 增加清理 + 秒下设置
`RepairPage.tsx` L510-L538：与 `onComplete` 一致

---

## 实施顺序

1. **步骤 1a**（`_repair_dual_track` 使用 params 路径）
2. **步骤 1b**（返回值增加路径字段）
3. **步骤 2a**（单轨秒下：`useEffect` 监听 `autoRenderInfo` 清理+设置）
4. **步骤 2b**（双轨 `onComplete` 清理+设置）
5. **步骤 2c**（双轨 `handleUseDualCache` 清理+设置）
6. **验证**：TypeScript 编译 + 打包

---

## 文件变更清单

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `backend/services/repair/repair_v3_3/core.py` | 修改 | `_repair_dual_track` 使用 params 路径 + 返回值增加路径 |
| 2 | `src/pages/RepairPage.tsx` | 修改 | 单轨 `useEffect` 秒下清理+设置 + 双轨 `onComplete`/`handleUseDualCache` 清理+设置 |
| 3 | `src/hooks/useAudioProcessor.ts` | 修改 | 无（`autoRenderInfo` 已设置，RepairPage 监听即可） |

---

## 注意事项
1. 先清理后设置：`setInstantDownloadInfo(null)` → `setShowDownloadModal(false)` → 设置新值 → `setShowDownloadModal(true)`
2. React 的 state 更新是异步批处理的，`setInstantDownloadInfo(null)` 和后续的 `setInstantDownloadInfo({...})` 可能会被合并。需要确保清理生效，可以用 `useEffect` 分两步或使用 ref
3. 双轨的下载弹窗需要额外支持 vocal/accompaniment 单独下载
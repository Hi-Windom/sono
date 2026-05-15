# v3.3 双轨路径修复 + 秒下弹窗修复

## 问题 1：双轨"修复结果不存在"

`_repair_dual_track` 自行计算输出路径，与 `params` 中存储的路径不一致。

**修复**：`_repair_dual_track` 从 `params` 读取 `vocal_output_path` 和 `accompaniment_output_path`，返回值也带上这两个字段。

## 问题 2：秒下弹窗不工作

### 现状

**单轨** `applySettings`（`useAudioProcessor.ts` L1347-L1355）：
- 渲染完成后调 `setRenderDownloadUrl(result.downloadUrl)` ✅
- 调 `setShowDownloadModal(true)` ❌ 但 `instantDownloadInfo` 没设，弹窗条件不满足，死代码

**双轨** `onComplete`（`RepairPage.tsx` L187-L215）：
- 渲染完成后什么都没设 ❌

### 修复

**步骤 1：移除 `applySettings` 中的 `setShowDownloadModal`（2 处死代码）**

**步骤 2：`applySettings` 渲染完成后设 `instantDownloadInfo`**
改为和 `onInstantDownload`（秒下用户点缓存）一模一样的逻辑：
```typescript
renderAndDownload(...).then(result => {
    if (result?.downloadUrl) {
        setRenderDownloadUrl(result.downloadUrl);
        setInstantDownloadInfo({
            filename: result.fileName,
            fileSize: '计算中...',
            sampleRate: `${result.renderInfo.output_sample_rate / 1000} kHz`,
            bitDepth: result.renderInfo.output_bit_depth,
            channels: result.renderInfo.channels,
        });
        setShowDownloadModal(true);
    }
});
```

**步骤 3：双轨 `onComplete` 渲染成功后同上**
设 `setRenderDownloadUrl` + `setInstantDownloadInfo` + `setShowDownloadModal`

**步骤 4：双轨 `handleUseDualCache` 渲染成功后同上**

## 文件变更

| 文件 | 修改 |
|------|------|
| `backend/services/repair/repair_v3_3/core.py` | `_repair_dual_track` 使用 params 路径 + 返回值增加路径 |
| `src/hooks/useAudioProcessor.ts` | `applySettings` 移除死代码 + 加 `instantDownloadInfo` |
| `src/pages/RepairPage.tsx` | 双轨 `onComplete`/`handleUseDualCache` 渲染完成后设 `instantDownloadInfo` |
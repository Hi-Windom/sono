# v3.3 双轨路径修复 + 秒下弹窗修复

## 问题 1：双轨"修复结果不存在"

### 根因：路径不匹配

`_repair_dual_track`（`core.py` L202-L205）自行计算输出路径，与 `params` 中存储的路径不一致。

**修复**：`_repair_dual_track` 从 `params` 读取 `vocal_output_path` 和 `accompaniment_output_path`，返回值也带上这两个字段。

---

## 问题 2：秒下弹窗不工作（单轨+双轨）

### 根因

秒下弹窗的显示条件（`RepairPage.tsx` L1090）：
```typescript
{showDownloadModal && instantDownloadInfo && (<DownloadModal ... />)}
```

需要 `showDownloadModal` 和 `instantDownloadInfo` **同时**满足。

但渲染完成后：
- **单轨**（`applySettings`）：只设了 `showDownloadModal=true`，没设 `instantDownloadInfo` → 弹窗不显示
- **双轨**（`onComplete`）：什么都没设 → 弹窗不显示
- 且渲染开始时没有清理旧状态 → 残留数据污染

### 修复

统一方案：**渲染开始时清理 → 渲染完成后设置**，单轨双轨共用同一套逻辑。

#### 步骤 2a：`renderAndDownload` 开始时清理 `autoRenderInfo`
`useAudioProcessor.ts`：函数开头设 `setAutoRenderInfo(null)`

#### 步骤 2b：`RepairPage.tsx` 添加 `useEffect` 监听 `autoRenderInfo`
```typescript
useEffect(() => {
    if (autoRenderInfo === null) {
        setInstantDownloadInfo(null);
        setShowDownloadModal(false);
        setRenderDownloadUrl('');
    } else if (autoRenderInfo && renderDownloadUrl) {
        setInstantDownloadInfo({
            filename: generateExportFilename(...),
            fileSize: '计算中...',
            sampleRate: `${autoRenderInfo.output_sample_rate / 1000} kHz`,
            bitDepth: autoRenderInfo.output_bit_depth,
            channels: autoRenderInfo.channels,
        });
        setShowDownloadModal(true);
    }
}, [autoRenderInfo, renderDownloadUrl]);
```

#### 步骤 2c：双轨 `onComplete` 设置 `renderDownloadUrl`
`RepairPage.tsx`：`renderAndDownload` 成功后设 `setRenderDownloadUrl(result.downloadUrl)`

#### 步骤 2d：双轨 `handleUseDualCache` 设置 `renderDownloadUrl`
`RepairPage.tsx`：同上

---

## 文件变更

| 文件 | 修改 |
|------|------|
| `backend/services/repair/repair_v3_3/core.py` | `_repair_dual_track` 使用 params 路径 + 返回值增加路径 |
| `src/hooks/useAudioProcessor.ts` | `renderAndDownload` 开头设 `setAutoRenderInfo(null)` |
| `src/pages/RepairPage.tsx` | 添加 `useEffect` 监听 `autoRenderInfo` + 双轨设 `renderDownloadUrl` |
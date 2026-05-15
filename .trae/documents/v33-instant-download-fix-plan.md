# v3.3 秒下弹窗修复计划

## 问题分析

### 问题 1：秒下弹窗不触发

秒下弹窗显示条件（`RepairPage.tsx` L1090）：
```typescript
{showDownloadModal && instantDownloadInfo && (<DownloadModal ... />)}
```

需要 **同时** 满足 `showDownloadModal` 和 `instantDownloadInfo`。

**现状**：
- 用户点击缓存条目（秒下）：`onInstantDownload` 设了 `instantDownloadInfo` + `setShowDownloadModal(true)` ✅
- 单轨渲染完成：`applySettings` 只设了 `setShowDownloadModal(true)`，没设 `instantDownloadInfo` ❌
- 双轨渲染完成：`onComplete` / `handleUseDualCache` 什么都没设 ❌

### 问题 2：单轨/双轨切换污染秒下刷新

切换函数（`handleSwitchToSingleTrack` L278-L286）没有清理弹窗状态：
```typescript
const handleSwitchToSingleTrack = useCallback(() => {
    sessionActions.setDualTrackMode(false);
    setDualTrackTaskId(null);
    // ... 其他清理
    // ❌ 没有清理 instantDownloadInfo 和 showDownloadModal
}, ...);
```

**后果**：切换后残留旧状态的 `instantDownloadInfo`，秒下刷新时显示错误数据。

## 修复方案

### 步骤 1：单轨渲染完成后设 `instantDownloadInfo`

`useAudioProcessor.ts` `applySettings` 中，`renderAndDownload` 成功后：
```typescript
renderAndDownload(...).then(result => {
    if (result?.downloadUrl) {
        setRenderDownloadUrl(result.downloadUrl);
        // 新增：设 instantDownloadInfo（通过回调传给 RepairPage）
        onRenderComplete?.(result);
    }
});
```

由于 `useAudioProcessor` 无法直接访问 `setInstantDownloadInfo`，需要：
- 在 `RepairPage.tsx` 中监听 `autoRenderInfo` 变化，当 `autoRenderInfo` 更新且 `renderDownloadUrl` 存在时，自动设置 `instantDownloadInfo`

### 步骤 2：双轨 `onComplete` 渲染完成后设 `instantDownloadInfo`

`RepairPage.tsx` L187-L215，`renderAndDownload` 成功后：
```typescript
const result = await renderAndDownload(...);
if (result) {
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
```

### 步骤 3：双轨 `handleUseDualCache` 渲染完成后设 `instantDownloadInfo`

同上。

### 步骤 4：单轨/双轨切换时清理弹窗状态

`handleSwitchToSingleTrack` 增加：
```typescript
setInstantDownloadInfo(null);
setShowDownloadModal(false);
```

## 文件变更

| 文件 | 修改 |
|------|------|
| `src/pages/RepairPage.tsx` | 双轨 `onComplete`/`handleUseDualCache` 设 `instantDownloadInfo` + 切换时清理 |
| `src/hooks/useAudioProcessor.ts` | `applySettings` 渲染完成后触发 `onRenderComplete` 回调（或改用 `useEffect` 监听 `autoRenderInfo`） |

## 实施顺序

1. 双轨 `onComplete` 设 `instantDownloadInfo`
2. 双轨 `handleUseDualCache` 设 `instantDownloadInfo`
3. 单轨/双轨切换时清理弹窗状态
4. 单轨 `useEffect` 监听 `autoRenderInfo` 设 `instantDownloadInfo`
5. 验证
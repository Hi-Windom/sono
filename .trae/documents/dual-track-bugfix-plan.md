# 双轨模式 Bug 修复计划

## 现状分析

### Bug 1: 双轨上传「人声音频不存在」

**根因**: [routes.py:L785](file:///workspace/backend/api/routes.py#L785) 中 `submit_repair_task(request.task_id, vocal_path, params)` 将 `vocal_path` 作为 `audio_path` 传给 `_run_repair`。但在 `_run_repair` ([task_manager.py:L319](file:///workspace/backend/services/task_manager.py#L319)) 中会校验 `os.path.exists(audio_path)` — 这个 `audio_path` 只代表人声轨，但 v3.0/v3.1 双轨修复实际上使用 `params["vocal_path"]` 和 `params["accompaniment_path"]` 来加载音频。

更关键的问题：当用户上传双轨文件后，vocal task 的 `original_path` 存储在 task 记录中。但如果用户**重新选择文件**（通过 `handleDualTrackFileReplace`），task IDs 被设为 null，后续 `handleDualTrackRepair` 走 `repairDualFromHash` 分支时，`find_task_by_hash` 查找原始上传任务，但该任务可能已被后端清理或 `original_path` 文件已不存在。

**解决方案**: 在 `_run_repair` 中，当检测到双轨模式（`processing_mode == "dual"`）时，不校验 `audio_path`（因为真正使用的是 params 中的路径），改为校验 `params["vocal_path"]` 和 `params["accompaniment_path"]`。

### Bug 2: MP3 转换失败 MPEGMode is not defined

**根因**: `lamejs` 是 CommonJS 库，内部通过 `var MPEGMode = require('./MPEGMode.js')` 引用子模块。当前 Worker 使用 `{ type: 'module' }` 模式创建，Vite 在打包 module Worker 时，lamejs 内部的 CJS `require()` 调用未能正确解析为 ESM，导致 `MPEGMode` 变量未定义。

**解决方案**: 将 mp3EncoderWorker 改为 classic Worker（移除 `{ type: 'module' }`），Vite 会以 IIFE 格式打包 classic Worker，能正确处理 CommonJS 依赖。

涉及文件:
- [mp3Encoder.ts:L5-L8](file:///workspace/src/utils/mp3Encoder.ts#L5-L8): 移除 `{ type: 'module' }`
- 无需修改 Worker 代码本身，Vite 自动处理 import 转换

### Bug 3: 修复→渲染交付间进度条空白

**根因**: `startDualTrackPolling` 的 `onComplete` 回调中，[RepairPage.tsx:L162-L181](file:///workspace/src/pages/RepairPage.tsx#L162-L181):
```typescript
onComplete: async (status) => {
    setIsProcessing(false);  // ← 修复完成，立即关闭进度条
    ...
    try {
        await renderAndDownload();  // ← 然后开始渲染，但进度条已关闭
    }
}
```

`renderAndDownload` 内部虽然设置了 `setIsProcessing(true)` 和 `setProcessingStep`，但 `setIsProcessing(false)` 在 WebSocket onComplete 时立即执行，然后 `renderAndDownload` 异步开始。在此期间（修复完成 → 渲染开始之间）进度条是空白的。

**解决方案**: 在 `onComplete` 中先设置进度条状态为"渲染交付中"，再调用 `renderAndDownload`：

```typescript
onComplete: async (status) => {
    sessionActions.setDualTrackProcessed(true);
    setDualTrackRepairResult(status);
    const downloadUrl = getDownloadUrl(taskId);
    setDualTrackDownloadUrl(downloadUrl);
    setTaskId(taskId);
    try {
        const buffer = await loadAudioFromUrl(downloadUrl, processingOptions.sampleRate, true);
        setBackendProcessedBuffer(buffer);
        setBackendWaveformPeaks(null);
    } catch (e) {
        console.error('加载双轨处理结果失败:', e);
    }
    // 不关闭 isProcessing，让 renderAndDownload 接管进度条
    setProcessingStep('准备渲染交付...');
    setProcessingProgress(0);
    try {
        await renderAndDownload();
    } catch (e) {
        console.error('双轨渲染交付失败:', e);
    }
    setCacheTriggerKey(k => k + 1);
},
```

### Bug 4: 双轨导出下载框适配

**根因**: 当前 `DownloadModal` 只支持单一 URL 下载。但双轨渲染后，后端返回多个文件（合并、人声、伴奏），需要分别下载。

**现状**:
- 后端渲染完成后，`render_cache_update` WebSocket 消息中包含 `files` 数组，每个文件有 `filename`、`track_type`（`"both"`、`"vocal"`、`"accompaniment"`）
- 前端 `AIRepairPanel` 的 `onInstantDownload` 回调只处理单个缓存条目
- `DownloadModal` 的 props 只有单个 `backendDownloadUrl`

**解决方案**:

1. **扩展 `DownloadModal` props**：新增 `dualTrackUrls` 字段
```typescript
interface DualTrackDownloadUrls {
    merged?: string;   // 合并轨下载URL
    vocal?: string;    // 人声轨下载URL  
    accompaniment?: string; // 伴奏轨下载URL
}
```

2. **扩展 `DownloadModal` UI**：双轨模式时显示三个下载区
   - 【合并_xxx.wav】+ WAV/MP3 下载按钮
   - 人声轨 + 单独下载
   - 伴奏轨 + 单独下载

3. **修改 `RepairPage`**：在 `onInstantDownload` 回调中，从 `renderCaches` 中提取所有 track_type 的文件，构建 `dualTrackUrls`

4. **合并文件名添加【合并_】前缀**：在生成下载文件名时添加前缀

---

## 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `backend/services/task_manager.py` | Bug 1: `_run_repair` 中双轨模式跳过 audio_path 校验 |
| `src/utils/mp3Encoder.ts` | Bug 2: 移除 Worker `{ type: 'module' }` |
| `src/pages/RepairPage.tsx` | Bug 3: onComplete 中不关闭 isProcessing；Bug 4: 传递双轨下载URLs |
| `src/components/DownloadModal.tsx` | Bug 4: 新增双轨多文件下载 UI，合并文件名【合并_】前缀 |

---

## 验证步骤

1. `bash scripts/start_dev.sh` 启动 dev 服务器
2. 双轨模式上传人声+伴奏文件 → 选择 v3.1 → 点击修复
3. 确认修复成功（无「人声音频不存在」错误）
4. 修复完成后确认进度条持续显示渲染进度
5. 渲染完成后点击下载 → 确认下载框显示合并/人声/伴奏三个下载选项
6. 确认合并文件名以【合并_】开头
7. 确认 MP3 下载正常（无 MPEGMode 错误）
8. `bash scripts/build_android_release.sh` 打包验证
# 优化非WAV缓存 + 秒下走DownloadModal + 波形缓存完善

## 当前状态

### 已完成（Steps 1-2）
- ✅ `GET /api/v1/audio-info/{file_hash}` — 使用 `miniaudio.get_file_info()` 毫秒级返回规格
- ✅ `GET /api/v1/waveform/{file_hash}` — 波形缓存端点，缓存到 `analysis_cache.waveform_peaks`
- ✅ `POST /upload` 返回值增加 `audio_info` 字段
- ✅ `analysis_cache` 表新增 `waveform_peaks` 列

### 待完成（Steps 3-7 + 构建）

---

## Step 3: decoded WAV缓存创建后清理原始MP3文件

**文件**: `backend/api/routes.py`

修改 `_convert_to_wav()` 内部函数（L847-859），在WAV缓存创建成功后：
1. 更新 task 的 `original_path` 指向 decoded WAV 文件
2. 删除原始MP3文件

```python
def _convert_to_wav():
    try:
        import numpy as np
        from services.audio_loader import load_audio_with_fallback
        y, sr = load_audio_with_fallback(original_path)
        if y.ndim == 2:
            y = y.T
        os.makedirs(DECODED_DIR, exist_ok=True)
        import soundfile as sf
        sf.write(decoded_path, y, sr)
        logger.info(f"解码WAV缓存创建完成: {decoded_path} size={os.path.getsize(decoded_path)}")
        # 更新task的original_path指向decoded WAV
        from database import update_task
        update_task(task_id, original_path=decoded_path)
        # 删除原始非WAV文件
        if original_path != decoded_path and os.path.exists(original_path):
            os.remove(original_path)
            logger.info(f"已删除原始文件: {original_path}")
    except Exception as e:
        logger.warning(f"解码WAV缓存创建失败: {e}")
```

注意：`_convert_to_wav` 是在 `executor.submit` 中异步执行的，需要确保 `task_id` 和 `original_path` 变量在闭包中可访问。当前代码中 `task_id` 和 `original_path` 在外层函数作用域中已定义，闭包可以访问。

---

## Step 4: 前端使用 audio-info 即时获取规格

**文件**: `src/hooks/useAudioProcessor.ts`

当前问题：非WAV文件上传后，`parseWavHeader` 返回 null，`wavInfo` 为 null，规格信息要等到浏览器 `decodeAudioData` 完成才能从 `audioBuffer` 获取。

修改 `loadAudioFile` 函数（L720-916）：

1. 在 `uploadAudio` 返回后，检查返回值中的 `audio_info` 字段
2. 如果 `wavInfo` 为 null（非WAV文件）且 `audio_info` 存在，用 `audio_info` 构造 `WavInfo` 对象

```typescript
// 在 uploadAudio 之后（约 L876-887）
const uploadRes = await uploadAudio(file, undefined, hash);
// ...
if (uploadRes.audio_info && !wavHeaderInfo) {
  const ai = uploadRes.audio_info;
  const infoFromApi: WavInfo = {
    sampleRate: ai.sample_rate,
    channels: ai.channels,
    duration: ai.duration,
    bitDepth: ai.sample_width * 8,
    dataSize: 0,
    format: 1,
  };
  setWavInfo(infoFromApi);
  setDuration(ai.duration);
  durationRef.current = ai.duration;
}
```

同时在会话恢复流程（约 L542-544）中，如果 `parseWavHeader` 返回 null 且有 `fileHash`，调用 `/api/v1/audio-info/{hash}` 获取规格：

```typescript
const wavHeaderInfo = parseWavHeader(arrayBuf.slice(0, 44 + 4096));
setWavInfo(wavHeaderInfo);
if (!wavHeaderInfo && session.fileHash) {
  try {
    const infoRes = await fetch(`/api/v1/audio-info/${session.fileHash}`);
    if (infoRes.ok) {
      const ai = await infoRes.json();
      const infoFromApi: WavInfo = {
        sampleRate: ai.sample_rate,
        channels: ai.channels,
        duration: ai.duration,
        bitDepth: ai.sample_width * 8,
        dataSize: 0,
        format: 1,
      };
      setWavInfo(infoFromApi);
    }
  } catch {}
}
```

---

## Step 5: 前端使用波形缓存

**文件**: `src/hooks/useAudioProcessor.ts`

当前问题：原始音频波形从 `audioBuffer` 实时绘制，非WAV文件在 `decodeAudioData` 完成前无波形。

修改 `loadAudioFile` 函数：

1. 新增 state: `originalWaveformPeaks`
2. 在 `uploadAudio` 返回后（或分析缓存命中后），调用 `/api/v1/waveform/{hash}` 获取波形缓存
3. 如果有波形缓存，在 `audioBuffer` 解码完成前即可显示原始波形

```typescript
// 新增 state（约 L170 附近）
const [originalWaveformPeaks, setOriginalWaveformPeaks] = useState<number[][] | null>(null);

// 在 loadAudioFile 中，uploadAudio 成功后（约 L903-906）
if (isNonWavFile) {
  fetch(`/api/v1/decoded-wav/${hash}`, { method: 'POST' }).catch(() => {});
  writeLog(`[loadAudioFile] 触发后端解码WAV缓存创建`);
}
// 获取原始波形缓存
fetch(`/api/v1/waveform/${hash}`)
  .then(res => res.ok ? res.json() : null)
  .then(data => {
    if (data?.peaks) {
      setOriginalWaveformPeaks(data.peaks);
      writeLog(`[loadAudioFile] 原始波形缓存已加载`);
    }
  })
  .catch(() => {});
```

在 `loadAudioFile` 重置状态时清空：
```typescript
setOriginalWaveformPeaks(null);
```

导出 `originalWaveformPeaks` 供页面使用。

**文件**: `src/pages/RepairPage.tsx`, `src/pages/Home.tsx`

修改 `WaveformVisualizer` 的 `waveformPeaks` prop：
```typescript
// 原始模式：如果有 originalWaveformPeaks 且 audioBuffer 还没解码好，用缓存
// 修复后模式：用 backendWaveformPeaks
waveformPeaks={
  playMode === 'backend' && !activeBuffer ? backendWaveformPeaks
  : playMode === 'original' && !activeBuffer ? originalWaveformPeaks
  : null
}
```

---

## Step 6: 秒下走DownloadModal

**文件**: `src/components/AIRepairPanel.tsx`

1. 新增 prop: `onInstantDownload?: (cacheEntry: RenderCacheEntry) => void`
2. 修改"秒下"按钮（L525-548）：调用 `onInstantDownload(selectedCache)` 替代 `fetch+blob+a.click()`

```typescript
// AIRepairPanelProps 新增
onInstantDownload?: (cacheEntry: RenderCacheEntry) => void;

// 秒下按钮 onClick
onClick={() => {
  if (onInstantDownload) {
    onInstantDownload(selectedCache);
  }
}}
```

**文件**: `src/pages/RepairPage.tsx`, `src/pages/Home.tsx`

在 AIRepairPanel 上传入 `onInstantDownload` 回调：
```typescript
<AIRepairPanel
  // ...existing props
  onInstantDownload={(cacheEntry) => {
    const downloadUrl = `/api/v1/download-file/${cacheEntry.filename}`;
    setRenderDownloadUrl(downloadUrl);
    setShowDownloadModal(true);
  }}
/>
```

注意：秒下场景中，文件已经渲染好了，所以 `backendDownloadUrl` 直接有值，DownloadModal 会直接显示"下载"和"复制链接"按钮，无需"渲染"按钮。

---

## Step 7: DownloadModal 支持秒下场景

**文件**: `src/components/DownloadModal.tsx`

当前 DownloadModal 已经支持 `backendDownloadUrl` 非空时显示下载+复制链接按钮，秒下场景传入 `backendDownloadUrl` 即可。

但秒下场景需要额外传入 `backendInfo`（文件信息）。当前 `backendInfo` 依赖 `repairResult`，秒下时可能没有 `repairResult`。

需要在页面中为秒下场景构造 `backendInfo`：从 `cacheEntry` 中提取信息。

```typescript
// RepairPage.tsx / Home.tsx 中
// 需要一个 state 来存储秒下时的文件信息
const [instantDownloadInfo, setInstantDownloadInfo] = useState<DownloadFileInfo | null>(null);

// onInstantDownload 回调
onInstantDownload={(cacheEntry) => {
  const downloadUrl = `/api/v1/download-file/${cacheEntry.filename}`;
  setRenderDownloadUrl(downloadUrl);
  setInstantDownloadInfo({
    filename: cacheEntry.filename,
    fileSize: `${(cacheEntry.size / (1024 * 1024)).toFixed(2)} MB`,
    sampleRate: `${cacheEntry.sample_rate / 1000} kHz`,
    bitDepth: cacheEntry.bit_depth,
    channels: 2, // 默认立体声
    duration: duration,
    algorithmVersion: cacheEntry.algorithm_version,
  });
  setShowDownloadModal(true);
}}

// DownloadModal 的 backendInfo
backendInfo={instantDownloadInfo || (hasBackendResult && repairResult ? { ... } : null)}
```

关闭弹窗时清空 `instantDownloadInfo`：
```typescript
onClose={() => {
  setShowDownloadModal(false);
  setInstantDownloadInfo(null);
}}
```

---

## 验证步骤

1. 上传MP3文件 → 规格信息（采样率、声道、时长）立即显示（不等解码完成）
2. 上传MP3文件 → 原始波形在上传后很快显示（从后端波形缓存）
3. 修复完成 → 自动弹出DownloadModal（含文件信息+下载按钮）
4. 点击下载 → 触发浏览器下载，无额外弹窗
5. AIRepairPanel中点击"秒下" → 弹出DownloadModal → 显示文件信息+下载+复制链接
6. decoded WAV缓存创建后，原始MP3文件被清理
7. 二次上传同一MP3 → 使用decoded WAV缓存快速解码
8. TypeScript编译通过
9. Android打包成功

# 修复双轨MP3下载 + 单轨缓存失效 + 单轨显示人声/伴奏轨

## Bug 1: 双轨下载MP3报错 "WAV音频文件不存在"

### 根因分析
[routes.py:1533](file:///workspace/backend/api/routes.py#L1533) 的 `/download-mp3/{task_id}` 端点查找 `{task_id}_repaired.wav`：
```python
wav_path = os.path.join(OUTPUT_DIR, f"{task_id}_repaired.wav")
```

但双轨任务的主 task_id（main_task_id）没有对应的 `_repaired.wav`。双轨任务的修复输出是 `{vocal_task_id}_repaired.wav` 和 `{accompaniment_task_id}_repaired.wav`（见 [routes.py:918-919](file:///workspace/backend/api/routes.py#L918-L919)）。

### 前端调用
[DownloadModal.tsx:344](file:///workspace/src/components/DownloadModal.tsx#L344) — 合并轨 MP3 下载调用 `handleDownloadMp3(dualTrackTaskId!)`
[DownloadModal.tsx:374](file:///workspace/src/components/DownloadModal.tsx#L374) — 人声轨 MP3 下载调用 `handleDownloadMp3(dualTrackVocalTaskId!)`

人声轨 MP3 下载（传入 `vocal_task_id`）应该已经能工作，因为有 `{vocal_task_id}_repaired.wav`。问题在主 task_id（`dualTrackTaskId`）。

### 修复方案
在 `/download-mp3/{task_id}` 端点中，检测任务是否为双轨主任务：
1. 获取任务信息
2. 如果 `params.processing_mode == "dual"`，检查 params 中是否有 `vocal_task_id` 和 `accompaniment_task_id`
3. 分别获取 `{vocal_task_id}_repaired.wav` 和 `{accompaniment_task_id}_repaired.wav`
4. 如果两个都存在，将它们混音合并为单声道/立体声 WAV，然后编码为 MP3
5. 如果只有一个存在，只编码那一个
6. 缓存合并后的 MP3 避免重复编码

具体实现：
```python
@router.get("/download-mp3/{task_id}")
async def download_mp3(task_id: str, request: Request):
    wav_path = os.path.join(OUTPUT_DIR, f"{task_id}_repaired.wav")
    
    # 检查是否为双轨主任务
    if not os.path.exists(wav_path):
        task = get_task(task_id)
        if task:
            params = task.get("params", {})
            if isinstance(params, str):
                params = json.loads(params)
            if params.get("processing_mode") == "dual":
                # 双轨模式：合并人声和伴奏
                vocal_task_id = params.get("vocal_task_id")
                acc_task_id = params.get("accompaniment_task_id")
                vocal_wav = os.path.join(OUTPUT_DIR, f"{vocal_task_id}_repaired.wav") if vocal_task_id else None
                acc_wav = os.path.join(OUTPUT_DIR, f"{acc_task_id}_repaired.wav") if acc_task_id else None
                
                if vocal_wav and os.path.exists(vocal_wav) and acc_wav and os.path.exists(acc_wav):
                    # 合并为临时WAV
                    merged_wav = os.path.join(OUTPUT_DIR, f"{task_id}_merged_temp.wav")
                    _merge_dual_tracks(vocal_wav, acc_wav, merged_wav)
                    wav_path = merged_wav
                    # 标记需要清理
                    # ... (编码后清理临时文件)
                elif vocal_wav and os.path.exists(vocal_wav):
                    wav_path = vocal_wav
                elif acc_wav and os.path.exists(acc_wav):
                    wav_path = acc_wav
    
    if not os.path.exists(wav_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")
    
    # ... 后续 MP3 编码逻辑不变
```

添加 `_merge_dual_tracks` 辅助函数：
```python
def _merge_dual_tracks(vocal_path: str, acc_path: str, output_path: str):
    import numpy as np
    import soundfile as sf
    from services.audio_loader import load_audio_with_fallback
    
    vocal_y, vocal_sr = load_audio_with_fallback(vocal_path, sr=None, mono=False)
    acc_y, acc_sr = load_audio_with_fallback(acc_path, sr=None, mono=False)
    
    # 确保采样率一致
    if vocal_sr != acc_sr:
        # 使用 scipy 重采样
        from scipy.signal import resample_poly
        if vocal_sr > acc_sr:
            acc_y = resample_poly(acc_y, vocal_sr, acc_sr, axis=1)
            acc_sr = vocal_sr
        else:
            vocal_y = resample_poly(vocal_y, acc_sr, vocal_sr, axis=1)
            vocal_sr = acc_sr
    
    # 对齐长度
    max_len = max(vocal_y.shape[1], acc_y.shape[1])
    if vocal_y.shape[1] < max_len:
        vocal_y = np.pad(vocal_y, ((0, 0), (0, max_len - vocal_y.shape[1])), mode='constant')
    if acc_y.shape[1] < max_len:
        acc_y = np.pad(acc_y, ((0, 0), (0, max_len - acc_y.shape[1])), mode='constant')
    
    # 混音
    mixed = (vocal_y + acc_y) / 2
    mixed = np.clip(mixed, -1.0, 1.0)
    sf.write(output_path, mixed.T if mixed.ndim > 1 else mixed, vocal_sr, subtype="PCM_16")
```

## Bug 2: 单轨修复缓存失效

### 根因分析
[database.py:201-208](file:///workspace/backend/database.py#L201-L208) 的 `find_repair_cache` 使用参数交集匹配：
```python
repair_param_keys = {
    "de_clipping", "noise_reduction", "de_essing", ...
}
stored_subset = {k: v for k, v in parsed.items() if k in repair_param_keys}
input_subset = {k: v for k, v in params.items() if k in repair_param_keys}
common_keys = stored_subset.keys() & input_subset.keys()
if common_keys and all(stored_subset[k] == input_subset[k] for k in common_keys):
    return result  # 匹配成功
```

问题：当 `common_keys` 为空时（`not common_keys`），不会返回缓存。这可能发生在：
1. 前后端参数 key 不匹配（比如前端发送 `declip` 但后端期望 `de_clipping`）
2. `algorithm_version` 发生变化

需要检查前端发送的参数 key 与后端 `repair_param_keys` 是否一致。

### 修复方案
检查前端传递的 params key 与后端定义的 `repair_param_keys` 是否完全匹配。如果存在映射问题，需要统一。

## Bug 3: 单轨处理显示人声轨/伴奏轨

### 根因分析
单轨修复任务不应该有 `processing_mode: "dual"`。但如果缓存查询返回了双轨任务的结果（因为 hash 匹配但 processing_mode 不同），前端可能会错误地显示双轨 UI。

问题可能在 `find_repair_cache` 不检查 `processing_mode`。单轨任务的 params 中没有 `processing_mode`，但如果之前有一个双轨任务使用了相同的文件 hash，缓存可能会匹配到双轨任务。

### 修复方案
在 `find_repair_cache` 中添加 `processing_mode` 过滤：
```python
# 单轨缓存不匹配双轨任务
if parsed.get("processing_mode") == "dual":
    continue  # 跳过双轨任务，单轨请求不应匹配
```

同时在前端，单轨修复结果的展示不应显示"人声轨/伴奏轨"标签。需要检查前端如何判断单轨 vs 双轨模式。

## 修改文件清单

### 1. `backend/api/routes.py`
- 修改 `/download-mp3/{task_id}` 端点：添加双轨主任务检测与合并逻辑
- 添加 `_merge_dual_tracks` 辅助函数

### 2. `backend/database.py`
- 修改 `find_repair_cache`：添加 `processing_mode` 过滤，单轨不匹配双轨

### 3. 前端代码（如需要）
- 检查单轨缓存展示组件是否正确区分单轨/双轨模式

## 验证步骤
1. 测试单轨修复缓存命中
2. 测试单轨任务不匹配双轨缓存
3. 测试双轨主任务 MP3 下载（应合并人声+伴奏）
4. 测试双轨人声轨 MP3 下载（应有独立文件）

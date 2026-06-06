# 修复双轨MP3下载 + 单轨缓存失效 + 单轨显示人声/伴奏轨

## Bug 1: 双轨下载MP3报错 "WAV音频文件不存在"

### 根因
`/download-mp3/{task_id}` 端点只找 `{task_id}_repaired.wav`。双轨主任务没有这个文件。

### 修复方案
在 `/download-mp3/{task_id}` 端点中：
1. 先检查 `{task_id}_repaired.wav` 是否存在（单轨情况）
2. 如果不存在，检查任务是否为双轨模式
3. 如果是双轨模式，找 `{task_id}_rendered_*_merged.wav`（render 缓存）
4. 如果没 render 缓存，找 `{vocal_task_id}_repaired.wav` 和 `{accompaniment_task_id}_repaired.wav`，合并为 WAV 后编码 MP3
5. MP3 不缓存，编码后立即删除临时文件

### 关键代码

添加 `_merge_wavs` 辅助函数：
```python
def _merge_wavs(vocal_path: str, acc_path: str, output_path: str):
    """合并人声和伴奏为混合 WAV"""
    import numpy as np
    import soundfile as sf
    from services.audio_loader import load_audio_with_fallback
    
    vocal_y, vocal_sr = load_audio_with_fallback(vocal_path, sr=None, mono=False)
    acc_y, acc_sr = load_audio_with_fallback(acc_path, sr=None, mono=False)
    
    max_len = max(vocal_y.shape[1], acc_y.shape[1])
    if vocal_y.shape[1] < max_len:
        vocal_y = np.pad(vocal_y, ((0, 0), (0, max_len - vocal_y.shape[1])), mode='constant')
    if acc_y.shape[1] < max_len:
        acc_y = np.pad(acc_y, ((0, 0), (0, max_len - acc_y.shape[1])), mode='constant')
    
    mixed = np.clip((vocal_y + acc_y) / 2, -1.0, 1.0)
    sf.write(output_path, mixed.T if mixed.ndim > 1 else mixed, vocal_sr, subtype="PCM_16")
```

端点逻辑：
```python
@router.get("/download-mp3/{task_id}")
async def download_mp3(task_id: str, request: Request):
    wav_path = os.path.join(OUTPUT_DIR, f"{task_id}_repaired.wav")
    temp_wav = None  # 用于清理临时合并 WAV
    
    if not os.path.exists(wav_path):
        task = get_task(task_id)
        if task:
            params = task.get("params", {})
            if isinstance(params, str):
                params = json.loads(params)
            if params.get("processing_mode") == "dual":
                # 找 render 合并缓存
                merged_wav = _find_rendered_merged(task_id)
                if merged_wav:
                    wav_path = merged_wav
                else:
                    # 回退：合并两个独立轨
                    vocal_task_id = params.get("vocal_task_id")
                    acc_task_id = params.get("accompaniment_task_id")
                    vocal_wav = os.path.join(OUTPUT_DIR, f"{vocal_task_id}_repaired.wav") if vocal_task_id else None
                    acc_wav = os.path.join(OUTPUT_DIR, f"{acc_task_id}_repaired.wav") if acc_task_id else None
                    if vocal_wav and os.path.exists(vocal_wav) and acc_wav and os.path.exists(acc_wav):
                        temp_wav = os.path.join(OUTPUT_DIR, f"{task_id}_temp_merged.wav")
                        _merge_wavs(vocal_wav, acc_wav, temp_wav)
                        wav_path = temp_wav
                    elif vocal_wav and os.path.exists(vocal_wav):
                        wav_path = vocal_wav
                    elif acc_wav and os.path.exists(acc_wav):
                        wav_path = acc_wav
    
    if not os.path.exists(wav_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")
    
    # MP3 不缓存，编码后删除
    mp3_path = os.path.join(OUTPUT_DIR, f"{task_id}_repaired.mp3")
    try:
        _wav_to_mp3(wav_path, mp3_path)
        # ... 流式返回 MP3
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MP3转码失败: {e}")
    finally:
        if os.path.exists(mp3_path):
            os.unlink(mp3_path)
        if temp_wav and os.path.exists(temp_wav):
            os.unlink(temp_wav)
```

添加 `_find_rendered_merged`：
```python
def _find_rendered_merged(task_id: str) -> str | None:
    if not os.path.isdir(OUTPUT_DIR):
        return None
    prefix = f"{task_id}_rendered_"
    for fname in os.listdir(OUTPUT_DIR):
        if fname.startswith(prefix) and fname.endswith("_merged.wav"):
            return os.path.join(OUTPUT_DIR, fname)
    return None
```

## Bug 2 + 3: 单轨缓存失效 / 单轨显示人声轨/伴奏轨

### 修复
在 `find_repair_cache` 中添加 `processing_mode` 过滤：
```python
if parsed.get("processing_mode") == "dual":
    continue  # 跳过双轨任务
```

## 修改文件
1. `backend/api/routes.py` — 修改 `/download-mp3/{task_id}` 端点
2. `backend/database.py` — 修改 `find_repair_cache`

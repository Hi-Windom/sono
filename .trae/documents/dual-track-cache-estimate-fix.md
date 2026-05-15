# 双轨修复缓存/交付缓存/预估大小修复计划 (v3)

## 摘要

双轨模式下三个功能全部失效，根因是前端缓存查询参数格式与后端存储格式不匹配。预估大小需要从后端获取文件元数据，而非依赖前端 localStorage。

## 根因分析

### 问题 1：修复缓存不命中（级联根因）

**前端**发送给 `lookupDualRepairCache` 的 params 格式为：
```json
{"params": {"algorithm_version": "v3.0", ...}, "vocal_params": {"de_clipping": 0.3, ...}, "accompaniment_params": {...}, "mix_ratio": 0.5}
```

**后端存储**的 params 格式为扁平结构（`repair_dual_audio_endpoint`/`repair_dual_from_hash` 中通过 `_VOCAL_KEY_MAP`/`_INST_KEY_MAP` 做扁平化后存储）：
```json
{"algorithm_version": "v3.0", ..., "vocal_declip": 0.3, "vocal_depop": 0.18, ..., "inst_declip": 0.3, ..., "vocal_ratio": 0.5, "accompaniment_ratio": 1.0}
```

`find_dual_repair_cache` 做 JSON 字符串全等比较，两种结构**永远不匹配**。

### 问题 2：交付缓存不显示

级联问题：修复缓存不命中 → 刷新后拿不到 `dualTrackTaskId` → `fetchRenderCache(taskId)` 不会触发 → 渲染交付列表为空。

### 问题 3：预估大小不显示

`upload-dual` 返回了 `vocal_info`/`accompaniment_info`（duration, channels, sample_rate），但这些信息未存入数据库。刷新后前端只能靠 localStorage 恢复，如果 store 版本变更或清除则丢失。

## 修改方案

### 修改 1：上传时将音频信息存入数据库

**文件**: `backend/api/routes.py` — `upload_dual_audio`

在创建 vocal_task 和 accompaniment_task 时，将音频信息存入 params：

```python
def get_audio_info(path):
    try:
        info = miniaudio.get_file_info(path)
        return {"sample_rate": info.sample_rate, "channels": info.nchannels, "duration": info.duration}
    except Exception:
        return None

vocal_audio_info = get_audio_info(vocal_upload_path)
acc_audio_info = get_audio_info(accompaniment_upload_path)

create_task(vocal_task_id, ..., {"audio_info": vocal_audio_info} if vocal_audio_info else {}, ...)
create_task(accompaniment_task_id, ..., {"audio_info": acc_audio_info} if acc_audio_info else {}, ...)
```

### 修改 2：新增后端接口 `POST /file-info-by-hash`

**文件**: `backend/api/routes.py`

```python
@router.post("/file-info-by-hash")
async def get_file_info_by_hash(request: FileInfoByHashRequest):
    """按文件哈希列表查询音频信息（duration, channels, sample_rate）"""
    result = {}
    for file_hash in request.file_hashes:
        task = find_task_by_hash(file_hash)
        if not task:
            continue
        params = task.get("params", {})
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except:
                params = {}
        audio_info = params.get("audio_info") if isinstance(params, dict) else None
        if audio_info:
            result[file_hash] = audio_info
        else:
            # 降级：从文件读取
            try:
                path = task.get("original_path")
                if path and os.path.exists(path):
                    info = miniaudio.get_file_info(path)
                    result[file_hash] = {"sample_rate": info.sample_rate, "channels": info.nchannels, "duration": info.duration}
            except:
                pass
    return result
```

前端 `backendApi.ts` 导出 `fetchFileInfoByHash(hashes: string[]): Promise<Record<string, AudioInfo>>`。

### 修改 3：后端 `/cache/lookup-dual` 端点扁平化处理

**文件**: `backend/api/routes.py`

修改 `DualRepairCacheLookupRequest` 增加 `vocal_params`, `accompaniment_params`, `mix_ratio`：

```python
class DualRepairCacheLookupRequest(BaseModel):
    vocal_file_hash: str
    accompaniment_file_hash: str
    params: dict
    vocal_params: dict | None = None
    accompaniment_params: dict | None = None
    mix_ratio: float | None = None
```

修改 `lookup_dual_repair_cache` 端点，在查询前做扁平化（与 `repair_dual_audio_endpoint` 和 `repair_dual_from_hash` 完全一致的扁平化逻辑）：

```python
@router.post("/cache/lookup-dual")
async def lookup_dual_repair_cache(req: DualRepairCacheLookupRequest):
    flat_params = req.params.copy()
    _VOCAL_KEY_MAP = { "de_clipping": "vocal_declip", ... }
    _INST_KEY_MAP = { "de_clipping": "inst_declip", ... }
    if req.vocal_params:
        for src_key, flat_key in _VOCAL_KEY_MAP.items():
            if src_key in req.vocal_params:
                flat_params[flat_key] = req.vocal_params[src_key]
    if req.accompaniment_params:
        for src_key, flat_key in _INST_KEY_MAP.items():
            if src_key in req.accompaniment_params:
                flat_params[flat_key] = req.accompaniment_params[src_key]
    if req.mix_ratio is not None:
        flat_params["vocal_ratio"] = req.mix_ratio
        flat_params["accompaniment_ratio"] = 1.0
    # 排除存储时添加的额外字段（已在 repair_dual 中设置的）
    flat_params.pop("processing_mode", None)
    flat_params.pop("vocal_path", None)
    flat_params.pop("accompaniment_path", None)
    flat_params.pop("vocal_task_id", None)
    flat_params.pop("accompaniment_task_id", None)
    
    from database import find_dual_repair_cache
    cached = find_dual_repair_cache(req.vocal_file_hash, req.accompaniment_file_hash, flat_params)
    ...
```

注意：`repair_dual_from_hash` 在扁平化后将 `params` 合并后存储，其中包含了 `processing_mode`, `vocal_path` 等字段，这些会被 `find_dual_repair_cache` 的 `filter_keys` 过滤掉，所以不需要在扁平化后额外移除。但为确保一致性，扁平化后的 params 应与存储时扁平化的最终结果完全一致。

### 修改 4：RepairPage mount 时从后端查询文件信息 + 恢复预估

**文件**: `src/pages/RepairPage.tsx`

在 mount useEffect 中，调用 `lookupDualRepairCache` 拿到 taskId 后，再调用 `fetchFileInfoByHash` 从后端获取文件元数据：

```typescript
// 刷新后恢复双轨状态
useEffect(() => {
    if (!isDualTrackMode || !dualTrackVocalFileHash || !dualTrackAccompanimentFileHash) return;
    
    let cancelled = false;
    (async () => {
      // 1. 查询修复缓存 → 拿到 taskId
      try {
        const mainParams = mapParamsToBackend(params, processingOptions, algorithmVersion);
        const vParams = mapVocalParamsToBackend(dualTrackVocalParams, processingOptions, algorithmVersion);
        const aParams = mapInstrumentParamsToBackend(dualTrackAccompanimentParams, processingOptions, algorithmVersion);
        const cacheResult = await lookupDualRepairCache(dualTrackVocalFileHash, dualTrackAccompanimentFileHash, {
          params: mainParams,
          vocal_params: vParams,
          accompaniment_params: aParams,
          mix_ratio: mixRatio,
        });
        if (cancelled) return;
        if (cacheResult.found && cacheResult.task_id) {
          setDualTrackTaskId(cacheResult.task_id);
          setTaskId(cacheResult.task_id);
          if (cacheResult.repair_result) {
            setDualTrackRepairResult(cacheResult.repair_result);
            sessionActions.setDualTrackProcessed(true);
          }
        }
      } catch {}
      
      // 2. 从后端查询文件音频信息 → 用于预估大小
      try {
        const fileInfo = await fetchFileInfoByHash([dualTrackVocalFileHash, dualTrackAccompanimentFileHash]);
        if (cancelled) return;
        if (fileInfo[dualTrackVocalFileHash]) {
          setDualTrackVocalInfo(fileInfo[dualTrackVocalFileHash]);
        }
        if (fileInfo[dualTrackAccompanimentFileHash]) {
          setDualTrackAccompanimentInfo(fileInfo[dualTrackAccompanimentFileHash]);
        }
      } catch {}
    })();
    return () => { cancelled = true; };
}, [isDualTrackMode, dualTrackVocalFileHash, dualTrackAccompanimentFileHash, ...]);
```

### 修改 5：添加日志

**文件**: `backend/api/routes.py` — 缓存查询日志
**文件**: `backend/database.py` — 参数比较不匹配时输出 key diff
**文件**: `src/pages/RepairPage.tsx` — 关键路径日志
**文件**: `src/components/AIRepairPanel.tsx` — 预估 API 调用日志

### 修改 6：自动化测试

**文件**: `backend/tests/test_dual_track_api.py`

新增测试类 `TestDualCacheLookup`：

```python
def test_cache_lookup_structured_params_matches_stored(self, api_client, fresh_db):
    """结构化参数（params+vocal_params+accompaniment_params+mix_ratio）→ 后端扁平化 → 命中缓存"""
    # 1. upload dual
    # 2. repair dual (with vocal_params, accompaniment_params, mix_ratio)
    # 3. lookup cache with same structured params
    # 4. assert found=True
```

新增测试方法 `TestAudioInfoStorage`：

```python
def test_audio_info_stored_during_upload(self, api_client, fresh_db):
    """上传时音频信息（duration, channels, sample_rate）存入数据库"""
    # 1. upload dual
    # 2. 查询 vocal_task 的 params 包含 audio_info
    # 3. 查询 accompaniment_task 的 params 包含 audio_info
    # 4. assert audio_info.duration > 0, audio_info.channels > 0, audio_info.sample_rate > 0
```

## 修改文件清单

| 文件 | 改动 |
|------|------|
| `backend/api/routes.py` | `upload_dual_audio` 存入 `audio_info`；新增 `POST /file-info-by-hash`；`DualRepairCacheLookupRequest` 增加 `vocal_params/accompaniment_params/mix_ratio`；`lookup_dual_repair_cache` 扁平化处理；日志 |
| `backend/database.py` | `find_dual_repair_cache` 不匹配时输出 key diff 日志 |
| `src/services/backendApi.ts` | 新增 `fetchFileInfoByHash` 函数导出 |
| `src/pages/RepairPage.tsx` | mount 时从后端查询文件信息恢复预估；缓存查询路径加日志；移除对 localStorage 恢复的依赖 |
| `src/components/AIRepairPanel.tsx` | 预估 API 调用加日志 |
| `backend/tests/test_dual_track_api.py` | 缓存参数格式一致性测试 + 音频信息存储测试 |

## 验证

1. `python -m pytest backend/tests/test_dual_track_api.py -v` — 所有测试通过（含新增）
2. `npx tsc --noEmit` — 零错误
3. `bash scripts/build_android_release.sh` — 打包成功
4. 手动验证：
   - 双轨上传 → 修复 → 再次修复时弹出缓存确认（修复缓存命中）
   - 刷新页面 → 预估大小正常显示（从后端查询）
   - 刷新页面 → 渲染交付列表恢复（修复缓存 → taskId → render cache）
   - 新的渲染完成后自动刷新列表（WebSocket 推送）
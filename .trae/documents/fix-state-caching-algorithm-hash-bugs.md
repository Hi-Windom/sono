# 全面修复前端状态缓存、默认最新算法、哈希命中跳过的 bug

## Summary

修复 3 个 bug：
1. **哈希命中未跳过修复流程** — 需改为：同文件+同算法版本+同参数+输出有效 才算缓存命中
2. **默认算法版本硬编码** — 新用户默认 `v2.0` 不会自动使用最新版本
3. **状态缓存不完整** — 浏览器-only 修复结果未保存到 session

## Current State Analysis

### Bug 1: 哈希命中条件不完整（最关键）

**用户明确要求**: "不是看任务id的，**算法版本和参数完全一致就视为命中缓存**（当然需要检查对应的输出文件是有效的）"

**现状问题**:

1. **后端未保存 repair params**: [routes.py L91](backend/api/routes.py#L91) upload 时 `create_task(..., params={})`；[routes.py L150](backend/api/routes.py#L150) `/repair` 收到 params 后传给 `submit_repair_task` → `_run_repair` 使用但 **从未 `update_task` 保存 params 回数据库**
   - 数据库 `tasks.params` 字段永远是上传时的空 `{}`
   
2. **后端 `check-file-hash` 返回信息不足**: [routes.py L63-71](backend/api/routes.py#L63-L71):
   ```python
   return {"exists": True, "task_id": ..., "output_path": ...}
   ```
   无 `status`、无 `params`，前端无法判断是否能复用

3. **前端未比对参数**: [useAudioProcessor.ts L897-904](src/hooks/useAudioProcessor.ts#L897-L904) 只要 `cached.task_id` 存在就算命中，直接设置 `backendProg=1.0` 但没跳过后续流程

4. **前端发送的完整 params** ([backendApi.ts L91-111](src/services/backendApi.ts#L91-L111)):
   ```typescript
   {
     de_clipping, noise_reduction, de_essing, de_crackle, de_pop,
     harmonic_enhance, dynamic_range, softness, presence_boost,
     bass_enhance, spatial_enhance, transient_repair, warmth, clarity,
     sample_rate, bit_depth, algorithm_version  // ← 包含算法版本
   }
   ```

### Bug 2: 默认算法版本硬编码

**文件**: [settingsStorage.ts L33](src/utils/settingsStorage.ts#L33), [useAudioProcessor.ts L207-238](src/hooks/useAudioProcessor.ts#L207-L238)

`defaultSettings.algorithmVersion = 'v2.0'` 硬编码。健康检查 effect 只在当前版本**不存在**时才切换，不会主动升级到最新。

### Bug 3: 状态缓存不完整

[useAudioProcessor.ts L1142-1154](src/hooks/useAudioProcessor.ts#L1142-L1154) 已有 backend 成功时的 session save，但浏览器-only 成功场景缺失。

## Proposed Changes

### 修改 1: 后端保存 repair params + 增强 hash 检查返回

**1a. `backend/services/task_manager.py` — `submit_repair_task` 保存 params**

```python
def submit_repair_task(task_id: str, audio_path: str, params: dict):
    logger.info(f"[submit_repair_task] task_id={task_id} params_keys={list(params.keys())}")
    # 保存 params 到任务记录，供后续缓存命中比对
    update_task(task_id, params=params)
    future = executor.submit(_run_repair, task_id, audio_path, params, MOBILE_MODE)
    future.add_done_callback(lambda f: _handle_future_exception(f, task_id, "repair"))
```

**1b. `backend/api/routes.py` — `check_file_hash` 返回完整任务信息**

```python
@router.post("/check-hash")
async def check_file_hash(request: CheckHashRequest):
    existing = find_task_by_hash(request.file_hash)
    if existing:
        return {
            "exists": True,
            "task_id": existing["id"],
            "output_path": existing.get("output_path", ""),
            "status": existing.get("status", ""),
            "params": existing.get("params", {}),       # ← 新增
        }
    return {"exists": False}
```

**1c. `backend/database.py` — `find_task_by_hash` 增加输出文件有效性检查**

已有 L93-94 的原始文件存在性检查，增加输出文件检查：
```python
def find_task_by_hash(file_hash: str) -> dict | None:
    ...
    if result.get("original_path") and not os.path.exists(result["original_path"]):
        return None
    # 新增：检查输出文件是否存在且有效（>0字节）
    output_path = result.get("output_path")
    if output_path and not os.path.exists(output_path):
        result["output_path"] = ""  # 标记输出不存在
    if result.get("params"):
        result["params"] = json.loads(result["params"])
    return result
```

### 修改 2: 前端完整缓存命中判断 + 跳过修复

**文件**: `src/hooks/useAudioProcessor.ts` — `applySettings` 函数

**2a. 构建 current params 用于比对**（在 hash 检查之前）:

```typescript
// 在 hash 检查之前，构建当前修复参数的完整表示
import { mapParamsToBackend } from '../services/backendApi';
// ... 在 applySettings 内部：
const currentParamsForCache = mapParamsToBackend(params, processingOptions, effectiveAlgorithmVersion);
```

**2b. 替换 L887-922 的 hash 检查逻辑**:

```typescript
let backendSkipped = false;
let cachedPreviewUrl: string | undefined;
let cachedRepairResult: object | undefined;

if (!currentTaskId || needsNewTask) {
  if (!audioFile) { ... return; }
  
  writeLog(`[applySettings] 检查后端缓存: fileHash=${fileHashRef.current}`);
  
  const hashCheck = await fetch(`/api/check-file-hash`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_hash: fileHashRef.current })
  });
  
  if (hashCheck.ok) {
    const cached = await hashCheck.json();
    
    if (cached.task_id && cached.exists) {
      // 比对参数一致性
      const cachedParams = cached.params || {};
      const paramsMatch = _compareRepairParams(currentParamsForCache, cachedParams);
      const outputValid = !!cached.output_path && cached.status === 'completed';
      
      writeLog(`[applySettings] 缓存检查: taskId=${cached.task_id} paramsMatch=${paramsMatch} outputValid=${outputValid} status=${cached.status}`);
      
      if (paramsMatch && outputValid) {
        // ✅ 完整缓存命中：文件+算法+参数一致，输出有效
        currentTaskId = cached.task_id;
        setTaskId(currentTaskId);
        taskIdRef.current = currentTaskId;
        backendProg.value = 1.0;
        backendSkipped = true;
        setProcessingStep('后端缓存命中');
        setProcessingProgress(0.5);
        cachedPreviewUrl = getPreviewUrl(currentTaskId, 'repaired');
        setBackendPreviewUrl(cachedPreviewUrl);
        writeLog(`[applySettings] ✅ 完整缓存命中，跳过后端修复`);
      } else {
        // 参数不匹配或输出无效 → 需要重新修复（复用已有 taskId 或新建）
        const reason = !paramsMatch ? '参数不一致' : !outputValid ? '输出无效' : `状态=${cached.status}`;
        writeLog(`[applySettings] 缓存未完全命中(${reason}), 需重新修复`);
        
        if (cached.task_id && cached.status !== 'completed') {
          // 任务存在但未完成/参数不同，复用 taskId 重新提交修复
          currentTaskId = cached.task_id;
          setTaskId(currentTaskId);
          taskIdRef.current = currentTaskId;
          setProcessingStep('重新提交修复...');
        } else {
          // 需要全新上传
          setProcessingStep('上传到后端...');
          setProcessingProgress(0.01);
          const uploadRes = await uploadAudio(audioFile, undefined, fileHashRef.current || undefined);
          currentTaskId = uploadRes.task_id;
          setTaskId(currentTaskId);
          taskIdRef.current = currentTaskId;
          setBackendAvailable(true);
          if (uploadRes.cached) {
            backendProg.value = 1.0;
            backendSkipped = true;  // upload 层面的缓存
            cachedPreviewUrl = getPreviewUrl(currentTaskId, 'repaired');
            setBackendPreviewUrl(cachedPreviewUrl);
            setProcessingStep('后端缓存命中');
            setProcessingProgress(0.5);
          }
        }
      }
    } else {
      // 完全无缓存 → 上传
      setProcessingStep('上传到后端...');
      setProcessingProgress(0.01);
      const uploadRes = await uploadAudio(audioFile, undefined, fileHashRef.current || undefined);
      currentTaskId = uploadRes.task_id;
      // ... 同上
    }
  } else {
    // hash 检查请求失败 → 上传
    ...existing upload fallback...
  }
}
```

**2c. 新增参数比对函数**:

```typescript
function _compareRepairParams(current: Record<string, unknown>, cached: Record<string, unknown>): boolean {
  const keysToCompare = [
    'algorithm_version', 'de_clipping', 'noise_reduction', 'de_essing',
    'de_crackle', 'de_pop', 'harmonic_enhance', 'dynamic_range',
    'softness', 'presence_boost', 'bass_enhance', 'spatial_enhance',
    'transient_repair', 'warmth', 'clarity', 'sample_rate', 'bit_depth',
  ];
  for (const key of keysToCompare) {
    if (current[key] !== cached[key]) {
      writeLog(`[cache] 参数不匹配: ${key} current=${current[key]} cached=${cached[key]}`);
      return false;
    }
  }
  return true;
}
```

**2d. 修改 backendRepairPromise 条件** (L958):

```typescript
const backendRepairPromise = (taskIdRef.current && !backendSkipped) ? (async () => {
  // 现有逻辑完全不变
})() : Promise.resolve(null);
```

**2e. Promise.allSettled 后适配** (L1110 之后):

```typescript
const [backendResult, browserResult] = await Promise.allSettled([backendRepairPromise, browserRepairPromise]);

let effectiveBackendResult = backendResult;
if (backendSkipped && backendResult.status === 'fulfilled' && backendResult.value === null) {
  effectiveBackendResult = {
    status: 'fulfilled' as const,
    value: { previewUrl: cachedPreviewUrl, repairResult: cachedRepairResult },
  };
}
```

后续 L1115-1154 用 `effectiveBackendResult` 替代 `backendResult`。

### 修改 3: 默认使用最新算法版本

**3a. `src/utils/settingsStorage.ts` L33**:
```typescript
algorithmVersion: '',  // 空哨兵：等待运行时解析为最新版本
```

**3b. `src/hooks/useAudioProcessor.ts` L128-129**:
```typescript
const savedAlgVer = savedSettings.algorithmVersion || '';
const [algorithmVersion, setAlgorithmVersionState] = useState<string>(savedAlgVer);
```

**3c. 健康检查 effect (L207-241)** — 空/无效版本自动选最新并持久化:
```typescript
fetchAlgorithmVersions().then(versions => {
  if (versions.length > 0) {
    setAvailableAlgorithms(versions);
    const current = versions.find(v => v.name === algorithmVersion);
    if (current && algorithmVersion) {
      // 用户有明确选择且有效 → 保持不变，加载 modes
      if (current.modes?.length) {
        const modes = current.modes.map(m => ({...}));
        setRepairModes(modes);
        setSelectedMode(modes[0].name);
      }
      versionInitializedRef.current = true;
    } else {
      // 无选择/无效 → 自动选最新
      const latest = versions[0];
      setAlgorithmVersionState(latest.name);
      saveSettings({ algorithmVersion: latest.name });
      if (latest.modes?.length) {
        const modes = latest.modes.map(m => ({...}));
        setRepairModes(modes);
        setSelectedMode(modes[0].name);
      }
      versionInitializedRef.current = true;
    }
  }
});
```

### 修改 4: 统一 Session 保存

**文件**: `src/hooks/useAudioProcessor.ts` — `applySettings` L1119-1167

将 session 保存从 `if (backendResult.status === 'fulfilled' && backendResult.value)` 内部提取到 `if (anySuccess)` 中统一处理：

```typescript
if (effectiveBackendResult.status === 'fulfilled' && effectiveBackendResult.value) {
  if (effectiveBackendResult.value.repairResult) {
    setRepairResult({...effectiveBackendResult.value.repairResult, completed_at: new Date().toISOString()});
  }
  anySuccess = true;
  setPlayMode('backend');
  const previewUrl = effectiveBackendResult.value.previewUrl;
  if (previewUrl) startStreamingPlayback(previewUrl);
  if (audioFile && taskIdRef.current) {
    loadAudioFromUrl(previewUrl, processingOptions.sampleRate).then(repairedBuffer => {
      setBackendProcessedBuffer(repairedBuffer);
    }).catch(err => console.warn('[applySettings] 后台下载失败:', err));
  }
}

if (browserResult.status === 'fulfilled' && browserResult.value) {
  setBrowserProcessedBuffer(browserResult.value);
  anySuccess = true;
}

if (anySuccess) {
  setHasBeenProcessed(true);
  if (!(effectiveBackendResult.status === 'fulfilled' && effectiveBackendResult.value)) {
    setPlayMode('browser');
  }
  // 统一保存 session（覆盖原有 L1142-1154 的位置）
  if (audioFile && taskIdRef.current) {
    saveSession({
      file: audioFile,
      fileName: audioFile.name,
      fileSize: audioFile.size,
      fileHash: fileHashRef.current || '',
      taskId: taskIdRef.current,
      backendAvailable: effectiveBackendResult.status === 'fulfilled' && !!effectiveBackendResult.value,
      hasBeenProcessed: true,
      wavInfo: wavInfo ? JSON.stringify(wavInfo) : '',
      repairResult: effectiveBackendResult.value?.repairResult
        ? JSON.stringify(effectiveBackendResult.value.repairResult)
        : '',
    });
  }
}
```

## Files to Modify

| 文件 | 修改内容 |
|------|---------|
| `backend/services/task_manager.py` L80-83 | `submit_repair_task` 增加 `update_task(task_id, params=params)` |
| `backend/database.py` L83-97 | `find_task_by_hash` 增加输出文件有效性检查 |
| `backend/api/routes.py` L63-71 | `check_file_hash` 返回 `status` + `params` |
| `src/utils/settingsStorage.ts` L33 | `algorithmVersion: 'v2.0'` → `''` |
| `src/hooks/useAudioProcessor.ts` L128-129 | 兼容空字符串初始化 |
| `src/hooks/useAudioProcessor.ts` L207-238 | 健康 effect: 空/无效版本自动选最新 |
| `src/hooks/useAudioProcessor.ts` L840-940 | hash 检查 → params 比对 → backendSkipped 标志 |
| `src/hooks/useAudioProcessor.ts` ~L958 | backendRepairPromise 增加 `!backendSkipped` |
| `src/hooks/useAudioProcessor.ts` L1110-1178 | effectiveBackendResult 适配 + 统一 session 保存 |

## Data Flow

```
用户点击"修复"
  ↓
构建 currentParams = mapParamsToBackend(params, options, algorithmVersion)
  ↓
POST /api/check-file-hash { file_hash }
  ↓
后端: find_task_by_hash() → 返回 {task_id, status, params, output_path}
  ↓
前端比对: currentParams === cached.params && status==='completed' && output_exists?
  ├─ ✅ 全匹配 → backendSkipped=true → 跳过 WebSocket + repairAudio
  └─ ❌ 不匹配 → 正常走上传/修复流程
  ↓
Promise.allSettled([backendRepairPromise, browserRepairPromise])
  ↓
effectiveBackendResult 适配（处理 backendSkipped 的 null → 虚拟成功结果）
  ↓
统一 session save（anySuccess 时都保存）
```

## Assumptions & Decisions

1. `mapParamsToBackend` 已从 `backendApi.ts` 导入（需确认 useAudioProcessor.ts 是否已导入）
2. `saveSettings` 已导入（已确认 ✓）
3. 后端 `update_task` 可正确序列化 params dict 为 JSON（已确认 ✓，database.py L59）
4. 向后兼容：老用户 localStorage 有有效版本的不受影响
5. params 比对忽略 value 为 0 vs undefined 的差异（均为 falsy 用 `!==` 精确比较）

## Verification Steps

1. **完整缓存命中验证**:
   - 上传文件 A → 用算法 v2.0 + 参数 X → 修复完成
   - 不换文件、不改参数 → 再次点修复 → 应显示"后端缓存命中"直接完成
   - 控制台: `[applySettings] ✅ 完整缓存命中，跳过后端修复`
   - 无新 WebSocket 连接、无 repairAudio 调用

2. **参数不匹配验证**:
   - 同上完成后 → 修改某个参数（如 noiseReduction）→ 点修复
   - 应走正常修复流程（不上传文件，复用 taskId 重新提交）

3. **算法版本切换验证**:
   - 同上完成后 → 切换算法版本 → 点修复
   - 应走正常修复流程

4. **默认算法验证**:
   - Clear Storage → Refresh → 算法版本应为后端最新（非 v2.0）

5. **Session 持久化验证**:
   - 任意路径修复完成 → Refresh → 确认状态恢复
   - 浏览器-only 修复 → Refresh → 确认 taskId 和音频保留

6. 全部通过后 `bash scripts/build_android_release.sh`

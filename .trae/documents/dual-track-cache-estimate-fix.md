# 双轨修复缓存/交付缓存/预估大小修复计划

## 摘要

双轨模式下三个功能全部失效：修复缓存、交付缓存、预估大小。根因是前端缓存查询参数字段格式与后端存储格式不匹配，导致级联失败。

## 当前状态分析

### 问题 1：修复缓存不命中（根因）

**前端** ([RepairPage.tsx:379-384](file:///workspace/src/pages/RepairPage.tsx#L379-L384)) 发送给 `lookupDualRepairCache` 的格式：
```json
{
  "params": { "algorithm_version": "v3.0", "de_clipping": 0.3, ... },
  "vocal_params": { "de_clipping": 0.3, ... },
  "accompaniment_params": { "de_clipping": 0.3, ... },
  "mix_ratio": 0.5
}
```

**后端存储** ([routes.py:842-871](file:///workspace/backend/api/routes.py#L842-L871)) 的格式（`repair_dual_from_hash` 和 `repair_dual_audio_endpoint` 的处理逻辑相同）：
```json
{
  "algorithm_version": "v3.0",
  "de_clipping": 0.3,
  ...
  "vocal_declip": 0.3,
  "vocal_depop": 0.18,
  ...
  "inst_declip": 0.3,
  ...
  "vocal_ratio": 0.5,
  "accompaniment_ratio": 1.0
}
```

**后端比较** ([database.py:263-269](file:///workspace/backend/database.py#L263-L269)) 时过滤掉 `vocal_file_hash`、`accompaniment_file_hash`、`vocal_task_id`、`accompaniment_task_id`、`vocal_filename`、`accompaniment_filename`、`processing_mode`、`vocal_path`、`accompaniment_path`、`vocal_output_path`、`accompaniment_output_path` 后做 JSON 字符串全等比较。

**结果**：嵌套 vs 扁平结构完全不同，永远不匹配。

### 问题 2：交付缓存（渲染缓存）不显示

- 页面刷新后，`dualTrackTaskId` 丢失
- mount 时的 `lookupDualRepairCache` 因参数格式问题返回 `{found: false}` → 拿不到 taskId → `fetchRenderCache(taskId)` 不会触发
- 即使有 `persistedRenderCaches` 静态快照，但没有 taskId 就无法从后端动态刷新

### 问题 3：预估大小不显示

- 上一轮修复已将 `fetchMemoryInfo`/`fetchStorageEstimate` 改为使用 `effectiveDuration`/`effectiveChannels`
- 但需要验证 `dualTrackVocalInfo` 是否正确传入和持久化
- 可能的问题：store 版本变更导致旧数据被清除

## 修改方案

### 修改 1：后端 `/cache/lookup-dual` 端点接受结构化参数并扁平化

**文件**: `backend/api/routes.py`

修改 `lookup_dual_repair_cache`，接受与 `/repair-dual` 相同的结构化参数（`params` + `vocal_params` + `accompaniment_params` + `mix_ratio`），在服务端做扁平化后再比较：

```python
class DualRepairCacheLookupRequest(BaseModel):
    vocal_file_hash: str
    accompaniment_file_hash: str
    params: dict
    vocal_params: dict | None = None
    accompaniment_params: dict | None = None
    mix_ratio: float | None = None
```

扁平化逻辑（与 `repair_dual_audio_endpoint` 和 `repair_dual_from_hash` 中的逻辑一致）：

```python
async def lookup_dual_repair_cache(req: DualRepairCacheLookupRequest):
    flat_params = req.params.copy()
    
    _VOCAL_KEY_MAP = { ... }  # 复用或引用
    _INST_KEY_MAP = { ... }
    
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
    
    # 用扁平化后的 params 查找缓存
    from database import find_dual_repair_cache
    cached = find_dual_repair_cache(req.vocal_file_hash, req.accompaniment_file_hash, flat_params)
    ...
```

**好处**：扁平化逻辑与服务端存储逻辑完全一致，前端不需要重复实现 key mapping。

### 修改 2：移除 `DualRepairCacheLookupResult` 中无用的 `params` 嵌套

**文件**: `backend/services/backendApi.ts`

前端的 `lookupDualRepairCache` 调用不变（仍发送 `params` + `vocal_params` + `accompaniment_params` + `mix_ratio`），因为后端现在已经能正确处理结构化输入。

### 修改 3：添加详细日志

**文件**: `backend/api/routes.py` — 在 `lookup_dual_repair_cache` 中添加日志：
```python
logger.info(f"[cache-lookup-dual] input structured params: params_keys={list(req.params.keys())} "
            f"vocal_params_keys={list(req.vocal_params.keys()) if req.vocal_params else 'none'} "
            f"acc_params_keys={list(req.accompaniment_params.keys()) if req.accompaniment_params else 'none'}")
logger.info(f"[cache-lookup-dual] flattened params: {json.dumps(flat_params, sort_keys=True)[:500]}")
```

**文件**: `backend/database.py` — 在 `find_dual_repair_cache` 中比较不匹配时输出 diff：
```python
stored_keys = set(filtered_stored.keys())
input_keys = set(params.keys())
logger.info(f"[cache-lookup-dual] MISMATCH: stored_keys={stored_keys} input_keys={input_keys}")
logger.info(f"[cache-lookup-dual] MISMATCH: stored_extra={stored_keys - input_keys} input_extra={input_keys - stored_keys}")
```

**文件**: `src/pages/RepairPage.tsx` — 在缓存查找和修复路径添加日志：
```typescript
console.log('[双轨缓存] 发送缓存查询', { 
  vocalHash: dualTrackVocalFileHash?.slice(0, 12), 
  accHash: dualTrackAccompanimentFileHash?.slice(0, 12),
  paramsKeys: Object.keys(dualParamsForCache),
});
```

**文件**: `src/components/AIRepairPanel.tsx` — 在预估 API 调用和渲染缓存查询添加日志：
```typescript
console.log('[预估] fetchMemoryInfo', { duration: fetchDuration, channels: fetchChannels, sr: processingOptions.sampleRate });
```

### 修改 4：自动化测试

**文件**: `backend/tests/test_dual_track_api.py`

添加两个测试：

```python
def test_dual_repair_cache_lookup_with_structured_params(self, api_client, fresh_db):
    """验证双轨修复缓存：用结构化参数（params+vocal_params+accompaniment_params）能正确命中"""
    # 1. 先执行修复（通过 repair-dual-from-hash）
    # 2. 用结构化参数调用 cache/lookup-dual
    # 3. 断言 found=True
    
def test_dual_repair_cache_lookup_params_consistency(self, api_client, fresh_db):
    """验证双轨修复缓存参数格式一致性：存储和查询使用同一扁平化逻辑"""
    # 1. 构造相同 params, vocal_params, accompaniment_params
    # 2. 先调用 repair-dual 模拟存储
    # 3. 再用相同结构化参数调用 cache/lookup-dual
    # 4. 断言 found=True
```

**文件**: 新增 `src/__tests__/dualTrackFlow.test.ts`（可选，如果项目有前端测试框架）

如果项目没有前端测试框架，则在 `backend/tests/` 中添加端到端测试。

### 修改 5：验证预估大小数据流

检查 `dualTrackVocalInfo` 从上传到 store 到 AIRepairPanel 的完整链路，添加保护性判断：

**文件**: `src/pages/RepairPage.tsx`

在 mount 恢复逻辑中增加日志：
```typescript
useEffect(() => {
    if (isDualTrackMode && persistedVocalInfo && !dualTrackVocalInfo) {
      console.log('[双轨] 从store恢复人声信息', persistedVocalInfo);
      setDualTrackVocalInfo(persistedVocalInfo);
    }
    ...
}, [...]);
```

## 修改文件清单

| 文件 | 改动 |
|------|------|
| `backend/api/routes.py` | `lookup_dual_repair_cache` 改为扁平化处理后再查询，添加详细日志 |
| `backend/database.py` | `find_dual_repair_cache` 不匹配时输出 key diff |
| `src/pages/RepairPage.tsx` | 缓存查询和修复路径添加日志 |
| `src/components/AIRepairPanel.tsx` | 预估 API 和渲染缓存查询添加日志 |
| `backend/tests/test_dual_track_api.py` | 新增缓存参数格式一致性测试 |

## 验证步骤

1. `cd /workspace && python -m pytest backend/tests/test_dual_track_api.py -v -k "dual_repair_cache"` — 新测试必须通过
2. `cd /workspace && npx tsc --noEmit` — 零错误
3. `bash scripts/build_android_release.sh` — 打包成功
4. 启动 dev 后手动验证：
   - 双轨上传 → 修复 → 再次修复时弹出缓存确认
   - 刷新页面 → 渲染交付列表恢复
   - 预估大小正常显示
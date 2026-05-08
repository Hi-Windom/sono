# 修复：结果缓存命中失败 + AI检测修复后结果不显示

## 当前状态分析

### Bug 1: 修复结果缓存命中失败，触发了新的修复

**代码路径**: [useAudioProcessor.ts](src/hooks/useAudioProcessor.ts#L915-L939) `applySettings()` 中：

```
上传完成(task_id) → GET /status/{task_id} → 比较 params + 检查 output_path
→ paramsMatch && outputValid → backendSkipped=true(跳过修复)
```

**问题定位**: `_compareRepairParams` 使用严格 `!==` 比较。后端 `/status` 返回的 `params` 经 SQLite → JSON序列化 → JSON反序列化，类型可能与前端 `mapParamsToBackend` 生成的对象不一致（如 `int vs float`、键缺失等）。另外当任务刚创建（params=`{}`）从未修复过时，cachedParams 为空对象，所有 key 的比较都会是 `current[key] !== undefined` → 返回 false，但此时 outputValid 也为 false 所以不会误命中。**真正的问题更可能在于参数值经 JSON 往返后的细微差异。**

### Bug 2: AI检测后端修复的结果显示"处理中..."

**代码路径**: [useAudioProcessor.ts](src/hooks/useAudioProcessor.ts#L1164-L1170) + [AIDetectionComparison.tsx](src/components/AIDetectionComparison.tsx#L258-L268)

**根因分析**（两种场景）:

**场景A — 修复缓存命中(`backendSkipped=true`)时**:
- L1115-L1121: 构造 synthetic `effectiveBackendResult = { value: { previewUrl, repairResult: undefined } }`
- L1164: `effectiveBackendResult.value` 是 truthy 对象 ✅ → 进入检测刷新块
- 调用 `detectAudio(repaired)` → 如果之前跑过检测且版本匹配 → `cached=true` → 设置 `backendAIDetection` ✅
- **但如果之前没跑过检测或版本变了** → `cached=false` → 不设置 → 显示"处理中..." ❌

**场景B — 修复实际执行完成后**:
- WebSocket 完成 → `effectiveBackendResult.value` 有真实值
- L1164 同样进入 → detectAudio(repaired)
- 同上，仅 cached 命中时才设置

**核心问题**: L1164 的逻辑只在 `res.cached === true` 时才设置 `backendAIDetection`。如果修复后检测从未执行过（或版本不匹配），则 `backendAIDetection` 永远为 null，UI 永远显示"处理中..."。

---

## 修改方案

### 修复 1: 增强 `_compareRepairParams` 容错性

**文件**: [useAudioProcessor.ts](src/hooks/useAudioProcessor.ts#L38-L52)

将严格 `!==` 比较改为容错比较：
- 数值类型容忍 `int/float` 差异（`==` 松散比较而非 `!==`）
- 缺失 key 视为不匹配（保持现有行为）
- 增加 debug 日志输出具体哪个字段不匹配

### 修复 2: 修复缓存命中时也加载已有的检测结果

**文件**: [useAudioProcessor.ts](src/hooks/useAudioProcessor.ts#L1164-L1170)

在修复成功（包括缓存命中）后，除了检查 `/detect` 缓存外，还从 `/status` 返回的 task 中直接读取已存储的 `repaired_detection_result`：

```typescript
// 现有逻辑: detectAudio 缓存命中才设置
// 改进: 还从 /status 响应中读取已存的 detection_result
if (effectiveBackendResult.status === 'fulfilled' && effectiveBackendResult.value && taskIdRef.current) {
  // 先尝试从 /status 已获取的 taskStatus 中读 repaired_detection_result
  // （需要把 taskStatus 提升到这个作用域可访问的位置）

  // 再尝试 detectAudio 缓存
  detectAudio(taskIdRef.current, 'repaired', detectorVersion).then(res => {
    if (res.detection_result) {  // 移除 res.cached 限制，有结果就显示
      setBackendAIDetection(mapDetectionResult(res.detection_result));
    }
  }).catch(() => {});
}
```

**关键改动**: 将 `taskStatus`（/status 的响应）提升到 `applySettings` 的作用域中，使其在 L1164 可访问。这样即使 `/detect` 缓存不命中，也能从 task 本身读取已存储的 `repaired_detection_result`。

同时：**移除 `res.cached` 前置条件** → 只要 `/detect` 返回了 `detection_result`（无论是新算的还是缓存的），都更新 UI。

### 修复 3: 会话恢复时也加载检测结果

**文件**: [useAudioProcessor.ts](src/hooks/useAudioProcessor.ts#L477-L489)

会话恢复（session restore）时，如果任务已完成，也需要从 `/status` 读取 `detection_result` 和 `repaired_detection_result` 并恢复到状态中。

---

## 具体文件改动清单

| 文件 | 改动 |
|------|------|
| `src/hooks/useAudioProcessor.ts` | 1. `_compareRepairParams` 容错改进<br>2. `applySettings` 中 `taskStatus` 变量提升作用域<br>3. 修复后检测刷新逻辑增强（移除 cached 限制 + 从 taskStatus 读取）<br>4. 会话恢复时加载检测结果 |

---

## 验证步骤

1. `npm run build` 通过
2. `bash scripts/build_android_release.sh` 打包成功

# 计划：重构缓存命中逻辑（数据驱动，不依赖任务状态）

## 核心原则

**缓存只看数据，不看状态。** 缓存命中的唯一条件：
1. `output_path` 存在（文件系统上文件存在）
2. 文件大小 > 10KB（有效音频）
3. `params` 与当前修复参数匹配

任务状态（pending/completed/error）**完全不参与缓存判定**。

## 日志证据

```
status=pending, algorithm_version: cached=undefined  ← 旧代码用status做门控，pending任务的空params导致永远不命中
```

旧代码的致命错误：**把"任务是否完成"和"是否有可用缓存结果"混为一谈**。

## 流程（扁平、无嵌套）

```
applySettings()
  ↓
① 有taskId? → GET /status/{id} 获取 taskStatus（纯数据查询）
  ↓
② evaluateCache(taskStatus, currentParams)
  │   只检查三件事：
  │   ├─ output_path 存在?
  │   ├─ output_size > 10KB?
  │   └─ params 匹配?
  ↓                    ↓
  CACHE_HIT            非 CACHE_HIT
  ↓                     ↓
③ 弹窗 confirm        ④ 正常修复路径
  ├─ 确定              上传(如需)→ 提交修复 → 等待结果
  │   ↓               （与缓存路径完全独立）
  │   applyCachedResult()
  │   同步设所有状态
  │   return ← 直接退出
  └─ 取消
      ↓
      fall through 到 ④
```

## evaluateCache() — 纯数据函数

```typescript
function evaluateCache(
  taskStatus: Record<string, unknown> | null,
  currentParams: Record<string, unknown>
): { hit: boolean; reason: string; outputSize: number } {
  // 无任务记录 → 不命中
  if (!taskStatus) return { hit: false, reason: '无任务记录', outputSize: 0 };

  // 检查输出文件（数据驱动，不看 status）
  const outputPath = taskStatus.output_path;
  if (!outputPath || typeof outputPath !== 'string') {
    return { hit: false, reason: '无输出文件', outputSize: 0 };
  }

  const outputSize = typeof taskStatus.output_size === 'number' ? taskStatus.output_size : 0;
  if (outputSize <= 0) {
    return { hit: false, reason: '输出文件无效', outputSize: 0 };
  }
  if (outputSize < 10240) {
    return { hit: false, reason: `文件过小(${formatBytes(outputSize)})`, outputSize: 0 };
  }

  // 检查参数匹配（数据驱动，不看 status）
  const cachedParams = (taskStatus.params && typeof taskStatus.params === 'object'
    ? taskStatus.params : {}) as Record<string, unknown>;
  if (!_compareRepairParams(currentParams, cachedParams)) {
    // 找出具体不匹配的字段用于日志
    return { hit: false, reason: '参数不一致', outputSize: 0 };
  }

  // 三项全通过 → 命中
  return { hit: true, reason: '', outputSize };
}
```

**注意**：没有一行代码检查 `taskStatus.status`。pending 任务如果有有效输出+匹配参数也能命中（虽然实际上不会有），completed 任务如果没有有效输出也不命中。

## applySettings 完整新结构

```typescript
const applySettings = useCallback(async () => {
  setIsProcessing(true);
  setProcessingProgress(0);
  setProcessingStep('准备修复...');

  const effectiveAlgorithmVersion = resolveAlgorithmVersion();
  const currentParamsForCache = mapParamsToBackend(params, processingOptions, effectiveAlgorithmVersion);

  let currentTaskId = taskIdRef.current;
  let taskStatus: Record<string, unknown> | null = null;

  // Step 1: 获取任务数据（纯数据查询，不基于状态做判断）
  if (currentTaskId && audioFile) {
    try {
      const res = await fetch(`/api/v1/status/${currentTaskId}`);
      if (res.ok) taskStatus = await res.json();
    } catch {}
  }

  // Step 2: 纯数据缓存评估
  const cache = evaluateCache(taskStatus, currentParamsForCache);

  // Step 3: 缓存命中 → 弹窗 → 可能直接返回
  if (cache.hit) {
    setProcessingStep('检测到已有修复记录...');
    setProcessingProgress(0.01);

    const ok = window.confirm(
      `检测到相同参数的修复记录。\n\n` +
      `输出文件大小: ${formatBytes(cache.outputSize)}\n\n` +
      `「确定」使用已有结果  「取消」重新修复`
    );

    if (ok) {
      // ★ 同步设置所有状态
      setRepairResult(/* 从 taskStatus.repair_result 映射 */);
      setBackendPreviewUrl(getPreviewUrl(currentTaskId!, 'repaired'));
      setHasBeenProcessed(true);
      setPlayMode('backend');
      setBackendAvailable(true);
      setProcessingStep('完成!');
      setProcessingProgress(1);
      saveSession({ /* ... */ });
      // AI检测恢复
      if (taskStatus!.detection_result) setOriginalAIDetection(...);
      if (taskStatus!.repaired_detection_result) setBackendAIDetection(...);

      // 异步加载 buffer（仅播放用，失败不影响导出）
      loadAudioFromUrl(getPreviewUrl(currentTaskId!, 'repaired'), processingOptions.sampleRate)
        .then(buf => setBackendProcessedBuffer(buf)).catch(() => {});

      setIsProcessing(false);
      setTimeout(() => { setProcessingStep(''); setProcessingProgress(0); }, 2000);
      return; // ★ 唯一出口：不走 Promise、不上传、不播放
    }
    writeLog('[applySettings] 用户选择重新修复');
  } else {
    writeLog(`[applySettings] ${cache.reason}`);
  }

  // Step 4: 正常修复路径（唯一，无嵌套）

  // 4a: 上传（需要时）
  if (!currentTaskId) {
    if (!audioFile) { setIsProcessing(false); return; }
    setProcessingStep('上传到后端...');
    try {
      const uploadRes = await uploadAudio(audioFile);
      currentTaskId = uploadRes.task_id;
      setTaskId(currentTaskId);
      taskIdRef.current = currentTaskId;
      setBackendAvailable(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setBackendError('上传失败: ' + msg);
      setProcessingStep('[上传失败] ' + msg);
      setIsProcessing(false);
      return;
    }
  }

  // 4b: 创建并执行修复 Promise（保持现有逻辑不变）
  const backendProg = { value: 0 };
  const backendRepairPromise = (async () => { /* ... 保持不变 ... */ })();
  const browserRepairPromise = enableBrowserRepair ? (async () => { /* ... */ })() : Promise.resolve(null);

  const [backendResult, browserResult] = await Promise.allSettled([backendRepairPromise, browserRepairPromise]);

  // 4c: 处理结果（保持现有逻辑不变，删除 backendSkipped 分支）
  // ...

}, [/* deps含 enableBrowserRepair */]);
```

## 删除的代码

| 内容 | 行数 | 原因 |
|---|---|---|
| 复用任务的 if/else 链（status==completed 判断） | ~25行 | 不再看 status |
| `checkRepairCache()` 内联函数 | ~15行 | 被 evaluateCache 替代 |
| 上传后的二次缓存检查 | ~50行 | 冗余，决策已在前面 |
| `backendSkipped` 变量及所有赋值 | ~8行 | 扁平结构不需要 |
| `backendProg = { value: 0 }` 在 skipped 时预置 | ~2行 | 不再需要 |
| Promise 结果处理中 backendSkipped 分支 | ~20行 | 缓存命中已提前 return |
| `needsNewTask` 变量及逻辑 | ~5行 | 用 `!currentTaskId` 替代 |

**净减少约 120 行嵌套条件代码。**

## 关键设计决策

### Q: 有 taskId 但缓存未命中时，是复用还是新建？
**A: 复用当前 taskId 提交新修复。** 因为：
- 缓存未命中说明这次参数不同或输出无效
- 但 taskId 对应的是同一个文件的上传记录
- 后端 `/repair` 会基于同一文件重新执行修复
- 不浪费存储空间

### Q: 上传还带 fileHash 吗？
**A: 不带。** 让后端每次创建全新 task，避免和旧 task 的状态混淆。
前端缓存判定已经独立于任务生命周期了，不需要上传层缓存。

### Q: pending 任务怎么处理？
**A: 不特殊处理。** 如果 pending 任务恰好有有效输出+匹配参数（几乎不可能），evaluateCache 会命中让用户选择。否则走正常修复路径——后端 `/repair` 对同一个 task_id 再次提交会覆盖之前的 pending 状态。

## 文件变更清单

| 文件 | 改动 |
|---|---|
| `src/hooks/useAudioProcessor.ts` | applySettings 重写前半部分(L867-L980)，删除 backendSkipped 分支(L1157-1177)，新增 evaluateCache + applyCachedResult |
| `src/pages/Home.tsx` | 无改动（hasBackendResult 已含 \|\| !!repairResult） |
| `src/pages/RepairPage.tsx` | 无改动 |
| `backend/database.py` | 已改好（output_size 字段） |

## 验证

1. `npm run build` 编译通过
2. `bash scripts/build_android_release.sh` 打包成功

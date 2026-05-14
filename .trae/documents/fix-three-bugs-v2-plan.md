# 修复计划：3个Bug深度分析 + 修复方案

---

## Bug 1: 单轨上传MP3解码失败

### 根因（已找到！）

**文件**：`src/workers/useAudioWorker.ts` 第86行

```typescript
const response = await sendToWorker<...>(
    { type: 'decode-wav', id, buffer },
    [buffer],  // ← ArrayBuffer 被 TRANSFER 到 Worker！
);
```

`sendToWorker` 的第二个参数 `[buffer]` 是 **transfer list**。当 ArrayBuffer 被 transfer 到 Worker 后，**原始 ArrayBuffer 会被 detach（变成零长度空buffer）**。

流程：
1. `loadAudioFile` 第829行：`const arrayBuf = await file.arrayBuffer()` → 获取原始字节
2. 第857行：`audioWorker.decodeWav(context, arrayBuf)` → Worker 内部用 `[buffer]` transfer → **原始 arrayBuf 被 detach**
3. Worker 返回 null（MP3 不是 WAV 格式，Worker 无法解码）
4. 第881行：`context.decodeAudioData(arrayBuf)` → **arrayBuf 已为空！** → decodeAudioData 抛出错误
5. 第886行：显示"音频解码失败：不支持的格式或文件已损坏"

### 是否关联前端状态恢复？
**是**。状态恢复时若尝试重新加载音频，同样会经过 `loadAudioFile` → Worker transfer → buffer detach → decodeAudioData 失败。

### 错误状态细分
当前只有一个通用错误信息。需要细分：
- `arrayBuf.byteLength === 0` → "解码缓冲区异常，请重新上传"（检测到 buffer 被 detach）
- `decodeErr.name === 'EncodingError'` → "浏览器不支持该音频格式"
- 其他 → "音频文件已损坏或无法解析"

### 修复方案

1. **`src/workers/useAudioWorker.ts`** — 在 transfer 前复制 ArrayBuffer：
   ```typescript
   const response = await sendToWorker<...>(
       { type: 'decode-wav', id, buffer },
       [buffer],  // 保持 transfer 性能优势
   );
   ```
   调用方 `useAudioProcessor.ts` 第857行改为传副本：
   ```typescript
   const workerDecoded = await audioWorker.decodeWav(context, arrayBuf.slice(0));
   ```
   ⚠️ 同时检查第870行 `audioWorker.decodeWav(context, wavBuf)` — 这里的 `wavBuf` 来自后端下载，不会被再次使用，不需要切片。

2. **`src/hooks/useAudioProcessor.ts`** — 细分 decodeAudioData 错误（第881-888行）：
   ```typescript
   try {
       buffer = await context.decodeAudioData(arrayBuf);
   } catch (decodeErr) {
       console.warn('[loadAudioFile] 浏览器解码失败:', decodeErr);
       setIsDecodingAudio(false);
       if (arrayBuf.byteLength === 0) {
           setBackendError('解码缓冲区异常，请重新上传文件');
       } else if (decodeErr instanceof DOMException && decodeErr.name === 'EncodingError') {
           setBackendError('浏览器不支持该音频格式，请尝试WAV格式');
       } else {
           setBackendError('音频解码失败：文件已损坏或无法解析');
       }
       return;
   }
   ```

---

## Bug 2: 预估大小和交付显示挂了 + 缓存命中没有

### 预估显示根因
与 Bug 1 同源：MP3 解码失败 → `audioBufferRef.current` 未设置 → `duration` 为 0 → `effectiveDuration` 为 0 → `estimateFileSize` 返回 0 → 显示空白。

修复 Bug 1 后此问题自然解决。

### 缓存命中根因
需验证 `find_repair_cache` 交集比较是否正确生效。

**问题1**：`find_repair_cache` 中的 `repair_param_keys` 使用旧式 key（`de_clipping`, `noise_reduction` 等），但前端 `mapParamsToBackend` 返回的 params 可能包含不同 key 集合。

**问题2**：`find_repair_cache` 的比较逻辑在 line 200-210：
```python
stored_subset = {k: v for k, v in parsed.items() if k in repair_param_keys}
input_subset = {k: v for k, v in params.items() if k in repair_param_keys}
common_keys = stored_subset.keys() & input_subset.keys()
if common_keys and all(stored_subset[k] == input_subset[k] for k in common_keys):
```

需要确认 `stored_subset` 和 `input_subset` 是否确实有公共 key。

**修复方案**：
1. 在 `find_repair_cache` 中添加调试日志，输出 `stored_subset` 和 `input_subset` 的 key 集合
2. 确保 `mapParamsToBackend` 返回的 key 与 `repair_param_keys` 一致

---

## Bug 3: 测试是摆设

### 当前测试问题
`test_cache_lookup.py` 只测试了数据库函数，没有测试：
1. **ArrayBuffer transfer 问题** — 前端 Worker transfer 导致 buffer detach
2. **端到端上传解码流程** — MP3 上传后能否正确解码
3. **实际缓存查找流程** — 前端 `lookupRepairCache` 调用后端 `/cache/lookup`

### 修复方案
新增测试覆盖：

1. **`backend/tests/test_cache_lookup.py`** 追加：
   - 单轨缓存：输入有 `algorithm_version` 但存储没有 → 交集比较应命中
   - 单轨缓存：存储有 `mastering_style` 但输入没有 → 交集比较应命中
   - 双轨缓存：`algorithm_version` 在输入但不在存储 → 交集比较应命中

2. **新增 `backend/tests/test_mp3_upload.py`**：
   - 创建真实 MP3 文件（用 `lameenc` 编码）
   - 调用 `/api/v1/upload` 上传 MP3
   - 验证后端 `miniaudio.get_file_info()` 能正确读取 MP3 信息
   - 验证后端 `/api/v1/decoded-wav/{hash}` 返回正确的 WAV

3. **新增前端测试（如果项目有前端测试框架）**：
   - 验证 `useAudioWorker` 的 `decodeWav` 调用后原始 buffer 不被 detach

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `src/hooks/useAudioProcessor.ts` | 第857行：`arrayBuf.slice(0)`；第881-888行：细分 decodeAudioData 错误 |
| `src/workers/useAudioWorker.ts` | 无需修改（保持 transfer 性能优势，由调用方切片） |
| `backend/database.py` | `find_repair_cache` 添加调试日志 |
| `backend/tests/test_cache_lookup.py` | 追加交集比较边界用例 |
| `backend/tests/test_mp3_upload.py` | 新增 MP3 上传和解码测试 |

---

## 验证步骤

1. **MP3 上传**：上传 MP3 文件 → 不再显示"解码失败"
2. **错误细分**：故意破坏 buffer 测试不同错误消息
3. **预估显示**：MP3 上传成功后预估大小正常显示
4. **缓存命中**：执行修复，第二次相同参数时查看日志确认 `[cache-lookup] ✅ MATCH`
5. **运行测试**：`python -m pytest backend/tests/test_cache_lookup.py -v`
6. **构建验证**：`npm run build`
7. **Android 打包**：`bash scripts/build_android_release.sh`
8. **启动 dev**：`bash scripts/start_dev.sh`
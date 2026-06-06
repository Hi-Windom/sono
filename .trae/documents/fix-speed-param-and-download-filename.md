# 修复倍速参数不生效 + 下载文件名加倍速信息

## 问题 1：倍速参数没生效

### 根因

双轨模式下，repair core 用**前缀过滤**来拆分参数：
```python
vocal_params = {k.replace("vocal_", ""): v for k, v in params.items() if k.startswith("vocal_")}
inst_params = {k.replace("inst_", ""): v for k, v in params.items() if k.startswith("inst_")}
```

但 `speed` 在 `params` 中存储为无前缀的 `"speed"` 键（routes.py 第 762 行），不匹配 `vocal_` 或 `inst_` 前缀 → 被排除 → 变速不生效。

**根本问题**：前缀过滤本身就是脆弱的模式。任何新增的共享参数（如 speed）都需要手动处理，容易遗漏。

### 修复方案

**重构参数传递架构**：不再依赖前缀过滤，而是将 vocal/inst 参数作为嵌套 dict 直接传递。

#### 修改 1：`param_maps.py`

`VOCAL_KEY_MAP` 和 `INST_KEY_MAP` 中 `speed` 映射改为带前缀的键，避免 flatten 时冲突：

```python
# 修改前
VOCAL_KEY_MAP = { ..., "speed": "speed" }
INST_KEY_MAP = { ..., "speed": "speed" }

# 修改后
VOCAL_KEY_MAP = { ..., "speed": "vocal_speed" }
INST_KEY_MAP = { ..., "speed": "inst_speed" }
```

`DUAL_REPAIR_PARAM_KEYS` 自动从 map values 派生，无需手动修改。

#### 修改 2：`routes.py` 双轨端点

在 flatten 的同时，将结果也存为嵌套 dict，供 repair core 直接使用：

```python
# 修改前
if request.vocal_params:
    params.update(flatten_vocal_params(request.vocal_params))
if request.accompaniment_params:
    params.update(flatten_inst_params(request.accompaniment_params))

# 修改后
if request.vocal_params:
    flat_vocal = flatten_vocal_params(request.vocal_params)
    params["vocal_params"] = flat_vocal       # 供 repair core 使用
    params.update(flat_vocal)                  # 供缓存比较使用（flat keys）
if request.accompaniment_params:
    flat_inst = flatten_inst_params(request.accompaniment_params)
    params["inst_params"] = flat_inst          # 供 repair core 使用
    params.update(flat_inst)                   # 供缓存比较使用（flat keys）
```

`params["speed"] = request.speed` 保持不变（共享参数在顶层）。

#### 修改 3：`repair_v3_2/core.py` 和 `repair_v3_2a/core.py` 双轨段

用嵌套 dict 直接读取替代前缀过滤：

```python
# 修改前
vocal_params = {k.replace("vocal_", ""): v for k, v in params.items() if k.startswith("vocal_")}
inst_params = {k.replace("inst_", ""): v for k, v in params.items() if k.startswith("inst_")}

# 修改后
vocal_params = params.get("vocal_params", {}).copy()
inst_params = params.get("inst_params", {}).copy()
# 共享参数（无前缀）显式传递给两轨
for shared_key in ("speed",):
    if shared_key in params:
        vocal_params[shared_key] = params[shared_key]
        inst_params[shared_key] = params[shared_key]
```

#### 修改 4：`database.py`

无需修改。缓存比较继续使用 `DUAL_REPAIR_PARAM_KEYS` 从 flat keys 中提取比较，逻辑不变。

---

## 问题 2：下载文件名加上倍速信息

当 speed ≠ 1.0 时，下载文件名应包含倍速信息。

### 修改 5：`routes.py` WAV 下载 `/download/{task_id}`（第 1325-1327 行）

```python
# 修改前
download_name = f"{base_name}_repaired.wav"

# 修改后
speed = task.get("params", {}).get("speed", 1.0)
speed_tag = f"{speed}x_" if speed and speed != 1.0 else ""
download_name = f"{base_name}_{speed_tag}repaired.wav"
```

### 修改 6：`routes.py` MP3 下载 `/download-mp3/{task_id}`（第 1558-1562 行）

```python
# 修改前
download_name = f"{original_basename}.mp3"

# 修改后
speed = task.get("params", {}).get("speed", 1.0) if task else 1.0
speed_tag = f"{speed}x_" if speed and speed != 1.0 else ""
download_name = f"{original_basename}_{speed_tag}repaired.mp3"
```

### 修改 7：`routes.py` 渲染缓存下载 `/download-file/{filename}`（第 1393-1399 行）

```python
# 修改前
name_parts = [original_basename]
if algo_ver_display:
    name_parts.append(algo_ver_display)

# 修改后
name_parts = [original_basename]
if algo_ver_display:
    name_parts.append(algo_ver_display)
speed = task.get("params", {}).get("speed", 1.0) if task else 1.0
if speed and speed != 1.0:
    name_parts.append(f"{speed}x")
```

### 修改 8：`routes.py` 渲染文件名生成（第 946-952 行）

```python
# 修改前
render_filename = f"{request.task_id}_rendered_{algo_ver}_{request.sample_rate}_{request.bit_depth}..."

# 修改后
speed = task_params.get("speed", 1.0)
speed_tag = f"_{speed}x" if speed and speed != 1.0 else ""
render_filename = f"{request.task_id}_rendered_{algo_ver}{speed_tag}_{request.sample_rate}_{request.bit_depth}..."
```

### 修改 9：前端 `generateExportFilename`（`src/hooks/useAudioProcessor.ts` 第 111-124 行）

增加可选的 `speed` 参数：

```typescript
export function generateExportFilename(
  audioFileName: string | undefined,
  algorithmVersion: string,
  sampleRate: number,
  bitDepth: number,
  suffix?: string,
  speed?: number,
): string {
  const baseName = audioFileName ? audioFileName.replace(/\.[^/.]+$/, '') : 'audio';
  const ts = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 15);
  const parts = [baseName];
  if (suffix) parts.push(suffix);
  parts.push(algorithmVersion);
  if (speed && speed !== 1.0) parts.push(`${speed}x`);
  parts.push(`${sampleRate / 1000}k`, `${bitDepth}bit`, ts);
  return `${parts.join('_')}.wav`;
}
```

同时更新所有调用处传递 speed 参数。

---

## 验证

1. 双轨模式下设置 speed ≠ 1.0，确认修复后音频时长按比例变化
2. 下载文件名包含 `{speed}x` 信息
3. 运行 `python -m pytest backend/tests/test_cache_lookup.py -v` 确认缓存测试通过
4. TypeScript 编译零错误
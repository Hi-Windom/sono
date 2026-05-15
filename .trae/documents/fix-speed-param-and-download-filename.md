# 修复倍速参数不生效 + 下载文件名加倍速信息

## 问题 1：倍速参数没生效

### 根因分析

双轨模式下，`speed` 参数在参数拆分时丢失。

**数据流追踪**：

1. 前端发送 `vocal_params = {speed: 1.5, ...}` 和 `accompaniment_params = {speed: 1.5, ...}`
2. `routes.py` 中 `flatten_vocal_params` 和 `flatten_inst_params` 将 `speed` 映射为无前缀的 `"speed"` 键（见 `param_maps.py` 第 25、50 行）
3. 最终 `params["speed"] = request.speed`（第 762 行）覆盖了 flatten 的结果
4. 在 repair core 的双轨函数中，`vocal_params` 和 `inst_params` 通过前缀过滤提取：
   ```python
   vocal_params = {k.replace("vocal_", ""): v for k, v in params.items() if k.startswith("vocal_")}
   inst_params = {k.replace("inst_", ""): v for k, v in params.items() if k.startswith("inst_")}
   ```
5. `params["speed"]` 没有 `vocal_` 或 `inst_` 前缀 → 被排除 → `process_vocal_track` 和 `process_instrument_track` 拿不到 speed → `params.get('speed', 1.0)` 返回 1.0 → 变速不生效

### 修复方案

在双轨参数拆分后，显式将 `speed` 从 `params` 复制到 `vocal_params` 和 `inst_params`。

**修改文件**：
- `backend/services/repair/repair_v3_2/core.py`（第 1304-1308 行附近）
- `backend/services/repair/repair_v3_2a/core.py`（第 943-944 行附近）

**修改内容**（两处相同）：
```python
vocal_params = {k.replace("vocal_", ""): v for k, v in params.items() if k.startswith("vocal_")}
inst_params = {k.replace("inst_", ""): v for k, v in params.items() if k.startswith("inst_")}

# speed 存储在 params 中无前缀，需显式传递给两轨
if "speed" in params:
    vocal_params["speed"] = params["speed"]
    inst_params["speed"] = params["speed"]
```

---

## 问题 2：下载文件名加上倍速信息

### 需求

当 speed ≠ 1.0 时，下载文件名应包含倍速信息，例如：
- `{原始名}_1.5x_repaired.wav`
- `{原始名}_1.5x.mp3`
- `{原始名}_v2.4a_1.5x_44k_16bit_20260515_123456.wav`

### 修改点

#### 2.1 WAV 下载 `/download/{task_id}`

**文件**：`backend/api/routes.py` 第 1325-1327 行

从 `task.get("params", {})` 中读取 `speed`，若不为 None 且 ≠ 1.0，在文件名中加入 `{speed}x`。

```python
# 修改前
download_name = f"{base_name}_repaired.wav"

# 修改后
speed = task.get("params", {}).get("speed", 1.0)
speed_suffix = f"{speed}x_" if speed and speed != 1.0 else ""
download_name = f"{base_name}_{speed_suffix}repaired.wav"
```

#### 2.2 MP3 下载 `/download-mp3/{task_id}`

**文件**：`backend/api/routes.py` 第 1558-1562 行

同样从 task params 读取 speed，加入文件名。

```python
# 修改前
download_name = f"{original_basename}.mp3"

# 修改后
speed = task.get("params", {}).get("speed", 1.0) if task else 1.0
speed_suffix = f"{speed}x_" if speed and speed != 1.0 else ""
download_name = f"{original_basename}_{speed_suffix}repaired.mp3"
```

#### 2.3 渲染缓存下载 `/download-file/{filename}`

**文件**：`backend/api/routes.py` 第 1393-1399 行

在 `name_parts` 中加入 speed 信息。

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

#### 2.4 渲染文件名生成（服务器存储用）

**文件**：`backend/api/routes.py` 第 946-952 行

在 render_filename 中加入 speed 信息，以便后续下载时能解析。

```python
# 修改前
render_filename = f"{request.task_id}_rendered_{algo_ver}_{request.sample_rate}_{request.bit_depth}..."

# 修改后
speed = task_params.get("speed", 1.0)
speed_tag = f"_{speed}x" if speed and speed != 1.0 else ""
render_filename = f"{request.task_id}_rendered_{algo_ver}{speed_tag}_{request.sample_rate}_{request.bit_depth}..."
```

#### 2.5 前端导出文件名

**文件**：`src/hooks/useAudioProcessor.ts` 第 111-124 行

`generateExportFilename` 函数增加可选的 `speed` 参数。

```typescript
export function generateExportFilename(
  audioFileName: string | undefined,
  algorithmVersion: string,
  sampleRate: number,
  bitDepth: number,
  suffix?: string,
  speed?: number,  // 新增
): string {
  const baseName = audioFileName ? audioFileName.replace(/\.[^/.]+$/, '') : 'audio';
  const ts = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 15);
  const parts = [baseName];
  if (suffix) parts.push(suffix);
  parts.push(algorithmVersion);
  if (speed && speed !== 1.0) parts.push(`${speed}x`);  // 新增
  parts.push(`${sampleRate / 1000}k`, `${bitDepth}bit`, ts);
  return `${parts.join('_')}.wav`;
}
```

同时更新所有调用处，传递 speed 参数。

---

## 验证

1. 双轨模式下设置 speed ≠ 1.0，确认修复后音频时长按比例变化
2. 下载文件名包含 `{speed}x` 信息
3. 运行 `python -m pytest backend/tests/test_cache_lookup.py -v` 确认缓存测试通过
4. TypeScript 编译零错误
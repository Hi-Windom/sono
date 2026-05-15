# v3.3 双轨"修复结果不存在" Bug 修复

## 根因分析

### 路径不匹配（核心问题）

`_repair_dual_track`（`core.py` L202-L205）**自行计算**输出文件路径：

```python
output_dir = os.path.dirname(output_path)
base_name = os.path.splitext(os.path.basename(output_path))[0]
vocal_output = os.path.join(output_dir, f"{base_name}_vocal.wav")       # {task_id}_repaired_vocal.wav
inst_output = os.path.join(output_dir, f"{base_name}_accompaniment.wav") # {task_id}_repaired_accompaniment.wav
```

但修复端点（`routes.py` L771-L775）在 `params` 中**存储了不同的路径**：

```python
params["vocal_output_path"] = os.path.join(OUTPUT_DIR, f"{vocal_task_id}_repaired.wav")
params["accompaniment_output_path"] = os.path.join(OUTPUT_DIR, f"{accompaniment_task_id}_repaired.wav")
```

**后果**：
- 实际文件写入：`{task_id}_repaired_vocal.wav` / `{task_id}_repaired_accompaniment.wav`
- 渲染端点查找：`{vocal_task_id}_repaired.wav` / `{accompaniment_task_id}_repaired.wav`
- 文件不存在 → 返回 400 "修复结果不存在"

### 次要问题：返回值缺少路径

`_repair_dual_track` 的返回值（L344-L353）不包含 `vocal_output_path` 和 `accompaniment_output_path`，导致 `task_manager.py` L384-L392 无法更新子任务的 `output_path`。

## 修复方案

### 步骤 1：`_repair_dual_track` 使用 params 中的路径

将 `core.py` L202-L205 改为从 `params` 读取路径：

```python
vocal_output = params.get("vocal_output_path", os.path.join(output_dir, f"{base_name}_vocal.wav"))
inst_output = params.get("accompaniment_output_path", os.path.join(output_dir, f"{base_name}_accompaniment.wav"))
```

这样：
- 如果 `params` 中有 `vocal_output_path`，使用它（与修复端点一致）
- 如果没有，fallback 到旧逻辑

### 步骤 2：返回值增加路径字段

在 `_repair_dual_track` 的返回值中增加：

```python
return {
    ...
    "vocal_output_path": vocal_output,
    "accompaniment_output_path": inst_output,
}
```

这样 `task_manager.py` L384-L392 能正确更新子任务的 `output_path`。

### 涉及文件

| 文件 | 修改 |
|------|------|
| `backend/services/repair/repair_v3_3/core.py` | `_repair_dual_track` 使用 params 路径 + 返回值增加路径字段 |

### 验证

1. 修复后：双轨修复完成 → 文件写入正确路径 → 渲染端点找到文件 → 渲染正常启动
2. 子任务的 `output_path` 正确设置 → 下载端点可用
3. TypeScript 编译零错误
4. `npm run build` 成功
5. `bash scripts/build_android_release.sh` 打包成功
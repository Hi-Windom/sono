# 修复四个 Bug 的实施计划

## 概述

修复用户报告的四个问题：
1. MP3 下载转换失败（`MPEGMode is not defined`）— 前端转码改后端
2. ComparePage 直接访问无更新记录（本质 bug）
3. 双轨修复缓存命中未生效
4. 移动端 v3.1a 缺少母带风格

---

## Bug 1: MP3 下载转换失败

### 当前状态
- 前端 `mp3EncoderWorker.ts` 使用 `lamejs` 在 Web Worker 中编码 MP3
- `lamejs` 在 Worker 上下文中引用了未定义的 `MPEGMode`，导致 `"MPEGMode is not defined"` 错误
- 同时，上传非 WAV 文件时前端 `decodeAudioData` 也可能失败（之前加过 try-catch 但仍有边缘情况）

### 修改方案
**删除前端 MP3 编码，统一由后端处理**

1. **删除文件：**
   - 删除 `/workspace/src/workers/mp3EncoderWorker.ts` — Worker 实现
   - 删除 `/workspace/src/utils/mp3Encoder.ts` — 前端工具函数

2. **修改 [DownloadModal.tsx](/workspace/src/components/DownloadModal.tsx)：**
   - 移除 `handleDownloadMp3` 函数中的前端编码逻辑
   - MP3 下载改为请求后端端点，下载已转码的 MP3 文件
   - 所有 MP3 按钮调用同一个后端下载端点（传 `format=mp3` 参数）

3. **新增后端端点 [backend/api/routes.py](/workspace/backend/api/routes.py)：**
   - 新增 `GET /api/v1/download-mp3/{task_id}` 端点
   - 从 `OUTPUT_DIR` 查找 `{task_id}_repaired.wav`
   - 使用 `pydub` 或 `subprocess` 调用 `ffmpeg` 将 WAV 转为 MP3 (128kbps)
   - 返回 MP3 文件流
   - 转换结果缓存到 `OUTPUT_DIR/{task_id}_repaired.mp3`，下次直接返回

4. **删除不再使用的依赖引用：**
   - 检查 `package.json` 中 `lamejs` 依赖，确认是否可以移除

### 验证
- 点击 MP3 下载按钮，后端返回正确的 MP3 文件
- 前端不再调用 `mp3EncoderWorker`

---

## Bug 2: ComparePage 直接访问无更新记录

### 当前状态
- ComparePage 通过 `/api/v1/cache/info` 获取任务列表
- 前端过滤 `tasks.filter(t => t.output_exists)`，只显示有输出文件的任务
- 用户直接访问时列表为空，但从修复页跳转（带 `taskId`）可以正常显示

### 根因分析
根因在 `/api/v1/cache/info` 端点：返回的任务列表中 `output_exists` 可能为 `false`，因为：
- 数据库中的 `output_path` 可能为相对路径或空值
- 输出文件可能被清理或路径不匹配

**更根本的问题**：ComparePage 应该显示所有已完成修复任务（无论输出文件是否仍存在），而不是只显示有输出文件的。用户需要看到"曾经修复过"的记录，即使文件已被清理。

### 修改方案

1. **修改 [ComparePage.tsx](/workspace/src/pages/ComparePage.tsx)：**
   - 不再过滤 `output_exists`，改为显示所有任务
   - 对于 `output_exists: false` 的任务，在 UI 上标记为"文件已过期"或"输出文件不可用"
   - 点击"文件已过期"的任务时提示用户重新修复

2. **确保 [backend/api/routes.py](/workspace/src/pages/ComparePage.tsx#L120-L133) 返回所有任务：**
   - 确认 `/cache/info` 端点返回的任务列表包含所有已创建的任务
   - `output_exists` 作为标记字段保留，前端据此判断是否可播放

### 验证
- 直接访问 ComparePage，能看到所有修复过的任务
- 有输出文件的任务可正常播放对比
- 无输出文件的任务显示"文件已过期"标记

---

## Bug 3: 双轨修复缓存命中未生效

### 当前状态
- 前端调用 `lookupDualRepairCache` 检查缓存
- 后端 `find_dual_repair_cache` 比较存储参数与输入参数
- 使用严格的 JSON 精确匹配（`stored_json == params_json`）

### 根因分析
`find_dual_repair_cache` 中的 `filter_keys` 只排除了少数已知字段，但存储的参数可能包含额外字段（如 `_issues`、`source_bit_depth` 等），导致 JSON 精确匹配失败。

### 修改方案
**扩大 filter_keys 覆盖范围，或改用模糊匹配**

**方案 A（推荐）— 扩大 filter_keys：**
修改 `/workspace/backend/database.py` 中 `find_dual_repair_cache` 的 `filter_keys`：
```python
filter_keys = {
    "vocal_file_hash", "accompaniment_file_hash",
    "vocal_task_id", "accompaniment_task_id",
    "vocal_filename", "accompaniment_filename",
    "processing_mode",
    "vocal_path", "accompaniment_path",
    "vocal_output_path", "accompaniment_output_path",
    "_issues", "source_bit_depth", "file_size",
    "original_filename", "original_path", "output_path",
    "status", "error", "progress", "step",
    "detection_result", "repair_result",
    "vocal_params", "accompaniment_params",
    "waveform_peaks",
}
```

同时只比较关键的修复参数子集，而不是所有参数：
```python
# 只比较影响修复结果的参数
REPAIR_PARAM_KEYS = {
    "algorithm_version", "sample_rate", "bit_depth",
    "vocal_declip", "vocal_depop", "vocal_formant_repair",
    "vocal_de_ess", "vocal_breath_enhance", "vocal_ai_repair",
    "vocal_bass_enhance", "vocal_air_texture", "vocal_loudness",
    "inst_declip", "inst_depop", "inst_noise_reduction",
    "inst_dynamic", "inst_spatial", "inst_warmth",
    "inst_timbre_protect", "inst_stereo_enhance", "inst_loudness",
    "vocal_ratio", "accompaniment_ratio",
    "mastering_style", "processing_mode",
}
stored_subset = {k: v for k, v in filtered_stored.items() if k in REPAIR_PARAM_KEYS}
input_subset = {k: v for k, v in params.items() if k in REPAIR_PARAM_KEYS}
if stored_subset == input_subset:
    # 缓存命中
```

### 验证
- 双轨修复完成后，再次用相同参数修复，应该命中缓存
- 修改非关键参数（如界面显示相关）不应影响缓存匹配
- 后端日志应输出 `[cache-lookup-dual] MATCH` 确认命中

---

## Bug 4: 移动端 v3.1a 缺少母带风格

### 当前状态
- `ALGORITHM_VERSIONS` 中 v3.1a 的 `default_params` 包含 `"mastering_style": "none"`
- 移动端使用默认参数，因此没有母带处理

### 修改方案
**修改 [backend/services/audio_repair.py](/workspace/backend/services/audio_repair.py)：**
- 将 v3.1a `default_params` 中的 `"mastering_style"` 从 `"none"` 改为 `"standard"`
- 保留各模式（智能双轨、纯净人声等）的独立 mastering_style 配置不变

### 验证
- 移动端 v3.1a 修复后，音频应经过 standard 母带处理
- 各模式（智能双轨/纯净人声等）的独立配置不受影响
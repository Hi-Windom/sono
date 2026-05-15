# 修复计划：v3.x闷声 + 自动下载缓存bug

## 问题1：v3.x 音质闷声

### 根因

v3.x 的 `_hf_protect` 函数是**致命的低通滤波器**，直接切除了所有高频：

| 版本 | `_hf_protect` 截止频率 | 效果 |
|------|----------------------|------|
| v3.0 | **3000Hz** | 3kHz以上全部消失 |
| v3.1 | **4000Hz** | 4kHz以上全部消失 |
| v3.0a | **4000Hz** | 4kHz以上全部消失 |
| v3.1a | **4000Hz** | 4kHz以上全部消失 |
| v2.4a | **无此函数** | 完整保留0-24kHz |

加上 `_spectral_hf_gate`（5kHz以上激进门控，strength=5.0）和母带低通（8-12kHz），高频被从多个层面反复削减。

**这些低截止频率是之前为了测试数据好看乱改的**，需要在测试中添加注释说明。

### 修复方案

1. **移除所有 `_hf_protect` 和 `_spectral_hf_gate` 调用**（4个 v3.x 版本）
2. **移除母带函数中的低通滤波**（`_mastering_standard_lite`、`_mastering_powerful_lite`、`_mastering_warm_lite`）
3. **在测试文件中添加注释**，说明 `_hf_protect` 的截止频率不应低于奈奎斯特频率的80%，避免重蹈覆辙

---

## 问题2：自动下载缓存bug

### 根因

切换算法版本后，`renderDownloadUrl` 没有被清除，导致下载弹窗中的下载按钮仍然指向旧版本的文件。

**具体场景**：
1. 用户用 v3.1a 修复 → `renderDownloadUrl = /api/v1/download-file/task_v31a_rendered_v3p1a_48000_24.wav`
2. 用户切换到 v2.4a → `algorithmVersion` state 更新为 "v2.4a"
3. 但 `renderDownloadUrl` 仍然是 v3.1a 的 URL
4. 下载弹窗中的下载按钮指向 v3.1a 的文件

**交付规格区域的"秒下"按钮是正确的**——因为 `AIRepairPanel` 中的渲染缓存查询用的是当前 `taskId` 和 `algorithmVersion` state，能正确匹配到当前版本的缓存。`onInstantDownload` 用 `cacheEntry.filename` 构建新的下载 URL。

### 修复方案

在 `applyAlgorithmVersion` 中清除 `renderDownloadUrl`，确保切换算法版本后不会下载旧版本的文件。

同时修复 `renderAndDownload` 中 `algorithmVersionRef` 的时序问题：将 `algorithmVersion` 作为参数传入，而非从 ref 读取。

---

## 实施步骤

### Step 1: v3.1a — 移除高频切除 + 修复母带低通

文件：`backend/services/repair/repair_v3_1a/core.py`

- `_repair_single_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect` 调用
- `process_vocal_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect` 调用
- 双轨模式混音后：移除 `_spectral_hf_gate` 和 `_hf_protect` 调用
- `_mastering_standard_lite()`：移除 `butter(2, 12000/nyq, btype='low')` 低通
- `_mastering_powerful_lite()`：移除 `butter(2, 14000/nyq, btype='low')` 低通
- `_mastering_warm_lite()`：移除 `butter(2, 8000/nyq, btype='low')` 低通

### Step 2: v3.0a — 同样修复

文件：`backend/services/repair/repair_v3_0a/core.py`

同 Step 1 的改动。

### Step 3: v3.1 — 移除高频切除

文件：`backend/services/repair/repair_v3_1/core.py`

- `_repair_single_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect` 调用
- `process_vocal_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect` 调用
- `process_instrument_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect` 调用
- 双轨模式混音后：移除 `_spectral_hf_gate` 和 `_hf_protect` 调用

### Step 4: v3.0 — 移除高频切除

文件：`backend/services/repair/repair_v3_0/core.py`

同 Step 3 的改动。注意 v3.0 的 `_hf_protect` 截止频率是 3000Hz（更极端）。

### Step 5: 在测试文件中添加注释

文件：`backend/tests/test_repair_quality.py` 或 `backend/tests/test_dependencies.py`

在相关测试项添加注释：`_hf_protect` 的截止频率不应低于奈奎斯特频率的80%（如 48kHz 采样率下不低于 19200Hz），低截止频率会导致高频丢失使声音发闷。

### Step 6: 修复前端自动下载缓存bug

文件：`src/hooks/useAudioProcessor.ts`

1. `applyAlgorithmVersion` 中添加 `setRenderDownloadUrl(null)` 清除旧下载URL
2. `renderAndDownload` 增加 `overrideAlgoVersion?: string` 参数，内部使用 `overrideAlgoVersion || algorithmVersionRef.current`
3. 所有调用点传入当前 `algorithmVersion` state 值

### Step 7: 运行测试 + 打包

- `pytest backend/tests/test_repair_quality.py -v`
- `pytest backend/tests/test_dependencies.py -v`
- `bash scripts/build_android_release.sh`

---

## 修改文件清单

| 文件 | 改动 |
|------|------|
| `backend/services/repair/repair_v3_1a/core.py` | 移除高频切除调用 + 修复母带低通 |
| `backend/services/repair/repair_v3_0a/core.py` | 移除高频切除调用 + 修复母带低通 |
| `backend/services/repair/repair_v3_1/core.py` | 移除高频切除调用 |
| `backend/services/repair/repair_v3_0/core.py` | 移除高频切除调用 |
| `backend/tests/test_repair_quality.py` | 添加 `_hf_protect` 截止频率注释 |
| `src/hooks/useAudioProcessor.ts` | 清除旧下载URL + 修复 algorithmVersionRef 时序 |

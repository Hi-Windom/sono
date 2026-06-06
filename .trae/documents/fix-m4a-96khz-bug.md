# Bug 修复：96kHz 渲染交付后下载 M4A/MP3 实际是 48kHz（更低采样率）

## 根因分析（从根源链路追踪）

### 完整链路梳理

1. **修复流程** — 后端 `/repair` 端点跑修复算法，输出 `{task_id}_repaired.wav`
   - 采样率 = 修复算法内部 working_sr（v2.x 默认 48000）
   - 用户选 96kHz 渲染时，**不会**影响 `_repaired.wav` 的采样率

2. **渲染流程** — 后端 `/render` 端点接收 `sample_rate=96000` 调用 `render_output()`
   - `render_output()` 在 `target_sr != sr` 时做 `resample_poly` 上采样到 96000
   - 写出文件命名为 `{task_id}_rendered_{algo}_{96000}_{24}.wav`（96kHz 真正落盘）

3. **前端 DownloadModal** — 用户在 96kHz 渲染缓存上点 "下载" 按钮
   - `onInstantDownload(cacheEntry)` 用 `cacheEntry.filename` 拼出 `/api/v1/download-file/{filename}` 96kHz WAV
   - 设置到 `renderDownloadUrl` 作为 WAV 下载 URL ✅ **这条链路是 96kHz**

4. **M4A/MP3 下载端点** — 前端只发 `/api/v1/download-m4a/{taskId}`，不传采样率
   - 后端 `download_m4a()` 第一行硬编码查找 `{task_id}_repaired.wav` ⚠️
   - **这个文件采样率是修复算法的 working_sr (48kHz)，不是渲染后的 96kHz！**
   - 即使用户刚刚做了 96kHz 渲染，M4A/MP3 端点根本不看 `_rendered_*.wav`，直接拿低采样率的 `_repaired.wav` 编码
   - 这就是用户看到的"96kHz 渲染了但 M4A 是 48kHz"的根本原因

### 根因一句话

**`/download-mp3/{task_id}` 和 `/download-m4a/{task_id}` 两个端点只看 `{task_id}_repaired.wav`（修复输出，48kHz），从不看渲染交付产物 `{task_id}_rendered_*.wav`（用户真正选定的 96kHz 规格）。** 而前端用 `taskId` 路径发起 M4A/MP3 下载时，丢失了"用户选的是哪个渲染规格"这个上下文。

### 同样的 bug 在哪

| 端点 | 现状 | 是否受影响 |
|------|------|------|
| `/download/{task_id}` | 读 `task.get("output_path")`（即 `_repaired.wav`） | ❌ 不会 96kHz |
| `/download-file/{filename}` | 读任意 WAV 文件 | ✅ 96kHz OK（前端走这条） |
| `/download-mp3/{task_id}` | 硬编码 `_repaired.wav` | ❌ **bug** |
| `/download-m4a/{task_id}` | 硬编码 `_repaired.wav` | ❌ **bug**（用户报的） |
| `/download-wav/{task_id}` | 不存在 | - |

## 修复方案

### 核心思路

把 M4A/MP3 下载从 "用 taskId 间接查" 改成 "用具体渲染文件名直接拿"——和 `/download-file/{filename}` 行为一致。前端按当前 `renderDownloadUrl` 中编码的 filename 传给后端，后端直接读这个 WAV 编码。

### 实现步骤

#### 1. 新增 `/download-m4a-file/{filename}` 和 `/download-mp3-file/{filename}` 端点

仿照现有 `/download-m4a/{task_id}` 实现，但接受 `filename` 参数：
- 直接从 `OUTPUT_DIR` 读指定的 `_rendered_*.wav`
- 编码到 `OUTPUT_DIR` 下的 `<filename>.m4a` / `<filename>.mp3`（独立缓存，不与 `_repaired.*` 冲突）
- 支持 Range 请求
- Content-Type 分别为 `audio/mp4` / `audio/mpeg`
- ffmpeg 不可用时 501

#### 2. 前端 DownloadModal 改造

- `handleDownloadM4a` / `handleDownloadMp3` 改为支持传 `filename` 而非 `taskId`
- 当用户在某个渲染缓存条目（96kHz 渲染产物）上点下载时，调新端点
- 当用户走"修复后直接下载"流程时，保留旧端点（`_repaired.wav`）
- 关键：保留所有 taskId 调用（兼容 dual track 等场景），新增 `filename` 调用路径

#### 3. 双轨模式（M4A/MP3 人声/伴奏）同样改造

双轨的人声/伴奏也是 96kHz 渲染产物。新端点要支持 `dualTrackUrls.vocal` 传过来的 96kHz 渲染文件名。

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/api/routes.py` | 修改 | 新增 `/download-m4a-file/{filename}` 和 `/download-mp3-file/{filename}` 端点 |
| `src/components/DownloadModal.tsx` | 修改 | `handleDownloadM4a` / `handleDownloadMp3` 接收文件名参数（同时保留 taskId 兼容路径） |

## 不需要变更的文件

- `m4a_encoder.py` / `mp3_encoder.py` — 编码器无需感知文件来源
- `render.py` — 渲染产物正常 96kHz 落盘
- `config.py` — 不变

## 验证步骤

1. **回归测试**：
   - 完成 96kHz 渲染 → 点 M4A → 后端用 96kHz 渲染 WAV 编码 → 解码新 M4A 验证 `sample_rate=96000`
   - 完成 96kHz 渲染 → 点 MP3 → 同样验证 96kHz
   - 不渲染、直接修复后点 MP3/M4A → 仍然能用（走 taskId 旧端点，48kHz）
2. **双轨测试**：人声/伴奏轨同样 96kHz
3. **错误处理**：ffmpeg 不可用时按钮降级；Range 请求正常
4. **缓存**：每个文件名独立缓存 `_rendered_xxx.m4a`，不污染 `_repaired.m4a`

## 风险点

- 前端 `handleDownloadMp3` 已有逻辑改起来要小心保持 taskId 路径（无渲染时仍可用）
- M4A/MP3 缓存文件从 `_repaired.{ext}` 改成 `<filename>.{ext}`，**老的 `_repaired.m4a` 文件变成孤儿**（建议保留向后兼容：找不到 filename 缓存时才 fallback 到 taskId 路径编码到 `_repaired.m4a`）

## 决策点（需要确认）

**方案 A（推荐）**：新增两个 file 参数端点，优先用 filename 路径，taskId 路径保留为 fallback。

**方案 B**：扩展现有 taskId 端点，让前端传 `?filename=xxx`，但这会污染 API 语义。

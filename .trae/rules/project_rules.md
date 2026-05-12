# Project Rules

## ⚠️ 强制性规则（每次操作前必须遵守）

1. **执行任何构建/部署/启动操作前，必须先读取本规则文件**
2. **项目已有专用脚本的，必须使用脚本，禁止手动拼凑步骤**
3. **"打包安卓" = `bash scripts/build_android_release.sh`，不是手动 npm build + cp**
4. **"重启dev" = 先停旧服务，再用 `bash scripts/start_dev.sh` 启动完整开发环境（前端+后端），不是只启动后端**
5. **遇到用户指令与已有脚本功能匹配时，直接调用脚本，不要自己拆解步骤**

## Build & Deploy Commands

### Android 打包（必须使用脚本，禁止手动执行步骤）
```bash
bash scripts/build_android_release.sh
```
此脚本自动完成：清理旧产物 → npm run build → 复制 dist 到 backend → 打包 release_android.tar.gz

**绝对禁止**手动执行 `npm run build` + `cp -r dist backend/` 来替代此脚本。

### Android 完整部署（Termux 端，含前端部署+后端重启）
```bash
bash scripts/build_android.sh
```
此脚本自动完成：清理旧产物 → npm run build → 部署前端到 backend/dist → 验证 → 重启后端

### 桌面开发环境（热重载，推荐开发时使用）
```bash
# 一键启动前后端（推荐）
bash scripts/start_dev.sh
# 访问地址: http://localhost:5173

# 或手动分别启动：
# 终端1：启动 Vite 前端开发服务器（热重载）
npm run dev
# 终端2：启动后端 API 服务（仅 API，不 serve 静态文件）
cd /workspace/backend && python main.py
```

**"重启dev"的正确流程**：
1. 停止旧服务：`pkill -f "python main.py"` + `pkill -f "vite"`
2. 启动新服务：`bash scripts/start_dev.sh`（同时启动前端和后端）
3. 或者用 `npm run dev:full`

**绝对禁止**只启动后端 `python main.py` 就当作"重启dev"。

### 桌面生产预览（使用打包后的 dist，非开发环境）
```bash
# 先构建前端，再启动后端（SERVE_STATIC=1 会 serve backend/dist）
npm run build
cp -r dist backend/dist
cd /workspace/backend && SERVE_STATIC=1 python main.py
# 访问地址: http://localhost:8000
```
**注意**：`SERVE_STATIC=1` 仅用于生产/打包验证，开发时请勿使用，应使用 `npm run dev` 获得热重载体验。

## Architecture

- Frontend: React + TypeScript + Vite → builds to `dist/`
- Backend: FastAPI (Python) in `backend/`
- Static serving: `backend/dist/` served by FastAPI when `SERVE_STATIC=1`
- Audio loading: miniaudio only (no librosa, no pydub)
- DSP functions: `backend/services/dsp_utils.py` (pure numpy+scipy, no librosa)
- Compatibility layer: `backend/services/librosa_compat.py` (re-exports dsp_utils)
- librosa is ONLY used in `backend/training/feature_extractor.py` (desktop-only training)

## Web Worker 策略

前端计算密集型任务**必须优先考虑使用 Web Worker**，避免阻塞主线程导致 UI 卡顿。

适合 Worker 的任务特征：
- 逐样本音频数据处理（解码、分析、编码）
- 大数组遍历/变换（>1M 次运算）
- 可脱离 DOM 独立完成的纯计算

不适合 Worker 的任务：
- 需要 DOM/Canvas API 的操作
- 已由 requestAnimationFrame 驱动的轻量渲染
- 异步 I/O 操作（fetch、IndexedDB）
- 计算量极低（<10ms）的任务

Worker 与缓存协同：
- 缓存命中时跳过 Worker 计算（避免不必要的通信开销）
- 缓存未命中时 Worker 异步计算，结果写回缓存
- Worker 结果不直接写缓存，由主线程负责缓存写入（Worker 无法访问 fetch/IndexedDB）

当前 Worker 使用：
- `src/workers/audioWorker.ts` — WAV PCM 解码 + 音频分析

## Memory Optimization (v2.2/v2.3/v2.3a)

Design target: **60min audio @ 4GB RAM** without quality reduction.

4-layer optimization:
1. **Corrected estimation** (`memory_guard.py`): Formula accounts for streaming STFT, algorithm-specific peak_temp, and float32 elem_size
2. **Float32 auto-conversion**: Audio >10min auto-converts to float32 (halves memory), converts back to float64 before WAV export
3. **Streaming spectral processing** (`dsp_utils.py::streaming_spectral_process`): Processes audio in 10s chunks with overlap-add, keeping STFT memory fixed at ~15MB regardless of audio length. Used by spectral_group_a/b, subband_processing, v2.3a denoise
4. **In-place operations**: All repair steps modify `y` directly instead of creating copies (peak memory 4x→1x for multiband compress)

Memory estimation is algorithm-version-aware:
- v2.2/v2.3: +50% peak_temp (full processing pipeline)
- v2.2a/v2.3a: +15% peak_temp (lightweight pipeline)
- v1.x: +30% peak_temp (moderate pipeline)

Result: 5min audio 3907MB→537MB, 60min audio ~3108MB (fits 4GB target)

## Directory Structure

```
scripts/     # 开发构建脚本（在开发机/CI 上运行）
  ├── build_android_release.sh   # PC端打包Android发布包
  └── build_android.sh           # Termux端完整构建部署

deploy/      # 运行时部署脚本（被打包进Android发布包，在用户设备上运行）
  ├── setup_android.sh           # Termux首次部署
  └── start_android.sh           # Termux启动服务
```

**关键区别**：
- `scripts/` = 开发者工具，不会进入 release_android.tar.gz
- `deploy/` = 用户脚本，会被 build_android_release.sh 复制到发布包中

## Key Files
- `backend/services/audio_loader.py` - audio loading (miniaudio only)
- `backend/services/dsp_utils.py` - all DSP functions (stft, istft, features)
- `backend/services/librosa_compat.py` - compatibility layer for dsp_utils
- `backend/main.py` - FastAPI entry point
- `backend/config.py` - configuration

## Git Commit
- git提交时禁止擅自丢弃未暂存的更改，必须得到用户二次确认
- Always commit with descriptive messages
- After code changes that affect Android, run `bash scripts/build_android_release.sh` to rebuild

## Testing
```bash
# 运行音频修复质量测试
cd /workspace && python -m pytest backend/tests/test_repair_quality.py -v
```

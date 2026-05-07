# Project Rules

## Build & Deploy Commands

### Android 打包（必须使用脚本，禁止手动执行步骤）
```bash
bash scripts/build_android_release.sh
```
此脚本自动完成：清理旧产物 → npm run build → 复制 dist 到 backend → 打包 release_android.tar.gz

### Android 完整部署（Termux 端，含前端部署+后端重启）
```bash
bash scripts/build_android.sh
```
此脚本自动完成：清理旧产物 → npm run build → 部署前端到 backend/dist → 验证 → 重启后端

### 桌面预览启动
```bash
cd /workspace/backend && SERVE_STATIC=1 python main.py
```
访问地址: http://localhost:8000

## Architecture

- Frontend: React + TypeScript + Vite → builds to `dist/`
- Backend: FastAPI (Python) in `backend/`
- Static serving: `backend/dist/` served by FastAPI when `SERVE_STATIC=1`
- Audio loading: miniaudio only (no librosa, no pydub)
- DSP functions: `backend/services/dsp_utils.py` (pure numpy+scipy, no librosa)
- Compatibility layer: `backend/services/librosa_compat.py` (re-exports dsp_utils)
- librosa is ONLY used in `backend/training/feature_extractor.py` (desktop-only training)

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

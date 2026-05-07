# Android (Termux) 部署指南

## 架构概述

Sono 在 Android 上通过 **Termux** 运行完整 Python 后端，前端通过浏览器访问 `http://localhost:8000`。

```
┌─────────────────────────────────────────┐
│  Android 手机                           │
│                                         │
│  ┌──────────┐    ┌───────────────────┐  │
│  │ 浏览器    │───▶│ Termux            │  │
│  │ localhost │    │ FastAPI + 前端静态 │  │
│  │  :8000   │◀───│ numpy/scipy       │  │
│  └──────────┘    │ miniaudio (MP3)   │  │
│                  └───────────────────┘  │
└─────────────────────────────────────────┘
```

## 快速部署

### 1. 下载 Release

从 [GitHub Releases](../../releases) 下载 `release_android.tar.gz`，传输到手机。

### 2. 一键部署

在 Termux 中执行：

```bash
tar -xzf release_android.tar.gz && cd sono-android && bash setup_android.sh
```

### 3. 日常启动

```bash
cd ~/sono-android && ./start_android.sh
```

浏览器访问 `http://localhost:8000`

## Termux 环境特殊处理

### C 扩展包安装策略

Termux 的 Python 平台标签是 `aarch64-linux-android`，PyPI 上没有预编译 wheel。直接 `pip install numpy` 会触发源码编译，而 Termux 的 Bionic libc 缺少 `spawn.h` 等头文件，导致编译失败（ninja → spawn.h 缺失 → numpy 编译失败）。

**解决方案：分层安装**

| 层级 | 包 | 安装方式 | 说明 |
|------|---|---------|------|
| 系统层 | numpy, scipy | `pkg install python-numpy python-scipy` | Termux 官方预编译 |
| 系统层 | ninja, cmake, clang | `pkg install ninja cmake clang` | C 扩展编译工具链 |
| 系统层 | rust | `pkg install rust` | Rust 扩展编译工具链（pydantic_core, miniaudio） |
| 构建层 | setuptools, setuptools_scm, scikit_build_core, maturin | `pip install` | 各类 C/Rust 扩展的构建后端 |
| 应用层 | fastapi, miniaudio 等 | `pip install --no-build-isolation` | 纯 Python 或可编译 C 扩展 |
| 应用层 | librosa | `pip install --no-deps --no-build-isolation` | 跳过 scikit-learn 依赖 |

### `--no-build-isolation` 的必要性

pip 默认为每个包创建隔离构建环境，在隔离环境中重新安装 build dependencies（包括 numpy → ninja → 编译失败）。`--no-build-isolation` 让 pip 直接使用系统已安装的 numpy/scipy/ninja，跳过重复编译。

前提条件：必须先通过 `pkg install` 安装好 numpy/scipy/ninja/rust，再通过 `pip install setuptools setuptools_scm scikit_build_core maturin` 安装构建后端。

### librosa 与 scikit-learn

librosa 将 scikit-learn 列为硬依赖，但 scikit-learn 在 Termux 上无法编译（构建后端 mesonpy 不可用）。我们的代码只使用 librosa 的核心功能（stft/istft/feature/effects），不依赖 scikit-learn。

解决：用 `pip install --no-deps librosa` 安装，手动安装其核心依赖（joblib/decorator/lazy_loader/msgpack/platformdirs/pooch），跳过 scikit-learn。

### MP3 解码：miniaudio

librosa 在 Termux 上无法解码 MP3 文件（soundfile 不支持 MP3 格式，audioread 找不到可用后端）。我们使用 **miniaudio** 作为 MP3 解码的 fallback：

- `miniaudio` 是 Python 绑定的 [miniaudio](https://github.com/mackron/miniaudio) C 库
- 支持 MP3、FLAC、WAV、Vorbis 等格式，无需 ffmpeg
- 比 ffmpeg 轻量得多，适合 Termux 环境
- 需要 Rust 编译器（`pkg install rust`）来构建 Python 绑定

音频加载流程：
1. 优先使用 `librosa.load()`（WAV/FLAC 等格式正常工作）
2. 如果 librosa 失败（MP3 文件在 Termux 上），自动 fallback 到 `miniaudio.read_file()`
3. 统一由 `backend/services/audio_loader.py` 的 `load_audio_with_fallback()` 处理

### noisereduce 不可用

noisereduce 依赖 scikit-learn，而 scikit-learn 在 Termux 上无法编译。代码中已有 try/except 回退机制，缺失时自动使用内置频谱门控降噪算法。

### 镜像源配置

国内网络环境下，需配置镜像源：

- **Termux 软件源**：清华镜像 `https://mirrors.tuna.tsinghua.edu.cn/termux`
- **Python 包源**：清华 PyPI `https://pypi.tuna.tsinghua.edu.cn/simple`

setup_android.sh 会自动配置，也可手动执行：

```bash
# Termux 镜像
sed -i 's@^\(deb.*stable main\)$@#\1\ndeb https://mirrors.tuna.tsinghua.edu.cn/termux/apt/termux-main stable main@' $PREFIX/etc/apt/sources.list
pkg update

# Python 镜像（pip 临时指定）
pip install -r requirements_android.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
```

## 修复算法版本

| 版本 | 移动端兼容 | 特点 |
|------|-----------|------|
| v1.0 | ✗ | 基础修复 |
| v1.1 | ✗ | 增强修复 |
| v1.2 | ✗ | 96kHz 全频带处理 |
| v2.0 | ✓ | 自适应采样率，频域合并优化 |
| v2.1 | ✓ | v2.0 基础上全面向量化优化，性能提升 10-100 倍 |

### v2.1 相比 v2.0 的升级

| 模块 | v2.0 | v2.1 |
|------|------|------|
| 清晰度 | 单频段高通滤波 | 三频段增强 (2-4k, 4-8k, 8-12k) |
| 峰值限制 | Python 逐样本循环 | lfilter 向量化包络检测 |
| 多段压缩 | Python 逐样本循环 | lfilter 向量化包络检测 |
| 瞬态修复 | Python 逐样本循环 | lfilter 向量化包络 + 向量化淡入淡出 |
| 去爆音 | Python 逐样本循环 | 向量化淡入淡出掩码 |
| 空间感 | 低频居中保护 | 低频居中 + 高频空间增强 |
| 音频加载 | librosa.load | librosa + miniaudio fallback |

## 常见问题

### Q: `spawn.h` file not found

Termux 的 Bionic libc 不包含 `spawn.h`。这是 ninja 从源码编译时的典型错误。解决：`pkg install ninja` 使用预编译版本，并加 `--no-build-isolation` 避免重复编译。

### Q: `Cannot import 'scikit_build_core.build'`

soxr 使用 scikit_build_core 作为构建后端，`--no-build-isolation` 不会自动安装它。解决：先 `pip install setuptools setuptools_scm scikit_build_core`，再安装 soxr。

### Q: `Cannot import 'mesonpy'` 或 scikit-learn 编译失败

scikit-learn 使用 meson-python 作为构建后端，mesonpy 在 Termux 上不可用。librosa 依赖 scikit-learn，但我们的代码不需要 scikit-learn 功能。解决：`pip install --no-deps librosa` 跳过 scikit-learn 依赖。

### Q: `Cannot import 'maturin'` 或 pydantic_core 编译失败

pydantic_core 是 Rust 扩展，使用 maturin 作为构建后端。解决：`pkg install rust` 安装 Rust 编译器，`pip install maturin` 安装构建后端。编译 pydantic_core 在手机上可能需要 5-15 分钟。

### Q: MP3 文件解码失败 (NoBackendError)

librosa 在 Termux 上无法解码 MP3。确保 miniaudio 已安装：`pip install miniaudio`。如果编译失败，确认已安装 Rust：`pkg install rust && pip install maturin`。

### Q: `Unable to locate package soxr`

Termux 仓库没有 `soxr` 系统包。soxr Python 包需要从源码编译，前提是安装了 `libsndfile` 和编译工具链。

### Q: 镜像源 `from versions: none`

镜像同步延迟或 SSL 证书问题。setup_android.sh 会自动回退到官方 PyPI。也可手动安装 `ca-certificates`：`pkg install ca-certificates`。

### Q: 息屏后服务被杀

关闭 Termux 的电池优化：系统设置 → 应用 → Termux → 电池 → 不受限。

### Q: 桌面快捷启动

将 `start_android.sh` 复制到 `~/.shortcuts/` 目录，安装 Termux:Widget 插件，即可桌面一键启动。

## 与桌面端的差异

| 特性 | 桌面端 | Android (Termux) |
|------|--------|------------------|
| 包管理 | uv / pip + venv | pkg + pip（系统级） |
| numpy/scipy | pip 预编译 wheel | pkg 预编译 |
| scikit-learn | pip 安装 | 不可用，librosa 用 --no-deps 安装 |
| noisereduce | 可用 | 不可用，回退到内置算法 |
| MP3 解码 | librosa (soundfile/audioread) | miniaudio fallback |
| 前端访问 | 开发服务器 / 独立部署 | FastAPI 静态文件服务 (SERVE_STATIC=1) |
| 虚拟环境 | .venv | 不使用（Termux 单用户环境） |

## 文件说明

| 文件 | 用途 |
|------|------|
| `scripts/setup_android.sh` | Termux 一键部署脚本 |
| `scripts/start_android.sh` | Termux 启动脚本模板 |
| `scripts/build_android_release.sh` | PC 端打包脚本 |
| `backend/requirements_android.txt` | Android 专用 Python 依赖（排除 numpy/scipy/noisereduce） |
| `backend/services/audio_loader.py` | 统一音频加载器（librosa + miniaudio fallback） |

## 1. Product Overview

Sono 是一个 AI 音频检测与修复工具，帮助用户识别 AI 生成音频并进行音质修复。

- **核心功能**: AI 音频检测、音频修复、AB 对比、参数配置管理
- **目标用户**: 音乐制作人、内容创作者、音频工程师
- **部署方式**: 桌面端（Vite dev server + FastAPI）和 Android（Termux + FastAPI）

## 2. Core Features

### 2.1 AI 音频检测
- 独立检测页面（`/detect`），支持本地文件上传和服务端缓存音频
- A/B 对比分析：两个检测槽位，不同颜色标识（红/青）
- 检测时间记录，可追溯
- 支持多版本检测算法（v1.0/v1.1/v1.2）

### 2.2 音频修复
- 后端修复为主力（numpy+scipy 自研 DSP），无浏览器端修复
- 多版本算法支持（v1.0~v2.4a），轻量版（a-suffix）适配低内存环境
- 智能缓存：上传层按文件 hash 去重，修复结果按文件+算法+参数三重匹配
- 全栈任务取消机制
- WebSocket 实时进度推送

### 2.3 AB 对比
- 独立对比页面（`/compare`），播放服务器缓存的原始与修复后音频
- 实时切换对比，波形可视化

### 2.4 导出系统
- 采样率: 44.1kHz, 48kHz, 96kHz, 192kHz
- 位深: 16-bit, 24-bit, 32-bit float
- 格式: WAV
- 后端渲染管线：上采样（频谱超分+谐波增强）/ 下采样（低通+重采样）

### 2.5 参数配置管理
- 保存/加载/导入/导出修复参数预设
- 多预设快速切换

## 3. Page Structure

| Route | Page | Purpose |
|-------|------|---------|
| `/` | LandingPage | 功能概览、最近更新、统计信息 |
| `/repair` | RepairPage | 完整修复工作流 |
| `/home` | Home | 带播放器的修复界面 |
| `/detect` | DetectPage | 独立 AI 检测 |
| `/compare` | ComparePage | 服务端音频 AB 对比 |
| `/profile-manager` | ProfileManagerPage | 参数预设管理 |
| `/quality-tests` | QualityTestPage | 自动化质量测试 |
| `/cache-manager` | CacheManagerPage | 缓存管理 |
| `/training-upload` | TrainingUploadPage | 训练素材上传 |

## 4. Technical Architecture

- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS
- **Backend**: FastAPI (Python 3.10+) + SQLite + WebSocket
- **Audio Processing**: NumPy + SciPy (custom dsp_utils.py, no librosa in production)
- **Audio Loading**: miniaudio only
- **Memory Optimization**: Streaming spectral processing, 60min audio @ 4GB RAM
- **Type Checking**: pyright strict mode (backend core)

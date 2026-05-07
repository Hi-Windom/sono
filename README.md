# Sono

AI 音频检测与修复工具

## 功能

- **AI 检测**: 检测音频是否由 AI 生成，支持 v1.0/v1.1/v1.2 三版本算法
- **音频修复**: 修复 AI 音频的常见问题（毛刺、撕裂、数字伪影等），支持 v1.0/v1.1/v1.2/v2.0/v2.1 五版本算法
- **前后对比**: 直观对比修复前后的 AI 检测概率变化
- **浏览器处理**: 支持纯浏览器端处理，无需上传文件
- **后端处理**: 支持 Python 后端高性能处理
- **实时进度**: WebSocket 实时推送任务进度，自动降级到 HTTP 轮询
- **Android 支持**: 通过 Termux 在 Android 设备上运行完整后端

## 技术栈

- **前端**: React + TypeScript + Vite + Tailwind CSS
- **后端**: Python + FastAPI + SQLite + WebSocket
- **音频处理**: Web Audio API / NumPy + SciPy (librosa 已移除，使用自研 dsp_utils)
- **包管理**: uv（桌面端）/ pkg + pip（Android）

## 快速开始

### 前置要求

- Node.js >= 18
- Python >= 3.10
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip

### 安装 uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 安装前端依赖

```bash
npm install
```

### 启动开发服务器

```bash
npm run dev
```

### 启动后端服务（桌面端）

```bash
cd backend
uv venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
python main.py
```

后端启动后访问 http://localhost:8000，API 文档 http://localhost:8000/docs

### PM2 进程管理（可选）

如需使用 PM2 管理后端进程：

```bash
# 确保已安装 PM2
npm install -g pm2

# 启动后端（项目根目录）
pm2 start ecosystem.config.cjs

# 查看状态
pm2 status

# 重启
pm2 restart sono-backend

# 停止
pm2 stop sono-backend
```

> 注意：`ecosystem.config.cjs` 已从 .gitignore 中移除，请根据需要修改其配置。

### 构建生产版本

```bash
npm run build
```

## Android (Termux) 部署

详细指南请参阅 [docs/android.md](docs/android.md)。

### 快速部署

1. 从 [GitHub Releases](../../releases) 下载 `release_android.tar.gz`
2. 传输到手机，在 Termux 中执行：

```bash
tar -xzf release_android.tar.gz && cd sono-android && bash setup_android.sh
```

3. 之后每次启动：`cd sono-android && ./start_android.sh`
4. 手机浏览器访问 http://localhost:8000

### 本地打包

```bash
npm run build
bash scripts/build_android_release.sh
```

### 与桌面端的差异

| 特性 | 桌面端 | Android |
|------|--------|---------|
| 包管理 | uv + venv | pkg + pip（系统级） |
| numpy/scipy | pip 预编译 wheel | pkg 预编译 |
| noisereduce | 可用 | 不可用，回退内置频谱算法 |
| pedalboard | 可用 | 不可用，回退 scipy 滤波算法 |
| librosa | 可用(仅训练) | 不需要，已用自研 dsp_utils 替代 |
| 前端访问 | 开发服务器 | FastAPI 静态文件服务 |

## 使用说明

1. 上传音频文件（支持 WAV、MP3、FLAC 等格式）
2. 查看 AI 检测分析结果
3. 选择修复算法版本和修复模式
4. 应用修复并对比前后效果
5. 下载修复后的音频文件

## 版本说明

### AI 检测版本

- **v1.0**: 基础 AI 检测算法
- **v1.1**: 多维特征分析 + 混合创作判定
- **v1.2**: 增强版特征分析，更精准的 AI 检测

### 修复算法版本

- **v1.0**: 基础修复算法，稳定可靠
- **v1.1**: 多频段压缩、自适应降噪、响度归一化（pedalboard 可选，缺失时自动降级到 scipy）
- **v1.2**: 深度学习辅助修复、智能谐波增强、自适应响度优化
- **v2.0**: 移动端优化版，自适应采样率，频域合并优化
- **v2.1**: 移动端优化升级版，增强降噪和清晰度

## 项目结构

```
.
├── src/                    # 前端源代码
│   ├── components/         # React 组件
│   ├── hooks/             # 自定义 Hooks
│   ├── pages/             # 页面组件
│   ├── services/          # API 服务 + WebSocket
│   ├── utils/             # 工具函数
│   └── workers/           # Web Workers
├── backend/               # 后端源代码
│   ├── api/              # API 路由（含 WebSocket）
│   ├── services/         # 业务逻辑
│   │   ├── ws_manager.py # WebSocket 连接管理器
│   │   └── ...           # 音频处理服务
│   ├── training/         # 训练工具
│   ├── requirements.txt        # 桌面端依赖
│   └── requirements_android.txt # Android 依赖
├── scripts/              # 开发构建脚本
│   ├── build_android_release.sh  # PC端打包Android发布包
│   └── build_android.sh          # Termux端完整构建部署
├── deploy/               # 运行时部署脚本（打包进Android发布包）
│   ├── setup_android.sh  # Termux 一键部署
│   └── start_android.sh  # Termux 启动脚本
├── docs/                 # 文档
│   └── android.md        # Android 部署详细指南
├── public/               # 静态资源
└── dist/                 # 构建输出
```

## 许可证

MIT

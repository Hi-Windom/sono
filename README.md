# Sono

AI 音频检测与修复工具

## 功能

- **AI 检测**: 检测音频是否由 AI 生成，支持 v1.0/v1.1 双版本算法
- **音频修复**: 修复 AI 音频的常见问题（毛刺、撕裂、数字伪影等），支持 v1.0/v1.1 双版本算法
- **前后对比**: 直观对比修复前后的 AI 检测概率变化
- **浏览器处理**: 支持纯浏览器端处理，无需上传文件
- **后端处理**: 支持 Python 后端高性能处理

## 技术栈

- **前端**: React + TypeScript + Vite + Tailwind CSS
- **后端**: Python + FastAPI + SQLite
- **音频处理**: Web Audio API / Librosa + NumPy

## 快速开始

### 安装依赖

```bash
npm install
```

### 启动开发服务器

```bash
npm run dev
```

### 启动后端服务

```bash
cd backend
pip install -r requirements.txt
python main.py
```

### 构建生产版本

```bash
npm run build
```

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

### 修复算法版本

- **v1.0**: 基础修复算法，稳定可靠
- **v1.1**: 多频段压缩、自适应降噪、响度归一化

## 项目结构

```
.
├── src/                    # 前端源代码
│   ├── components/         # React 组件
│   ├── hooks/             # 自定义 Hooks
│   ├── pages/             # 页面组件
│   ├── services/          # API 服务
│   ├── utils/             # 工具函数
│   └── workers/           # Web Workers
├── backend/               # 后端源代码
│   ├── api/              # API 路由
│   ├── services/         # 业务逻辑
│   └── database.py       # 数据库操作
├── public/               # 静态资源
└── dist/                 # 构建输出
```

## 许可证

MIT

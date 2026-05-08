# 修复开发服务器启动问题

## 问题总结

多次出现无法正确启动 Vite 热重载前端 + Python 后端的问题，根本原因：

1. **缺少统一启动脚本** — 需要分别运行 `npm run dev` 和 `python main.py`，容易遗漏或顺序错误
2. **前端构建产物位置不一致** — `dist/` 在根目录，但后端静态服务从 `backend/dist/` 读取
3. **Vite 代理硬编码** — `vite.config.ts` 中后端地址写死 `localhost:8000`，无法适应不同环境
4. **Python 依赖缺失** — 新环境缺少 `uvicorn`、`fastapi` 等依赖，启动报错后才安装
5. **没有健康检查** — 启动后无法自动确认前后端是否正常工作

## 当前状态分析

### 前端 (Vite)
- **入口**: `/workspace/package.json` → `npm run dev` → Vite dev server
- **配置**: `/workspace/vite.config.ts`
  - 代理 `/api` 和 `/health` 到 `http://localhost:8000`
  - 端口默认 5173
- **构建产物**: `/workspace/dist/` (build 后)

### 后端 (FastAPI)
- **入口**: `/workspace/backend/main.py` → `python main.py`
- **配置**: `/workspace/backend/config.py`
  - HOST=0.0.0.0, PORT=8000
- **静态文件**: `SERVE_STATIC=1` 时从 `backend/dist/` 服务
- **依赖**: `requirements.txt` (缺少 `uvicorn`, `fastapi`)

### Android 打包脚本
- `/workspace/scripts/build_android_release.sh` — 构建前端 → 复制 dist → 打包
- 已正确处理 `dist` → `backend/dist` 的复制

## 改动方案

### 1. 新增统一开发启动脚本 `scripts/start_dev.sh`

**功能**: 一个命令同时启动前后端

```bash
scripts/start_dev.sh
```

**行为**:
1. 检查并安装前端依赖 (`npm install`)
2. 检查并安装后端 Python 依赖 (`pip install -r requirements.txt`)
3. 启动后端 (后台): `cd backend && python main.py`
4. 等待后端健康检查通过 (`curl http://localhost:8000/health`)
5. 启动前端 (前台): `npm run dev`
6. 捕获 Ctrl+C，优雅关闭后端进程

### 2. 新增后端依赖检查增强 `backend/check_deps.py`

**功能**: 在 `main.py` 之前运行，确保所有依赖已安装

**行为**:
- 检查 `requirements.txt` 中列出的所有包
- 缺失时自动安装
- 包含 `uvicorn`, `fastapi`, `python-multipart` 等关键依赖

### 3. 修改 `vite.config.ts` — 支持环境变量配置后端地址

**改动**:
- 读取 `.env` 或环境变量 `VITE_API_URL`
- 默认保持 `http://localhost:8000`
- 代理配置使用变量而非硬编码

### 4. 新增 `.env.example` 环境变量模板

```
# 后端地址
VITE_API_URL=http://localhost:8000

# 后端配置
HOST=0.0.0.0
PORT=8000
```

### 5. 修改 `backend/requirements.txt` — 补充缺失依赖

**补充**:
- `uvicorn>=0.30.0`
- `fastapi>=0.110.0`
- `python-multipart>=0.0.9`
- `python-jose>=3.3.0`

### 6. 修改 `package.json` — 添加开发启动命令

```json
{
  "scripts": {
    "dev": "vite",
    "dev:full": "bash scripts/start_dev.sh",
    "build": "tsc -b && vite build",
    ...
  }
}
```

## 文件改动清单

| 文件 | 操作 | 说明 |
|-----|------|------|
| `scripts/start_dev.sh` | 新建 | 统一开发启动脚本 |
| `backend/check_deps.py` | 新建 | 依赖检查增强 |
| `vite.config.ts` | 修改 | 支持环境变量配置代理 |
| `.env.example` | 新建 | 环境变量模板 |
| `backend/requirements.txt` | 修改 | 补充缺失依赖 |
| `package.json` | 修改 | 添加 dev:full 命令 |

## 验证步骤

1. 运行 `bash scripts/start_dev.sh`
2. 确认后端启动：访问 http://localhost:8000/health 返回 OK
3. 确认前端启动：访问 http://localhost:5173 正常显示页面
4. 确认 API 代理：前端页面能正常调用后端 API
5. 测试热重载：修改前端代码，页面自动刷新
6. 测试 Ctrl+C：优雅关闭前后端进程

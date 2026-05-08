import os
import time
import logging
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from api.routes import router
from config import MOBILE_MODE
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / 'server.log'

_BANNER = (
    "\n"
    "╔══════════════════════════════════════════════╗\n"
    "║   Next-Gen AI Audio Repair Server v2.0      ║\n"
    "║   http://0.0.0.0:8000                     ║\n"
    "║                                              ║\n"
    "║   API文档: http://0.0.0.0:8000/docs        ║\n"
    "╚══════════════════════════════════════════════╝\n\n"
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(str(LOG_FILE), mode='w'),
        logging.StreamHandler(),
    ]
)
with open(LOG_FILE, 'a', encoding='utf-8') as _f:
    _f.write(_BANNER)

logger = logging.getLogger(__name__)

class LogRequest(BaseModel):
    message: str
    level: str = "info"


def create_app() -> FastAPI:
    from database import init_db, init_training_db
    init_db()
    init_training_db()

    app = FastAPI(
        title="Next-Gen AI Audio Repair API",
        version="2.0.0",
        description="AI音频修复与检测后端服务",
    )

    # 添加 /api/log 路由（不带 v1 前缀）
    @app.post("/api/log")
    async def log_message(request: LogRequest):
        level = request.level.lower()
        if level == "error":
            logger.error(request.message)
        elif level == "warning":
            logger.warning(request.message)
        elif level == "debug":
            logger.debug(request.message)
        else:
            logger.info(request.message)
        return {"status": "ok"}

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.time()
        logger.info(f">>> {request.method} {request.url.path} query={dict(request.query_params)} client={request.client.host if request.client else 'unknown'}")
        try:
            response = await call_next(request)
            elapsed = time.time() - start
            logger.info(f"<<< {request.method} {request.url.path} status={response.status_code} time={elapsed:.3f}s")
            return response
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"!!! {request.method} {request.url.path} error={e} time={elapsed:.3f}s")
            raise

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.get("/health")
    async def health():
        logger.info("Health check OK")
        return {"status": "ok", "version": "2.0.0", "mobile": MOBILE_MODE}

    @app.get("/api/v1/logs")
    async def download_logs(lines: int = 2000):
        if not LOG_FILE.exists():
            raise HTTPException(status_code=404, detail="日志文件不存在")
        try:
            with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
                all_lines = f.readlines()
            total = len(all_lines)
            tail = all_lines[-lines:] if total > lines else all_lines
            content = ''.join(tail)
            return Response(
                content=content,
                media_type='text/plain; charset=utf-8',
                headers={
                    'Content-Disposition': f'inline; filename="server.log"',
                    'Cache-Control': 'no-cache, no-store',
                    'X-Log-Total-Lines': str(total),
                    'X-Log-Returned-Lines': str(len(tail)),
                },
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"读取日志失败: {e}")

    # 桌面开发预览/生产环境静态文件服务
    # 注意：此功能仅在 SERVE_STATIC=1 时启用，用于桌面端打包后的预览或生产部署
    # 开发环境（热重载）应使用 `npm run dev` 启动 Vite 开发服务器（端口 5173）
    # 后端仅提供 API 服务（端口 8000），前端通过代理访问 API
    # Android 打包时，dist 会被复制到 backend/dist，此时 SERVE_STATIC=1 提供完整服务
    dist_dir = BASE_DIR / "dist"
    serve_static = os.getenv("SERVE_STATIC", "").lower() in ("1", "true", "yes")
    if serve_static and dist_dir.is_dir():
        # --- 自定义静态文件服务（禁用缓存）---
        @app.get("/assets/{file_path:path}")
        async def serve_asset(file_path: str):
            full_path = dist_dir / "assets" / file_path
            if full_path.is_file():
                response = FileResponse(str(full_path))
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                return response
            raise HTTPException(status_code=404, detail="Asset not found")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = dist_dir / full_path
            if full_path and file_path.is_file():
                response = FileResponse(str(file_path))
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                return response
            response = FileResponse(str(dist_dir / "index.html"))
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        logger.info(f"Static file serving enabled: {dist_dir}")

    logger.info("App created, server starting...")
    return app

import os
import time
import asyncio
import logging
import uuid
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
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


def create_app() -> FastAPI:
    from database import init_db, init_training_db
    init_db()
    init_training_db()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from database import cleanup_stale_tasks
        stale_count = cleanup_stale_tasks()
        if stale_count > 0:
            logger.info(f"[startup] 已清理 {stale_count} 个停滞任务")
        from services.task_manager import set_event_loop
        loop = asyncio.get_running_loop()
        set_event_loop(loop)
        from services.message_bus import get_message_bus
        message_bus = get_message_bus()
        message_bus.set_loop(loop)
        message_bus.start()
        logger.info("[startup] MessageBus 已启动")
        yield
        message_bus.stop()
        logger.info("[shutdown] MessageBus 已停止")
        from services.task_manager import shutdown_executor
        shutdown_executor(wait=False, cancel_futures=True)
        logger.info("[shutdown] 线程池已关闭")

    app = FastAPI(
        title="Next-Gen AI Audio Repair API",
        version="2.0.0",
        description="AI音频修复与检测后端服务",
        lifespan=lifespan,
    )

    from api.routes.system import LogRequest, log_message as _v1_log_message

    @app.post("/api/log")
    async def log_message_compat(request: LogRequest):
        return await _v1_log_message(request)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = str(uuid.uuid4())[:12]
        request.state.request_id = request_id
        start = time.time()
        client_ip = request.client.host if request.client else 'unknown'
        logger.info(f"[{request_id}] >>> {request.method} {request.url.path} query={dict(request.query_params)} client={client_ip}")
        try:
            response = await call_next(request)
            elapsed = time.time() - start
            response.headers["X-Request-ID"] = request_id
            logger.info(f"[{request_id}] <<< {request.method} {request.url.path} status={response.status_code} time={elapsed:.3f}s")
            return response
        except Exception as e:
            elapsed = time.time() - start
            tb_str = traceback.format_exc()
            logger.error(f"[{request_id}] !!! {request.method} {request.url.path} error={type(e).__name__}: {e}\n{tb_str}")
            raise

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        request_id = getattr(request.state, "request_id", "unknown")
        error_detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        logger.error(f"[{request_id}] HTTP {exc.status_code}: {error_detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": f"http_{exc.status_code}",
                    "message": error_detail,
                    "detail": "",
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", "unknown")
        errors = []
        for err in exc.errors():
            loc = " -> ".join(str(x) for x in err.get("loc", []))
            msg = err.get("msg", "validation error")
            errors.append(f"{loc}: {msg}")
        error_msg = "; ".join(errors) if errors else "请求参数验证失败"
        logger.error(f"[{request_id}] Validation Error: {error_msg}")
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "请求参数验证失败",
                    "detail": error_msg,
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        tb_str = traceback.format_exc()
        logger.error(f"[{request_id}] Unhandled Exception: {type(exc).__name__}: {exc}\n{tb_str}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_server_error",
                    "message": "服务器内部错误",
                    "detail": f"{type(exc).__name__}: {str(exc)}",
                    "request_id": request_id,
                }
            },
        )

    @app.get("/health")
    async def health():
        from services.task_manager import get_active_task_count, can_accept_task
        from config import MAX_CONCURRENT_TASKS
        active = get_active_task_count()
        can_accept, _ = can_accept_task()
        return {
            "status": "ok" if can_accept else "busy",
            "version": "2.0.0",
            "mobile": MOBILE_MODE,
            "active_tasks": active,
            "max_concurrent_tasks": MAX_CONCURRENT_TASKS,
            "load_percent": round(active / MAX_CONCURRENT_TASKS * 100, 1) if MAX_CONCURRENT_TASKS > 0 else 0,
        }

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
            if full_path.startswith("api/") or full_path.startswith("health"):
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=404, content={"detail": "API endpoint not found"})
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

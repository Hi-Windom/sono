import os
import time
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.routes import router

BASE_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(str(BASE_DIR / 'server.log'), mode='w'),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    from database import init_db, init_training_db
    init_db()
    init_training_db()

    app = FastAPI(
        title="Next-Gen AI Audio Repair API",
        version="2.0.0",
        description="AI音频修复与检测后端服务",
    )

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
        return {"status": "ok", "version": "2.0.0"}

    dist_dir = BASE_DIR / "dist"
    serve_static = os.getenv("SERVE_STATIC", "").lower() in ("1", "true", "yes")
    if serve_static and dist_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(dist_dir / "assets")), name="static-assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = dist_dir / full_path
            if full_path and file_path.is_file():
                return FileResponse(str(file_path))
            return FileResponse(str(dist_dir / "index.html"))

        logger.info(f"Static file serving enabled: {dist_dir}")

    logger.info("App created, server starting...")
    return app

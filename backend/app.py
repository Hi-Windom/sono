import time
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/workspace/backend/server.log', mode='w'),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

def create_app() -> FastAPI:
    from database import init_db, init_training_db
    init_db()
    init_training_db()  # 初始化训练素材数据库

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

    logger.info("App created, server starting...")
    return app

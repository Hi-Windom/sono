import logging
from fastapi import APIRouter, Header, HTTPException

from services.perf_metrics import get_perf_collector
import config

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/perf/summary")
async def perf_summary():
    collector = get_perf_collector()
    return collector.get_summary()


@router.get("/perf/reset")
async def perf_reset(x_admin_token: str | None = Header(None)):
    admin_token = config.ADMIN_TOKEN
    if not admin_token:
        raise HTTPException(status_code=403, detail="性能统计重置接口未启用（未配置 ADMIN_TOKEN）")
    if x_admin_token != admin_token:
        raise HTTPException(status_code=401, detail="未授权的操作")
    collector = get_perf_collector()
    collector.repair_history.clear()
    collector.detect_history.clear()
    collector.upload_history.clear()
    collector.download_history.clear()
    collector.step_history.clear()
    return {"status": "ok", "message": "性能统计已重置"}

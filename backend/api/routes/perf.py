import logging
from fastapi import APIRouter

from services.perf_metrics import get_perf_collector

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/perf/summary")
async def perf_summary():
    collector = get_perf_collector()
    return collector.get_summary()


@router.get("/perf/reset")
async def perf_reset():
    collector = get_perf_collector()
    collector.repair_history.clear()
    collector.detect_history.clear()
    collector.upload_history.clear()
    collector.download_history.clear()
    collector.step_history.clear()
    return {"status": "ok", "message": "性能统计已重置"}

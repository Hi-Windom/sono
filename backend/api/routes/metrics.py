import logging
from fastapi import APIRouter, Query

from services.observability import get_task_tracer, get_system_metrics

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/metrics/summary")
async def metrics_summary():
    metrics = get_system_metrics()
    return metrics.get_summary()


@router.get("/metrics/tasks")
async def metrics_tasks(
    task_type: str = Query(None, description="按任务类型筛选"),
    limit: int = Query(100, ge=1, le=1000, description="返回历史记录数量"),
):
    metrics = get_system_metrics()
    tracer = get_task_tracer()

    task_stats = metrics.get_task_stats()

    history = tracer.get_task_history(task_type=task_type, limit=limit)
    history_list = [t.to_dict() for t in history]

    active_traces = tracer.get_active_traces()
    active_list = [t.to_dict() for t in active_traces]

    return {
        "stats": task_stats,
        "active": active_list,
        "history": history_list,
    }


@router.get("/metrics/cache")
async def metrics_cache():
    metrics = get_system_metrics()
    return metrics.get_cache_stats()


@router.get("/metrics/websocket")
async def metrics_websocket():
    metrics = get_system_metrics()
    return metrics.get_ws_stats()


@router.post("/metrics/reset")
async def metrics_reset():
    metrics = get_system_metrics()
    tracer = get_task_tracer()
    metrics.reset()
    tracer.clear_history()
    return {"status": "ok", "message": "指标统计已重置"}

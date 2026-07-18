from fastapi import APIRouter

from .system import router as system_router
from .upload import router as upload_router
from .detect import router as detect_router
from .repair import router as repair_router
from .render import router as render_router
from .download import router as download_router
from .cache import router as cache_router
from .perf import router as perf_router

from .download import _wav_to_mp3
from .cache import get_render_cache, lookup_repair_cache
from ._common import _get_audio_info

router = APIRouter(prefix="/api/v1")

router.include_router(cache_router)
router.include_router(system_router)
router.include_router(upload_router)
router.include_router(detect_router)
router.include_router(repair_router)
router.include_router(render_router)
router.include_router(download_router)
router.include_router(perf_router)

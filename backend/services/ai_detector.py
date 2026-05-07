from services.ai_detector_v1_0 import detect_ai_audio as detect_ai_audio_v1_0
from services.ai_detector_v1_1 import detect_ai_audio as detect_ai_audio_v1_1

DETECTOR_VERSIONS = {
    "v1.0": {
        "name": "v1.0",
        "label": "v1.0",
        "description": "基础AI检测算法",
        "detect_fn": detect_ai_audio_v1_0,
    },
    "v1.1": {
        "name": "v1.1",
        "label": "v1.1",
        "description": "多维特征分析+混合创作判定",
        "detect_fn": detect_ai_audio_v1_1,
    },
}

DEFAULT_VERSION = "v1.1"


def get_detector_versions() -> list[dict]:
    return [
        {"name": v["name"], "label": v["label"], "description": v["description"]}
        for v in DETECTOR_VERSIONS.values()
    ]


import logging

logger = logging.getLogger(__name__)


def detect_ai_audio(audio_path: str, progress_callback=None, version: str | None = None) -> dict:
    ver = version or DEFAULT_VERSION
    logger.info(f"[detect_ai_audio] 使用版本: {ver}, 请求版本: {version}")
    version_info = DETECTOR_VERSIONS.get(ver)
    if not version_info:
        logger.warning(f"[detect_ai_audio] 版本 {ver} 不存在，使用默认版本 {DEFAULT_VERSION}")
        version_info = DETECTOR_VERSIONS[DEFAULT_VERSION]
    return version_info["detect_fn"](audio_path, progress_callback)

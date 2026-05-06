from services.audio_repair_v10 import repair_audio as repair_audio_v10
from services.audio_repair_v11 import repair_audio as repair_audio_v11

PARAM_DEFINITIONS = {
    "de_clipping": {"key": "deClipping", "label": "去削波", "min": 0, "max": 1, "step": 0.01},
    "noise_reduction": {"key": "noiseReduction", "label": "降噪", "min": 0, "max": 1, "step": 0.01},
    "de_essing": {"key": "deEssing", "label": "去齿音", "min": 0, "max": 1, "step": 0.01},
    "de_crackle": {"key": "deCrackle", "label": "去毛刺", "min": 0, "max": 1, "step": 0.01},
    "de_pop": {"key": "dePop", "label": "去爆音", "min": 0, "max": 1, "step": 0.01},
    "harmonic_enhance": {"key": "harmonicEnhance", "label": "谐波增强", "min": 0, "max": 1, "step": 0.01},
    "dynamic_range": {"key": "dynamicRange", "label": "动态范围", "min": 0, "max": 1, "step": 0.01},
    "softness": {"key": "softness", "label": "柔和处理", "min": 0, "max": 1, "step": 0.01},
    "presence_boost": {"key": "presenceBoost", "label": "临场增强", "min": 0, "max": 1, "step": 0.01},
    "bass_enhance": {"key": "bassEnhance", "label": "低音增强", "min": 0, "max": 1, "step": 0.01},
    "spatial_enhance": {"key": "spatialEnhance", "label": "空间感", "min": 0, "max": 1, "step": 0.01},
    "transient_repair": {"key": "transientRepair", "label": "瞬态修复", "min": 0, "max": 1, "step": 0.01},
}

ALGORITHM_VERSIONS = {
    "v1.0": {
        "name": "v1.0",
        "label": "v1.0",
        "description": "基础修复算法，稳定可靠",
        "repair_fn": repair_audio_v10,
        "default_params": {
            "de_clipping": 0.25, "noise_reduction": 0.18, "de_essing": 0.22,
            "de_crackle": 0.2, "de_pop": 0.15, "harmonic_enhance": 0.12,
            "dynamic_range": 0.08, "softness": 0.06, "presence_boost": 0.05,
            "bass_enhance": 0.08, "spatial_enhance": 0.1, "transient_repair": 0.1,
        },
        "modes": [
            {
                "name": "AI人声修复",
                "description": "精准修复AI人声的毛刺、撕裂和数字伪影",
                "icon": "🎤",
                "params": {
                    "de_clipping": 0.2, "noise_reduction": 0.12, "de_essing": 0.18,
                    "de_crackle": 0.15, "de_pop": 0.12, "harmonic_enhance": 0.08,
                    "dynamic_range": 0.05, "softness": 0.05, "presence_boost": 0.08,
                    "bass_enhance": 0.05, "spatial_enhance": 0.08, "transient_repair": 0.1,
                },
            },
            {
                "name": "降噪修复",
                "description": "去除背景噪音和数字伪影",
                "icon": "🔇",
                "params": {
                    "de_clipping": 0.12, "noise_reduction": 0.25, "de_essing": 0.12,
                    "de_crackle": 0.12, "de_pop": 0.08, "harmonic_enhance": 0.03,
                    "dynamic_range": 0.03, "softness": 0.08, "presence_boost": 0.02,
                    "bass_enhance": 0.03, "spatial_enhance": 0.05, "transient_repair": 0.06,
                },
            },
            {
                "name": "温和修复",
                "description": "轻微处理，保留原始音质",
                "icon": "🌿",
                "params": {
                    "de_clipping": 0.08, "noise_reduction": 0.06, "de_essing": 0.08,
                    "de_crackle": 0.06, "de_pop": 0.04, "harmonic_enhance": 0.03,
                    "dynamic_range": 0.02, "softness": 0.02, "presence_boost": 0.01,
                    "bass_enhance": 0.02, "spatial_enhance": 0.02, "transient_repair": 0.03,
                },
            },
            {
                "name": "全面修复",
                "description": "综合修复所有常见问题",
                "icon": "🎵",
                "params": {
                    "de_clipping": 0.25, "noise_reduction": 0.18, "de_essing": 0.22,
                    "de_crackle": 0.18, "de_pop": 0.15, "harmonic_enhance": 0.1,
                    "dynamic_range": 0.06, "softness": 0.06, "presence_boost": 0.08,
                    "bass_enhance": 0.1, "spatial_enhance": 0.12, "transient_repair": 0.15,
                },
            },
        ],
    },
    "v1.1": {
        "name": "v1.1",
        "label": "v1.1",
        "description": "多频段压缩、自适应降噪、响度归一化",
        "repair_fn": repair_audio_v11,
        "default_params": {
            "de_clipping": 0.3, "noise_reduction": 0.22, "de_essing": 0.2,
            "de_crackle": 0.22, "de_pop": 0.18, "harmonic_enhance": 0.1,
            "dynamic_range": 0.12, "softness": 0.05, "presence_boost": 0.06,
            "bass_enhance": 0.1, "spatial_enhance": 0.12, "transient_repair": 0.12,
        },
        "modes": [
            {
                "name": "AI人声修复",
                "description": "多频段精准修复AI人声，自适应齿音抑制",
                "icon": "🎤",
                "params": {
                    "de_clipping": 0.25, "noise_reduction": 0.15, "de_essing": 0.2,
                    "de_crackle": 0.18, "de_pop": 0.15, "harmonic_enhance": 0.06,
                    "dynamic_range": 0.08, "softness": 0.03, "presence_boost": 0.1,
                    "bass_enhance": 0.06, "spatial_enhance": 0.1, "transient_repair": 0.12,
                },
            },
            {
                "name": "深度降噪",
                "description": "自适应频谱降噪+多频段动态优化",
                "icon": "🔇",
                "params": {
                    "de_clipping": 0.15, "noise_reduction": 0.35, "de_essing": 0.1,
                    "de_crackle": 0.15, "de_pop": 0.1, "harmonic_enhance": 0.02,
                    "dynamic_range": 0.1, "softness": 0.06, "presence_boost": 0.03,
                    "bass_enhance": 0.04, "spatial_enhance": 0.06, "transient_repair": 0.08,
                },
            },
            {
                "name": "温和修复",
                "description": "轻微处理，响度归一化保护音质",
                "icon": "🌿",
                "params": {
                    "de_clipping": 0.1, "noise_reduction": 0.08, "de_essing": 0.08,
                    "de_crackle": 0.08, "de_pop": 0.06, "harmonic_enhance": 0.02,
                    "dynamic_range": 0.04, "softness": 0.02, "presence_boost": 0.02,
                    "bass_enhance": 0.03, "spatial_enhance": 0.03, "transient_repair": 0.04,
                },
            },
            {
                "name": "全面修复",
                "description": "多频段压缩+响度归一化+峰值限制",
                "icon": "🎵",
                "params": {
                    "de_clipping": 0.3, "noise_reduction": 0.22, "de_essing": 0.2,
                    "de_crackle": 0.22, "de_pop": 0.18, "harmonic_enhance": 0.08,
                    "dynamic_range": 0.15, "softness": 0.05, "presence_boost": 0.08,
                    "bass_enhance": 0.12, "spatial_enhance": 0.15, "transient_repair": 0.15,
                },
            },
        ],
    },
}

DEFAULT_VERSION = "v1.1"


def get_available_versions() -> list[dict]:
    result = []
    for v in ALGORITHM_VERSIONS.values():
        version_data = {
            "name": v["name"],
            "label": v["label"],
            "description": v["description"],
            "defaultParams": {PARAM_DEFINITIONS[k]["key"]: val for k, val in v["default_params"].items()},
            "modes": [
                {
                    "name": m["name"],
                    "description": m["description"],
                    "icon": m["icon"],
                    "params": {PARAM_DEFINITIONS[k]["key"]: val for k, val in m["params"].items()},
                }
                for m in v["modes"]
            ],
        }
        result.append(version_data)
    return result


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    version = params.get("algorithm_version", DEFAULT_VERSION)
    version_info = ALGORITHM_VERSIONS.get(version)
    if not version_info:
        version_info = ALGORITHM_VERSIONS[DEFAULT_VERSION]

    return version_info["repair_fn"](input_path, output_path, params, progress_callback)

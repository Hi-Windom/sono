from services.audio_repair_v1_0 import repair_audio as repair_audio_v1_0
from services.audio_repair_v1_1 import repair_audio as repair_audio_v1_1
from services.audio_repair_v1_2 import repair_audio as repair_audio_v1_2
from services.repair_v2_0 import repair_audio as repair_audio_v2_0

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
    "loudness_optimize": {"key": "loudnessOptimize", "label": "响度优化", "min": 0, "max": 1, "step": 0.01},
    "stereo_width": {"key": "stereoWidth", "label": "立体声宽度", "min": 0, "max": 1, "step": 0.01},
    "harmonic_richness": {"key": "harmonicRichness", "label": "谐波丰富度", "min": 0, "max": 1, "step": 0.01},
    "warmth": {"key": "warmth", "label": "温暖度", "min": 0, "max": 1, "step": 0.01},
    "clarity": {"key": "clarity", "label": "清晰度", "min": 0, "max": 1, "step": 0.01},
}

ALGORITHM_VERSIONS = {
    "v1.0": {
        "name": "v1.0",
        "label": "v1.0",
        "description": "基础修复算法，稳定可靠",
        "mobile_compatible": False,
        "repair_fn": repair_audio_v1_0,
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
        "mobile_compatible": False,
        "repair_fn": repair_audio_v1_1,
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
    "v1.2": {
        "name": "v1.2",
        "label": "v1.2",
        "description": "深度学习辅助修复，智能谐波增强",
        "mobile_compatible": False,
        "repair_fn": repair_audio_v1_2,
        "default_params": {
            "de_clipping": 0.35, "noise_reduction": 0.25, "de_essing": 0.25,
            "de_crackle": 0.28, "de_pop": 0.2, "harmonic_enhance": 0.15,
            "dynamic_range": 0.15, "softness": 0.04, "presence_boost": 0.08,
            "bass_enhance": 0.12, "spatial_enhance": 0.15, "transient_repair": 0.15,
            "loudness_optimize": 0.6, "stereo_width": 0.4, "harmonic_richness": 0.5,
        },
        "modes": [
            {
                "name": "AI人声修复v3",
                "description": "深度学习辅助修复AI人声，智能齿音抑制+谐波增强",
                "icon": "🎤",
                "params": {
                    "de_clipping": 0.3, "noise_reduction": 0.18, "de_essing": 0.3,
                    "de_crackle": 0.25, "de_pop": 0.18, "harmonic_enhance": 0.2,
                    "dynamic_range": 0.1, "softness": 0.02, "presence_boost": 0.12,
                    "bass_enhance": 0.08, "spatial_enhance": 0.12, "transient_repair": 0.15,
                    "loudness_optimize": 0.5, "stereo_width": 0.3, "harmonic_richness": 0.6,
                },
            },
            {
                "name": "专业母带处理",
                "description": "模拟专业母带流程，响度优化+立体声增强+动态控制",
                "icon": "🎛️",
                "params": {
                    "de_clipping": 0.2, "noise_reduction": 0.12, "de_essing": 0.15,
                    "de_crackle": 0.15, "de_pop": 0.1, "harmonic_enhance": 0.12,
                    "dynamic_range": 0.25, "softness": 0.02, "presence_boost": 0.1,
                    "bass_enhance": 0.15, "spatial_enhance": 0.2, "transient_repair": 0.1,
                    "loudness_optimize": 0.9, "stereo_width": 0.6, "harmonic_richness": 0.4,
                },
            },
            {
                "name": "深度修复",
                "description": "最强修复力度，适合严重损坏的AI音频",
                "icon": "🔧",
                "params": {
                    "de_clipping": 0.45, "noise_reduction": 0.4, "de_essing": 0.35,
                    "de_crackle": 0.4, "de_pop": 0.3, "harmonic_enhance": 0.2,
                    "dynamic_range": 0.2, "softness": 0.06, "presence_boost": 0.1,
                    "bass_enhance": 0.15, "spatial_enhance": 0.18, "transient_repair": 0.25,
                    "loudness_optimize": 0.7, "stereo_width": 0.4, "harmonic_richness": 0.6,
                },
            },
            {
                "name": "温和优化",
                "description": "轻微处理，保留原始音质特征，适合质量较好的AI音频",
                "icon": "🌿",
                "params": {
                    "de_clipping": 0.12, "noise_reduction": 0.08, "de_essing": 0.1,
                    "de_crackle": 0.1, "de_pop": 0.06, "harmonic_enhance": 0.06,
                    "dynamic_range": 0.08, "softness": 0.02, "presence_boost": 0.04,
                    "bass_enhance": 0.05, "spatial_enhance": 0.06, "transient_repair": 0.06,
                    "loudness_optimize": 0.4, "stereo_width": 0.2, "harmonic_richness": 0.3,
                },
            },
        ],
    },
    "v2.0": {
        "name": "v2.0",
        "label": "v2.0",
        "description": "移动端友好，自适应采样率，频域合并优化",
        "mobile_compatible": True,
        "repair_fn": repair_audio_v2_0,
        "default_params": {
            "de_clipping": 0.4, "noise_reduction": 0.3, "de_essing": 0.3,
            "de_crackle": 0.3, "de_pop": 0.25, "harmonic_enhance": 0.18,
            "dynamic_range": 0.18, "softness": 0.04, "presence_boost": 0.1,
            "bass_enhance": 0.15, "spatial_enhance": 0.18, "transient_repair": 0.18,
            "warmth": 0.3, "clarity": 0.3,
        },
        "modes": [
            {
                "name": "AI人声修复",
                "description": "针对AI人声优化，去齿音+去毛刺+清晰度增强",
                "icon": "🎤",
                "params": {
                    "de_clipping": 0.3, "noise_reduction": 0.2, "de_essing": 0.35,
                    "de_crackle": 0.3, "de_pop": 0.2, "harmonic_enhance": 0.15,
                    "dynamic_range": 0.1, "softness": 0.02, "presence_boost": 0.15,
                    "bass_enhance": 0.08, "spatial_enhance": 0.12, "transient_repair": 0.15,
                    "warmth": 0.2, "clarity": 0.4,
                },
            },
            {
                "name": "深度修复",
                "description": "最强修复力度，适合严重损坏的AI音频",
                "icon": "🔧",
                "params": {
                    "de_clipping": 0.55, "noise_reduction": 0.45, "de_essing": 0.4,
                    "de_crackle": 0.45, "de_pop": 0.35, "harmonic_enhance": 0.25,
                    "dynamic_range": 0.25, "softness": 0.06, "presence_boost": 0.12,
                    "bass_enhance": 0.18, "spatial_enhance": 0.2, "transient_repair": 0.28,
                    "warmth": 0.35, "clarity": 0.35,
                },
            },
            {
                "name": "温和优化",
                "description": "轻微处理，保留原始音质特征",
                "icon": "🌿",
                "params": {
                    "de_clipping": 0.15, "noise_reduction": 0.1, "de_essing": 0.12,
                    "de_crackle": 0.1, "de_pop": 0.08, "harmonic_enhance": 0.06,
                    "dynamic_range": 0.08, "softness": 0.02, "presence_boost": 0.04,
                    "bass_enhance": 0.05, "spatial_enhance": 0.06, "transient_repair": 0.06,
                    "warmth": 0.15, "clarity": 0.2,
                },
            },
            {
                "name": "专业母带",
                "description": "模拟专业母带处理，响度归一化+动态范围+空间感",
                "icon": "🎛️",
                "params": {
                    "de_clipping": 0.2, "noise_reduction": 0.15, "de_essing": 0.18,
                    "de_crackle": 0.15, "de_pop": 0.12, "harmonic_enhance": 0.15,
                    "dynamic_range": 0.3, "softness": 0.02, "presence_boost": 0.12,
                    "bass_enhance": 0.18, "spatial_enhance": 0.25, "transient_repair": 0.12,
                    "warmth": 0.4, "clarity": 0.3,
                },
            },
        ],
    },
}

DEFAULT_VERSION = "v2.0"


def get_available_versions(mobile_mode: bool = False) -> list[dict]:
    result = []
    for v in ALGORITHM_VERSIONS.values():
        if mobile_mode and not v.get("mobile_compatible", True):
            continue
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


def repair_audio(input_path: str, output_path: str, params: dict, progress_callback=None, mobile_mode: bool = False) -> dict:
    version = params.get("algorithm_version", DEFAULT_VERSION)
    version_info = ALGORITHM_VERSIONS.get(version)
    if not version_info:
        version_info = ALGORITHM_VERSIONS[DEFAULT_VERSION]
    
    if mobile_mode and not version_info.get("mobile_compatible", True):
        raise ValueError(f"算法版本 {version} 不支持移动端，请使用 v2.0")
    
    return version_info["repair_fn"](input_path, output_path, params, progress_callback)


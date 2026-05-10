from __future__ import annotations

from typing import Any

_REPAIR_MODULES = {
    "v1.0": "services.repair.audio_repair_v1_0",
    "v1.1": "services.repair.audio_repair_v1_1",
    "v1.2": "services.repair.audio_repair_v1_2",
    "v2.0": "services.repair.repair_v2_0",
    "v2.1": "services.repair.repair_v2_1",
    "v2.2": "services.repair.repair_v2_2",
    "v2.2a": "services.repair.repair_v2_2a",
    "v2.3": "services.repair.repair_v2_3",
    "v2.3a": "services.repair.repair_v2_3a",
}

_REPAIR_FN_CACHE: dict[str, Any] = {}


def _get_repair_fn(version: str):
    if version in _REPAIR_FN_CACHE:
        return _REPAIR_FN_CACHE[version]
    module_path = _REPAIR_MODULES.get(version)
    if not module_path:
        return None
    import importlib
    mod = importlib.import_module(module_path)
    fn = getattr(mod, "repair_audio", None)
    if fn:
        _REPAIR_FN_CACHE[version] = fn
    return fn

PARAM_DEFINITIONS = {
    "music_type": {"key": "musicType", "label": "音乐类型", "min": 0, "max": 5, "step": 1},
    "repair_mode": {"key": "repairMode", "label": "修复模式", "min": 0, "max": 5, "step": 1},
    "quality": {"key": "quality", "label": "处理质量", "min": 0, "max": 1, "step": 1},
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
        "repair_version": "v1.0",
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
        "repair_version": "v1.1",
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
        "repair_version": "v1.2",
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
        "repair_version": "v2.0",
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
    "v2.1": {
        "name": "v2.1",
        "label": "v2.1",
        "description": "移动端优化升级版，增强降噪和清晰度",
        "mobile_compatible": True,
        "repair_version": "v2.1",
        "default_params": {
            "de_clipping": 0.45, "noise_reduction": 0.35, "de_essing": 0.35,
            "de_crackle": 0.35, "de_pop": 0.28, "harmonic_enhance": 0.2,
            "dynamic_range": 0.2, "softness": 0.05, "presence_boost": 0.12,
            "bass_enhance": 0.18, "spatial_enhance": 0.2, "transient_repair": 0.2,
            "warmth": 0.35, "clarity": 0.35,
        },
        "modes": [
            {
                "name": "AI人声修复",
                "description": "针对AI人声优化，增强去齿音和清晰度",
                "icon": "🎤",
                "params": {
                    "de_clipping": 0.35, "noise_reduction": 0.25, "de_essing": 0.4,
                    "de_crackle": 0.35, "de_pop": 0.25, "harmonic_enhance": 0.18,
                    "dynamic_range": 0.12, "softness": 0.03, "presence_boost": 0.18,
                    "bass_enhance": 0.1, "spatial_enhance": 0.15, "transient_repair": 0.18,
                    "warmth": 0.25, "clarity": 0.45,
                },
            },
            {
                "name": "深度修复",
                "description": "最强修复力度，适合严重损坏的AI音频",
                "icon": "🔧",
                "params": {
                    "de_clipping": 0.6, "noise_reduction": 0.5, "de_essing": 0.45,
                    "de_crackle": 0.5, "de_pop": 0.4, "harmonic_enhance": 0.28,
                    "dynamic_range": 0.28, "softness": 0.08, "presence_boost": 0.15,
                    "bass_enhance": 0.2, "spatial_enhance": 0.22, "transient_repair": 0.3,
                    "warmth": 0.4, "clarity": 0.4,
                },
            },
            {
                "name": "温和优化",
                "description": "轻微处理，保留原始音质特征",
                "icon": "🌿",
                "params": {
                    "de_clipping": 0.18, "noise_reduction": 0.12, "de_essing": 0.15,
                    "de_crackle": 0.12, "de_pop": 0.1, "harmonic_enhance": 0.08,
                    "dynamic_range": 0.1, "softness": 0.03, "presence_boost": 0.05,
                    "bass_enhance": 0.06, "spatial_enhance": 0.08, "transient_repair": 0.08,
                    "warmth": 0.2, "clarity": 0.25,
                },
            },
            {
                "name": "专业母带",
                "description": "模拟专业母带处理，响度归一化+动态范围+空间感",
                "icon": "🎛️",
                "params": {
                    "de_clipping": 0.25, "noise_reduction": 0.18, "de_essing": 0.2,
                    "de_crackle": 0.18, "de_pop": 0.15, "harmonic_enhance": 0.18,
                    "dynamic_range": 0.35, "softness": 0.03, "presence_boost": 0.15,
                    "bass_enhance": 0.2, "spatial_enhance": 0.28, "transient_repair": 0.15,
                    "warmth": 0.45, "clarity": 0.35,
                },
            },
        ],
    },
    "v2.2": {
        "name": "v2.2",
        "label": "v2.2 桌面版",
        "description": "最佳音质，流式分块处理（仅桌面端）",
        "mobile_compatible": False,
        "repair_version": "v2.2",
        "default_params": {
            "de_clipping": 0.35, "noise_reduction": 0.25, "de_essing": 0.25,
            "de_crackle": 0.25, "de_pop": 0.2, "harmonic_enhance": 0.12,
            "dynamic_range": 0.12, "softness": 0.03, "presence_boost": 0.08,
            "bass_enhance": 0.12, "spatial_enhance": 0.12, "transient_repair": 0.12,
            "warmth": 0.25, "clarity": 0.25, "music_type": "auto", "repair_mode": "smart",
            "quality": "standard",
        },
        "modes": [
            {
                "name": "智能修复",
                "description": "自动检测音乐类型，应用类型优化的处理参数",
                "icon": "🧠",
                "params": {
                    "de_clipping": 0.35, "noise_reduction": 0.25, "de_essing": 0.25,
                    "de_crackle": 0.25, "de_pop": 0.2, "harmonic_enhance": 0.12,
                    "dynamic_range": 0.12, "softness": 0.03, "presence_boost": 0.08,
                    "bass_enhance": 0.12, "spatial_enhance": 0.12, "transient_repair": 0.12,
                    "warmth": 0.25, "clarity": 0.25, "music_type": "auto", "repair_mode": "smart",
                    "quality": "standard",
                },
            },
            {
                "name": "人声修复",
                "description": "针对人声优化，去齿音+气息自然度+清晰度",
                "icon": "🎤",
                "params": {
                    "de_clipping": 0.3, "noise_reduction": 0.18, "de_essing": 0.35,
                    "de_crackle": 0.28, "de_pop": 0.22, "harmonic_enhance": 0.15,
                    "dynamic_range": 0.08, "softness": 0.02, "presence_boost": 0.12,
                    "bass_enhance": 0.08, "spatial_enhance": 0.1, "transient_repair": 0.15,
                    "warmth": 0.3, "clarity": 0.32, "music_type": "vocal", "repair_mode": "vocal",
                    "quality": "standard",
                },
            },
            {
                "name": "器乐修复",
                "description": "针对器乐优化，谐波丰富度+空间感+细节保留",
                "icon": "🎻",
                "params": {
                    "de_clipping": 0.25, "noise_reduction": 0.2, "de_essing": 0.12,
                    "de_crackle": 0.2, "de_pop": 0.12, "harmonic_enhance": 0.2,
                    "dynamic_range": 0.1, "softness": 0.01, "presence_boost": 0.1,
                    "bass_enhance": 0.1, "spatial_enhance": 0.18, "transient_repair": 0.1,
                    "warmth": 0.22, "clarity": 0.22, "music_type": "instrumental", "repair_mode": "instrumental",
                    "quality": "standard",
                },
            },
            {
                "name": "深度修复",
                "description": "最强修复力度，适合严重损坏的AI音频",
                "icon": "🔧",
                "params": {
                    "de_clipping": 0.5, "noise_reduction": 0.4, "de_essing": 0.38,
                    "de_crackle": 0.4, "de_pop": 0.32, "harmonic_enhance": 0.2,
                    "dynamic_range": 0.22, "softness": 0.06, "presence_boost": 0.14,
                    "bass_enhance": 0.18, "spatial_enhance": 0.18, "transient_repair": 0.22,
                    "warmth": 0.35, "clarity": 0.35, "music_type": "auto", "repair_mode": "deep",
                    "quality": "standard",
                },
            },
            {
                "name": "温和优化",
                "description": "轻微处理，保留原始音质",
                "icon": "🌿",
                "params": {
                    "de_clipping": 0.15, "noise_reduction": 0.1, "de_essing": 0.12,
                    "de_crackle": 0.1, "de_pop": 0.08, "harmonic_enhance": 0.06,
                    "dynamic_range": 0.06, "softness": 0.015, "presence_boost": 0.04,
                    "bass_enhance": 0.06, "spatial_enhance": 0.06, "transient_repair": 0.06,
                    "warmth": 0.15, "clarity": 0.18, "music_type": "auto", "repair_mode": "gentle",
                    "quality": "standard",
                },
            },
            {
                "name": "HiFi 模式",
                "description": "最小处理，追求最高音质保真度",
                "icon": "✨",
                "params": {
                    "de_clipping": 0.12, "noise_reduction": 0.05, "de_essing": 0.08,
                    "de_crackle": 0.06, "de_pop": 0.05, "harmonic_enhance": 0.03,
                    "dynamic_range": 0.03, "softness": 0.01, "presence_boost": 0.03,
                    "bass_enhance": 0.04, "spatial_enhance": 0.04, "transient_repair": 0.04,
                    "warmth": 0.1, "clarity": 0.12, "music_type": "auto", "repair_mode": "smart",
                    "quality": "hifi",
                },
            },
        ],
    },
    "v2.2a": {
        "name": "v2.2a",
        "label": "v2.2a 移动版",
        "description": "速度优先，精简处理（移动端专用）",
        "mobile_compatible": True,
        "repair_version": "v2.2a",
        "default_params": {
            "de_clipping": 0.3, "noise_reduction": 0.2, "de_essing": 0.2,
            "de_pop": 0.15, "dynamic_range": 0.1,
            "music_type": "auto", "repair_mode": "smart",
        },
        "modes": [
            {
                "name": "智能修复",
                "description": "自动检测类型，快速处理",
                "icon": "🧠",
                "params": {
                    "de_clipping": 0.3, "noise_reduction": 0.2, "de_essing": 0.2,
                    "de_pop": 0.15, "dynamic_range": 0.1,
                    "music_type": "auto", "repair_mode": "smart",
                },
            },
            {
                "name": "快速修复",
                "description": "极速处理，适合大文件",
                "icon": "⚡",
                "params": {
                    "de_clipping": 0.2, "noise_reduction": 0.15, "de_essing": 0.15,
                    "de_pop": 0.1, "dynamic_range": 0.05,
                    "music_type": "auto", "repair_mode": "fast",
                },
            },
            {
                "name": "深度修复",
                "description": "较强修复力度",
                "icon": "🔧",
                "params": {
                    "de_clipping": 0.45, "noise_reduction": 0.35, "de_essing": 0.35,
                    "de_pop": 0.3, "dynamic_range": 0.2,
                    "music_type": "auto", "repair_mode": "deep",
                },
            },
            {
                "name": "温和优化",
                "description": "轻微处理，保留音质",
                "icon": "🌿",
                "params": {
                    "de_clipping": 0.1, "noise_reduction": 0.08, "de_essing": 0.08,
                    "de_pop": 0.05, "dynamic_range": 0.03,
                    "music_type": "auto", "repair_mode": "gentle",
                },
            },
        ],
    },
    "v2.3": {
        "name": "v2.3",
        "label": "v2.3 桌面版",
        "description": "零AM伪影，流式分块+低内存（仅桌面端）",
        "mobile_compatible": False,
        "repair_version": "v2.3",
        "default_params": {
            "de_clipping": 0.35, "noise_reduction": 0.25, "de_essing": 0.25,
            "de_crackle": 0.25, "de_pop": 0.2, "harmonic_enhance": 0.12,
            "dynamic_range": 0.12, "softness": 0.03, "presence_boost": 0.08,
            "bass_enhance": 0.12, "spatial_enhance": 0.12, "transient_repair": 0.12,
            "warmth": 0.25, "clarity": 0.25, "music_type": "auto", "repair_mode": "smart",
            "quality": "standard",
        },
        "modes": [
            {
                "name": "智能修复",
                "description": "零AM伪影，自动检测音乐类型",
                "icon": "🧠",
                "params": {
                    "de_clipping": 0.35, "noise_reduction": 0.25, "de_essing": 0.25,
                    "de_crackle": 0.25, "de_pop": 0.2, "harmonic_enhance": 0.12,
                    "dynamic_range": 0.12, "softness": 0.03, "presence_boost": 0.08,
                    "bass_enhance": 0.12, "spatial_enhance": 0.12, "transient_repair": 0.12,
                    "warmth": 0.25, "clarity": 0.25, "music_type": "auto", "repair_mode": "smart",
                    "quality": "standard",
                },
            },
            {
                "name": "人声修复",
                "description": "零AM伪影，针对人声优化",
                "icon": "🎤",
                "params": {
                    "de_clipping": 0.3, "noise_reduction": 0.18, "de_essing": 0.35,
                    "de_crackle": 0.28, "de_pop": 0.22, "harmonic_enhance": 0.15,
                    "dynamic_range": 0.08, "softness": 0.02, "presence_boost": 0.12,
                    "bass_enhance": 0.08, "spatial_enhance": 0.1, "transient_repair": 0.15,
                    "warmth": 0.3, "clarity": 0.32, "music_type": "vocal", "repair_mode": "vocal",
                    "quality": "standard",
                },
            },
            {
                "name": "器乐修复",
                "description": "零AM伪影，针对器乐优化",
                "icon": "🎻",
                "params": {
                    "de_clipping": 0.25, "noise_reduction": 0.2, "de_essing": 0.12,
                    "de_crackle": 0.2, "de_pop": 0.12, "harmonic_enhance": 0.2,
                    "dynamic_range": 0.1, "softness": 0.01, "presence_boost": 0.1,
                    "bass_enhance": 0.1, "spatial_enhance": 0.18, "transient_repair": 0.1,
                    "warmth": 0.22, "clarity": 0.22, "music_type": "instrumental", "repair_mode": "instrumental",
                    "quality": "standard",
                },
            },
            {
                "name": "深度修复",
                "description": "零AM伪影，最强修复力度",
                "icon": "🔧",
                "params": {
                    "de_clipping": 0.5, "noise_reduction": 0.4, "de_essing": 0.38,
                    "de_crackle": 0.4, "de_pop": 0.32, "harmonic_enhance": 0.2,
                    "dynamic_range": 0.22, "softness": 0.06, "presence_boost": 0.14,
                    "bass_enhance": 0.18, "spatial_enhance": 0.18, "transient_repair": 0.22,
                    "warmth": 0.35, "clarity": 0.35, "music_type": "auto", "repair_mode": "deep",
                    "quality": "standard",
                },
            },
            {
                "name": "温和优化",
                "description": "零AM伪影，轻微处理保留音质",
                "icon": "🌿",
                "params": {
                    "de_clipping": 0.15, "noise_reduction": 0.1, "de_essing": 0.12,
                    "de_crackle": 0.1, "de_pop": 0.08, "harmonic_enhance": 0.06,
                    "dynamic_range": 0.06, "softness": 0.015, "presence_boost": 0.04,
                    "bass_enhance": 0.06, "spatial_enhance": 0.06, "transient_repair": 0.06,
                    "warmth": 0.15, "clarity": 0.18, "music_type": "auto", "repair_mode": "gentle",
                    "quality": "standard",
                },
            },
            {
                "name": "HiFi 模式",
                "description": "零AM伪影，最高音质保真度",
                "icon": "✨",
                "params": {
                    "de_clipping": 0.12, "noise_reduction": 0.05, "de_essing": 0.08,
                    "de_crackle": 0.06, "de_pop": 0.05, "harmonic_enhance": 0.03,
                    "dynamic_range": 0.03, "softness": 0.01, "presence_boost": 0.03,
                    "bass_enhance": 0.04, "spatial_enhance": 0.04, "transient_repair": 0.04,
                    "warmth": 0.1, "clarity": 0.12, "music_type": "auto", "repair_mode": "smart",
                    "quality": "hifi",
                },
            },
        ],
    },
    "v2.3a": {
        "name": "v2.3a",
        "label": "v2.3a 移动版",
        "description": "零AM伪影，流式降噪+低内存（移动端）",
        "mobile_compatible": True,
        "repair_version": "v2.3a",
        "default_params": {
            "de_clipping": 0.3, "noise_reduction": 0.15, "de_essing": 0.15,
            "de_pop": 0.15, "dynamic_range": 0.1,
            "music_type": "auto", "repair_mode": "smart",
        },
        "modes": [
            {
                "name": "智能修复",
                "description": "零AM伪影，自动检测+频谱降噪",
                "icon": "🧠",
                "params": {
                    "de_clipping": 0.3, "noise_reduction": 0.15, "de_essing": 0.15,
                    "de_pop": 0.15, "dynamic_range": 0.1,
                    "music_type": "auto", "repair_mode": "smart",
                },
            },
            {
                "name": "快速修复",
                "description": "零AM伪影，极速处理",
                "icon": "⚡",
                "params": {
                    "de_clipping": 0.2, "noise_reduction": 0.1, "de_essing": 0.1,
                    "de_pop": 0.1, "dynamic_range": 0.05,
                    "music_type": "auto", "repair_mode": "fast",
                },
            },
            {
                "name": "深度修复",
                "description": "零AM伪影，较强修复力度",
                "icon": "🔧",
                "params": {
                    "de_clipping": 0.45, "noise_reduction": 0.3, "de_essing": 0.3,
                    "de_pop": 0.3, "dynamic_range": 0.2,
                    "music_type": "auto", "repair_mode": "deep",
                },
            },
            {
                "name": "温和优化",
                "description": "零AM伪影，轻微处理保留音质",
                "icon": "🌿",
                "params": {
                    "de_clipping": 0.1, "noise_reduction": 0.08, "de_essing": 0.08,
                    "de_pop": 0.05, "dynamic_range": 0.03,
                    "music_type": "auto", "repair_mode": "gentle",
                },
            },
        ],
    },
}

DEFAULT_VERSION = "v2.1"


def get_available_versions(mobile_mode: bool = False) -> list[dict[str, Any]]:
    result = []
    for v in ALGORITHM_VERSIONS.values():
        if mobile_mode and not v.get("mobile_compatible", True):
            continue
        # 构建参数范围信息
        param_ranges = {}
        for internal_key, pdef in PARAM_DEFINITIONS.items():
            param_ranges[pdef["key"]] = {
                "min": pdef["min"],
                "max": pdef["max"],
                "step": pdef["step"],
                "label": pdef["label"],
            }
        version_data = {
            "name": v["name"],
            "label": v["label"],
            "description": v["description"],
            "defaultParams": {PARAM_DEFINITIONS[k]["key"]: val for k, val in v["default_params"].items()},
            "paramRanges": param_ranges,
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


def repair_audio(input_path: str, output_path: str, params: dict[str, Any], progress_callback: Any = None, mobile_mode: bool = False) -> dict[str, Any]:
    version = params.get("algorithm_version", DEFAULT_VERSION)
    version_info = ALGORITHM_VERSIONS.get(version)
    if not version_info:
        version_info = ALGORITHM_VERSIONS[DEFAULT_VERSION]
    
    if mobile_mode and not version_info.get("mobile_compatible", True):
        raise ValueError(f"算法版本 {version} 不支持移动端，请使用 v2.0")
    
    repair_fn = _get_repair_fn(version_info["repair_version"])
    if not repair_fn:
        raise ValueError(f"算法版本 {version} 加载失败")
    return repair_fn(input_path, output_path, params, progress_callback)


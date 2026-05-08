"""
音乐类型优化参数配置 v2 - 音质优化版本
针对不同音乐类型的处理参数优化 - 更温和、更自然
"""

from typing import Dict, Any


# 基础参数模板 - 桌面端：更强的处理力度，确保显著优于修复前
BASE_PARAMS = {
    "de_clipping": 0.45,
    "noise_reduction": 0.40,
    "de_essing": 0.35,
    "de_crackle": 0.35,
    "de_pop": 0.28,
    "harmonic_enhance": 0.22,
    "dynamic_range": 0.22,
    "softness": 0.05,
    "presence_boost": 0.15,
    "bass_enhance": 0.18,
    "spatial_enhance": 0.18,
    "transient_repair": 0.20,
    "warmth": 0.32,
    "clarity": 0.32,
}

# 人声主导音乐优化参数 - 桌面端：清晰自然的人声
VOCAL_PARAMS = {
    "de_clipping": 0.40,
    "noise_reduction": 0.32,
    "de_essing": 0.42,
    "de_crackle": 0.32,
    "de_pop": 0.28,
    "harmonic_enhance": 0.22,
    "dynamic_range": 0.15,
    "softness": 0.03,
    "presence_boost": 0.18,
    "bass_enhance": 0.12,
    "spatial_enhance": 0.14,
    "transient_repair": 0.22,
    "warmth": 0.35,
    "clarity": 0.38,
}

# 纯器乐优化参数 - 桌面端：丰富谐波与空间感
INSTRUMENTAL_PARAMS = {
    "de_clipping": 0.35,
    "noise_reduction": 0.28,
    "de_essing": 0.15,
    "de_crackle": 0.28,
    "de_pop": 0.18,
    "harmonic_enhance": 0.28,
    "dynamic_range": 0.15,
    "softness": 0.02,
    "presence_boost": 0.14,
    "bass_enhance": 0.14,
    "spatial_enhance": 0.22,
    "transient_repair": 0.15,
    "warmth": 0.28,
    "clarity": 0.28,
}

# 电子音乐优化参数 - 桌面端：强劲低音与清晰高频
ELECTRONIC_PARAMS = {
    "de_clipping": 0.50,
    "noise_reduction": 0.38,
    "de_essing": 0.22,
    "de_crackle": 0.30,
    "de_pop": 0.25,
    "harmonic_enhance": 0.18,
    "dynamic_range": 0.28,
    "softness": 0.02,
    "presence_boost": 0.16,
    "bass_enhance": 0.25,
    "spatial_enhance": 0.18,
    "transient_repair": 0.25,
    "warmth": 0.22,
    "clarity": 0.35,
}

# 古典音乐优化参数 - 桌面端：保留动态的同时提升细节
CLASSICAL_PARAMS = {
    "de_clipping": 0.28,
    "noise_reduction": 0.15,
    "de_essing": 0.12,
    "de_crackle": 0.18,
    "de_pop": 0.12,
    "harmonic_enhance": 0.12,
    "dynamic_range": 0.08,
    "softness": 0.01,
    "presence_boost": 0.08,
    "bass_enhance": 0.08,
    "spatial_enhance": 0.12,
    "transient_repair": 0.10,
    "warmth": 0.18,
    "clarity": 0.18,
}

# 流行音乐优化参数 - 桌面端：均衡全面的处理
POP_PARAMS = {
    "de_clipping": 0.42,
    "noise_reduction": 0.32,
    "de_essing": 0.32,
    "de_crackle": 0.30,
    "de_pop": 0.25,
    "harmonic_enhance": 0.22,
    "dynamic_range": 0.20,
    "softness": 0.04,
    "presence_boost": 0.14,
    "bass_enhance": 0.16,
    "spatial_enhance": 0.16,
    "transient_repair": 0.18,
    "warmth": 0.30,
    "clarity": 0.30,
}

# 通用参数（置信度低时使用）
GENERIC_PARAMS = BASE_PARAMS.copy()

# 类型参数映射
TYPE_PARAMS_MAP = {
    "vocal": VOCAL_PARAMS,
    "instrumental": INSTRUMENTAL_PARAMS,
    "electronic": ELECTRONIC_PARAMS,
    "classical": CLASSICAL_PARAMS,
    "pop": POP_PARAMS,
    "generic": GENERIC_PARAMS,
}


# 压缩参数配置 - 按音乐类型
COMPRESSION_CONFIGS = {
    "vocal": {
        "low": {"threshold": -18, "ratio": 2.0, "attack": 15, "release": 150},
        "mid": {"threshold": -16, "ratio": 1.8, "attack": 8, "release": 120},
        "high": {"threshold": -14, "ratio": 1.5, "attack": 5, "release": 100},
        "makeup_gain": 0.8,
    },
    "instrumental": {
        "low": {"threshold": -20, "ratio": 1.8, "attack": 12, "release": 180},
        "mid": {"threshold": -18, "ratio": 1.6, "attack": 6, "release": 150},
        "high": {"threshold": -16, "ratio": 1.4, "attack": 4, "release": 120},
        "makeup_gain": 0.6,
    },
    "electronic": {
        "low": {"threshold": -16, "ratio": 2.5, "attack": 10, "release": 120},
        "mid": {"threshold": -14, "ratio": 2.0, "attack": 5, "release": 100},
        "high": {"threshold": -12, "ratio": 1.6, "attack": 3, "release": 80},
        "makeup_gain": 1.2,
    },
    "classical": {
        "low": {"threshold": -26, "ratio": 1.3, "attack": 25, "release": 250},
        "mid": {"threshold": -24, "ratio": 1.2, "attack": 15, "release": 200},
        "high": {"threshold": -22, "ratio": 1.1, "attack": 10, "release": 180},
        "makeup_gain": 0.3,
    },
    "pop": {
        "low": {"threshold": -18, "ratio": 2.2, "attack": 12, "release": 140},
        "mid": {"threshold": -16, "ratio": 1.9, "attack": 6, "release": 110},
        "high": {"threshold": -14, "ratio": 1.6, "attack": 4, "release": 90},
        "makeup_gain": 1.0,
    },
    "generic": {
        "low": {"threshold": -19, "ratio": 2.0, "attack": 12, "release": 150},
        "mid": {"threshold": -17, "ratio": 1.8, "attack": 6, "release": 120},
        "high": {"threshold": -15, "ratio": 1.5, "attack": 4, "release": 100},
        "makeup_gain": 0.8,
    },
}


def get_params_for_music_type(music_type: str, base_params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    获取指定音乐类型的优化参数

    Args:
        music_type: 音乐类型字符串
        base_params: 基础参数（可选，用于覆盖默认值）

    Returns:
        优化后的参数字典
    """
    type_params = TYPE_PARAMS_MAP.get(music_type, GENERIC_PARAMS).copy()

    if base_params:
        # 如果提供了基础参数，使用类型参数作为权重调整
        result = base_params.copy()
        for key in type_params:
            if key in result:
                # 混合基础参数和类型优化参数
                result[key] = (result[key] + type_params[key]) / 2
            else:
                result[key] = type_params[key]
        return result

    return type_params


def apply_music_type_params(params: Dict[str, Any], music_type: str, confidence: float) -> Dict[str, Any]:
    """
    根据音乐类型和置信度应用优化参数

    Args:
        params: 原始参数
        music_type: 检测到的音乐类型
        confidence: 检测置信度 0-1

    Returns:
        调整后的参数
    """
    if confidence < 0.5 or music_type == "generic":
        return params

    type_params = TYPE_PARAMS_MAP.get(music_type, GENERIC_PARAMS)

    result = params.copy()
    blend = min(confidence, 0.85)  # 桌面端：更高的类型参数混合比例，效果更明显

    for key in type_params:
        if key in result:
            # 线性插值混合参数
            result[key] = result[key] * (1 - blend) + type_params[key] * blend

    return result


def get_compression_config(music_type: str) -> Dict[str, Any]:
    """获取指定音乐类型的压缩配置"""
    return COMPRESSION_CONFIGS.get(music_type, COMPRESSION_CONFIGS["generic"]).copy()


# 修复模式参数配置
REPAIR_MODES = {
    "smart": {
        "name": "智能修复",
        "description": "自动检测音乐类型，应用类型优化的处理参数",
        "icon": "🧠",
        "params": BASE_PARAMS.copy(),
    },
    "vocal": {
        "name": "人声修复",
        "description": "针对人声优化，去齿音+气息自然度+清晰度",
        "icon": "🎤",
        "params": VOCAL_PARAMS.copy(),
    },
    "instrumental": {
        "name": "器乐修复",
        "description": "针对器乐优化，谐波丰富度+空间感+细节保留",
        "icon": "🎻",
        "params": INSTRUMENTAL_PARAMS.copy(),
    },
    "deep": {
        "name": "深度修复",
        "description": "最强修复力度，适合严重损坏的AI音频",
        "icon": "🔧",
        "params": {
            "de_clipping": 0.60,
            "noise_reduction": 0.55,
            "de_essing": 0.50,
            "de_crackle": 0.50,
            "de_pop": 0.42,
            "harmonic_enhance": 0.30,
            "dynamic_range": 0.32,
            "softness": 0.08,
            "presence_boost": 0.20,
            "bass_enhance": 0.25,
            "spatial_enhance": 0.22,
            "transient_repair": 0.30,
            "warmth": 0.42,
            "clarity": 0.45,
        },
    },
    "gentle": {
        "name": "温和优化",
        "description": "轻微处理，保留原始音质",
        "icon": "🌿",
        "params": {
            "de_clipping": 0.25,
            "noise_reduction": 0.18,
            "de_essing": 0.20,
            "de_crackle": 0.18,
            "de_pop": 0.15,
            "harmonic_enhance": 0.12,
            "dynamic_range": 0.12,
            "softness": 0.03,
            "presence_boost": 0.08,
            "bass_enhance": 0.10,
            "spatial_enhance": 0.10,
            "transient_repair": 0.10,
            "warmth": 0.20,
            "clarity": 0.22,
        },
    },
    "hifi": {
        "name": "HiFi 模式",
        "description": "最小处理，追求最高音质保真度",
        "icon": "✨",
        "params": {
            "de_clipping": 0.18,
            "noise_reduction": 0.10,
            "de_essing": 0.12,
            "de_crackle": 0.10,
            "de_pop": 0.08,
            "harmonic_enhance": 0.08,
            "dynamic_range": 0.06,
            "softness": 0.015,
            "presence_boost": 0.05,
            "bass_enhance": 0.06,
            "spatial_enhance": 0.06,
            "transient_repair": 0.06,
            "warmth": 0.12,
            "clarity": 0.15,
        },
    },
}


def get_repair_mode_params(mode_name: str) -> Dict[str, Any]:
    """获取指定修复模式的参数"""
    mode = REPAIR_MODES.get(mode_name, REPAIR_MODES["smart"])
    return mode["params"].copy()

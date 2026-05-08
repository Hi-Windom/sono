"""
音乐类型优化参数配置
针对不同音乐类型的处理参数优化
"""

from typing import Dict, Any


# 基础参数模板
BASE_PARAMS = {
    "de_clipping": 0.45,
    "noise_reduction": 0.35,
    "de_essing": 0.35,
    "de_crackle": 0.35,
    "de_pop": 0.28,
    "harmonic_enhance": 0.2,
    "dynamic_range": 0.2,
    "softness": 0.05,
    "presence_boost": 0.12,
    "bass_enhance": 0.18,
    "spatial_enhance": 0.2,
    "transient_repair": 0.2,
    "warmth": 0.35,
    "clarity": 0.35,
}

# 人声主导音乐优化参数
VOCAL_PARAMS = {
    "de_clipping": 0.4,
    "noise_reduction": 0.25,  # 轻度降噪，保护人声细节
    "de_essing": 0.5,  # 增强去齿音
    "de_crackle": 0.4,
    "de_pop": 0.3,
    "harmonic_enhance": 0.25,  # 适度谐波增强，温暖感
    "dynamic_range": 0.15,  # 轻度压缩，保护动态
    "softness": 0.03,  # 轻微柔化
    "presence_boost": 0.18,  # 增强临场感
    "bass_enhance": 0.12,  # 轻度低音增强
    "spatial_enhance": 0.15,  # 适度空间感
    "transient_repair": 0.22,
    "warmth": 0.4,  # 增强温暖度
    "clarity": 0.45,  # 增强清晰度
}

# 纯器乐优化参数
INSTRUMENTAL_PARAMS = {
    "de_clipping": 0.35,
    "noise_reduction": 0.3,
    "de_essing": 0.2,  # 轻度去齿音
    "de_crackle": 0.3,
    "de_pop": 0.2,
    "harmonic_enhance": 0.35,  # 增强谐波，丰富度
    "dynamic_range": 0.18,  # 中等压缩
    "softness": 0.02,
    "presence_boost": 0.15,
    "bass_enhance": 0.15,
    "spatial_enhance": 0.3,  # 增强空间感
    "transient_repair": 0.18,
    "warmth": 0.3,
    "clarity": 0.3,
}

# 电子音乐优化参数
ELECTRONIC_PARAMS = {
    "de_clipping": 0.5,
    "noise_reduction": 0.4,  # 较强降噪
    "de_essing": 0.25,
    "de_crackle": 0.3,
    "de_pop": 0.25,
    "harmonic_enhance": 0.15,  # 轻度谐波增强
    "dynamic_range": 0.35,  # 强力压缩，增强冲击力
    "softness": 0.02,
    "presence_boost": 0.2,
    "bass_enhance": 0.25,  # 增强低音
    "spatial_enhance": 0.25,
    "transient_repair": 0.25,
    "warmth": 0.25,
    "clarity": 0.4,
}

# 古典音乐优化参数
CLASSICAL_PARAMS = {
    "de_clipping": 0.25,
    "noise_reduction": 0.15,  # 最小降噪，保护细节
    "de_essing": 0.15,
    "de_crackle": 0.2,
    "de_pop": 0.15,
    "harmonic_enhance": 0.1,  # 最小谐波增强
    "dynamic_range": 0.08,  # 极轻度压缩，保护动态
    "softness": 0.01,  # 几乎不柔化
    "presence_boost": 0.08,
    "bass_enhance": 0.1,
    "spatial_enhance": 0.1,  # 最小空间处理
    "transient_repair": 0.1,
    "warmth": 0.2,
    "clarity": 0.2,
}

# 流行音乐优化参数
POP_PARAMS = {
    "de_clipping": 0.4,
    "noise_reduction": 0.3,
    "de_essing": 0.35,
    "de_crackle": 0.32,
    "de_pop": 0.25,
    "harmonic_enhance": 0.22,
    "dynamic_range": 0.22,
    "softness": 0.04,
    "presence_boost": 0.15,
    "bass_enhance": 0.18,
    "spatial_enhance": 0.2,
    "transient_repair": 0.2,
    "warmth": 0.35,
    "clarity": 0.35,
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
    blend = min(confidence, 0.8)  # 最大混合比例 0.8

    for key in type_params:
        if key in result:
            # 线性插值混合参数
            result[key] = result[key] * (1 - blend) + type_params[key] * blend

    return result


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
            "de_clipping": 0.65,
            "noise_reduction": 0.55,
            "de_essing": 0.5,
            "de_crackle": 0.55,
            "de_pop": 0.45,
            "harmonic_enhance": 0.3,
            "dynamic_range": 0.35,
            "softness": 0.1,
            "presence_boost": 0.2,
            "bass_enhance": 0.25,
            "spatial_enhance": 0.25,
            "transient_repair": 0.35,
            "warmth": 0.45,
            "clarity": 0.45,
        },
    },
    "gentle": {
        "name": "温和优化",
        "description": "轻微处理，保留原始音质",
        "icon": "🌿",
        "params": {
            "de_clipping": 0.2,
            "noise_reduction": 0.15,
            "de_essing": 0.18,
            "de_crackle": 0.15,
            "de_pop": 0.12,
            "harmonic_enhance": 0.1,
            "dynamic_range": 0.1,
            "softness": 0.02,
            "presence_boost": 0.06,
            "bass_enhance": 0.08,
            "spatial_enhance": 0.1,
            "transient_repair": 0.1,
            "warmth": 0.2,
            "clarity": 0.25,
        },
    },
}


def get_repair_mode_params(mode_name: str) -> Dict[str, Any]:
    """获取指定修复模式的参数"""
    mode = REPAIR_MODES.get(mode_name, REPAIR_MODES["smart"])
    return mode["params"].copy()

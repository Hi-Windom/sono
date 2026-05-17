"""
v3.2 参数验证器 - 确保所有传递的参数都被正确处理

当发现未定义的参数时，立即抛出明确的错误，而不是静默忽略。
这确保问题在构建时暴露，而不是运行时才被发现。
"""

# v3.2 单轨处理允许的参数列表
ALLOWED_SINGLE_PARAMS = {
    # 基础参数
    'declip', 'depop', 'de_ess', 'formant_repair', 'breath_enhance',
    'ai_repair', 'ai_repair_adaptive', 'bass_enhance', 'air_texture',

    # v3.2 新参数
    'de_esser_improved', 'exciter_improved', 'resonance_suppress',
    'transient_aware', 'smart_compressor', 'compressor',

    # 增强参数
    'dynamic', 'spatial', 'loudness', 'warmth', 'stereo_enhance',
    'noise_reduction',

    # 特殊参数
    'speed', 'mastering_style', 'bit_depth', '_issues'
}

# v3.2 人声处理允许的参数列表
ALLOWED_VOCAL_PARAMS = {
    'declip', 'depop', 'de_ess', 'formant_repair', 'breath_enhance',
    'ai_repair', 'ai_repair_adaptive', 'bass_enhance', 'air_texture',
    'de_esser_improved', 'exciter_improved', 'resonance_suppress',
    'transient_aware', 'smart_compressor', 'compressor',
    'dynamic', 'spatial', 'loudness', 'warmth', 'speed', '_issues'
}

# v3.2 器乐处理允许的参数列表
ALLOWED_INST_PARAMS = {
    'declip', 'depop', 'timbre_protect', 'dynamic', 'noise_reduction',
    'spatial', 'warmth', 'stereo_enhance', 'loudness',
    'speed', '_issues'
}


def validate_single_params(params: dict) -> None:
    """
    验证单轨处理参数
    如果发现未定义的参数，立即抛出明确的错误

    Raises:
        ValueError: 当发现未定义的参数时

    Example:
        >>> params = {'declip': 0.5, 'unknown_param': 0.3}
        >>> validate_single_params(params)
        ValueError: v3.2 单轨处理收到未定义的参数: unknown_param
    """
    unexpected_params = []

    for key in params.keys():
        if key.startswith('_'):  # 内部参数跳过（如 _issues）
            continue
        if key not in ALLOWED_SINGLE_PARAMS:
            unexpected_params.append(key)

    if unexpected_params:
        raise ValueError(
            f"v3.2 单轨处理收到未定义的参数: {', '.join(unexpected_params)}. "
            f"请检查参数映射或更新 ALLOWED_SINGLE_PARAMS. "
            f"可用参数: {', '.join(sorted(ALLOWED_SINGLE_PARAMS))}"
        )


def validate_vocal_params(params: dict) -> None:
    """
    验证人声处理参数
    如果发现未定义的参数，立即抛出明确的错误

    Raises:
        ValueError: 当发现未定义的参数时
    """
    unexpected_params = []

    for key in params.keys():
        if key.startswith('_'):
            continue
        if key not in ALLOWED_VOCAL_PARAMS:
            unexpected_params.append(key)

    if unexpected_params:
        raise ValueError(
            f"v3.2 人声处理收到未定义的参数: {', '.join(unexpected_params)}. "
            f"请检查 process_vocal_track 函数中的参数处理. "
            f"可用参数: {', '.join(sorted(ALLOWED_VOCAL_PARAMS))}"
        )


def validate_inst_params(params: dict) -> None:
    """
    验证器乐处理参数
    如果发现未定义的参数，立即抛出明确的错误

    Raises:
        ValueError: 当发现未定义的参数时
    """
    unexpected_params = []

    for key in params.keys():
        if key.startswith('_'):
            continue
        if key not in ALLOWED_INST_PARAMS:
            unexpected_params.append(key)

    if unexpected_params:
        raise ValueError(
            f"v3.2 器乐处理收到未定义的参数: {', '.join(unexpected_params)}. "
            f"请检查 process_instrument_track 函数中的参数处理. "
            f"可用参数: {', '.join(sorted(ALLOWED_INST_PARAMS))}"
        )


def get_missing_params(params: dict, allowed_params: set) -> list:
    """
    获取参数中缺失的处理逻辑

    Returns:
        list: 未处理的参数列表
    """
    missing = []
    for key in params.keys():
        if key.startswith('_'):
            continue
        if key not in allowed_params:
            missing.append(key)
    return missing

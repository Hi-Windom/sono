"""
v3.2 参数响应曲线模块
提供参数敏感度增强的响应曲线函数
"""

import numpy as np


def logarithmic_boost(amount, base=2.0, threshold=0.05):
    """
    对数增强函数 - 使小参数值也有显著效果

    曲线特性:
    - amount=0.1 → 输出 ~0.45-0.5
    - amount=0.2 → 输出 ~0.6-0.65
    - amount=0.5 → 输出 ~0.85-0.9
    - amount=1.0 → 输出 ~1.0

    适合: compressor, exciter, spatial, warmth 等需要明显效果的处理
    """
    if amount <= 0:
        return 0.0
    if amount <= threshold:
        return amount * 2.0
    normalized = (amount - threshold) / (1.0 - threshold)
    log_val = np.log1p(normalized * (base - 1)) / np.log(base)
    result = threshold + (1.0 - threshold) * log_val * 1.2
    return min(result, 1.0)


def aggressive_boost(amount, power=0.5, multiplier=1.8):
    """
    激进增强函数 - 适用于需要强烈效果的处理

    使用平方根或更低的幂次，使低值有更明显的效果

    曲线特性:
    - amount=0.1 → 输出 ~0.57
    - amount=0.2 → 输出 ~0.80
    - amount=0.5 → 输出 ~1.27 (clamp to 1.0)
    """
    if amount <= 0:
        return 0.0
    result = np.power(amount, power) * multiplier
    return min(result, 1.0)


def steep_sigmoid(amount, steepness=4.0, midpoint=0.3):
    """
    陡峭S曲线 - 适用于需要锐利效果增强的处理

    曲线中点前移，让低参数值也能触发效果
    """
    if amount <= 0:
        return 0.0
    sigmoid = 1.0 / (1.0 + np.exp(-steepness * (amount - midpoint)))
    enhanced = sigmoid * 1.5
    return min(enhanced, 1.0)


def linear_then_exponential(amount, threshold=0.3, power=2.5):
    """
    线性-指数混合曲线

    低于阈值线性增长，高于阈值指数增长
    """
    if amount <= 0:
        return 0.0
    if amount <= threshold:
        return amount * 1.5
    excess = amount - threshold
    return threshold * 1.5 + np.power(excess, power) * 0.5

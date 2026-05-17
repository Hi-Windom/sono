"""
v3.2 参数响应曲线模块
提供参数敏感度增强的响应曲线函数
"""

import numpy as np


def parametric_curve(amount, steepness=2.5, midpoint=0.5):
    """
    S曲线参数响应函数，使小参数值也有明显效果

    参数:
        amount: 原始参数值 (0.0 - 1.0)
        steepness: 曲线陡峭度，值越大曲线越陡 (建议 2.0 - 3.5)
        midpoint: 曲线中点，值越小低参数效果越强 (建议 0.4 - 0.6)

    返回:
        增强后的参数值 (0.0 - 1.0+)
    """
    if amount <= 0:
        return 0.0

    # Sigmoid 曲线
    sigmoid = 1.0 / (1.0 + np.exp(-steepness * (amount - midpoint)))

    # 归一化到 [0, 1] 范围，但保留曲线特性
    enhanced = sigmoid * 1.5  # 放大曲线效果

    return min(enhanced, 1.0)


def enhance_amount(amount, multiplier=1.5):
    """
    简单增强参数效果

    参数:
        amount: 原始参数值 (0.0 - 1.0)
        multiplier: 增强倍数 (建议 1.5 - 2.5)

    返回:
        增强后的参数值
    """
    if amount <= 0:
        return 0.0

    # 使用平方根曲线，使小值也有效果
    enhanced = np.sqrt(amount) * multiplier

    return min(enhanced, 1.0)


def exponential_boost(amount, power=2.0, threshold=0.2):
    """
    指数增强函数，特别增强中高参数值

    参数:
        amount: 原始参数值
        power: 指数幂，值越大高参数效果越强 (建议 1.5 - 3.0)
        threshold: 阈值，低于此值的参数增强幅度较小

    返回:
        增强后的参数值
    """
    if amount <= threshold:
        # 低参数值线性增强
        return amount * 1.5
    else:
        # 高参数值指数增强
        excess = amount - threshold
        enhanced = threshold + excess ** power
        return min(enhanced, 1.0)

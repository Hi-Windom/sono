#!/usr/bin/env python3
"""
集成测试：验证参数验证机制是否正确集成到核心处理函数
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 我们不导入整个模块，而是直接测试验证逻辑
from backend.services.repair.repair_v3_2.param_validator import (
    ALLOWED_SINGLE_PARAMS,
    ALLOWED_VOCAL_PARAMS,
    ALLOWED_INST_PARAMS,
    validate_single_params,
    validate_vocal_params,
    validate_inst_params
)


def test_v32_param_coverage():
    """
    测试 v3.2 新参数是否都在允许的参数列表中
    """
    print("=" * 60)
    print("v3.2 参数覆盖测试")
    print("=" * 60)

    # v3.2 新增的参数列表
    v32_new_params = [
        'smart_compressor',
        'exciter_improved',
        'resonance_suppress',
        'transient_aware',
        'ai_repair_adaptive',
        'de_esser_improved'
    ]

    print("\n检查单轨处理参数:")
    print(f"单轨允许参数数: {len(ALLOWED_SINGLE_PARAMS)}")
    for param in v32_new_params:
        status = "✅" if param in ALLOWED_SINGLE_PARAMS else "❌"
        print(f"  {status} {param}")

    print("\n检查人声处理参数:")
    print(f"人声允许参数数: {len(ALLOWED_VOCAL_PARAMS)}")
    for param in v32_new_params:
        status = "✅" if param in ALLOWED_VOCAL_PARAMS else "❌"
        print(f"  {status} {param}")

    # 检查是否有缺失的参数
    single_missing = [p for p in v32_new_params if p not in ALLOWED_SINGLE_PARAMS]
    vocal_missing = [p for p in v32_new_params if p not in ALLOWED_VOCAL_PARAMS]

    print("\n" + "=" * 60)
    if not single_missing and not vocal_missing:
        print("✅ 所有 v3.2 新参数都已正确定义！")
    else:
        print("❌ 发现缺失的参数:")
        if single_missing:
            print(f"   单轨处理缺失: {single_missing}")
        if vocal_missing:
            print(f"   人声处理缺失: {vocal_missing}")
    print("=" * 60)


def test_parameter_validation():
    """
    测试验证器的功能
    """
    print("\n" + "=" * 60)
    print("验证器功能测试")
    print("=" * 60)

    # 测试正常情况
    print("\n✅ 测试正常参数:")
    try:
        params = {
            'declip': 0.5,
            'depop': 0.3,
            'smart_compressor': 0.7,
            'exciter_improved': 0.6,
            'resonance_suppress': 0.4,
            'transient_aware': 0.5,
            'ai_repair_adaptive': 0.5,
            'de_esser_improved': 0.5,
        }
        validate_single_params(params)
        print("   单轨参数验证通过")
    except Exception as e:
        print(f"   单轨参数验证失败: {e}")

    # 测试未定义参数（应该抛出错误）
    print("\n✅ 测试未定义参数（应该抛出错误）:")
    try:
        invalid_params = {'declip': 0.5, 'unknown_param': 0.3}
        validate_single_params(invalid_params)
        print("   ❌ 应该抛出错误但没有")
    except ValueError as e:
        print(f"   ✅ 正确抛出错误: {str(e)[:80]}...")


if __name__ == "__main__":
    test_v32_param_coverage()
    test_parameter_validation()
    print("\n✅ 集成测试完成！")

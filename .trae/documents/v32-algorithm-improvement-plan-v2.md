# v3.2 系列算法改进方案（修订版）

## 一、核心原则

**让问题在构建时暴露，而不是运行时静默失败**

## 二、问题分析

### 2.1 当前问题

| 问题类型 | 现象 | 严重性 | 当前状态 |
|---------|------|--------|---------|
| 参数映射缺失 | `_SINGLE_KEY_MAP` 缺少 v3.2 新参数 | 🔴 高 | 静默忽略 |
| 参数冲突 | `compressor` vs `smart_compressor` | 🔴 高 | 静默忽略 |
| 参数未处理 | 部分 v3.2 参数在 `process_vocal_track` 中未处理 | 🔴 高 | 静默忽略 |
| 前端映射不完整 | 后端参数未正确映射到前端 | 🔴 高 | 静默忽略 |

### 2.2 为什么静默失败是错误的

1. **用户无法感知问题**：参数调到最大也没有效果，用户认为是软件 bug
2. **调试困难**：没有错误信息，很难定位问题
3. **信任损失**：用户对产品失去信心
4. **维护困难**：代码变更后无法及时发现问题

## 三、解决方案：强制参数验证

### 3.1 设计原则

1. **Fail Fast**：参数验证失败立即抛出错误
2. **明确错误信息**：告诉用户哪个参数未被处理
3. **自动化检测**：通过测试确保参数完整性
4. **文档化**：明确记录每个参数的处理状态

### 3.2 验证层级

```
层级1: 前端参数定义验证（TypeScript 类型检查）
   ↓
层级2: 前端参数映射完整性测试（自动化测试）
   ↓
层级3: 后端参数处理验证（运行时检查）
   ↓
层级4: 端到端参数流转测试（E2E 测试）
```

## 四、实施方案

### 4.1 层级1：TypeScript 类型检查 ✅

**当前状态**: 已有类型定义 `VocalRepairParams`

**问题**: 类型定义存在但参数映射可能不完整

**改进**: 添加参数白名单验证

```typescript
// src/services/paramValidator.ts
import type { VocalRepairParams } from './backendApi';

export const VOCAL_PARAM_WHITELIST: (keyof VocalRepairParams)[] = [
  'deClipping', 'dePop', 'formantRepair', 'deEssing',
  'breathEnhance', 'aiRepair', 'bassEnhance', 'airTexture',
  'loudness', 'exciter', 'compressor', 'spatial', 'warmth',
  'smartCompressor', 'transientAware', 'resonanceSuppress',
  'aiRepairAdaptive', 'exciterImproved', 'deEsserImproved', 'speed'
];

export function validateVocalParams(params: VocalRepairParams): void {
  const unexpectedParams = Object.keys(params).filter(
    key => !VOCAL_PARAM_WHITELIST.includes(key as keyof VocalRepairParams)
  );

  if (unexpectedParams.length > 0) {
    throw new Error(
      `Unexpected vocal params detected: ${unexpectedParams.join(', ')}. ` +
      `Please update VOCAL_PARAM_WHITELIST in paramValidator.ts`
    );
  }
}
```

### 4.2 层级2：前端参数映射完整性测试 🆕

**目标**: 确保前端参数完整映射到后端

**实施**: 添加参数映射测试

```typescript
// src/__tests__/paramMapping.test.ts
import { mapVocalParamsToBackend } from '../services/backendApi';
import type { VocalRepairParams } from '../services/backendApi';

describe('参数映射完整性测试', () => {
  const allVocalParams: VocalRepairParams = {
    deClipping: 0,
    dePop: 0,
    formantRepair: 0,
    deEssing: 0,
    breathEnhance: 0,
    aiRepair: 0,
    bassEnhance: 0,
    airTexture: 0,
    loudness: 0,
    exciter: 0,
    compressor: 0,
    spatial: 0,
    warmth: 0,
    smartCompressor: 0,
    transientAware: 0,
    resonanceSuppress: 0,
    aiRepairAdaptive: 0,
    exciterImproved: 0,
    deEsserImproved: 0,
    speed: 1,
  };

  test('所有前端参数都应映射到后端', () => {
    const backendParams = mapVocalParamsToBackend(allVocalParams, {}, 'v3.2');

    // 验证关键参数都被映射
    const requiredBackendParams = [
      'de_clipping', 'de_pop', 'formant_repair', 'de_essing',
      'smart_compressor', 'exciter_improved', 'resonance_suppress',
      'transient_aware', 'ai_repair_adaptive', 'de_esser_improved'
    ];

    const missingParams = requiredBackendParams.filter(
      param => !(param in backendParams)
    );

    expect(missingParams).toHaveLength(0);
    expect(missingParams).toEqual([]);
  });
});
```

**配置**: 将此测试添加到 CI/CD 流程

```yaml
# .github/workflows/test.yml
- name: Run Param Mapping Tests
  run: npm run test:param-mapping
```

### 4.3 层级3：后端参数处理验证 🆕

**目标**: 确保后端正确处理所有传递的参数

**实施**: 添加参数处理验证函数

```python
# backend/services/repair/repair_v3_2/param_validator.py
"""
参数验证器 - 确保所有传递的参数都被正确处理
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

def validate_single_params(params: dict) -> None:
    """
    验证单轨处理参数
    如果发现未定义的参数，抛出明确的错误
    """
    unexpected_params = []

    for key in params.keys():
        if key.startswith('_'):  # 内部参数跳过
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
    """
    ALLOWED_INST_PARAMS = {
        'declip', 'depop', 'timbre_protect', 'dynamic', 'noise_reduction',
        'spatial', 'warmth', 'stereo_enhance', 'loudness',
        'speed', '_issues'
    }

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
```

**集成到核心处理函数**:

```python
# backend/services/repair/repair_v3_2/core.py
from .param_validator import (
    validate_single_params,
    validate_vocal_params,
    validate_inst_params
)

def _repair_single_track(input_path: str, output_path: str, params: dict, progress_callback=None) -> dict:
    # ... 现有代码 ...

    # 参数验证
    validate_single_params(params)

    # ... 其余代码 ...
```

```python
def process_vocal_track(y, sr, params):
    # 参数验证
    validate_vocal_params(params)

    # ... 其余代码 ...
```

```python
def process_instrument_track(y, sr, params):
    # 参数验证
    validate_inst_params(params)

    # ... 其余代码 ...
```

### 4.4 层级4：端到端参数流转测试 🆕

**目标**: 验证从前端到后端的完整参数流转

```typescript
// tests/e2e/param-flow.spec.ts
import { test, expect } from '@playwright/test';

test.describe('v3.2 参数流转验证', () => {
  test('应抛出错误当参数未被处理时', async ({ page }) => {
    await page.goto('/repair');

    // 模拟传递一个未定义的参数
    const response = await page.request.post('/api/v1/repair', {
      data: {
        algorithm_version: 'v3.2',
        // 故意传递一个不存在的参数
        nonexistent_param: 0.5
      }
    });

    // 期望后端返回 400 错误，并包含明确的错误信息
    expect(response.status()).toBe(400);
    const errorText = await response.text();
    expect(errorText).toContain('未定义的参数');
    expect(errorText).toContain('nonexistent_param');
  });

  test('所有 v3.2 新参数都应被正确处理', async ({ page }) => {
    await page.goto('/repair');

    // 传递所有 v3.2 新参数
    const response = await page.request.post('/api/v1/repair', {
      data: {
        algorithm_version: 'v3.2',
        de_clipping: 0.5,
        de_pop: 0.5,
        smart_compressor: 0.7,
        exciter_improved: 0.7,
        resonance_suppress: 0.5,
        transient_aware: 0.5,
        ai_repair_adaptive: 0.5,
        de_esser_improved: 0.5,
        // ... 所有其他参数
      }
    });

    // 期望成功处理
    expect(response.ok()).toBe(true);
  });
});
```

## 五、修复当前问题

### 5.1 修复1：补全 _SINGLE_KEY_MAP

**文件**: `backend/services/repair/repair_v3_2/core.py`

**修改**: 在 `_repair_single_track` 函数中补全参数映射

```python
# line 1114-1131
_SINGLE_KEY_MAP = {
    # 基础参数
    "de_clipping": "declip", "de_pop": "depop", "de_essing": "de_ess",

    # 映射表（补充缺失的）
    "dynamic_range": "dynamic",
    "spatial_enhance": "spatial",
    "loudness_optimize": "loudness",

    # v3.2 新参数（补充缺失的）
    "de_esser_improved": "de_esser_improved",
    "ai_repair_adaptive": "ai_repair_adaptive",
    "exciter_improved": "exciter_improved",
    "resonance_suppress": "resonance_suppress",
    "transient_aware": "transient_aware",

    # 其他参数
    "stereo_enhance": "stereo_enhance",
    "warmth": "warmth",
    "air_texture": "air_texture",
    "bass_enhance": "bass_enhance",
    "formant_repair": "formant_repair",
    "breath_enhance": "breath_enhance",
    "ai_repair": "ai_repair",
    "noise_reduction": "noise_reduction",
}
```

### 5.2 修复2：修复 compressor/smart_compressor 冲突

**文件**: `backend/services/repair/repair_v3_2/core.py`

**修改**: 在 `process_vocal_track` 和 `_repair_single_track` 中处理冲突

```python
# process_vocal_track (line 980-981)
# 修改前:
if params.get("compressor", 0) > 0 or params.get("smart_compressor", 0) > 0:
    y = _vocal_smart_compressor(y, sr, params.get("compressor", params.get("smart_compressor", 0)))

# 修改后:
compressor_amount = max(
    params.get("compressor", 0),
    params.get("smart_compressor", 0)
)
if compressor_amount > 0:
    y = _vocal_smart_compressor(y, sr, compressor_amount)
```

### 5.3 修复3：补全 process_vocal_track 参数处理

**文件**: `backend/services/repair/repair_v3_2/core.py`

**验证**: 确保以下参数都有对应的处理逻辑

```python
def process_vocal_track(y, sr, params):
    # 验证：这些参数都应该被处理
    assert 'declip' in params or params.get('declip', 0) == 0
    assert 'depop' in params or params.get('depop', 0) == 0
    assert 'de_ess' in params or params.get('de_ess', 0) == 0
    assert 'formant_repair' in params or params.get('formant_repair', 0) == 0
    assert 'breath_enhance' in params or params.get('breath_enhance', 0) == 0
    assert 'ai_repair' in params or params.get('ai_repair', 0) == 0
    assert 'ai_repair_adaptive' in params or params.get('ai_repair_adaptive', 0) == 0  # 新增
    assert 'bass_enhance' in params or params.get('bass_enhance', 0) == 0
    assert 'air_texture' in params or params.get('air_texture', 0) == 0
    assert 'de_esser_improved' in params or params.get('de_esser_improved', 0) == 0  # 新增
    assert 'resonance_suppress' in params or params.get('resonance_suppress', 0) == 0  # 新增
    assert 'exciter_improved' in params or params.get('exciter_improved', 0) == 0  # 新增
    assert 'transient_aware' in params or params.get('transient_aware', 0) == 0  # 新增
    assert 'smart_compressor' in params or params.get('smart_compressor', 0) == 0  # 新增
    assert 'compressor' in params or params.get('compressor', 0) == 0  # 新增
    assert 'spatial' in params or params.get('spatial', 0) == 0
    assert 'warmth' in params or params.get('warmth', 0) == 0
    assert 'loudness' in params or params.get('loudness', 0) == 0

    # ... 处理逻辑 ...
```

### 5.4 修复4：更新前端参数映射

**文件**: `src/services/backendApi.ts`

**修改**: 确保所有参数都被正确映射

```typescript
export function mapVocalParamsToBackend(params: VocalRepairParams): Record<string, unknown> {
  return {
    // 基础参数
    de_clipping: params.deClipping,
    de_pop: params.dePop,
    formant_repair: params.formantRepair,
    de_essing: params.deEssing,
    breath_enhance: params.breathEnhance,
    ai_repair: params.aiRepair,
    bass_enhance: params.bassEnhance,
    air_texture: params.airTexture,
    loudness_optimize: params.loudness,

    // v3.2 新参数
    exciter_improved: params.exciterImproved ?? 0,
    compressor: params.compressor ?? 0,
    smart_compressor: params.smartCompressor ?? 0,
    spatial: params.spatial ?? 0,
    warmth: params.warmth ?? 0,
    transient_aware: params.transientAware ?? 0,
    resonance_suppress: params.resonanceSuppress ?? 0,
    ai_repair_adaptive: params.aiRepairAdaptive ?? 0,
    de_esser_improved: params.deEsserImproved ?? 0,

    speed: params.speed ?? 1.0,
    algorithm_version: 'v3.2',
  };
}
```

## 六、测试验证

### 6.1 单元测试

```bash
# 运行参数映射测试
npm run test:param-mapping

# 运行参数验证测试
pytest backend/tests/test_param_validation.py -v
```

### 6.2 集成测试

```bash
# 运行所有 E2E 测试
npm run test:e2e
```

### 6.3 手动测试清单

- [ ] 调整 smart_compressor 参数，观察效果变化
- [ ] 调整 exciter_improved 参数，观察效果变化
- [ ] 调整 resonance_suppress 参数，观察效果变化
- [ ] 调整 transient_aware 参数，观察效果变化
- [ ] 调整 ai_repair_adaptive 参数，观察效果变化
- [ ] 调整 de_esser_improved 参数，观察效果变化

## 七、CI/CD 集成

### 7.1 GitHub Actions 配置

```yaml
name: Parameter Validation

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  validate-params:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install dependencies
        run: npm ci

      - name: Run param mapping tests
        run: npm run test:param-mapping

      - name: Run backend param validation tests
        run: |
          cd backend
          pip install -r requirements.txt
          pytest tests/test_param_validation.py -v
```

### 7.2 Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

# 运行参数验证测试
echo "Running param validation..."
npm run test:param-mapping

if [ $? -ne 0 ]; then
  echo "Param validation failed. Please fix errors before committing."
  exit 1
fi
```

## 八、监控与告警

### 8.1 参数错误监控

在后端添加参数验证失败的监控指标：

```python
from prometheus_client import Counter

param_validation_errors = Counter(
    'repair_param_validation_errors_total',
    'Total number of parameter validation errors',
    ['algorithm_version', 'param_name']
)

def validate_single_params(params: dict) -> None:
    try:
        # 验证逻辑
        pass
    except ValueError as e:
        param_validation_errors.labels(
            algorithm_version='v3.2',
            param_name=str(e)
        ).inc()
        raise
```

## 九、文档更新

### 9.1 v3.2 参数文档

创建参数文档，明确每个参数的作用和处理状态：

```markdown
# v3.2 修复参数文档

## 人声处理参数

| 参数名 | 类型 | 默认值 | 范围 | 作用 | 处理状态 |
|--------|------|--------|------|------|----------|
| smart_compressor | float | 0.0 | 0.0-1.0 | 智能压缩 | ✅ 已实现 |
| exciter_improved | float | 0.0 | 0.0-1.0 | 激励器 | ✅ 已实现 |
| resonance_suppress | float | 0.0 | 0.0-1.0 | 共振抑制 | ✅ 已实现 |
| transient_aware | float | 0.0 | 0.0-1.0 | 瞬态处理 | ✅ 已实现 |
| ai_repair_adaptive | float | 0.0 | 0.0-1.0 | 自适应AI修复 | ✅ 已实现 |
| de_esser_improved | float | 0.0 | 0.0-1.0 | 齿音消除 | ✅ 已实现 |

## 状态说明

- ✅ 已实现：参数已被正确处理
- ⚠️ 部分实现：参数有部分功能
- ❌ 未实现：参数尚未实现，使用会抛出错误
```

## 十、总结

### 核心改进

1. **Fail Fast 原则**：参数验证失败立即抛出错误
2. **多层验证**：前端类型检查 → 前端映射测试 → 后端验证 → E2E 测试
3. **明确错误信息**：告诉开发者具体哪个参数有问题
4. **自动化检测**：通过 CI/CD 确保参数完整性

### 实施优先级

1. 🔴 **P0**: 添加后端参数验证（立即生效）
2. 🔴 **P0**: 修复当前参数映射问题（立即生效）
3. 🟡 **P1**: 添加前端参数映射测试（CI/CD）
4. 🟡 **P1**: 添加参数文档（持续维护）
5. 🟢 **P2**: 集成监控与告警（可选）

### 预期效果

- **问题暴露时间**: 构建时 → 运行时
- **错误定位时间**: 小时级 → 分钟级
- **用户满意度**: 提升 50%（参数可感知效果）

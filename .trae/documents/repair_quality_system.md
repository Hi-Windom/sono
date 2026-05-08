# 修复算法质量保障体系

## Summary

将本次 v2.2a 杂音修复的调试思路和经验固化为：
1. **自动化测试套件**：pytest 测试覆盖全部活跃版本（v1.x ~ v2.2a），确保每个处理步骤不引入可闻失真
2. **思路经验文档**：精简版放在 `backend/services/repair/QUALITY_RULES.md`，完整版放在 `.trae/documents/repair_quality_guide.md`

## Current State Analysis

### 现状
- 7 个修复版本（v1.0 ~ v2.2a），**零自动化测试**
- v2.2a 曾存在严重杂音问题，根因是两个处理步骤引入了 AM 伪影
- 每次修改处理链只能靠人耳听，无法量化验证
- 版本间无质量基线对比，升级时无法检测回归

### 本次修复发现的关键问题

| 问题 | 根因 | 诊断方法 |
|------|------|----------|
| depop 产生"呲呲"声 | 余弦插值替换 265 样本窗口，误差 119% | 逐步 SNR 测试：depop SNR=19.3dB |
| compress 产生"呲呲"声 | 时变增益 = AM 调制，5-10kHz 噪声 3.13e+01 | 逐步频谱分析：compress HF 噪声是其他步骤的 30-50 倍 |
| 硬削波产生高频谐波 | `np.clip(y, -0.95, 0.95)` 截平波形 | THD 测试 + flat-top 样本计数 |
| analyser 重复连接 | 每次 play/switch 都 `connect(destination)` | 代码审查 |

### 核心诊断方法论

1. **逐步 SNR 测试**：对每个处理步骤单独测量 scale-adjusted SNR
2. **频谱噪声分析**：测量残差在 5-10kHz、10-16kHz 频段的能量
3. **THD 测试**：用纯净正弦波输入，测量输出总谐波失真
4. **flat-top 检测**：统计输出中 `|diff| < 1e-8` 的样本数（硬削波指标）

## Proposed Changes

### 1. 创建测试套件 `backend/tests/test_repair_quality.py`

**测试框架**：pytest（项目已有 pyproject.toml）

**测试内容**：

#### A. 通用质量基线测试（所有版本共用）

```python
class TestRepairQualityBaseline:
    """每个活跃版本必须通过的最低质量标准"""

    # 测试信号：纯净正弦波 + 真实风格音频
    - test_pure_sine_no_artifacts(): 纯正弦波输入，输出 THD < -60dB
    - test_no_hard_clipping(): 输出无 flat-top 样本（硬削波指标）
    - test_no_high_frequency_noise(): 输出 5-16kHz 频段噪声 < 输入的 1.5 倍
    - test_scale_adjusted_snr(): 全流程 scale-adjusted SNR > 40dB
    - test_per_step_snr(): 每个处理步骤单独 SNR > 60dB
```

#### B. 逐步回归测试

```python
class TestPerStepRegression:
    """逐步测量每个处理步骤的失真，确保不回归"""

    - test_declip_snr(): declip 步骤 SNR > 80dB
    - test_depop_snr(): depop 步骤 SNR > 60dB
    - test_compress_snr(): compress 步骤 SNR > 60dB
    - test_peak_limit_snr(): peak_limit 步骤 SNR > 80dB
    - test_loudness_norm_snr(): loudness_norm 步骤 SNR > 80dB
```

#### C. 版本参数化

```python
@pytest.fixture(params=["v2.0", "v2.1", "v2.2", "v2.2a"])
def repair_version(request):
    return request.param
```

#### D. 信号生成工具

```python
# backend/tests/conftest.py
def generate_test_signals(sr=44100):
    """生成标准测试信号集"""
    - pure_sine_440(): 纯 440Hz 正弦波
    - multi_tone(): 440Hz + 1kHz + 3kHz 混合
    - speech_like(): 带包络调制的类语音信号
    - with_transients(): 带瞬态的信号
    - with_clipping(): 带削波的信号
    - with_pops(): 带爆音的信号
```

### 2. 创建精简版质量规则 `backend/services/repair/QUALITY_RULES.md`

内容要点：
- 3 条铁律（禁止硬削波、禁止逐样本增益调制、禁止大窗口替换）
- 每条规则附带反例和正例代码
- 新版本开发 checklist

### 3. 创建完整经验文档 `.trae/documents/repair_quality_guide.md`

内容要点：
- 完整的调试方法论（逐步 SNR、频谱分析、THD 测试）
- 本次修复的完整案例分析
- 诊断脚本模板
- 版本升级流程

### 4. 添加 pytest 配置到 `pyproject.toml`

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
```

## Files to Create/Modify

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/tests/__init__.py` | 新建 | 测试包初始化 |
| `backend/tests/conftest.py` | 新建 | 测试信号生成、版本参数化 fixture |
| `backend/tests/test_repair_quality.py` | 新建 | 质量基线 + 逐步回归测试 |
| `backend/services/repair/QUALITY_RULES.md` | 新建 | 精简版质量规则（3 铁律 + checklist） |
| `.trae/documents/repair_quality_guide.md` | 新建 | 完整经验文档（方法论 + 案例 + 模板） |
| `pyproject.toml` | 修改 | 添加 pytest 配置 |

## Assumptions & Decisions

1. **测试信号用合成信号**，不依赖真实音频文件，确保测试可重复
2. **SNR 阈值设定**：纯线性操作 > 80dB，有损操作 > 40dB，基于本次诊断数据
3. **v1.x 版本**：接口不同（类式 API），需要适配器包装
4. **CI 集成**：暂不配置，但测试应能在本地 `pytest backend/tests/` 一键运行
5. **文档语言**：中文（与项目规则一致）

## Verification Steps

1. `cd /workspace && python -m pytest backend/tests/test_repair_quality.py -v` 全部通过
2. 手动验证：修改某个步骤引入硬削波，测试应失败
3. 文档内容完整，包含本次修复的全部经验

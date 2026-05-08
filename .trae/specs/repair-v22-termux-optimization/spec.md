# v2.2 Termux 性能优化 Spec

## Why

当前 v2.2 实现存在严重问题：
1. **Termux 不兼容**：使用了 Numba 库，在 Termux 环境中无法安装/运行
2. **性能未达预期**：纯 Python 实现未实现 3x+ 提速目标
3. **代码质量问题**：spectral_combined.py 存在语法错误导致服务崩溃

需要重新设计一个**纯 Python/SciPy 实现**、**Termux 完全兼容**、**真正达到 3x+ 提速**的优化方案。

## What Changes

- 重写 `spectral_group_a.py` — 移除 Numba 依赖，使用纯 SciPy 优化
- 重写 `spectral_combined.py` — 修复语法错误，优化合并处理流程
- 重写 `transient.py` — 简化算法，减少计算量
- 优化 `core.py` — 减少不必要的处理步骤
- 修复所有语法错误和导入问题

## Impact

- 后端: `backend/services/repair/repair_v2_2/spectral_group_a.py` (重写)
- 后端: `backend/services/repair/repair_v2_2/spectral_combined.py` (重写)
- 后端: `backend/services/repair/repair_v2_2/transient.py` (重写)
- 后端: `backend/services/repair/repair_v2_2/core.py` (优化)
- 后端: `backend/requirements.txt` (移除 numba)

## ADDED Requirements

### Requirement: Termux 完全兼容

系统 SHALL 确保所有代码在 Termux 环境中可正常运行：

#### 约束 1: 依赖限制
- 仅使用 Termux 预装或 pip 可安装的库
- 禁止依赖：numba, torch, torchaudio 等二进制扩展库
- 允许使用：numpy, scipy, miniaudio (纯 Python 或有 Termux 支持)

#### 约束 2: 语法正确性
- 所有 Python 文件必须通过 `python -m py_compile` 检查
- 无未闭合字符串、缩进错误等基础语法问题

### Requirement: 3x+ 性能提速

系统 SHALL 实现频谱修复和瞬态修复 3x+ 提速：

#### 策略 1: 算法简化
- 减少嵌套循环层数
- 简化数学运算（如用简单平均替代复杂统计）
- 减少处理步骤数量

#### 策略 2: 向量化操作
- 使用 NumPy 向量化替代 Python 循环
- 使用 scipy.signal.lfilter (C 实现) 替代手动平滑
- 批量处理多通道数据

#### 策略 3: 减少 STFT/ISTFT 次数
- 合并 group_a 和 group_b 处理，单次频谱变换
- 缓存中间结果避免重复计算

### Requirement: 代码质量保证

系统 SHALL 确保代码质量：

#### 检查 1: 语法检查
- 所有文件通过 Python 语法检查
- 无运行时导入错误

#### 检查 2: 功能测试
- 处理正常音频不崩溃
- 输出音频质量可接受
- 性能达到预期目标

## MODIFIED Requirements

### Requirement: 移除 Numba 依赖

`backend/requirements.txt` SHALL 移除 numba 依赖：
- 删除 `numba>=0.60` 行
- 确保其他依赖在 Termux 可用

## REMOVED Requirements

无移除项。保留 v2.2 功能特性，仅优化实现方式。

# Tasks

## v2.2 桌面端完整版

- [x] Task 1: 创建 v2.2 目录结构和基础模块
  - [x] SubTask 1.1: 创建 `backend/services/repair/repair_v2_2/` 目录
  - [x] SubTask 1.2: 创建 `__init__.py` 导出主函数
  - [x] SubTask 1.3: 创建 `core.py` 主处理流程

- [x] Task 2: 实现音乐类型检测模块
  - [x] SubTask 2.1: 创建 `music_type_detector.py`
  - [x] SubTask 2.2: 实现频谱特征提取
  - [x] SubTask 2.3: 实现人声检测算法
  - [x] SubTask 2.4: 实现类型分类器

- [x] Task 3: 实现 C 原生库加速模块
  - [x] SubTask 3.1: 创建 `backend/services/dsp_native/` 目录
  - [x] SubTask 3.2: 编写 C 代码
  - [x] SubTask 3.3: 编写 Makefile
  - [x] SubTask 3.4: 创建 ctypes 封装

- [x] Task 4: 实现频谱处理模块
  - [x] SubTask 4.1: 创建 `spectral_group_a.py`
  - [x] SubTask 4.2: 创建 `spectral_group_b.py`
  - [x] SubTask 4.3: 实现类型自适应参数

- [x] Task 5: 实现时域处理模块
  - [x] SubTask 5.1: 创建 `declip.py`
  - [x] SubTask 5.2: 创建 `depop.py`
  - [x] SubTask 5.3: 创建 `transient.py`

- [x] Task 6: 实现滤波和空间处理模块
  - [x] SubTask 6.1: 创建 `filters.py`
  - [x] SubTask 6.2: 创建 `spatial.py`

- [x] Task 7: 实现动态处理和后期处理模块
  - [x] SubTask 7.1: 创建 `dynamics.py` 多段压缩
  - [x] SubTask 7.2: 创建 `postprocess.py`

## v2.2a 移动端精简版

- [ ] Task 8: 创建 v2.2a 目录结构
  - [ ] SubTask 8.1: 创建 `backend/services/repair/repair_v2_2a/` 目录
  - [ ] SubTask 8.2: 创建 `__init__.py`
  - [ ] SubTask 8.3: 创建 `core.py` 精简流程

- [ ] Task 9: 实现移动端频谱处理
  - [ ] SubTask 9.1: 创建 `spectral_fast.py` 极速处理
  - [ ] SubTask 9.2: 简化降噪算法
  - [ ] SubTask 9.3: 固定频段去齿音

- [ ] Task 10: 实现移动端动态处理
  - [ ] SubTask 10.1: 创建 `dynamics_simple.py` 单段压缩
  - [ ] SubTask 10.2: 简化包络检测

- [ ] Task 11: 实现移动端其他模块
  - [ ] SubTask 11.1: 简化时域处理
  - [ ] SubTask 11.2: 简化后期处理
  - [ ] SubTask 11.3: 精简参数配置

## 版本注册

- [x] Task 12: 注册 v2.2 桌面端版本
  - [x] SubTask 12.1: 修改 `audio_repair.py`
  - [x] SubTask 12.2: 配置 `mobile_compatible: False`

- [ ] Task 13: 注册 v2.2a 移动端版本
  - [ ] SubTask 13.1: 添加 v2.2a 配置
  - [ ] SubTask 13.2: 配置 `mobile_compatible: True`
  - [ ] SubTask 13.3: 配置精简参数

## 测试验证

- [x] Task 14: 桌面端测试
  - [x] SubTask 14.1: 功能测试
  - [x] SubTask 14.2: 音质测试

- [ ] Task 15: 移动端测试
  - [ ] SubTask 15.1: 速度测试（目标 5x+）
  - [ ] SubTask 15.2: 音质测试
  - [ ] SubTask 15.3: Termux 兼容性测试

# Task Dependencies

- Task 9, 10, 11 依赖 Task 8
- Task 13 依赖 Task 8, 9, 10, 11
- Task 15 依赖 Task 13

# Tasks

- [x] Task 1: 创建 v2.2 目录结构和基础模块
  - [x] SubTask 1.1: 创建 `backend/services/repair/repair_v2_2/` 目录
  - [x] SubTask 1.2: 创建 `__init__.py` 导出主函数
  - [x] SubTask 1.3: 创建 `core.py` 主处理流程

- [x] Task 2: 实现音乐类型检测模块
  - [x] SubTask 2.1: 创建 `music_type_detector.py`
  - [x] SubTask 2.2: 实现频谱特征提取（质心、带宽、对比度）
  - [x] SubTask 2.3: 实现人声检测算法
  - [x] SubTask 2.4: 实现类型分类器（人声/器乐/电子/古典/流行）

- [x] Task 3: 实现 C 原生库加速模块
  - [x] SubTask 3.1: 创建 `backend/services/dsp_native/` 目录
  - [x] SubTask 3.2: 编写 C 代码（stft.c, filter.c, compressor.c）
  - [x] SubTask 3.3: 编写 Makefile 构建脚本
  - [x] SubTask 3.4: 创建 `native_dsp.py` ctypes 封装
  - [x] SubTask 3.5: 实现 Python 回退方案

- [x] Task 4: 实现类型优化的频谱处理模块
  - [x] SubTask 4.1: 创建 `spectral_group_a.py`（降噪/去齿音/去毛刺）
  - [x] SubTask 4.2: 创建 `spectral_group_b.py`（谐波增强）
  - [x] SubTask 4.3: 实现类型自适应参数调整

- [x] Task 5: 实现时域处理模块
  - [x] SubTask 5.1: 创建 `declip.py` 去削波
  - [x] SubTask 5.2: 创建 `depop.py` 去爆音
  - [x] SubTask 5.3: 创建 `transient.py` 瞬态修复

- [x] Task 6: 实现滤波和空间处理模块
  - [x] SubTask 6.1: 创建 `filters.py`（临场/低音/温暖/清晰度）
  - [x] SubTask 6.2: 创建 `spatial.py` 空间感增强
  - [x] SubTask 6.3: 实现类型优化参数

- [x] Task 7: 实现动态处理和后期处理模块
  - [x] SubTask 7.1: 创建 `dynamics.py` 多段压缩
  - [x] SubTask 7.2: 创建 `postprocess.py` 响度归一化和峰值限制

- [x] Task 8: 注册 v2.2 版本到主模块
  - [x] SubTask 8.1: 修改 `backend/services/audio_repair.py`
  - [x] SubTask 8.2: 添加 v2.2 版本配置和 5 种修复模式
  - [x] SubTask 8.3: 添加 `music_type` 参数定义

- [x] Task 9: 构建 C 原生库
  - [x] SubTask 9.1: 在 Linux 环境编译测试
  - [x] SubTask 9.2: 验证 ctypes 加载和调用

- [x] Task 10: 集成测试
  - [x] SubTask 10.1: 测试音乐类型检测准确性
  - [x] SubTask 10.2: 测试不同类型音频的处理效果
  - [x] SubTask 10.3: 测试移动端兼容性

# Task Dependencies

- Task 3 依赖 Task 1（需要目录结构）
- Task 4, 5, 6, 7 依赖 Task 1 和 Task 2（需要类型检测）
- Task 8 依赖 Task 1, 4, 5, 6, 7（需要完整模块）
- Task 9 依赖 Task 3
- Task 10 依赖 Task 8 和 Task 9

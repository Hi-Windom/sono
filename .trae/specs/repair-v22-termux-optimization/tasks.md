# Tasks

- [ ] Task 1: 修复 spectral_combined.py 语法错误
  - [ ] SubTask 1.1: 检查并修复文件中的语法错误
  - [ ] SubTask 1.2: 运行 python -m py_compile 验证

- [ ] Task 2: 重写 spectral_group_a.py
  - [ ] SubTask 2.1: 移除所有 Numba 相关代码
  - [ ] SubTask 2.2: 使用纯 SciPy lfilter 实现平滑
  - [ ] SubTask 2.3: 向量化降噪、去齿音、毛刺修复
  - [ ] SubTask 2.4: 运行语法检查和功能测试

- [ ] Task 3: 重写 transient.py
  - [ ] SubTask 3.1: 简化瞬态检测算法
  - [ ] SubTask 3.2: 使用向量化修复替代循环
  - [ ] SubTask 3.3: 运行语法检查和功能测试

- [ ] Task 4: 优化 core.py
  - [ ] SubTask 4.1: 简化处理流程
  - [ ] SubTask 4.2: 优化参数传递
  - [ ] SubTask 4.3: 运行语法检查

- [ ] Task 5: 更新 requirements.txt
  - [ ] SubTask 5.1: 移除 numba 依赖
  - [ ] SubTask 5.2: 验证其他依赖 Termux 兼容

- [ ] Task 6: 性能测试和验证
  - [ ] SubTask 6.1: 测试频谱修复性能
  - [ ] SubTask 6.2: 测试瞬态修复性能
  - [ ] SubTask 6.3: 验证 3x+ 提速目标

- [ ] Task 7: Android 打包
  - [ ] SubTask 7.1: 运行 build_android_release.sh
  - [ ] SubTask 7.2: 验证打包产物

# Task Dependencies

- Task 1 优先于其他所有任务（修复语法错误）
- Task 2, 3, 4 可并行执行
- Task 5 依赖 Task 2, 3, 4 完成
- Task 6 依赖 Task 1-5 完成
- Task 7 依赖 Task 6 完成

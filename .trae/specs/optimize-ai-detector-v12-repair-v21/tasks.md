# Tasks

## Phase 1: AI 检测算法 v1.2 优化

- [ ] Task 1: 分析 AI 音乐素材特征分布
  - [ ] SubTask 1.1: 运行 analyze_features.py 提取所有训练素材特征
  - [ ] SubTask 1.2: 统计当前 v1.2 在这些 AI 音乐上的 AI 概率分布
  - [ ] SubTask 1.3: 识别检出不足的关键特征和阈值

- [x] Task 2: 重新校准检测算法权重（提高 AI 检出率）
  - [x] SubTask 2.1: 反转策略：将"过度规律/稳定"判定为 AI 特征（而非人类特征）
  - [x] SubTask 2.2: 调整 spectral_correlation 阈值（>0.90 = AI）
  - [x] SubTask 2.3: 调整 centroid_cv 阈值（<0.20 = AI）
  - [x] SubTask 2.4: 调整 micro_rhythm_consistency 阈值（>0.92 = AI）
  - [x] SubTask 2.5: 调整 rms_cv 阈值（<0.30 = AI）
  - [x] SubTask 2.6: 调整 mfcc_variability 阈值（<0.6 = AI）
  - [x] SubTask 2.7: 重新平衡所有特征的 ai_score/human_score 分配

- [ ] Task 3: 验证优化效果
  - [ ] SubTask 3.1: 重新运行检测，验证所有 AI 音乐素材 AI 概率 > 70%
  - [ ] SubTask 3.2: 用人类创作音频验证误判率（人类概率 > 50%）
  - [ ] SubTask 3.3: 调整至最佳平衡点

## Phase 2: AI 修复算法 v2.1 音质优化

- [ ] Task 4: 频谱处理平滑化改进
  - [ ] SubTask 4.1: 修改 `repair_v2_1/spectral_group_a.py`：Wiener 掩码增加时域平滑
  - [ ] SubTask 4.2: 修改 `repair_v2_1/spectral_group_a.py`：降噪 floor 参数自适应调整
  - [ ] SubTask 4.3: 修改 `repair_v2_1/spectral_group_b.py`：谐波注入增加频域交叉淡化

- [ ] Task 5: 响度归一化改进
  - [ ] SubTask 5.1: 修改 `repair_v2_1/postprocess.py`：滑动窗口 RMS 替代 block-based
  - [ ] SubTask 5.2: 增加 lookahead 限制器减少 pumping
  - [ ] SubTask 5.3: 目标响度 -16 LUFS，容差 ±1 LUFS

- [ ] Task 6: 动态范围控制优化
  - [ ] SubTask 6.1: 修改 `repair_v2_1/dynamics.py`：多段压缩器增加自动 makeup gain
  - [ ] SubTask 6.2: 压缩/释放时间自适应（根据信号特性）

- [ ] Task 7: 后处理链优化
  - [ ] SubTask 7.1: 修改 `repair_v2_1/postprocess.py`：峰值限制器 4x 超采样
  - [ ] SubTask 7.2: 优化软削波曲线减少失真

## Phase 3: 构建与测试

- [ ] Task 8: 构建验证
  - [ ] SubTask 8.1: 运行 `npm run build` 确认前端构建成功
  - [ ] SubTask 8.2: 重新打包 `release_android.tar.gz`

- [ ] Task 9: 音质测试
  - [ ] SubTask 9.1: 用测试音频对比优化前后的 v2.1 输出音质
  - [ ] SubTask 9.2: 验证 artifacts 减少
  - [ ] SubTask 9.3: 验证响度归一化 pumping 减少

# Task Dependencies

- Task 2 依赖 Task 1 完成
- Task 3 依赖 Task 2 完成
- Task 4-7 可并行开发
- Task 8-9 依赖 Task 3 和 Task 4-7 完成

# Checklist: v3.0/v3.0a 人声伴奏双轨处理

## Phase 1: 后端算法
- [ ] `backend/services/repair/repair_v3_0/` 包创建完成
- [ ] 人声处理链实现（口型修复 + 齿音抑制 + 气息增强 + AI频谱修复）
- [ ] 伴奏处理链实现（音色保护 + 动态控制 + 频谱降噪）
- [ ] `_vocal_formant_repair` 口型修复算法
- [ ] `_vocal_breath_enhance` 气息增强算法
- [ ] `_instrument_timbre_protect` 音色保护算法
- [ ] `_mix_tracks` 混音模块
- [ ] `backend/services/repair/repair_v3_0a/` 包创建完成
- [ ] 移动端简化处理链实现

## Phase 2: 版本注册
- [ ] v3.0 注册到 `_REPAIR_MODULES`
- [ ] v3.0a 注册到 `_REPAIR_MODULES`
- [ ] v3.0 版本配置（6 个模式）
- [ ] v3.0a 版本配置（4 个模式）
- [ ] 双轨处理参数定义
- [ ] v3.0 内存估算（+100%）
- [ ] v3.0a 内存估算（+50%）

## Phase 3: 后端 API
- [ ] `/upload-dual` 端点（双轨上传）
- [ ] `/repair-dual` 端点（双轨处理）
- [ ] `/track-status/{task_id}` 端点
- [ ] 双轨任务处理函数
- [ ] 双轨进度追踪

## Phase 4: 前端
- [ ] `backendApi.ts` 双轨参数类型
- [ ] 双轨上传 API 函数
- [ ] 双轨处理 API 函数
- [ ] `useAudioProcessor.ts` 双轨状态管理
- [ ] 双轨模式切换 UI
- [ ] 人声轨/伴奏轨分别上传 UI
- [ ] 人声/伴奏独立参数滑块
- [ ] 混音比例调节 UI
- [ ] 输出轨道选择 UI

## Phase 5: 测试
- [ ] v3.0 逐步测试类
- [ ] v3.0a 逐步测试类
- [ ] 口型修复测试
- [ ] 气息增强测试
- [ ] 双轨混音测试

## Phase 6: 验证
- [ ] 完整测试套件通过
- [ ] 内存占用符合预期
- [ ] 处理速度符合预期
- [ ] Android 打包成功

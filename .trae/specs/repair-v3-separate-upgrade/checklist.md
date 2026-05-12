# Checklist: v3.0/v3.0a 人声伴奏分轨处理

## Phase 1: 音频分离服务
- [ ] `backend/services/audio_separator.py` 创建完成
- [ ] Demucs 分离接口实现（v3.0）
- [ ] 简化频谱分离实现（v3.0a）
- [ ] 流式/渐进式处理支持
- [ ] 分离结果缓存机制

## Phase 2: 后端算法
- [ ] `backend/services/repair/repair_v3_0/` 包创建完成
- [ ] 人声处理链实现
- [ ] 伴奏处理链实现
- [ ] `_vocal_formant_repair` 口型修复算法
- [ ] `_vocal_breath_enhance` 气息增强算法
- [ ] `_instrument_timbre_protect` 音色保护算法
- [ ] `_mix_tracks` 混音模块
- [ ] `backend/services/repair/repair_v3_0a/` 包创建完成
- [ ] 移动端简化处理链实现

## Phase 3: 版本注册
- [ ] v3.0 注册到 `_REPAIR_MODULES`
- [ ] v3.0a 注册到 `_REPAIR_MODULES`
- [ ] v3.0 版本配置（6 个模式）
- [ ] v3.0a 版本配置（4 个模式）
- [ ] 分轨参数定义
- [ ] v3.0 内存估算（+100%）
- [ ] v3.0a 内存估算（+50%）

## Phase 4: 后端 API
- [ ] `/repair` 端点支持分轨参数
- [ ] `/separate` 端点
- [ ] `/tracks/{task_id}` 端点
- [ ] 分轨任务处理函数
- [ ] 分轨进度追踪

## Phase 5: 前端
- [ ] `backendApi.ts` 分轨参数类型
- [ ] `mapParamsToBackend` 支持分轨
- [ ] 分轨 API 调用函数
- [ ] `useAudioProcessor.ts` 分轨状态管理
- [ ] 分轨开关 UI
- [ ] 分轨参数滑块
- [ ] 输出轨道选择 UI

## Phase 6: 测试
- [ ] v3.0 逐步测试类
- [ ] v3.0a 逐步测试类
- [ ] 口型修复测试
- [ ] 气息增强测试
- [ ] 分轨混音测试

## Phase 7: 验证
- [ ] 完整测试套件通过
- [ ] 内存占用符合预期
- [ ] 处理速度符合预期
- [ ] Android 打包成功

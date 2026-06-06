# Tasks

- [x] Task 1: 修复后端参数映射断裂 — `/repair-dual` 端点展平 vocal_params/accompaniment_params
  - [x] SubTask 1.1: 修改 `routes.py` 的 `repair_dual_audio_endpoint`，将 `vocal_params` 嵌套字典展平为 `vocal_` 前缀键合并入 `params`，`accompaniment_params` 展平为 `inst_` 前缀键合并入 `params`
  - [x] SubTask 1.2: `mix_ratio` 映射为 `vocal_ratio`（值=mix_ratio）和 `accompaniment_ratio`（值=1.0）
  - [x] SubTask 1.3: 验证 `repair_v3_0/core.py` 的参数提取逻辑（`vocal_`/`inst_` 前缀）与展平后的 params 匹配
  - [x] SubTask 1.4: 同样检查 `repair_v3_0a/core.py` 的参数提取逻辑
  - [x] SubTask 1.5: 更新 `test_dual_track_api.py` 测试用例验证参数展平

- [x] Task 2: 定义前端双轨专用参数类型和映射
  - [x] SubTask 2.1: 在 `backendApi.ts` 中定义 `VocalRepairParams` 接口（deClipping, dePop, formantRepair, deEssing, breathEnhance, aiRepair, bassEnhance, airTexture, loudness）
  - [x] SubTask 2.2: 在 `backendApi.ts` 中定义 `InstrumentRepairParams` 接口（deClipping, dePop, timbreProtect, dynamicRange, noiseReduction, spatialEnhance, warmth, loudness）
  - [x] SubTask 2.3: 新增 `mapVocalParamsToBackend` 函数，映射为 `vocal_declip`/`vocal_depop`/`vocal_formant_repair` 等
  - [x] SubTask 2.4: 新增 `mapInstrumentParamsToBackend` 函数，映射为 `inst_declip`/`inst_depop`/`inst_timbre_protect` 等
  - [x] SubTask 2.5: 修改 `repairDualAudio` 使用新的映射函数

- [x] Task 3: 重构 AIRepairPanel 双轨参数面板
  - [x] SubTask 3.1: 人声参数面板使用 `VocalRepairParams` 的专用参数键和标签（去削波/去爆音/口型修复/齿音抑制/气息增强/AI修复/低音增强/空气质感/响度优化）
  - [x] SubTask 3.2: 伴奏参数面板使用 `InstrumentRepairParams` 的专用参数键和标签（去削波/去爆音/音色保护/动态控制/降噪/空间增强/温暖度/响度优化）
  - [x] SubTask 3.3: 参数默认值从后端 v3.0 ALGORITHM_VERSIONS 的 default_params 中 `vocal_`/`inst_` 前缀参数获取
  - [x] SubTask 3.4: 混合比例滑块映射为 mix_ratio

- [x] Task 4: 修改 RepairPage 双轨参数状态管理
  - [x] SubTask 4.1: 将 `dualTrackVocalParams` 状态类型改为 `VocalRepairParams`
  - [x] SubTask 4.2: 将 `dualTrackAccompanimentParams` 状态类型改为 `InstrumentRepairParams`
  - [x] SubTask 4.3: 初始化默认值使用 v3.0 的 vocal_/inst_ 默认参数
  - [x] SubTask 4.4: 修复完成后同时显示"下载双轨修复结果"和"前往 AB 对比"按钮

- [x] Task 5: 适配 ComparePage 双轨 AB 对比
  - [x] SubTask 5.1: ComparePage 识别双轨任务（通过 URL 参数或 task params 中的 processing_mode=dual）
  - [x] SubTask 5.2: 双轨模式显示三选一切换：人声/伴奏/合并
  - [x] SubTask 5.3: 人声模式：加载 vocal_task_id 的原始/修复后音频进行对比
  - [x] SubTask 5.4: 伴奏模式：加载 accompaniment_task_id 的原始/修复后音频进行对比
  - [x] SubTask 5.5: 合并模式：加载主 task_id 的修复后合并结果进行对比

- [x] Task 6: 适配双轨交付规格渲染
  - [x] SubTask 6.1: render 端点支持双轨任务（使用主 task 的 output_path 作为渲染源）
  - [x] SubTask 6.2: 前端 AIRepairPanel 双轨模式下交付规格面板正常工作

- [x] Task 7: 编写自动化测试并验证
  - [x] SubTask 7.1: 后端测试 — 验证参数展平逻辑（vocal_params → vocal_ 前缀，accompaniment_params → inst_ 前缀）
  - [x] SubTask 7.2: 后端测试 — 验证 v3.0 repair_audio 接收到正确的前缀参数
  - [x] SubTask 7.3: 运行全部测试通过
  - [x] SubTask 7.4: 打包安卓 release_android.tar.gz

# Task Dependencies

- [Task 2] depends on [Task 1] — 前端映射需与后端展平逻辑对齐
- [Task 3] depends on [Task 2] — 面板使用新参数类型
- [Task 4] depends on [Task 3] — 页面状态管理使用新参数类型
- [Task 5] independent — ComparePage 适配可并行
- [Task 6] depends on [Task 1] — 渲染依赖后端参数修复
- [Task 7] depends on [Task 1-6] — 最终验证

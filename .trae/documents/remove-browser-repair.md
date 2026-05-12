# 浏览器修复移除 - 含性能评估

## 性能评估：前端 Worker vs 后端修复

### 后端修复流程（当前主力）
1. 上传音频 → 等待队列 → 后端修复（numpy+scipy，v2.4a 算法）→ 返回结果
2. 渲染交付规格：上采样 + 频谱超分 + 谐波增强 / 下采样 + 低通滤波 + 位深增强

### 前端 Worker 修复流程（待移除）
1. 本地加载 → Worker 内修复（纯 JS 实现，v1.0 级算法）→ 本地播放/下载

### 关键对比

| 维度 | 前端 Worker | 后端 |
|------|------------|------|
| 算法版本 | v1.0 级（简单 DSP） | v2.0-v2.4a（高级 DSP + 流式处理） |
| 降噪 | FFT 门限降噪（2048 点） | 多子带谱减法 + 维纳滤波 |
| 去削波 | 三次样条插值 | 深度学习级重建 |
| 上采样 | 无（仅原始采样率） | 频谱超分 + 谐波增强 |
| 处理速度 | 5min 音频 ~10-30s | 5min 音频 ~5-15s（含队列等待） |
| 网络依赖 | 无 | 需要（上传+下载） |

### 关于"降规格"场景的评估

用户问题：如果交付规格是降规格（如 48kHz→44.1kHz，24bit→16bit），前端 Worker 能否和后端一样快或更快？

**答案：不能，且差距更大。**

原因：
1. **前端 Worker 没有重采样能力**：`audioRepairWorker.ts` 只在原始采样率上处理，没有上/下采样逻辑。降规格需要低通滤波 + 重采样，前端 Worker 完全没有实现。
2. **后端降规格非常快**：`render.py` 中降规格路径（L207-222）只是低通滤波 + `resample_poly`，5min 音频大约 1-3 秒完成，比前端 Worker 的修复过程还快。
3. **前端 Worker 算法质量远低于后端**：即使用户只需要降规格，前端 Worker 的修复质量（v1.0 级）远不如后端（v2.4a），这不是速度问题而是效果问题。
4. **网络开销可忽略**：降规格场景下后端渲染极快，主要时间花在上传（~2-5s）和下载（~1s），总时间仍远快于前端 Worker 的 10-30s 修复。

**结论：前端 Worker 在任何场景下都没有优势，彻底移除是正确的。**

## 实施计划

### Step 1: useAudioProcessor.ts — 移除浏览器修复核心

1. `PlayMode` 类型：`'original' | 'browser' | 'backend'` → `'original' | 'backend'`
2. 移除 `createRepairWorker` 函数
3. 移除状态：`browserProcessedBuffer`, `browserRepairInfo`, `enableBrowserRepair`, `workerRef`, `browserProcessedBufferRef`
4. 移除函数：`repairWithWorker`, `encodeWavWithWorker`, `downloadProcessedAudio`（浏览器分支）
5. 简化 `applySettings`：移除 `browserRepairPromise` 分支，`Promise.allSettled` 改为只等后端
6. 简化 `getCurrentBuffer`：移除 `'browser'` 分支
7. 简化 `switchPlayMode`：移除 `'browser'` 分支
8. 简化 `currentSampleRate`：移除 `'browser'` 分支
9. `processingSource` 类型：`'backend' | 'browser' | null` → `'backend' | null`
10. 移除 `setBrowserProcessedBuffer(null)` 调用
11. 移除 `audioBufferToWav` 辅助函数
12. 移除 return 对象中的浏览器相关导出
13. 移除 `highFrequencyEnhancer` 动态 import
14. 清理依赖数组

### Step 2: AIRepairPanel.tsx — 移除浏览器修复开关

1. 移除 `enableBrowserRepair` / `onEnableBrowserRepairChange` props
2. 移除浏览器修复开关 UI

### Step 3: RepairPage.tsx — 移除浏览器修复引用

1. 移除解构中的浏览器相关变量
2. 移除 `hasBrowserResult`, `browserBufferInfo` 变量
3. 移除 AIRepairPanel 和 DownloadModal 的浏览器相关 props

### Step 4: Home.tsx — 移除浏览器修复引用

1. 移除解构中的浏览器相关变量
2. 移除 `hasBrowserResult`, `browserBufferInfo`, `activeBuffer` 中的 browser 分支
3. 移除 AIRepairPanel 和 DownloadModal 的浏览器相关 props

### Step 5: DownloadModal.tsx — 移除浏览器下载

1. 移除 `browserInfo` / `browserDownloadAction` props
2. 移除浏览器下载 UI 和 `browserFilename` 状态

### Step 6: 删除文件

1. 删除 `/workspace/src/workers/audioRepairWorker.ts`
2. 删除 `/workspace/src/utils/highFrequencyEnhancer.ts`

### Step 7: 清理 advancedAudioProcessing.ts

1. 移除 `processWithAIRepair` 函数（死代码）

### Step 8: 构建验证

```bash
npm run build
bash scripts/build_android_release.sh
```

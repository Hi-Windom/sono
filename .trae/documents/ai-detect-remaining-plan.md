# AI检测独立页面 - 完整实施计划

## 当前状态

已完成：
- ✅ 后端：3个新API端点 (`/detect-file`, `/audio-files`, `/detect-path`)
- ✅ 前端：3个新API函数 (`detectFile`, `getAudioFiles`, `detectByPath`)
- ✅ 前端：DetectPage.tsx 双槽独立检测页面
- ✅ 前端：App.tsx 路由注册 `/detect`
- ✅ 前端：LandingPage.tsx 入口卡片

## 剩余工作

### 1. 确保 DetectPage 检测结果样式完整

对比 AIDetectionComparison（修复页用的组件）和 DetectPage（新页面）：

**AIDetectionComparison 的 AIDetectionCard 使用：**
- `color="from-red-900/50 to-primary/50"` (修复前) / `from-cyan-900/50 to-primary/50` (修复后)
- `detectTime` 属性传递

**DetectPage 的 AIDetectionCard 使用：**
- `color="from-purple-900/30 to-primary/30"` — 两个槽用相同颜色，不够区分
- 未传 `detectTime` — 独立检测页面不需要
- 缺少 AIDetectionCard 中的 `detectTime` 显示 — 可忽略，独立页面无此概念

**需要改进：**
- 两个槽的 AIDetectionCard 颜色应区分：A 用 `from-red-900/30 to-primary/30`，B 用 `from-cyan-900/30 to-primary/30`
- 对比摘要区域样式检查：当前实现已有 AI概率差异和人类概率差异的对比展示，功能完整

### 2. 从 RepairPage.tsx 完全移除 AI 检测

**文件: `/workspace/src/pages/RepairPage.tsx`**

移除：
- 第6行：`import { AIDetectionComparison } from '../components/AIDetectionComparison';`
- 第30-31行：解构中的 `originalAIDetection`, `backendAIDetection`
- 第33-34行：解构中的 `originalDetectTime`, `repairedDetectTime`
- 第47-49行：解构中的 `detectorVersion`, `availableDetectors`, `setDetectorVersion`
- 第63行：解构中的 `runAIDetection`
- 第377-388行：`<AIDetectionComparison>` 组件及其所有 props

### 3. 从 useAudioProcessor.ts 完全移除 AI 检测

**文件: `/workspace/src/hooks/useAudioProcessor.ts`**

移除以下状态变量（L161-164, L172-173）：
- `originalAIDetection` / `setOriginalAIDetection`
- `backendAIDetection` / `setBackendAIDetection`
- `originalDetectTime` / `setOriginalDetectTime`
- `repairedDetectTime` / `setRepairedDetectTime`
- `detectorVersion` / `setDetectorVersion`
- `availableDetectors` / `setAvailableDetectors`

移除 import（L3）：
- `import { AISongDetectionResult } from '../utils/aiSongChecker';`

移除 import 中的检测相关（L26-28）：
- `fetchDetectorVersions`
- `DetectorVersion`

移除 useEffect 中的 fetchDetectorVersions 调用（L327-330）

移除 saveSettings 中的 detectorVersion（L350）

移除会话恢复中的检测相关（L638-649）：
- `setOriginalAIDetection` / `setBackendAIDetection`
- `setOriginalDetectTime` / `setRepairedDetectTime`

移除修复后自动检测逻辑（L1514-1526）：
- `detectAudio(taskIdRef.current, 'repaired', detectorVersion)` 调用

移除 runAIDetection 整个函数（L1580-1786）

移除 applySettings 依赖数组中的 `originalAIDetection` 和 `detectorVersion`（L1578）

移除 return 对象中的检测相关导出（L2511-2514, L2527-2529, L2546）：
- `originalAIDetection`, `backendAIDetection`, `originalDetectTime`, `repairedDetectTime`
- `detectorVersion`, `availableDetectors`, `setDetectorVersion`
- `runAIDetection`

移除所有 saveSession 调用中的 `originalDetectTime` / `repairedDetectTime` 字段

移除 pendingSessionRef 类型中的 `originalDetectTime` / `repairedDetectTime` 字段（L481-482）

移除 handleUseRepairCache 依赖数组中的 `originalDetectTime`（L2461）

### 4. 从 settingsStorage.ts 移除 detectorVersion

**文件: `/workspace/src/utils/settingsStorage.ts`**

移除：
- AppSettings 接口中的 `detectorVersion: string`（L24）
- defaultSettings 中的 `detectorVersion: 'v1.0'`（L43）
- loadSettings 中的 `detectorVersion` 恢复逻辑（L66）

注意：保留 `detectorVersion` 在 settings 中不会造成错误，但既然修复页不再需要，应清理。DetectPage 有自己的 detectorVersion 状态。

### 5. 构建验证

```bash
npm run build
bash scripts/build_android_release.sh
```

验证：
- TypeScript 编译无错误
- Vite 构建成功
- Android 打包成功

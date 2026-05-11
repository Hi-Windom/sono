# AI检测独立页面 - 剩余实施计划

## 当前状态

已完成：
- ✅ 后端：3个新API端点 (`/detect-file`, `/audio-files`, `/detect-path`)
- ✅ 前端：3个新API函数 (`detectFile`, `getAudioFiles`, `detectByPath`)
- ✅ 前端：DetectPage.tsx 双槽独立检测页面
- ✅ 前端：App.tsx 路由注册 `/detect`
- ✅ 前端：LandingPage.tsx 入口卡片

## 剩余工作

### 1. 从 RepairPage.tsx 移除 AI 检测组件

**文件**: `/workspace/src/pages/RepairPage.tsx`

需要移除的内容：
- 第6行：`import { AIDetectionComparison } from '../components/AIDetectionComparison';`
- 第377-388行：`<AIDetectionComparison>` 组件使用及其所有props

同时需要检查 `useAudioProcessor` hook 中是否有仅服务于 RepairPage AI 检测的状态/方法，如果这些状态在 DetectPage 中不再需要（DetectPage 有自己的检测逻辑），则不需要从 hook 中移除——RepairPage 可能仍需要保留这些状态用于修复流程中的检测功能。

**决策**：仅移除 RepairPage 中的 `AIDetectionComparison` 组件渲染和 import。保留 `useAudioProcessor` 中的相关状态（`originalAIDetection`, `backendAIDetection`, `detectorVersion` 等），因为修复流程本身可能仍需要检测功能作为内部步骤。

### 2. 构建验证

```bash
npm run build
bash scripts/build_android_release.sh
```

验证：
- TypeScript 编译无错误
- Vite 构建成功
- Android 打包成功

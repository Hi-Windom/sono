# 双轨上传 UI 重构计划

## 概述

重构前，`AIRepairPanel.tsx` 同时处理单轨和双轨模式，通过 props 传入 `isDualTrackMode`、`vocalParams`、`accompanimentParams` 等参数，复用预估大小、算法选择、参数滑块等 UI 组件。

当前版本把这些 props 都删了，导致需要单独的 `DualTrackPanel.tsx`（604 行），代码重复且 UI 不一致。

本计划恢复重构前的设计：**AIRepairPanel 复用于单轨和双轨**。

## 重构前 vs 当前

| 方面 | 重构前 (0fd22a6) | 当前 (ceeb210) |
|------|------------------|----------------|
| AIRepairPanel props | 包含 isDualTrackMode, vocalParams, accompanimentParams, mixRatio, onDualTrackRepair 等 | 全部删除 |
| 双轨 UI | AIRepairPanel 内部条件渲染 | 独立 DualTrackPanel.tsx (604 行) |
| 预估大小 | 复用 AIRepairPanel 的 allEstimates | DualTrackPanel 重新实现 |
| 算法选择 | 复用 AIRepairPanel 的下拉框 | DualTrackPanel 重新实现 |
| 参数滑块 | 复用 AIRepairPanel 的滑块 | DualTrackPanel 重新实现 |

## 修改方案

### 修改 1：恢复 AIRepairPanel.tsx 的双轨 props

从 `0fd22a6` 提交恢复以下 props：

```tsx
interface AIRepairPanelProps {
  // ... 现有 props ...

  // 双轨模式相关
  isDualTrackMode?: boolean;
  vocalParams?: VocalRepairParams;
  accompanimentParams?: InstrumentRepairParams;
  mixRatio?: number;
  onVocalParamChange?: (key: keyof VocalRepairParams, value: number) => void;
  onAccompanimentParamChange?: (key: keyof InstrumentRepairParams, value: number) => void;
  onMixRatioChange?: (ratio: number) => void;
  onDualTrackRepair?: () => void;
  dualTrackVocalInfo?: { sample_rate: number; channels: number; duration: number } | null;
  dualTrackAccompanimentInfo?: { sample_rate: number; channels: number; duration: number } | null;
}
```

### 修改 2：AIRepairPanel 内部条件渲染

当 `isDualTrackMode=true` 时：
- 算法下拉框只显示 v3.0/v3.0a
- 参数区显示人声参数 + 伴奏参数 + 混音比例
- 修复按钮文字改为"双轨修复"
- 预估大小使用 `dualTrackVocalInfo` 和 `dualTrackAccompanimentInfo` 计算

### 修改 3：RepairPage.tsx 传入双轨 props

```tsx
<AIRepairPanel
  // ... 现有 props ...
  isDualTrackMode={isDualTrackMode}
  vocalParams={dualTrackVocalParams}
  accompanimentParams={dualTrackAccompanimentParams}
  mixRatio={mixRatio}
  onVocalParamChange={handleVocalParamChange}
  onAccompanimentParamChange={handleAccompanimentParamChange}
  onMixRatioChange={setMixRatio}
  onDualTrackRepair={handleDualTrackRepair}
  dualTrackVocalInfo={dualTrackVocalInfo}
  dualTrackAccompanimentInfo={dualTrackAccompanimentInfo}
/>
```

### 修改 4：删除 DualTrackPanel.tsx

不再需要独立的 DualTrackPanel 组件。

### 修改 5：保留 DualTrackUploader.tsx

用于双轨模式的文件上传 UI（拖放支持）。

## 文件修改清单

| 文件 | 操作 |
|------|------|
| `src/components/AIRepairPanel.tsx` | 恢复双轨 props，添加条件渲染逻辑 |
| `src/pages/RepairPage.tsx` | 传入双轨 props，使用 DualTrackUploader |
| `src/components/DualTrackPanel.tsx` | 删除 |
| `src/store/dualTrackStore.ts` | 可选保留或删除 |
| `src/hooks/useDualTrackProcessor.ts` | 可选保留或删除 |

## 验证步骤

1. `npm run check` 类型检查
2. `npm run build` 构建验证
3. 手动测试单轨/双轨模式切换
# 修复计划：导航重构 + 流程可视化增强 + 双轨缓存修复

## 一、概述

本计划涵盖三个独立但并行的工作流：
1. **导航重构** — 移除各页面"返回首页"按钮，Header 左上角点击返回首页；改进离开二次确认
2. **流程可视化增强** — DAG 层级布局 + 动画动效
3. **双轨修复** — 预估大小、渲染缓存卡片、缓存命中完全失效

---

## 二、Issue 1：导航重构

### 当前状态

- **4 个页面**有"返回首页"按钮：RepairPage.tsx (L576-597)、DetectPage.tsx (L424-434)、ComparePage.tsx (L978-987)、TrainingUploadPage.tsx (L120-131)
- **Header.tsx**：logo+标题区域不可点击（无导航功能）
- **离开确认**：RepairPage 使用 `window.confirm` (L580)，其他页面无确认
- **SPA 导航拦截**：未使用 `useBlocker`

### 改动清单

#### 1.1 Header.tsx — 左上角可点击返回首页

**文件**：`/workspace/src/components/Header.tsx`

- 桌面端：将 logo+标题区域（L166-L181）包裹在 `<button>` 或 `<div onClick>` 中
- 移动端：将 logo+标题区域（L223-L231）同样处理
- 使用 `useNavigate()` 调用 `navigate('/')`
- 添加 `cursor-pointer` 样式和 hover 效果
- 导入：`import { useNavigate } from 'react-router-dom'`

#### 1.2 新增 LeaveConfirmModal 组件

**文件**：`/workspace/src/components/LeaveConfirmModal.tsx`

样式参考 DownloadModal.tsx（fixed inset-0、backdrop-blur、rounded-2xl 卡片）。

Props：
```typescript
interface LeaveConfirmModalProps {
  isOpen: boolean;
  onConfirm: () => void;    // 确认离开
  onCancel: () => void;     // 取消离开
  title: string;            // 标题，如"确认离开？"
  tasks: Array<{            // 当前正在进行的任务列表
    name: string;
    step?: string;
    progress?: number;
  }>;
}
```

结构：
- 顶部：图标+标题"确认离开？"
- 中间：显示当前正在进行的任务列表（任务名称、当前步骤、进度）
- 底部：两个按钮 — "取消"（主色调）和"确认离开"（红色警告）

#### 1.3 RepairPage.tsx — 移除返回按钮 + 替换确认 + useBlocker

**文件**：`/workspace/src/pages/RepairPage.tsx`

改动：
1. **删除** L576-L597 的"返回首页"按钮区块
2. **替换** L579-L584 的 `window.confirm` 逻辑
3. **添加** `useBlocker` 拦截 SPA 内导航：
   - 当 `isProcessing || isRenderLoading` 为 true 时阻止导航
   - 弹出 LeaveConfirmModal 显示当前任务详情
4. **添加** `beforeunload` 事件监听（浏览器关闭/刷新）
5. **使用** LeaveConfirmModal 组件

关键代码模式：
```typescript
import { useBlocker } from 'react-router-dom';

const blocker = useBlocker(
  ({ currentLocation, nextLocation }) =>
    (isProcessing || isRenderLoading) &&
    currentLocation.pathname !== nextLocation.pathname
);

useEffect(() => {
  if (blocker.state === 'blocked') {
    setShowLeaveConfirm(true);
  }
}, [blocker]);

// beforeunload
useEffect(() => {
  const handler = (e: BeforeUnloadEvent) => {
    if (isProcessing || isRenderLoading) {
      e.preventDefault();
    }
  };
  window.addEventListener('beforeunload', handler);
  return () => window.removeEventListener('beforeunload', handler);
}, [isProcessing, isRenderLoading]);
```

确认离开时调用 `blocker.proceed()`，取消时调用 `blocker.reset()`。

#### 1.4 DetectPage.tsx — 移除返回按钮 + 添加离开确认

**文件**：`/workspace/src/pages/DetectPage.tsx`

改动：
1. **删除** L424-L434 的"返回首页"按钮区块
2. **添加** `useBlocker` + `beforeunload` + LeaveConfirmModal
   - 检测进行中（`isAnalyzing` 状态）时触发拦截

#### 1.5 ComparePage.tsx — 移除返回按钮

**文件**：`/workspace/src/pages/ComparePage.tsx`

改动：
- **删除** L978-L987 的"返回首页"按钮区块

#### 1.6 TrainingUploadPage.tsx — 移除返回按钮

**文件**：`/workspace/src/pages/TrainingUploadPage.tsx`

改动：
- **删除** L120-L131 的"返回首页"按钮区块

---

## 三、Issue 2：流程可视化增强

### 当前状态

- 简单平铺网格布局（FlowVisualizationPage.tsx L83-L114）
- 按 layer 分组后从左到右排列，无层级结构
- 无动画/动效

### 改动清单

#### 2.1 添加 dagre 依赖

```bash
npm install dagre @types/dagre
```

dagre 用于计算 DAG 有向图的层级布局，支持拓扑排序、层级分配、正交路由。

#### 2.2 FlowVisualizationPage.tsx — 重构布局

**文件**：`/workspace/src/pages/FlowVisualizationPage.tsx`

**布局算法变更**：

替换当前平铺布局（L83-L114）为 dagre 计算布局：

1. **图构建**：
   - 从 `flowData.nodes` 和 `flowData.edges` 构建 dagre 图实例
   - 设置 `rankdir: 'TB'`（从上到下）或 `'LR'`（从左到右）
   - 设置节点间距和层级间距

2. **层级分配**：
   - 同一 layer（frontend/backend/shared）的节点在同一层级
   - 子节点（children）在父节点下方缩进排列
   - 使用 dagre 的 `setNode` 和 `setEdge` 方法

3. **正交边路由**：
   - 使用 dagre 计算的 `points` 生成正交折线路径
   - 替换当前简单的二次贝塞尔曲线（L139-L140）

4. **视觉分组**：
   - 每个 layer 用半透明背景矩形包裹
   - layer 标签显示在左上角
   - 前端层：青色系、后端层：绿色系、共享层：灰色系

**动画实现**：

1. **展开/收起动画**：
   - 每个节点添加展开/收起按钮（显示子节点数量）
   - 展开时：子节点组从 `max-height: 0` → `max-height: 500px`，`opacity: 0` → `1`
   - 收起时：反向过渡
   - 使用 CSS transition + React state 控制

2. **自动聚焦**：
   - 选中节点时，计算 SVG viewport 的平移量
   - 使用 CSS `transition: transform 0.4s ease` 平滑移动到视野中央
   - 选中节点放大 1.2x 并添加发光效果

3. **布局过渡动画**：
   - 当 filter（搜索/层级筛选）变化时，节点位置重新计算
   - 使用 `<g>` 的 `transition: transform 0.5s ease` 或 requestAnimationFrame 插值
   - 确保节点从旧位置平滑移动到新位置

**代码结构**：

```typescript
// 新增 layout 相关函数
function buildDagreGraph(nodes, edges): { nodes: LayoutNode[], edges: Edge[] }
function renderOrthogonalEdge(points): string  // 生成正交路径
function animateNodePosition(oldPos, newPos): void  // 位置过渡动画

// 修改布局计算
const layoutNodes = useMemo(() => {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: 'TB', nodesep: 30, ranksep: 80 });
  // ... 构建图
  dagre.layout(g);
  // 提取布局结果
  return layoutResult;
}, [filteredNodes]);
```

---

## 四、Issue 3：双轨修复

### 当前状态分析

代码探索确认了 4 个具体问题：

#### 问题 A：预估大小完全失效（AIRepairPanel.tsx）

**根因**：L189-L201 的两个 `useEffect` 使用 `duration` 和 `channels` props 而非 `effectiveDuration`/`effectiveChannels`。双轨模式下 `duration` prop 为 0（无单音频文件加载），导致 `fetchStorageEstimate` 使用默认值 300 秒、2 声道，与双轨实际时长无关。

**代码位置**：`/workspace/src/components/AIRepairPanel.tsx` L175-L201

```typescript
// 错误：使用了 props.duration 而非 effectiveDuration
const fetchDuration = duration > 0 ? duration : 300;
const fetchChannels = channels > 0 ? channels : 2;
```

#### 问题 B：渲染缓存卡片不显示双轨缓存（AIRepairPanel.tsx）

**根因**：
1. `refreshRenderCache`（L204-L211）使用 `taskId` prop，双轨模式下 `taskId={isDualTrackMode ? dualTrackTaskId : taskId}` 在 RepairPage 传参正确（L822），但后端 `/render-cache/{task_id}` 返回的条目包含 `track_type` 字段（"vocal"/"accompaniment"/"both"）
2. 缓存匹配逻辑（L601）不区分 `track_type`，可能匹配到 vocal-only 条目
3. 双轨模式下 `allEstimates` 可能为空（因为问题 A），导致缓存卡片直接显示占位符（L635-L648）

#### 问题 C：缓存命中完全不会触发（useAudioProcessor.ts）

**根因**：`applySettings` 的缓存查找（L1100-L1135）使用 `fileHashRef.current`，双轨模式下 `fileHash` 为空。双轨修复直接调用 `handleDualTrackRepair` → `repairDualAudio()`，完全不经过 `applySettings` 的缓存查找路径。

**代码位置**：
- `/workspace/src/hooks/useAudioProcessor.ts` L1100-L1135
- `/workspace/src/pages/RepairPage.tsx` L347-L404（handleDualTrackRepair）

#### 问题 D：双轨渲染后缓存未刷新

**根因**：`handleDualTrackRepair` 完成后（L162-L181），在 `onComplete` 中调用 `renderAndDownload()`，但 `renderAndDownload` 内部的渲染缓存检查（L1804）可能在渲染尚未写入文件系统时执行，导致缓存检查失败。同时 `setCacheTriggerKey(k => k + 1)`（L181）在 `renderAndDownload` 之后执行，但 `renderAndDownload` 本身会设置 `setAutoRenderInfo` 等状态，时序上有问题。

### 改动清单

#### 3.1 修复预估大小（AIRepairPanel.tsx）

**文件**：`/workspace/src/components/AIRepairPanel.tsx`

**改动**：
1. 将 L180-L181 和 L194-L195 中的 `duration`/`channels` 改为 `effectiveDuration`/`effectiveChannels`
2. 更新依赖数组为 `[effectiveDuration, effectiveChannels, ...]`

```typescript
// 修改前
const fetchDuration = duration > 0 ? duration : 300;
const fetchChannels = channels > 0 ? channels : 2;

// 修改后
const fetchDuration = effectiveDuration > 0 ? effectiveDuration : 300;
const fetchChannels = effectiveChannels > 0 ? effectiveChannels : 2;
```

同时更新 useEffect 的依赖数组。

#### 3.2 修复渲染缓存卡片（AIRepairPanel.tsx）

**文件**：`/workspace/src/components/AIRepairPanel.tsx`

**改动**：
1. **缓存匹配过滤**（L601）：在匹配时优先选择 `track_type === "both"` 或 `is_merged === true` 的条目；如果没有 merged 条目，才选择其他 track_type

```typescript
// 修改匹配逻辑
const renderCachesForSrBd = renderCaches.filter(
  c => c.sample_rate === est.sampleRate && 
      c.bit_depth === est.bitDepth && 
      c.algorithm_version === algorithmVersion
);
// 优先选 merged/both 条目
const renderCache = renderCachesForSrBd.find(c => c.is_merged || c.track_type === 'both') 
  || renderCachesForSrBd[0];
```

2. **缓存卡片显示**：在缓存详情弹窗（L656-L689）中，增加 `track_type` 和 `is_merged` 的显示

3. **确保 dualTrackTaskId 传入**：确认 `taskId={isDualTrackMode ? dualTrackTaskId : taskId}` 在双轨修复完成后能正确更新

#### 3.3 修复缓存命中（useAudioProcessor.ts + RepairPage.tsx）

**文件**：`/workspace/src/hooks/useAudioProcessor.ts`、`/workspace/src/pages/RepairPage.tsx`

**改动**：

1. **新增双轨缓存查找函数**：

在 `backendApi.ts` 中添加：
```typescript
export async function lookupDualRepairCache(
  vocalFileHash: string,
  accompanimentFileHash: string,
  params: Record<string, unknown>
): Promise<RepairCacheLookupResult> {
  const res = await fetch(`${API_BASE}/cache/lookup-dual`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ vocal_file_hash: vocalFileHash, accompaniment_file_hash: accompanimentFileHash, params }),
  });
  if (!res.ok) return { found: false };
  return res.json();
}
```

2. **后端新增 `/cache/lookup-dual` 端点**（`routes.py`）：

```python
@router.post("/cache/lookup-dual")
async def lookup_dual_repair_cache(req: DualRepairCacheLookupRequest):
    # 使用 vocal_file_hash + accompaniment_file_hash 的组合作为复合键查询
    cached = find_dual_repair_cache(req.vocal_file_hash, req.accompaniment_file_hash, req.params)
    if not cached:
        return {"found": False}
    # ... 同单轨缓存返回格式
```

3. **修改 `handleDualTrackRepair`**（RepairPage.tsx L347）：

在 `handleDualTrackRepair` 开始时添加缓存检查：
```typescript
// 在 repair 之前检查缓存
if (dualTrackVocalFileHash && dualTrackAccompanimentFileHash) {
  try {
    const cacheResult = await lookupDualRepairCache(
      dualTrackVocalFileHash,
      dualTrackAccompanimentFileHash,
      mapParamsToBackend(params, processingOptions, algorithmVersion)
    );
    if (cacheResult.found) {
      // 显示缓存命中弹窗（复用 RepairCacheModal 或新建双轨版本）
      setDualTrackCacheHitInfo(cacheResult);
      setShowDualTrackCacheModal(true);
      return;
    }
  } catch (e) {
    // 缓存查询失败，继续正常修复
  }
}
// 继续正常修复流程...
```

4. **缓存命中后的处理**：
   - 使用已有的 RepairCacheModal 或扩展支持双轨
   - "使用已有结果" → 设置 dualTrackTaskId 等状态，跳转到渲染步骤
   - "重新修复" → 继续正常 repair 流程

#### 3.4 修复双轨渲染后缓存刷新时序（RepairPage.tsx）

**文件**：`/workspace/src/pages/RepairPage.tsx`

**改动**：
1. 在 `onComplete` 回调（L162-L181）中，确保 `renderAndDownload` 完成后立即刷新 render cache
2. 将 `setCacheTriggerKey` 移动到 `renderAndDownload` 的 `.then()` 内，确保渲染完成后才触发刷新
3. 增加 `forceRenderRef.current = true` 强制渲染（缓存刚生成可能还不可用）

```typescript
onComplete: async (status) => {
  setIsProcessing(false);
  sessionActions.setDualTrackProcessed(true);
  setDualTrackRepairResult(status);
  const downloadUrl = getDownloadUrl(taskId);
  setDualTrackDownloadUrl(downloadUrl);
  setTaskId(taskId);
  // ... 加载音频 ...
  try {
    const result = await renderAndDownload(undefined, true); // force render
    setCacheTriggerKey(k => k + 1); // 渲染完成后刷新缓存卡片
  } catch (e) {
    console.error('双轨渲染交付失败:', e);
    setCacheTriggerKey(k => k + 1); // 即使失败也尝试刷新
  }
}
```

---

## 五、验证步骤

### 5.1 导航重构验证
1. 各页面不再显示"返回首页"按钮
2. Header 左上角 logo/标题点击后导航到首页
3. 修复页面有任务时，点击其他页面链接弹出 LeaveConfirmModal
4. LeaveConfirmModal 显示当前正在进行的任务信息
5. 取消不离开，确认才离开
6. 浏览器刷新/关闭时触发 beforeunload

### 5.2 流程可视化验证
1. 页面加载后节点按 DAG 层级排列，结构清晰
2. 不同 layer 有视觉分组背景
3. 展开/收起子节点动画流畅
4. 选中节点自动聚焦到视野中央
5. 筛选/搜索时节点位置平滑过渡
6. 无性能问题（213 节点、254 边）

### 5.3 双轨修复验证
1. 双轨模式预估大小显示正确的时长和声道数
2. 渲染缓存卡片显示双轨的合并缓存条目
3. 缓存命中：重复上传相同双轨文件时弹出缓存命中弹窗
4. 缓存命中后"使用已有结果"能正常渲染和下载
5. 双轨修复完成后缓存卡片自动刷新
6. 单轨模式不受影响

---

## 六、文件变更汇总

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/components/Header.tsx` | 修改 | 左上角可点击返回首页 |
| `src/components/LeaveConfirmModal.tsx` | **新建** | 离开确认模态弹窗 |
| `src/pages/RepairPage.tsx` | 修改 | 移除返回按钮 + useBlocker + 双轨缓存命中 |
| `src/pages/DetectPage.tsx` | 修改 | 移除返回按钮 + 添加离开确认 |
| `src/pages/ComparePage.tsx` | 修改 | 移除返回按钮 |
| `src/pages/TrainingUploadPage.tsx` | 修改 | 移除返回按钮 |
| `src/pages/FlowVisualizationPage.tsx` | 修改 | DAG 布局 + 动画 |
| `src/components/AIRepairPanel.tsx` | 修改 | 修复预估大小 + 渲染缓存匹配 |
| `src/hooks/useAudioProcessor.ts` | 修改 | 修复双轨缓存命中 + 渲染时序 |
| `src/services/backendApi.ts` | 修改 | 新增双轨缓存查找 API |
| `backend/api/routes.py` | 修改 | 新增 `/cache/lookup-dual` 端点 |
| `package.json` | 修改 | 添加 dagre 依赖 |

---

## 七、执行顺序

1. **Issue 1（导航重构）**：独立，可先做
2. **Issue 3（双轨修复）**：独立，可并行
3. **Issue 2（流程可视化）**：独立，可并行

建议按 1 → 3 → 2 顺序或全部并行执行。
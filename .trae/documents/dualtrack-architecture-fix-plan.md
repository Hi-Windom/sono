# 双轨架构重构计划

## 概述

双轨模式当前与单轨模式深度耦合：共享 `useAudioProcessor` hook、共用 `AIRepairPanel` 组件、依赖单轨 `taskId`/`duration`/`audioFile` 等状态。这种耦合导致预估大小、缓存卡片、缓存命中等功能全部失效。

本次重构的目标：**从顶层设计，与单轨完全解耦，拥有完善的控制机制与扩展能力，以及精细可靠的自动化测试。**

---

## 顶层架构设计

```
┌─────────────────────────────────────────────────────────────────────┐
│                         RepairPage                                  │
│  ┌─────────────────────┐          ┌──────────────────────────────┐  │
│  │  AudioUploadSection  │          │   DualTrackPanel (NEW)       │  │
│  │  (单轨)              │          │                               │  │
│  └─────────────────────┘          │  ┌─────────────────────────┐  │  │
│                                    │  │ DualTrackUploadZone     │  │  │
│  ┌─────────────────────┐          │  └─────────────────────────┘  │  │
│  │  AIRepairPanel       │          │  ┌─────────────────────────┐  │  │
│  │  (单轨, 简化)        │          │  │ DualTrackParamPanel     │  │  │
│  └─────────────────────┘          │  └─────────────────────────┘  │  │
│                                    │  ┌─────────────────────────┐  │  │
│                                    │  │ DualTrackCachePanel     │  │  │
│  ┌─────────────────────┐          │  └─────────────────────────┘  │  │
│  │ DualTrackStore       │◄────────►│  ┌─────────────────────────┐  │  │
│  │ (Zustand, NEW)       │          │  │ DualTrackProgressPanel  │  │  │
│  └─────────────────────┘          │  └─────────────────────────┘  │  │
│                                    └──────────────────────────────┘  │
│  ┌─────────────────────┐                                            │
│  │ useDualTrackProcessor│──→ backendApi (双轨专用方法) ──→ Backend  │
│  │ (NEW)               │                                            │
│  └─────────────────────┘                                            │
└─────────────────────────────────────────────────────────────────────┘
```

### 核心原则

1. **完全独立的数据流**：双轨不引用任何单轨状态（`audioFile`、`taskId`、`duration` 等）
2. **显式的状态机**：每个阶段都有明确的状态转换，无隐式依赖
3. **组件级隔离**：双轨 UI 使用独立组件，不与单轨共享渲染逻辑
4. **可扩展性**：新增算法版本、输出格式、处理步骤时不需修改现有代码
5. **可测试性**：每一层都可以独立测试

---

## 详细设计

### 1. DualTrackStore — 独立状态管理层

**新增文件：** `src/store/dualTrackStore.ts`

```typescript
interface DualTrackState {
  // 上传状态
  uploadStatus: 'idle' | 'uploading' | 'done' | 'error'
  vocalFile: File | null
  accompanimentFile: File | null
  vocalFileName: string
  accompanimentFileName: string
  vocalFileHash: string
  accompanimentFileHash: string
  
  // 任务 ID
  mainTaskId: string | null
  vocalTaskId: string | null
  accompanimentTaskId: string | null
  
  // 音频信息（用于预估大小）
  vocalInfo: AudioInfo | null
  accompanimentInfo: AudioInfo | null
  
  // 修复状态
  repairStatus: 'idle' | 'repairing' | 'done' | 'error' | 'cached'
  repairProgress: number
  repairStep: string
  repairError: string | null
  repairResult: any | null
  
  // 渲染状态
  renderStatus: 'idle' | 'rendering' | 'done' | 'error'
  renderProgress: number
  renderStep: string
  renderError: string | null
  renderCaches: RenderCacheEntry[]
  
  // 缓存状态
  cacheHit: DualRepairCacheLookupResult | null
  showCacheModal: boolean
  
  // Actions
  setUpload: (files: { vocal: File; accompaniment: File }) => void
  setUploadResult: (result: DualUploadResponse) => void
  setUploadError: (error: string) => void
  setRepairStatus: (status: DualTrackState['repairStatus']) => void
  setRepairProgress: (progress: number, step: string) => void
  setRenderCaches: (caches: RenderCacheEntry[]) => void
  reset: () => void
}
```

**关键设计决策：**
- 使用 Zustand（与现有状态管理一致）
- **不持久化**到 localStorage（修复 session 是短暂的）
- 所有状态通过显式 action 修改，没有隐式副作用
- 每个状态字段都有明确的初始值

### 2. useDualTrackProcessor — 独立处理 Hook

**新增文件：** `src/hooks/useDualTrackProcessor.ts`

```typescript
interface DualTrackProcessor {
  // 上传
  upload: (vocalFile: File, accompanimentFile: File) => Promise<void>
  
  // 缓存检查
  checkCache: () => Promise<DualRepairCacheLookupResult | null>
  
  // 修复
  repair: (params: RepairParams) => Promise<void>
  
  // 使用缓存
  useRepairCache: (cachedTaskId: string) => Promise<void>
  
  // 渲染
  render: (options: ProcessingOptions) => Promise<RenderResult | null>
  
  // 缓存刷新
  refreshRenderCache: () => Promise<void>
  
  // 重置
  reset: () => void
  
  // 状态
  state: DualTrackState
}
```

**内部实现：**
- 使用 `useRef` 存储 WebSocket 控制对象
- 使用 `useCallback` 提供稳定的方法引用
- 每个方法都有完整的 try/catch 错误处理
- 状态转换通过 store actions 完成

**关键设计决策：**
- **不再使用 `useAudioProcessor` 的 `renderAndDownload`**，而是使用独立的双轨渲染方法
- **不再依赖 `taskIdRef`**，而是直接从 store 获取 `mainTaskId`
- **不再依赖 `audioFile`**，而是使用 store 中的文件信息

### 3. DualTrackPanel — 独立 UI 组件

**新增文件：** `src/components/DualTrackPanel.tsx`

包含以下子组件：

```
DualTrackPanel
├── DualTrackUploadZone        # 文件上传区（拖拽/选择）
├── DualTrackFileInfo          # 文件信息展示（文件名、大小、时长）
├── DualTrackParamPanel        # 双轨参数面板（人声/伴奏参数 + 混音比）
├── DualTrackEstimateGrid      # 预估大小表格（完全自包含，不依赖单轨 state）
├── DualTrackCachePanel        # 渲染缓存卡片（独立获取和展示）
├── DualTrackProgressPanel     # 处理进度展示
├── DualTrackRepairButton      # 修复按钮
└── DualTrackRepairCacheModal  # 缓存命中弹窗
```

**关键设计决策：**
- 预估大小、缓存卡片、进度展示都在 DualTrackPanel 内部完成
- 不再依赖 `AIRepairPanel` 的共享逻辑
- 每个子组件只接收必要的 props，从 store 读取状态

### 4. 后端改进

#### 4.1 上传端点添加 `processing_mode='dual'`

**文件：** `backend/api/routes.py`

```python
create_task(main_task_id, ..., {
    "processing_mode": "dual",  # ← 添加
    "vocal_task_id": vocal_task_id,
    ...
})
```

#### 4.2 完善缓存查找

**文件：** `backend/database.py`

`find_dual_repair_cache` 需要：
- 查询 params 字段中包含 `processing_mode='dual'` 的任务
- 同时匹配 `vocal_file_hash` 和 `accompaniment_file_hash`
- 返回最新完成的修复任务
- 支持按算法版本过滤

### 5. 与单轨的解耦策略

| 当前耦合点 | 重构后方案 |
|-----------|-----------|
| `renderAndDownload` from `useAudioProcessor` | 独立的 `dualTrackRender` 方法 |
| `taskId`/`taskIdRef` from `useAudioProcessor` | Store 中的 `mainTaskId` |
| `audioFile` from `useAudioProcessor` | Store 中的 `vocalFile`/`accompanimentFile` |
| `duration`/`channels` from `useAudioProcessor` | Store 中的 `vocalInfo.duration`/`accompanimentInfo.duration` |
| `setCacheTriggerKey` → `AIRepairPanel` 刷新 | 独立的 `DualTrackCachePanel` 自动刷新 |
| `AIRepairPanel` 共享预估/缓存逻辑 | `DualTrackEstimateGrid` + `DualTrackCachePanel` 独立实现 |
| `RepairPage` 中的双轨状态变量 | `DualTrackStore` 统一管理 |

---

## 实现步骤

### Step 1: 创建 `DualTrackStore`

**文件：** `src/store/dualTrackStore.ts`

- 定义完整的 state 接口
- 实现所有 actions
- 确保与 `repairSessionStore` 不冲突

### Step 2: 创建 `useDualTrackProcessor` hook

**文件：** `src/hooks/useDualTrackProcessor.ts`

- 实现上传方法（包装 `uploadDualAudio`）
- 实现缓存检查方法（包装 `lookupDualRepairCache`）
- 实现修复方法（包装 `repairDualAudio`/`repairDualFromHash` + WS 监听）
- 实现渲染方法（独立实现，不依赖 `useAudioProcessor`）
- 实现缓存刷新方法（包装 `fetchRenderCache`）
- 完整的错误处理和状态转换

### Step 3: 创建双轨 UI 组件

**文件：** `src/components/DualTrackPanel.tsx`

- 上传区域组件
- 文件信息展示
- 参数面板
- 预估大小表格（独立计算 `effectiveDuration`）
- 缓存卡片（独立获取和展示）
- 进度展示
- 缓存弹窗

### Step 4: 集成到 RepairPage

**文件：** `src/pages/RepairPage.tsx`

- 引入 `DualTrackPanel` 组件
- 移除原有的双轨状态变量（`dualTrackTaskId`、`dualTrackVocalInfo` 等）
- 移除原有的双轨处理方法（`handleDualTrackUpload`、`handleDualTrackRepair` 等）
- 移除 `startDualTrackPolling`、`stopDualTrackPolling` 等
- 移除 `cacheTriggerKey` 相关的双轨逻辑
- 简化 `AIRepairPanel`（只保留单轨功能）

### Step 5: 后端修复

**文件：** `backend/api/routes.py`, `backend/database.py`

- 上传端点添加 `processing_mode='dual'`
- 完善 `find_dual_repair_cache`

### Step 6: 自动化测试

**新增文件：** `src/__tests__/dualTrackStore.test.ts`、`src/__tests__/useDualTrackProcessor.test.ts`、`backend/tests/test_dual_track.py`

#### 前端测试

```
dualTrackStore.test.ts:
  ✓ upload status transitions
  ✓ repair status transitions
  ✓ render status transitions
  ✓ cache hit flow
  ✓ error handling
  ✓ reset clears all state

useDualTrackProcessor.test.ts:
  ✓ upload calls backendApi and updates store
  ✓ repair starts WS polling
  ✓ repair complete triggers render
  ✓ render complete refreshes cache
  ✓ cache hit returns cached task
  ✓ error during repair sets error state
```

#### 后端测试

```
test_dual_track.py:
  ✓ /upload-dual creates main task with processing_mode='dual'
  ✓ /repair-dual starts repair with correct params
  ✓ /render detects dual-track mode
  ✓ _run_render_dual produces merged + vocal + accompaniment files
  ✓ /cache/lookup-dual finds cached repair
  ✓ render cache endpoint returns files for dual task
```

---

## 涉及文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/store/dualTrackStore.ts` | **新增** | 双轨状态管理层 |
| `src/hooks/useDualTrackProcessor.ts` | **新增** | 双轨处理逻辑 hook |
| `src/components/DualTrackPanel.tsx` | **新增** | 双轨 UI 主组件 |
| `src/pages/RepairPage.tsx` | 修改 | 集成 DualTrackPanel，移除双轨状态/方法 |
| `src/components/AIRepairPanel.tsx` | 修改 | 移除双轨相关 props 和逻辑 |
| `backend/api/routes.py` | 修改 | 上传端点添加 processing_mode |
| `backend/database.py` | 修改 | 完善缓存查找 |
| `src/__tests__/dualTrackStore.test.ts` | **新增** | Store 单元测试 |
| `src/__tests__/useDualTrackProcessor.test.ts` | **新增** | Hook 单元测试 |
| `backend/tests/test_dual_track.py` | **新增** | 后端集成测试 |

---

## 验证标准

1. **上传后**：预估大小表格显示正确的数值（非 "—"）
2. **修复+渲染后**：预估大小表格中对应组合显示绿色圆点（缓存可用）
3. **再次上传相同文件**：缓存命中弹窗提示
4. **缓存命中后使用缓存**：直接渲染完成，无需重新修复
5. **错误处理**：任何阶段失败都有明确的错误提示
6. **所有测试通过**：`npm test` 和 `pytest` 均通过

---

## 未完成事项

- 本次重构**不涉及**双轨模式下的音频播放/波形展示
- 本次重构**不涉及**双轨交付文件的批量下载管理
- 本次重构**不涉及**双轨模式下的实时预览（"先听再修"）
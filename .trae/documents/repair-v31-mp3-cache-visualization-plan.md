# 实施计划：MP3交付 + 缓存刷新修复 + 流程可视化页面

## 概述

本计划涵盖三项独立但有关联的特性开发：

| 特性 | 优先级 | 独立性 |
|------|--------|--------|
| 128k MP3 交付格式 | P1 | 独立，前后端少量修改 |
| 多轨缓存即时刷新 | P1 | 后端 WebSocket + 前端监听 |
| 流程可视化页面 | P2 | 独立新页面，构建时脚本 |

---

## 1. 128k MP3 交付格式

### 当前状态
- 渲染只输出 WAV（`render_output` 仅用 `soundfile.write` 写 WAV）
- 下载只提供 WAV（`/api/v1/download-file/{filename}` 返回 `audio/wav`）

### 改动方案

#### 1.1 新增 npm 依赖
```bash
npm install lamejs
```

#### 1.2 新建 `src/workers/mp3EncoderWorker.ts`
- 接收主线程消息：`{ type: 'encode', audioData: Float32Array, sampleRate: number, bitRate: 128 }`
- 用 `lamejs` 将 PCM Float32Array 编码为 MP3（128kbps）
- 返回 MP3 Blob 给主线程

#### 1.3 新增 `src/utils/mp3Encoder.ts`
- 封装 Worker 通信的 Promise 接口
- `encodeMp3(audioData: Float32Array, sampleRate: number): Promise<Blob>`

#### 1.4 修改 `src/hooks/useAudioProcessor.ts`
- 新增 `downloadAsMp3()` 方法
  - 从已下载的 WAV 数据或通过 `fetch('/api/v1/download-file/{filename}')` 获取 PCM
  - 送到 Worker 编码为 MP3
  - 触发 Blob 下载（`.mp3` 后缀）
- 返回 `{ downloadUrl, fileName, renderInfo }` 中增加 `mp3Download` 可选属性

#### 1.5 修改 `src/components/DownloadModal.tsx` 或渲染完成 UI
- 在现有「下载 WAV」按钮旁新增「下载 MP3 (128k)」按钮
- 点击后调用 `downloadAsMp3()`
- 编码过程中显示进度提示

#### 1.6 修改 `vite.config.ts`（如需要）
- 确保 worker 文件能被正确构建

### 不涉及修改
- 后端无需修改（MP3 完全由前端编码）
- 不改变现有 WAV 下载流程

---

## 2. 多轨缓存即时刷新（WebSocket 推送）

### 当前状态
- `fetchRenderCache(taskId)` 在渲染完成后被调用，但缓存列表不自动更新
- `CacheManagerPage` 的「交付渲染」Tab 仅在页面加载时拉取一次
- 后端无「缓存变更」的主动推送机制

### 改动方案

#### 2.1 后端 — 新增 WS 事件 `render_cache_updated`
**修改** `backend/services/ws_manager.py`
- 新增 `broadcast_render_cache_update(task_id: str, filename: str, sample_rate: int, bit_depth: int)` 方法
- 发送 WS 消息格式：
```json
{
  "type": "render_cache_updated",
  "task_id": "...",
  "files": [
    {"filename": "...", "sample_rate": 48000, "bit_depth": 24, "track_type": "both"},
    {"filename": "...", "sample_rate": 48000, "bit_depth": 24, "track_type": "vocal"},
    {"filename": "...", "sample_rate": 48000, "bit_depth": 24, "track_type": "accompaniment"}
  ]
}
```

**修改** `backend/api/routes.py`
- 在 `_run_render` 函数末尾，渲染成功后调用 `ws_manager.broadcast_render_cache_update()`
- 在 `_run_render_dual` 函数末尾，三个文件都渲染完后调用广播

#### 2.2 前端 — 监听 WS `render_cache_updated` 事件
**修改** `src/services/backendApi.ts`
- 在 `connectProgressWS` 或新增 `connectCacheWS` 中增加对 `render_cache_updated` 事件的解析
- 导出 `CacheUpdateEvent` 类型

**修改** `src/hooks/useAudioProcessor.ts`
- 在 `renderAndDownload` 成功后，连接 WS 并注册 `render_cache_updated` 监听
- 收到事件后自动刷新缓存列表（重新调用 `fetchRenderCache`）

**修改** `src/pages/CacheManagerPage.tsx`
- 页面挂载时连接 WS 并注册 `render_cache_updated` 监听
- 收到事件后自动调用 `fetchDeliveryFiles()` 刷新「交付渲染」列表
- 组件卸载时断开 WS 连接

#### 2.3 补充测试
**修改** `backend/tests/test_dual_track_api.py`
- 新增测试：渲染完成后验证 WS 事件是否正确广播
- 新增测试：双轨模式三个文件是否都被广播

---

## 3. 流程可视化页面

### 当前状态
- 无相关页面或基础设施
- 路由在 `src/App.tsx` 中定义

### 改动方案

#### 3.1 构建时预分析脚本 `scripts/analyze-flow.mjs`
新建 Node.js 脚本，在 `npm run build` 之前运行：

**分析目标**（解析源码获取结构信息）：

| 分析范围 | 分析内容 | 输出数据 |
|----------|----------|----------|
| 前端组件树 | 解析 `src/pages/*.tsx`、`src/components/*.tsx` 的 import 图 | 组件层级、父子关系 |
| 前端 Hook 调用链 | 解析 `src/hooks/*.ts` 调用了哪些 service API | hook → API 映射 |
| 后端路由 | 解析 `backend/api/routes.py` 的 `@router` 装饰器 | 路由列表、方法、参数 |
| 后端任务管线 | 解析 `backend/services/task_manager.py` 的任务生命周期 | 状态机（submit → run → complete/error） |
| 算法版本 | 解析 `backend/services/audio_repair.py` 的 ALGORITHM_VERSIONS | 版本列表、依赖模块 |
| 修复管线 | 解析各 `repair_v*/core.py` 的 `repair_audio` 函数调用链 | 处理步骤序列 |

**输出**：`public/flow-data.json`

**集成到构建流程**：
修改 `package.json` 的 `build` 脚本：
```json
"build": "node scripts/analyze-flow.mjs && vite build"
```

#### 3.2 前端 — `FlowVisualizationPage`
**新建** `src/pages/FlowVisualizationPage.tsx`

布局：
- 顶部：标题 + 说明
- 主区域：交互式力导向图或分层流程图

交互功能：
- **缩放/平移**：鼠标滚轮缩放，拖拽平移
- **节点点击**：点击组件/模块节点 → 右侧面板显示详情（文件路径、函数列表、imports）
- **路径高亮**：点击某个流程（如「渲染」）→ 高亮该路径上的所有节点和边
- **分层展开**：系统层（Frontend/Backend/Shared）→ 展开到组件层 → 展开到函数层
- **搜索**：搜索框，实时过滤节点

可视化技术：
- 使用 `d3-force` 力导向布局或 `dagre` 分层布局
- SVG 渲染，支持 hover 高亮
- 节点颜色按层级区分（前端蓝/后端绿/共享灰）

#### 3.3 新增路由
**修改** `src/App.tsx`
- 新增路由 `/flow` → `FlowVisualizationPage`
- 在导航栏或菜单中添加入口链接

#### 3.4 类型定义
**新建** `src/types/flow.ts`
```typescript
export interface FlowNode {
  id: string;
  label: string;
  type: 'page' | 'component' | 'hook' | 'service' | 'api' | 'module' | 'function';
  layer: 'frontend' | 'backend' | 'shared';
  filePath: string;
  description?: string;
  children?: string[];  // child node IDs
}

export interface FlowEdge {
  source: string;
  target: string;
  label?: string;
  type: 'import' | 'call' | 'data-flow' | 'renders';
}

export interface FlowData {
  nodes: FlowNode[];
  edges: FlowEdge[];
}
```

#### 3.5 不涉及修改
- 后端无需为此特性做任何修改
- 不影响现有页面功能

---

## 任务依赖关系

```
Task A (MP3 Worker + Utils) ── 独立
Task B (MP3 Download UI) ──── 依赖 Task A
Task C (WS 后端推送) ──────── 独立
Task D (前端 WS 监听 + 刷新) ─ 依赖 Task C
Task E (分析脚本) ──────────── 独立
Task F (FlowVisualizationPage) ─ 依赖 Task E
Task G (路由 + 导航入口) ───── 依赖 Task F
```

可并行：Task A、Task C、Task E

---

## 验证清单

### MP3 交付
- [ ] `lamejs` 安装成功，Worker 构建正常
- [ ] MP3 编码 Worker 能正确将 PCM 转为 128kbps MP3
- [ ] 下载按钮出现，点击后生成 `.mp3` 文件
- [ ] 生成的 MP3 可正常播放，码率 ~128kbps

### 缓存刷新
- [ ] 渲染完成后 WS 推送 `render_cache_updated` 事件
- [ ] 前端收到事件后自动刷新缓存列表
- [ ] CacheManagerPage 交付渲染 Tab 自动更新
- [ ] 双轨模式三个文件均被推送
- [ ] WS 断开后自动重连

### 流程可视化
- [ ] `scripts/analyze-flow.mjs` 能正确解析源码结构
- [ ] 构建产物中包含 `flow-data.json`
- [ ] `/flow` 页面可访问，加载 flow-data.json 正常
- [ ] 力导向图/分层图正确渲染
- [ ] 节点点击显示详情面板
- [ ] 路径高亮功能正常工作
- [ ] 搜索过滤功能正常工作

### 通用
- [ ] 打包 `release_android.tar.gz` 成功
- [ ] dev 环境启动正常，预览可访问

---

## 关键决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| MP3 编码位置 | 前端 Web Worker | 用户选择，不增加后端依赖 |
| 缓存刷新方式 | WebSocket 推送 | 用户选择，比轮询更高效实时 |
| 可视化数据来源 | 构建时预分析 | 用户选择，运行时解析太慢且不可靠 |
| 可视化库 | d3-force/dagre | 成熟的交互式图表库，SVG 性能好 |
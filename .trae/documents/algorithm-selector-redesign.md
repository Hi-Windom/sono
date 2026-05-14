# 算法版本选择器重构计划

## 现状分析

当前算法版本选择器是 AIRepairPanel.tsx 中的一个原生 `<select>` 下拉框（L371-403），存在以下问题：

1. **样式潦草**：原生 `<select>` 无法自定义下拉项样式，`<option>` 中只能显示纯文本
2. **信息密度低**：只显示 `{algo.label} — {algo.description}`，无法展示标签、分组等
3. **无视觉层次**：移动版/桌面版/稳定版/增强版等关键信息无法用标签区分

## 设计方案

### 新建项目级组件 `AlgorithmSelector`

创建 `src/components/AlgorithmSelector.tsx`，作为可复用的项目级组件。

#### 组件结构

```
┌─────────────────────────────────────────────────┐
│ 🏷 算法版本                              [v3.1 ▾] │  ← 触发器（显示当前选中版本）
├─────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────┐ │
│ │ v3.1 桌面增强版     [桌面] [双轨] [推荐]     │ │  ← 选中项高亮
│ │ 增强型AI人声修复+人声效果器+三种母带风格       │ │  ← 小字描述
│ ├─────────────────────────────────────────────┤ │
│ │ v3.0 桌面版         [桌面] [双轨]            │ │
│ │ 双轨处理，人声+伴奏分别优化后混音              │ │
│ ├─────────────────────────────────────────────┤ │
│ │ v2.4 桌面版         [桌面] [稳定]            │ │
│ │ HiFi优化+BPM自适应+节奏感知处理              │ │
│ ├─────────────────────────────────────────────┤ │
│ │ v2.4a 移动版        [移动] [稳定]            │ │
│ │ AI频谱修复+次谐波低频+空气质感重建            │ │
│ ├─────────────────────────────────────────────┤ │
│ │ ...更多版本...                               │ │
│ └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

#### 标签系统

基于版本名自动推断标签（无需后端改动）：

| 标签 | 条件 | 样式 |
|------|------|------|
| **移动** | name 以 `a` 结尾（v2.2a, v2.3a, v2.4a, v3.0a, v3.1a） | 绿色底色 |
| **桌面** | name 不以 `a` 结尾且 v2.2+ | 蓝色底色 |
| **稳定** | v2.4 / v2.4a | 琥珀色底色 |
| **推荐** | 列表中最新版本（reverse 后第一个） | 紫色底色 |
| **双轨** | supportsDualTrack === true | 青色底色 |

#### 交互设计

- 点击触发器展开/收起下拉面板
- 点击选项选中并关闭面板
- 点击面板外部关闭面板
- 键盘 Escape 关闭面板
- disabled 状态下禁止交互
- 选中项高亮显示
- 最大高度限制 + 滚动（版本多时）

### 数据层改动

#### 后端：`AlgorithmVersion` 类型扩展

在 `AlgorithmVersion` 接口中新增 `tags` 字段：

```typescript
export interface AlgorithmVersion {
  name: string;
  label: string;
  description: string;
  supportsDualTrack?: boolean;
  tags?: string[];  // 新增：标签列表，如 ["desktop", "stable", "dual-track"]
  defaultParams: Record<string, number>;
  paramRanges: Record<string, { min: number; max: number; step: number; label: string; }>;
  modes: { name: string; description: string; icon: string; params: Record<string, number>; }[];
}
```

#### 后端：`ALGORITHM_VERSIONS` 添加 tags

在每个版本定义中添加 `tags` 字段：

| 版本 | tags |
|------|------|
| v1.0 | `[]` |
| v1.1 | `[]` |
| v1.2 | `[]` |
| v2.0 | `["mobile"]` |
| v2.2 | `["desktop"]` |
| v2.2a | `["mobile"]` |
| v2.3 | `["desktop"]` |
| v2.3a | `["mobile"]` |
| v2.4 | `["desktop", "stable"]` |
| v2.4a | `["mobile", "stable"]` |
| v3.0 | `["desktop", "dual-track"]` |
| v3.0a | `["mobile", "dual-track"]` |
| v3.1 | `["desktop", "dual-track", "recommended"]` |
| v3.1a | `["mobile", "dual-track", "recommended"]` |

#### 后端：`get_available_versions` 传递 tags

在 `version_data` 中添加 `"tags": v.get("tags", [])`。

### 前端标签渲染

标签颜色映射：

```typescript
const TAG_CONFIG: Record<string, { label: string; className: string }> = {
  'mobile':      { label: '移动',   className: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' },
  'desktop':     { label: '桌面',   className: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
  'stable':      { label: '稳定',   className: 'bg-amber-500/20 text-amber-400 border-amber-500/30' },
  'recommended': { label: '推荐',   className: 'bg-purple-500/20 text-purple-400 border-purple-500/30' },
  'dual-track':  { label: '双轨',   className: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30' },
};
```

## 实施步骤

### Step 1: 后端 — ALGORITHM_VERSIONS 添加 tags 字段

在 `backend/services/audio_repair.py` 的每个版本定义中添加 `tags` 列表。

### Step 2: 后端 — get_available_versions 传递 tags

在 `get_available_versions()` 函数的 `version_data` 中添加 `"tags": v.get("tags", [])`。

### Step 3: 前端 — AlgorithmVersion 类型添加 tags

在 `src/services/backendApi.ts` 的 `AlgorithmVersion` 接口中添加 `tags?: string[]`。

### Step 4: 前端 — 创建 AlgorithmSelector 组件

创建 `src/components/AlgorithmSelector.tsx`，实现：
- 触发器（显示当前选中版本名 + 下拉箭头）
- 下拉面板（自定义渲染，支持标签、描述、选中高亮）
- 点击外部关闭（useRef + useEffect 监听 mousedown）
- 键盘 Escape 关闭
- disabled 状态
- 最大高度 + 滚动
- 标签渲染（TAG_CONFIG 映射）

### Step 5: 前端 — AIRepairPanel 替换选择器

将 AIRepairPanel.tsx 中的原生 `<select>` 替换为 `<AlgorithmSelector>` 组件，保持 props 接口不变。

### Step 6: 测试 + 打包

运行后端测试 + 前端构建 + Android 打包。

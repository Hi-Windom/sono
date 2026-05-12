# 修复 _ws_send_final 未定义 + 缓存逻辑 + 播放页面拆分（ComparePage）

## 摘要

解决 3 个问题并执行 1 个架构调整：
1. **后端崩溃**: `routes.py` `_ws_send_final` 未导入 → **已完成**
2. **自动下载旧缓存**: 全新修复后 `renderAndDownload` 可能命中旧 render 缓存 → **forceRenderRef 已实现，待验证构建**
3. **播放功能迁移**: 从 RepairPage 拆出独立 ComparePage，仅支持服务端缓存音频 AB 对比

---

## 当前状态分析

### 已完成 ✅

| 步骤 | 状态 | 说明 |
|------|------|------|
| Step 1: `_ws_send_final` 导入修复 | ✅ 完成 | [routes.py:359](backend/api/routes.py#L359) 已添加 `_ws_send_final` 到 import |
| Step 2: forceRenderRef 缓存绕过 | 📝 代码已写入待验证 | [useAudioProcessor.ts:231](src/hooks/useAudioProcessor.ts#L231) 声明 ref；[L2318](src/hooks/useAudioProcessor.ts#L2318) 跳过缓存查找；[L1609](src/hooks/useAudioProcessor.ts#L1609) 全新修复设 true；[L2505](src/hooks/useAudioProcessor.ts#L2505) 缓存修复设 false |

### 待完成 ⏳

| 步骤 | 状态 | 说明 |
|------|------|------|
| Step 3: 创建 ComparePage | ❌ 未开始 | 新建 `src/pages/ComparePage.tsx` |
| Step 3b: 后端原始音频预览接口 | ❌ 未开始 | 当前 `/preview/{task_id}` 只返回 repaired，需支持 original |
| Step 3c: 注册路由 | ❌ 未开始 | `App.tsx` 添加 `/compare` 路由 |
| Step 4: 简化 RepairPage | ❌ 未开始 | 移除 AudioPlayer/SpectrumVisualizer/WaveformVisualizer，添加跳转按钮 |
| Step 5: 测试+构建+打包 | ❌ 未开始 | 验证全部改动 |

---

## 实施步骤

### Step 1 ✅ — `_ws_send_final` 导入修复（已完成）

**文件**: [backend/api/routes.py:359](backend/api/routes.py#L359)
```python
from services.task_manager import _ws_send_progress, _ws_send_final
```

### Step 2 ✅ — forceRenderRef 缓存绕过（代码已写入）

**文件**: [src/hooks/useAudioProcessor.ts](src/hooks/useAudioProcessor.ts)

三处修改：
1. **L231** — 声明 `forceRenderRef = useRef(false)`
2. **L2318** — `renderAndDownload` 中：`if (!forceRenderRef.current)` 包裹缓存查找逻辑
3. **L1609** — 全新修复完成后设 `forceRenderRef.current = true` 再调 `renderAndDownload()`
4. **L2505** — 使用已有修复缓存时设 `forceRenderRef.current = false` 再调 `renderAndDownload()`

### Step 3 — 创建 ComparePage（AB对比页面）

#### 3a. 后端：扩展预览接口支持原始音频

**文件**: [backend/api/routes.py](backend/api/routes.py) — 修改 `/preview/{task_id}` 端点（当前 L982-L995）

当前端点只返回 repaired 音频。需增加 `type` 查询参数：
```python
@router.get("/preview/{task_id}")
async def preview_audio(task_id: str, type: str = 'repaired'):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if type == 'original':
        # 返回原始上传音频
        original_path = task.get("original_path") or task.get("upload_path", "")
        if not original_path or not os.path.exists(original_path):
            raise HTTPException(status_code=404, detail="原始音频不存在")
        return FileResponse(original_path, media_type="audio/wav")
    else:
        # 返回修复后音频（默认行为不变）
        output_path = task.get("output_path")
        if not output_path or not os.path.exists(output_path):
            raise HTTPException(status_code=404, detail="修复后的音频不存在")
        return FileResponse(output_path, media_type="audio/wav")
```

> 注意：任务表中字段名为 `original_path`（见 database.py L27 CREATE TABLE），存储的是 `upload_path`。

#### 3b. 前端：新建 ComparePage.tsx

**新建文件**: `src/pages/ComparePage.tsx`

**核心设计**：

```
URL 格式: /compare?taskId=xxx
数据来源: URL searchParams 获取 taskId
音频加载: 通过 /api/v1/preview/{taskId}?type=original|repaired 加载
解码方式: fetch(url) → ArrayBuffer → AudioContext.decodeAudioData → AudioBuffer
播放控制: 内部管理 AudioBuffer + currentTime + isPlaying（不依赖 useAudioProcessor）
可视化:   SpectrumVisualizer（需要 AnalyserNode，通过 AudioContext.createAnalyser 创建）
           WaveformVisualizer（直接用 AudioBuffer）
AB 切换:  两种模式: 'original' | 'repaired'
```

**组件结构**：
```
ComparePage
├── Header（复用）
├── 返回修复页按钮
├── 任务信息卡片（文件名、参数摘要）
├── AudioPlayer（简化版：play/pause + AB切换，移除 browser 模式）
├── SpectrumVisualizer（从 RepairPage 迁移模式）
├── WaveformVisualizer（从 RepairPage 迁移模式）
└── 底部操作栏（下载修复后音频等）
```

**关键实现细节**：
- 使用 `useSearchParams()` 从 URL 读取 `taskId`
- 用两个 `AudioBuffer` ref 分别缓存原始和修复后音频
- 用一个 `AnalyserNode` 连接到当前活跃的 `AudioBufferSourceNode`
- AB 切换时断开旧 source，连接新 source，更新可视化颜色/标签
- 不调用 useAudioProcessor hook，完全独立的播放逻辑

#### 3c. 路由注册

**文件**: [src/App.tsx](src/App.tsx) — L43 后添加

```tsx
import ComparePage from "@/pages/ComparePage";
// ...
<Route path="/compare" element={<ComparePage />} />
```

### Step 4 — 简化 RepairPage

**文件**: [src/pages/RepairPage.tsx](src/pages/RepairPage.tsx)

**移除内容**：
1. **import 清理**: 移除 `AudioPlayer`, `WaveformVisualizer`, `SpectrumVisualizer` 的导入（L5-L7）
2. **props 解构清理**: 移除以下 props（L22-24, L65-68, L76）:
   - `isPlaying`, `currentTime`, `duration`, `playMode`
   - `play`, `pause`, `seek`, `switchPlayMode`
   - `analyserRef`
3. **JSX 移除**: 移除 `<AudioPlayer>` (L367-378), `<SpectrumVisualizer>` (L380-388), `<WaveformVisualizer>` (L391-401)
4. **变量清理**: 移除 `activeBuffer`, `isBufferReady`, `browserBufferInfo`, `hasBrowserResult`, `hasBackendResult`（如果仅用于播放区）

**新增内容**：
- 在文件信息卡片的操作区域（替换文件按钮旁或底部），添加「前往 AB 对比」按钮：
```tsx
{taskId && hasBeenProcessed && (
  <button
    onClick={() => navigate(`/compare?taskId=${taskId}`)}
    className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-cyan-500/20 to-purple-500/20 hover:from-cyan-500/30 hover:to-purple-500/30 border border-cyan-400/30 rounded-lg text-cyan-400 text-sm transition-all"
  >
    <svg>...</svg>
    <span>前往 AB 对比</span>
  </button>
)}
```

### Step 5 — 测试 + 构建 + 打包

#### 5a. 后端测试

**文件**: [backend/tests/test_api_and_db.py](backend/tests/test_api_and_db.py)

新增测试：
- `test_preview_endpoint_supports_original_type`: 验证 `/preview/{task_id}?type=original` 返回原始音频
- `test_preview_endpoint_default_is_repaired`: 验证不带 type 参数默认返回 repaired

#### 5b. 前端构建验证

```bash
npm run build   # 确保 TypeScript 编译无错误
```

#### 5c. Android 打包

```bash
bash scripts/build_android_release.sh
```

---

## 涉及文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/api/routes.py` | **修改** | preview 端点增加 type 参数支持原始音频 |
| `src/pages/ComparePage.tsx` | **新建** | AB对比播放页面 |
| `src/App.tsx` | **修改** | 注册 /compare 路由 |
| `src/pages/RepairPage.tsx` | **修改** | 移除播放组件，添加跳转按钮 |
| `backend/tests/test_api_and_db.py` | **修改** | 新增 preview 端点测试 |

---

## 验证步骤

```bash
# 1. 后端测试
cd /workspace && python -m pytest backend/tests/test_api_and_db.py -v

# 2. 前端构建
npm run build

# 3. Android 打包
bash scripts/build_android_release.sh
```

**通过标准**: 全部测试通过，TypeScript 编译零错误，Android 打包产物生成。

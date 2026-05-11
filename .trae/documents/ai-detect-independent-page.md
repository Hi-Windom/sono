# AI检测独立页面实现计划

## Summary

将AI检测功能从修复页面中独立出来，创建新的 `/detect` 页面。支持两个独立的文件槽，每个槽都可以本地上传或选择服务端缓存音频，两个检测非阻塞并行互不影响。新增后端一步式检测API，不依赖task体系。

## Current State Analysis

### 现有架构
- **AI检测逻辑**：后端 `backend/services/ai_detector.py` + `task_manager.py::_run_detect`
- **现有API**：`POST /detect` 需要 `task_id`，通过 `task_manager` 提交异步检测，WS推送进度
- **前端组件**：`AIDetectionComparison.tsx`（对比修复前后检测结果）、`AIDetectionCard.tsx`
- **前端调用**：`backendApi.ts::detectAudio()` → `/detect` → WS等待结果 → `mapDetectionResult()` 转换
- **检测结果类型**：`AISongDetectionResult`（前端）、`BackendDetectionResult`（后端）

### 问题
- 现有 `/detect` 强依赖 `task_id`，无法直接检测上传文件
- 服务端缓存音频散布在 `uploads/`、`outputs/` 中，没有统一的文件级索引API
- 前端检测逻辑深度嵌入 `useAudioProcessor.ts`，与修复流程耦合

## Proposed Changes

### 1. 后端：新增一步式检测API

**文件**: `backend/api/routes.py`

新增 `POST /detect-file` 端点：
- 接收 `UploadFile` + `detector_version` 参数
- 生成临时 task_id，保存文件到 uploads，创建 task 记录
- 调用 `submit_detect_task()` 执行检测
- 返回 `{ task_id, status: "detecting" }`
- 前端通过现有 WS 机制等待结果

```python
@router.post("/detect-file")
async def detect_file(file: UploadFile = File(...), detector_version: str = Form("v1.1")):
    # 1. 保存上传文件，创建临时task
    # 2. submit_detect_task(task_id, audio_path, "original", detector_version)
    # 3. 返回 { task_id, status: "detecting" }
```

### 2. 后端：新增服务端音频列表API

**文件**: `backend/api/routes.py`

新增 `GET /audio-files` 端点：
- 扫描 `uploads/` 和 `outputs/` 目录
- 返回所有有效音频文件列表（去重，按修改时间倒序）
- 每个条目包含：`file_id`(路径hash)、`filename`、`path`、`size`、`type`(upload/output/render)、`modified_at`
- 不依赖task体系

```python
@router.get("/audio-files")
async def list_audio_files():
    # 扫描 uploads/ + outputs/ 目录
    # 返回 [{ file_id, filename, path, size, type, modified_at }]
```

新增 `POST /detect-path` 端点：
- 接收 `file_id`（路径hash）+ `detector_version`
- 查找文件路径，创建临时task，执行检测
- 返回 `{ task_id, status: "detecting" }`

```python
class DetectPathRequest(BaseModel):
    file_id: str
    detector_version: str = "v1.1"

@router.post("/detect-path")
async def detect_by_path(request: DetectPathRequest):
    # 1. 根据 file_id 查找文件路径
    # 2. 创建临时task
    # 3. submit_detect_task()
    # 4. 返回 { task_id, status: "detecting" }
```

### 3. 前端：新增检测页面

**文件**: `src/pages/DetectPage.tsx`（新建）

页面结构：
```
┌─────────────────────────────────────────┐
│ Header                                  │
├─────────────────────────────────────────┤
│ ┌──────────────┐  ┌──────────────┐      │
│ │  文件槽 A    │  │  文件槽 B    │      │
│ │  ┌────────┐  │  │  ┌────────┐  │      │
│ │  │上传区域│  │  │  │上传区域│  │      │
│ │  └────────┘  │  │  └────────┘  │      │
│ │  或 服务端选择│  │  或 服务端选择│      │
│ │             │  │             │      │
│ │  [检测按钮]  │  │  [检测按钮]  │      │
│ │             │  │             │      │
│ │  检测结果    │  │  检测结果    │      │
│ │  AIDetection │  │  AIDetection │      │
│ │  Card        │  │  Card        │      │
│ └──────────────┘  └──────────────┘      │
│                                         │
│  对比摘要（两个都有结果时显示）           │
└─────────────────────────────────────────┘
```

核心状态：
```typescript
interface DetectSlot {
  id: 'a' | 'b';
  source: 'none' | 'local' | 'server';
  localFile: File | null;
  serverFileId: string | null;
  serverFileName: string | null;
  taskId: string | null;       // 检测用的临时task_id
  status: 'idle' | 'uploading' | 'detecting' | 'done' | 'error';
  progress: number;
  step: string;
  result: AISongDetectionResult | null;
  error: string | null;
}
```

核心逻辑：
- 两个slot完全独立，各自维护状态
- 本地上传：`POST /detect-file` → WS等待 → 结果
- 服务端选择：`GET /audio-files` 列表 → 选择 → `POST /detect-path` → WS等待 → 结果
- 检测进度通过现有 `waitWithWS()` 机制跟踪
- 两个检测可同时进行，互不阻塞

移动端布局：
- 小屏幕：两个slot垂直堆叠
- 大屏幕：两个slot并排

### 4. 前端：新增API调用函数

**文件**: `src/services/backendApi.ts`

```typescript
// 上传文件并检测
export async function detectFile(file: File, detectorVersion: string): Promise<{ task_id: string; status: string }>

// 获取服务端音频文件列表
export async function getAudioFiles(): Promise<AudioFileInfo[]>

// 通过服务端路径检测
export async function detectByPath(fileId: string, detectorVersion: string): Promise<{ task_id: string; status: string }>
```

### 5. 前端：路由注册

**文件**: `src/App.tsx`

添加 `/detect` 路由指向 `DetectPage`

### 6. 前端：落地页入口

**文件**: `src/pages/LandingPage.tsx`

添加"AI检测分析"卡片，导航到 `/detect`

### 7. 前端：从修复页面移除AI检测

**文件**: `src/pages/RepairPage.tsx`, `src/pages/Home.tsx`

- 移除 `AIDetectionComparison` 组件的渲染
- 移除相关 props 传递（`originalAIDetection`, `backendAIDetection`, `onDetect` 等）
- 保留 `useAudioProcessor.ts` 中的检测逻辑（不删除，因为可能其他地方仍引用），但修复页面不再调用

### 8. 后端测试

**文件**: `backend/tests/test_api_and_db.py`

新增测试类 `TestDetectFileEndpoint`：
- `test_detect_file_success`：上传文件检测成功
- `test_detect_file_unsupported_format`：不支持格式返回400
- `test_detect_path_success`：服务端路径检测成功
- `test_detect_path_not_found`：无效file_id返回404
- `test_audio_files_list`：音频文件列表返回正确

## Assumptions & Decisions

1. **一步式API**：`/detect-file` 上传+检测合一，不缓存上传文件（用户需要缓存时应走修复流程）
2. **临时task**：检测用临时task_id，检测完成后task记录保留（含检测结果），不主动清理
3. **服务端音频**：通过 `/audio-files` 扫描文件系统，不依赖task数据库
4. **file_id**：使用文件路径的SHA256前16位作为唯一标识，避免暴露服务器路径
5. **WS复用**：检测进度仍通过现有WS机制跟踪，不新建WS通道
6. **检测版本**：默认使用 v1.1，页面提供版本选择下拉框
7. **对比摘要**：两个slot都有结果时，底部显示对比差异（AI概率差值）
8. **不删除useAudioProcessor中的检测逻辑**：避免大范围重构，修复页面只是不展示

## Verification Steps

1. 后端测试：`python -m pytest backend/tests/test_api_and_db.py -v` 全部通过
2. 前端构建：`npm run build` 成功
3. Android打包：`bash scripts/build_android_release.sh` 成功
4. 手动验证：
   - 访问 `/detect` 页面，两个slot独立上传文件检测
   - 选择服务端音频检测
   - 两个检测同时运行互不阻塞
   - 移动端布局正常
   - 落地页有入口卡片
   - 修复页面不再显示AI检测区域

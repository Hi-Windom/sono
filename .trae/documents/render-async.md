# Render 异步化 — 解决同步阻塞导致前后端通信中断

## 问题分析

### 当前状态
`POST /api/v1/render` 端点声明为 `async def`，但内部直接调用同步函数 `render_output()`：
```python
# routes.py L300-321
@router.post("/render")
async def render_audio_endpoint(request: RenderRequest):
    ...
    result = render_output(output_path, render_path, request.sample_rate, request.bit_depth)
    return {...}
```

### 根因
`render_output()` 是纯 CPU 密集型同步函数（上采样 + 谐波增强 + 写文件），大文件 48kHz→96kHz 渲染可能耗时 10-30 秒。在 `async def` 中直接调用同步函数会**阻塞整个 asyncio 事件循环**，导致：
1. 所有其他请求（包括 `/health`）无法被处理
2. 前端健康检查超时 → `setBackendAvailable(false)`
3. 前端显示"后端不可用"

### 对比：修复任务的正确模式
修复任务（repair）使用 `ThreadPoolExecutor` + WebSocket 进度推送：
```python
# task_manager.py
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
future = executor.submit(_run_repair, task_id, audio_path, params, MOBILE_MODE)
```
前端通过 WebSocket 接收进度，通过 `/status/{task_id}` 轮询结果。

## 修复方案

将 render 从同步阻塞改为与 repair 一致的异步模式：**提交任务 → 线程池执行 → 轮询状态**。

### 后端修改

**文件**：`/workspace/backend/api/routes.py`

将 `render_audio_endpoint` 改为：
1. 提交 render 任务到 `executor` 线程池（复用 task_manager 的 executor）
2. 立即返回 `{task_id, status: "rendering"}`
3. 渲染结果写入 task 状态，前端通过 `/status/{task_id}` 轮询获取

```python
@router.post("/render")
async def render_audio_endpoint(request: RenderRequest):
    task = get_task(request.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    output_path = task.get("output_path")
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(status_code=400, detail="修复结果不存在，请先完成修复")

    render_filename = f"{request.task_id}_rendered_{request.sample_rate}_{request.bit_depth}.wav"
    render_path = os.path.join(OUTPUT_DIR, render_filename)

    update_task(request.task_id, status="rendering", step="渲染交付规格...", progress=0)

    from services.task_manager import executor
    executor.submit(_run_render, request.task_id, output_path, render_path, request.sample_rate, request.bit_depth, render_filename)

    return {"task_id": request.task_id, "status": "rendering"}


def _run_render(task_id, input_path, output_path, target_sr, bit_depth, render_filename):
    from services.render import render_output
    from services.task_manager import update_task, _ws_send_progress

    def progress_callback(pct, step):
        update_task(task_id, progress=pct, step=step)
        _ws_send_progress(task_id, {
            "task_id": task_id,
            "status": "rendering",
            "progress": pct,
            "step": step,
        })

    try:
        result = render_output(input_path, output_path, target_sr, bit_depth, progress_callback=progress_callback)
        update_task(task_id,
            status="render_completed",
            progress=1.0,
            step="渲染完成",
            render_filename=render_filename,
            render_result=result,
        )
        _ws_send_progress(task_id, {
            "task_id": task_id,
            "status": "render_completed",
            "progress": 1.0,
            "step": "渲染完成",
            "render_filename": render_filename,
            "render_result": result,
        })
    except Exception as e:
        update_task(task_id, status="error", error=str(e), step="渲染失败")
        _ws_send_progress(task_id, {
            "task_id": task_id,
            "status": "error",
            "error": str(e),
            "step": "渲染失败",
        })
```

### 前端修改

**文件**：`/workspace/src/hooks/useAudioProcessor.ts`

将 `downloadProcessedAudio` 中的 render 调用从等待响应改为轮询状态：

1. `renderAudio()` 只返回 `{task_id, status: "rendering"}`
2. 轮询 `/api/v1/status/{task_id}` 等待 `status === "render_completed"`
3. 从 task 状态中获取 `render_filename` 和 `render_result`
4. 渲染期间健康检查不会超时（因为事件循环不被阻塞）

**文件**：`/workspace/src/services/backendApi.ts`

`renderAudio()` 返回类型改为：
```typescript
export interface RenderResult {
  task_id: string;
  status: string;
}
```

新增轮询函数：
```typescript
export async function pollRenderStatus(
  taskId: string,
  onProgress?: (progress: number, step: string) => void,
): Promise<{render_filename: string; render_result: {...}}> {
  while (true) {
    const task = await getTaskStatus(taskId);
    if (task.status === 'render_completed') {
      return { render_filename: task.render_filename, render_result: task.render_result };
    }
    if (task.status === 'error') {
      throw new Error(task.error || '渲染失败');
    }
    if (onProgress && task.progress != null) {
      onProgress(task.progress, task.step || '');
    }
    await new Promise(r => setTimeout(r, 500));
  }
}
```

### 健康检查回退

之前为了应急做的健康检查修改（15s 超时 + 连续3次失败）可以保留作为额外保护，但核心问题由 render 异步化解决后，健康检查不会再因 render 阻塞而超时。

## 验证步骤

1. `npm run build` 编译通过
2. 启动 dev 环境，加载大文件，选择 96kHz 交付，点击导出
3. 验证：导出期间前端仍显示"后端已连接"，进度正常更新
4. 验证：导出完成后 DownloadButton 显示正确的 96kHz 采样率
5. `bash scripts/build_android_release.sh` Android 打包通过

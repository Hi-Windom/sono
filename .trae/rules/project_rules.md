# Project Rules

## ⚠️ 强制性规则（每次操作前必须遵守）

1. **执行任何构建/部署/启动操作前，必须先读取本规则文件**
2. **项目已有专用脚本的，必须使用脚本，禁止手动拼凑步骤**
3. **"打包安卓" = `bash scripts/build_android_release.sh`，不是手动 npm build + cp**
4. **"重启dev" = 先停旧服务，再用 `bash scripts/start_dev.sh` 启动完整开发环境（前端+后端），不是只启动后端**
5. **遇到用户指令与已有脚本功能匹配时，直接调用脚本，不要自己拆解步骤**

## Build & Deploy Commands

### Android 打包（必须使用脚本，禁止手动执行步骤）
```bash
bash scripts/build_android_release.sh
```
此脚本自动完成：清理旧产物 → npm run build → 复制 dist 到 backend → 打包 release_android.tar.gz

**绝对禁止**手动执行 `npm run build` + `cp -r dist backend/` 来替代此脚本。

### Android 完整部署（Termux 端，含前端部署+后端重启）
```bash
bash scripts/build_android.sh
```
此脚本自动完成：清理旧产物 → npm run build → 部署前端到 backend/dist → 验证 → 重启后端

### 桌面开发环境（热重载，推荐开发时使用）
```bash
# 一键启动前后端（推荐）
bash scripts/start_dev.sh
# 访问地址: http://localhost:5173

# 或手动分别启动：
# 终端1：启动 Vite 前端开发服务器（热重载）
npm run dev
# 终端2：启动后端 API 服务（仅 API，不 serve 静态文件）
cd /workspace/backend && python main.py
```

**"重启dev"的正确流程**：
1. 停止旧服务：`pkill -f "python main.py"` + `pkill -f "vite"`
2. 启动新服务：`bash scripts/start_dev.sh`（同时启动前端和后端）
3. **必须使用 `OpenPreview` 工具激活预览**，否则外部无法访问沙箱端口
4. 或者用 `npm run dev:full`

**绝对禁止**只启动后端 `python main.py` 就当作"重启dev"。

### 预览访问规则（重要！）
沙箱环境需要特殊命令激活预览才能被外部访问：
- 启动服务后，**必须使用 `OpenPreview` 工具**激活预览
- 示例：`OpenPreview(command_id="xxx", preview_url="http://localhost:5173")`
- 不使用 `OpenPreview` 会导致端口只在容器内部可用，外部无法访问

### 桌面生产预览（使用打包后的 dist，非开发环境）
```bash
# 先构建前端，再启动后端（SERVE_STATIC=1 会 serve backend/dist）
npm run build
cp -r dist backend/dist
cd /workspace/backend && SERVE_STATIC=1 python main.py
# 访问地址: http://localhost:8000
```
**注意**：`SERVE_STATIC=1` 仅用于生产/打包验证，开发时请勿使用，应使用 `npm run dev` 获得热重载体验。

## Architecture

- Frontend: React + TypeScript + Vite → builds to `dist/`
- Backend: FastAPI (Python) in `backend/`
- Static serving: `backend/dist/` served by FastAPI when `SERVE_STATIC=1`
- Audio loading: miniaudio only (no librosa, no pydub)
- DSP functions: `backend/services/dsp_utils.py` (pure numpy+scipy, no librosa)
- Compatibility layer: `backend/services/librosa_compat.py` (re-exports dsp_utils)
- librosa is ONLY used in `backend/training/feature_extractor.py` (desktop-only training)

## Web Worker 策略

前端计算密集型任务**必须优先考虑使用 Web Worker**，避免阻塞主线程导致 UI 卡顿。

适合 Worker 的任务特征：
- 逐样本音频数据处理（解码、分析、编码）
- 大数组遍历/变换（>1M 次运算）
- 可脱离 DOM 独立完成的纯计算

不适合 Worker 的任务：
- 需要 DOM/Canvas API 的操作
- 已由 requestAnimationFrame 驱动的轻量渲染
- 异步 I/O 操作（fetch、IndexedDB）
- 计算量极低（<10ms）的任务

Worker 与缓存协同：
- 缓存命中时跳过 Worker 计算（避免不必要的通信开销）
- 缓存未命中时 Worker 异步计算，结果写回缓存
- Worker 结果不直接写缓存，由主线程负责缓存写入（Worker 无法访问 fetch/IndexedDB）

当前 Worker 使用：
- `src/workers/audioWorker.ts` — WAV PCM 解码 + 音频分析

## Memory Optimization (v2.2/v2.3/v2.3a)

Design target: **60min audio @ 4GB RAM** without quality reduction.

4-layer optimization:
1. **Corrected estimation** (`memory_guard.py`): Formula accounts for streaming STFT, algorithm-specific peak_temp, and float32 elem_size
2. **Float32 auto-conversion**: Audio >10min auto-converts to float32 (halves memory), converts back to float64 before WAV export
3. **Streaming spectral processing** (`dsp_utils.py::streaming_spectral_process`): Processes audio in 10s chunks with overlap-add, keeping STFT memory fixed at ~15MB regardless of audio length. Used by spectral_group_a/b, subband_processing, v2.3a denoise
4. **In-place operations**: All repair steps modify `y` directly instead of creating copies (peak memory 4x→1x for multiband compress)

Memory estimation is algorithm-version-aware:
- v2.2/v2.3: +50% peak_temp (full processing pipeline)
- v2.2a/v2.3a: +15% peak_temp (lightweight pipeline)
- v1.x: +30% peak_temp (moderate pipeline)

Result: 5min audio 3907MB→537MB, 60min audio ~3108MB (fits 4GB target)

## Directory Structure

```
scripts/     # 开发构建脚本（在开发机/CI 上运行）
  ├── build_android_release.sh   # PC端打包Android发布包
  └── build_android.sh           # Termux端完整构建部署

deploy/      # 运行时部署脚本（被打包进Android发布包，在用户设备上运行）
  ├── setup_android.sh           # Termux首次部署
  └── start_android.sh           # Termux启动服务
```

**关键区别**：
- `scripts/` = 开发者工具，不会进入 release_android.tar.gz
- `deploy/` = 用户脚本，会被 build_android_release.sh 复制到发布包中

## Key Files
- `backend/services/audio_loader.py` - audio loading (miniaudio only)
- `backend/services/dsp_utils.py` - all DSP functions (stft, istft, features)
- `backend/services/librosa_compat.py` - compatibility layer for dsp_utils
- `backend/main.py` - FastAPI entry point
- `backend/config.py` - configuration

## Git Commit
- git提交时禁止擅自丢弃未暂存的更改，必须得到用户二次确认
- Always commit with descriptive messages
- After code changes that affect Android, run `bash scripts/build_android_release.sh` to rebuild

## Testing
```bash
# 运行音频修复质量测试
cd /workspace && python -m pytest backend/tests/test_repair_quality.py -v

# 运行回归测试（必须每次修改相关代码后跑，防止历史bug复发）
cd /workspace && python -m pytest backend/tests/test_regression.py -v
```

### 防回归测试铁律
1. **每修一个 bug 必须补对应的回归测试**，禁止修完就完事
2. 测试文件：`backend/tests/test_regression.py`
3. 测试命名规范：`Test<Bug类别>` + 明确的测试用例，注释写明对应的历史 bug 是什么
4. **每次修改相关代码后必须跑回归测试**，不能只测新增功能
5. 回归测试覆盖范围（持续补充）：
   - 修复算法 progress/progress_callback 变量名一致性
   - HTTP 轮询模式下 error 状态正确回调
   - 打包产物不含测试/开发文件
   - 自定义 hook 返回对象引用稳定性
   - 服务器启动时清理停滞任务（pending/processing 等非终态）
   - cancel_task 发送 WebSocket 最终消息 + 清理活跃任务计数
   - WebSocket 发送异常必须打 warning 日志，禁止 bare except + pass
   - perf_collector.end_repair 必须在 finally 中调用，防止性能数据泄漏
6. 涉及 Android 的修改，提交前必须跑 `bash scripts/build_android_release.sh` 确保打包成功

## 🚨 问题排查铁律（血的教训）

### 1. 先复现再修复，严禁猜测
- **禁止**在没有复现问题、没有日志/网络请求/控制台报错等实锤证据的情况下，凭感觉修改代码
- **必须**先看真实日志（后端日志、浏览器控制台、Network面板），定位问题根因
- **禁止**用"应该是"、"可能是"、"大概率"这种推测性表述来定位问题
- 反面教材：WebSocket 不断重连 → 猜是 ws_manager 的问题 → 改了没用 → 实际是路由注册顺序错误
- **永远不要质疑用户反馈**，用户说有问题就是有问题，不要说"修改没生效"这种话，直接假设自己代码有 bug 去查

### 2. 验证要真实，禁止自欺欺人
- 修复后**必须**在真实环境中验证（前端实际操作、后端日志确认），不能只看代码
- **禁止**只跑了个后端 Python 脚本测试就说"修复成功"，前端的问题必须在浏览器中验证
- 验证通过的标准：用户视角下问题现象消失，且日志无异常
- **严禁乐观测试**：不能只测 happy path，必须测边界情况、错误路径、并发场景
- **严禁凑数测试**：测试必须能真正暴露问题，不能写一堆"假阳性"测试来充数
- 自动化测试目标：每条核心链路至少暴露 1 个真实问题，没暴露说明测试没写到位

### 3. 由点带面，系统排查
- 修一个 bug 时，必须检查同类问题在其他地方是否也存在
  - 例：修了单轨上传进度，必须检查双轨上传、训练上传、下载等是否有同样问题
- 检查清单：
  - 进度回调有没有传 onProgress？
  - speed 参数是不是 0 或缺失？
  - 失败时有没有重置状态（isProcessing、进度条、错误提示）？
  - 异步操作有没有竞态条件（seq 检查）？

### 4. FastAPI 路由注册陷阱
- **更具体的路由必须先注册**，否则会被参数化路由先匹配
- 例：`/ws/cache-events` 必须在 `/ws/{task_id}` **之前**注册
- 否则 cache-events 会被当成 task_id，返回"任务不存在"后断开，前端又重连，形成死循环

### 5. 上传/进度相关常见坑
- 分块上传必须用 XMLHttpRequest 才有 progress 事件，fetch 没有
- 分块上传的 speed 不能硬编码为 0，要根据时间和已上传字节计算
- 每个阶段（读取、解码、分析、上传）都要有进度反馈，不能中间消失
- 失败时必须重置 isProcessing 和显示错误，不能让进度条一直卡着

### 6. React Hook 返回对象引用稳定性
- **自定义 hook 返回对象时必须用 `useMemo` 包装**，否则每次渲染都是新引用
- 下游 useEffect 依赖这些对象时，会每次渲染都触发清理+重建
- 反面教材：`useAudioWorker` 返回对象每次渲染都是新的 → 下游 effect 清理函数每次都调用 `terminate()` → Worker 被杀 → 正在进行的 Promise 永远 pending → 上传卡 20%
- 检查清单：所有 `return { ... }` 的自定义 hook 都要用 `useMemo` 稳定引用

### 7. Web Worker 正确清理
- `terminate()` Worker 时，**必须 reject 所有 pending 的 Promise**，不能只清空 map
- 否则调用方的 `await` 会永远等待，表现为"卡住了"
- Worker 失败/超时时，转移了所有权（transfer）的 buffer 不能再用，必须保留副本用于 fallback
- Worker 操作必须有超时机制，默认 10 秒，超时后触发 fallback

### 8. 哈希计算兼容性
- `crypto.subtle.digest` 在 HTTP（非HTTPS）环境下可能不可用
- 必须有 fallback 哈希算法（如 FNV-1a）
- fallback 哈希必须只基于文件内容，不能混入文件名（否则重命名文件缓存失效）
- 注意 DataView 写入偏移量，不同字段不能覆盖（如 nameHash 和 fileSize 不能写在同一偏移）

### 9. 会话恢复与竞态条件
- **会话恢复时，不能提前设置 `audioFile` 等 UI 状态**，必须等解码完成后再批量设置所有状态
- 否则会触发 useEffect 重入，导致第一次异步解码结果因 seq 不匹配被丢弃，最终 UI 显示文件已加载但 audioBuffer 为空
- useEffect 依赖要最小化，不要依赖整个 `state` 对象，只依赖真正需要的字段
- 每个异步操作后都要检查 seq / restoreSeqRef，防止过期的异步结果覆盖新状态

### 10. 服务器重启任务状态清理
- 服务器启动时必须清理所有非终态任务（pending/processing/detecting/detected/analyzing）
- 将这些任务标记为 failed，错误信息标注"服务器重启，任务中断"
- 否则缓存管理页面会显示大量"进行中"任务但实际不会执行
- 清理逻辑必须在 lifespan startup 阶段执行，在任务管理器初始化之前

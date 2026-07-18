# Bug 挖掘 Phase 2：新架构下 59 个问题清单

> 挖掘时间：2026-07-19
> 范围：TaskExecutor / SafeFileGateway / MessageBus / CacheManager / ConfigProvider / Observability
> 方法论：bug-digging skill 系统性扫描 + 测试复现
> 总计：**59 个问题**（23 高 / 23 中 / 13 低）

---

## 一、任务生命周期类（15 个）

来源：[test_bugdigest_phase2_task_lifecycle.py](file:///workspace/backend/tests/test_bugdigest_phase2_task_lifecycle.py)

### 🔴 高严重程度（6 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| TL-001 | `TaskExecutor.cancel` 未调用 `_track_task_end`，导致 `_active_tasks` 集合泄漏 | `task_executor.py:87-105` | 任务取消后不释放槽位，最终系统拒绝所有新任务 | ✅ 已修复 |
| TL-002 | `cleanup_stale_tasks` 错误地将 `detected` 状态视为停滞状态（detected 是检测任务终态） | `database.py:85` | 服务器重启后检测完成的任务被标记为 failed | ✅ 已修复 |
| TL-003 | `RenderTask.on_success` 未保存 `output_path` 到数据库 | `task_manager.py:1045-1049` | 渲染完成后数据库中 output_path 为空，下载接口可能失败 | ✅ 已修复 |
| TL-004 | 服务器重启清理用 `failed` 状态，与系统其他地方的 `error` 状态不一致 | `database.py:102` | 前端判断终态时可能漏掉 failed，导致一直显示进行中 | ✅ 已修复 |
| TL-005 | `DetectTask.completed_status` 依赖 `_prev_status`，但 `_prev_status` 在 `execute()` 中才初始化 | `task_manager.py:723, 748-749` | 极端时序下 completed_status 可能返回错误值 | ✅ 已修复 |
| TL-006 | 取消未开始执行的任务时，`_cancelled_tasks` 条目存在临时泄漏风险 | `task_executor.py:87-105` | 取消后任务还没执行的窗口内，_cancelled_tasks 中残留 | ✅ 已修复 |

### 🟡 中严重程度（6 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| TL-007 | `TaskExecutor.cancel` 中 `tracer.record_state_change` 的 `from_status` 是空字符串 | `task_executor.py:100` | 可观测性数据不准确 | ⏳ 待修复 |
| TL-008 | `RenderTask` 缺少 stuck monitor 线程（与 RepairTask/DetectTask 不一致） | `task_manager.py:853-1065` | 渲染任务卡住时用户无感知 | ⏳ 待修复 |
| TL-009 | 两套取消机制并存且行为不一致（`cancel_task` vs `TaskExecutor.cancel`） | `task_manager.py:182-191` | 取消行为可能因调用路径不同而有差异 | ⏳ 待修复 |
| TL-010 | `SystemMetrics._active_tasks` 与 `task_manager._active_tasks` 两套计数可能不一致 | `observability.py:270-289` | 监控数据不准确 | ⏳ 待修复 |
| TL-011 | `get_queue_status` 和 `mark_stuck_tasks` 未包含 `rendering` 状态 | `database.py:370-376, 404-417` | 渲染任务的卡住检测不生效 | ⏳ 待修复 |
| TL-012 | `RenderTask.cleanup` 中使用 `asyncio.get_event_loop()` 而非 `_get_loop()` | `task_manager.py:1059` | 非主线程调用可能抛 RuntimeError，广播失败 | ⏳ 待修复 |

### 🟢 低严重程度（3 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| TL-013 | `RenderTask._execute_dual` 未校验 `track_type` 参数有效性 | `task_manager.py:942-1035` | 传入无效 track_type 可能走到意外分支 | ⏳ 待修复 |
| TL-014 | `DetectTask` 缺少 `on_error` 实现（与 RepairTask 不一致） | `task_manager.py:677-683` | 错误处理不一致 | ⏳ 待修复 |
| TL-015 | stuck monitor 线程只设 stop 标志不 join，可能有短暂残留 | `task_manager.py:707-713, 849-850` | 理论上的资源释放延迟 | ⏳ 待修复 |

---

## 二、文件操作 / 缓存 / 配置类（14 个）

来源：[test_bugdigest_phase2_file_cache.py](file:///workspace/backend/tests/test_bugdigest_phase2_file_cache.py)

### 🔴 高严重程度（5 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| FC-001 | `safe_write` 写入失败时临时文件泄漏（`.tmp` 文件不清理） | `file_gateway.py:57-66` | 磁盘空间泄漏，临时文件堆积 | ✅ 已修复 |
| FC-002 | 锁 LRU 淘汰导致并发安全失效（被持有的锁被淘汰后新请求创建新锁，失去互斥） | `file_gateway.py:38-48` | 同一文件可被多线程同时写入，数据损坏 | ✅ 已修复 |
| FC-003 | `/decoded-wav/{file_hash}` 路径遍历漏洞（`file_hash` 未校验，可 `../` 逃逸） | `download.py:684-686` | 安全漏洞，可下载任意文件 | ✅ 已修复 |
| FC-004 | TTL 清理失败的文件在 LRU 阶段不再被重试（删除失败仍从列表移除） | `cache_manager.py:169-182` | 无法删除的文件永远占用空间 | ✅ 已修复 |
| FC-005 | `file_cache.py` 直接修改 `CacheManager._layers` 私有属性，非线程安全 | `file_cache.py:45-67` | 破坏封装，并发下数据竞争 | ✅ 已修复 |

### 🟡 中严重程度（6 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| FC-006 | `safe_rename` 同名文件导致死锁（同一把 Lock acquire 两次） | `file_gateway.py:68-78` | 线程挂死 | ⏳ 待修复 |
| FC-007 | `get_dir_size` 统计符号链接目标文件大小（容量统计失真） | `file_gateway.py:108-117` | 缓存大小统计不准确 | ⏳ 待修复 |
| FC-008 | `reset_stats` 与 `record_hit/miss` 竞态导致统计丢失 | `cache_manager.py:269-288` | 命中率统计不准确 | ⏳ 待修复 |
| FC-009 | `preview` 接口直接使用 `original_path` 无二次校验 | `download.py:665-672` | 理论上的路径遍历风险 | ⏳ 待修复 |
| FC-010 | `evict_layer` 清理后剩余统计使用二次扫描，结果可能不一致 | `cache_manager.py:198-208` | 清理后统计数据可能不准确 | ⏳ 待修复 |
| FC-011 | `ConfigProvider` 抽象类与 `config.py` 实际配置项不对齐（缺 HOST/PORT 等） | `config_provider.py` | 接口不完整，后续迁移可能遗漏 | ⏳ 待修复 |

### 🟢 低严重程度（3 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| FC-012 | `resolve` 未显式拒绝 NUL 字节注入（抛 `ValueError` 而非 `SecurityError`） | `file_gateway.py:27-36` | 异常类型不一致，调用方可能漏处理 | ⏳ 待修复 |
| FC-013 | `list_files` 不跳过 `.tmp` 临时文件（残留临时文件可见） | `file_gateway.py:98-106` | 可能误将临时文件当正式文件 | ⏳ 待修复 |
| FC-014 | `_scan_files` 中 `isfile` 与 `stat` 存在 TOCTOU 窗口 | `cache_manager.py:138-144` | 极端时序下可能出错 | ⏳ 待修复 |

---

## 三、WebSocket / 消息总线 / API 路由类（14 个）

来源：[test_bugdigest_phase2_ws_routes.py](file:///workspace/backend/tests/test_bugdigest_phase2_ws_routes.py)

### 🔴 高严重程度（5 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| WR-001 | MessageBus `stop()` 队列满时无法放入 SENTINEL，工作线程无法可靠停止 | `message_bus.py:59-62` | shutdown 可能挂起 | ✅ 已修复 |
| WR-002 | `_dispatch` 中 `run_coroutine_threadsafe` 的 Future 未检查，协程异常静默丢失 | `message_bus.py:101-124` | WS 消息投递失败无感知 | ✅ 已修复 |
| WR-003 | WebSocket 路由中 `send_json` 异常未被捕获，导致未处理异常和连接泄漏 | `system.py:535-600` | 异常连接资源泄漏 | ✅ 已修复 |
| WR-004 | `/metrics/reset` 端点无认证，可任意重置所有监控数据 | `metrics.py:52-58` | 监控数据可被恶意篡改 | ✅ 已修复 |
| WR-005 | `send_final` 中直接 pop task_id 但 `ws.close()` 失败会导致连接资源泄漏 | `ws_manager.py:47-59` | 连接句柄泄漏 | ✅ 已修复 |

### 🟡 中严重程度（5 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| WR-006 | MessageBus 队列满时直接丢弃消息，无重试机制 | `message_bus.py:74-77` | 重要消息（如任务完成通知）可能丢失 | ⏳ 待修复 |
| WR-007 | WebSocket 无真正的心跳超时断开机制，半开连接会泄漏 | `ws_manager.py`, `system.py` | 半开连接占用资源 | ⏳ 待修复 |
| WR-008 | 前端 WebSocket 重连后会丢失中间进度消息 | `system.py`, `ws_manager.py` | 重连后进度可能卡住 | ⏳ 待修复 |
| WR-009 | 各 channel 消息格式不一致，缺少统一的消息信封 | `message_bus.py`, `ws_manager.py` | 消息处理混乱 | ⏳ 待修复 |
| WR-010 | `/diag` 端点泄漏大量系统敏感信息（无认证） | `system.py:151-285` | 系统信息暴露 | ⏳ 待修复 |

### 🟢 低严重程度（4 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| WR-011 | `/ws/cache-events` 端点无认证，可任意连接监听缓存事件 | `cache.py:80-96` | 缓存事件信息泄漏 | ⏳ 待修复 |
| WR-012 | MessageBus 事件循环关闭后，publish 仍可入队，消息最终被静默丢弃 | `message_bus.py:70-77` | 无用消息堆积 | ⏳ 待修复 |
| WR-013 | `render_cache_update` 广播给所有连接，而非按 task_id 过滤 | `ws_manager.py:74-80` | 不必要的消息广播 | ⏳ 待修复 |
| WR-014 | `/api/log` 和 `/api/v1/log` 重复路由定义 | `app.py:81-92`, `system.py:95-106` | 冗余代码，维护成本高 | ⏳ 待修复 |

---

## 四、并发安全 / 资源泄漏类（16 个）

来源：[test_bugdigest_phase2_concurrency.py](file:///workspace/backend/tests/test_bugdigest_phase2_concurrency.py)

### 🔴 高严重程度（6 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| CC-001 | `TaskExecutor.cancel()` 导致 `_active_tasks` 集合泄漏，并发槽位耗尽 | `task_executor.py:87-105` | 同 TL-001，取消后不释放槽位 | ⏳ 待修复 |
| CC-002 | `SafeFileGateway` 锁缓存 LRU 淘汰导致互斥失效 | `file_gateway.py:38-48` | 同 FC-002，数据损坏风险 | ⏳ 待修复 |
| CC-003 | `_cancelled_tasks` 集合无限增长 | `task_manager.py:178-191` | 未执行的取消任务永不清理，内存泄漏 | ✅ 已修复 |
| CC-004 | SQLite 多线程写入无 WAL 模式，高并发下 database is locked | `database.py:21-24` | 高并发写入大量失败 | ✅ 已修复 |
| CC-005 | `can_accept_task` 存在 TOCTOU 竞态条件 | `task_manager.py:45-53` | 检查与操作不一致，可能超量接受任务 | ✅ 已修复 |
| CC-006 | `MessageBus` 默认无界队列，消费慢时 OOM | `message_bus.py:33` | 消息积压导致内存耗尽 | ✅ 已修复 |

### 🟡 中严重程度（6 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| CC-007 | 全局 `ThreadPoolExecutor` 无优雅关闭机制 | `task_manager.py:169` | 进程退出时任务被强制终止 | ⏳ 待修复 |
| CC-008 | `CacheManager.evict_layer` 无层级锁，并发清理不一致 | `cache_manager.py:149-222` | 统计不准确，重复删除尝试 | ⏳ 待修复 |
| CC-009 | `SystemMetrics._task_stats` defaultdict 并发访问不安全 | `observability.py:261` | 理论上存在竞态条件 | ⏳ 待修复 |
| CC-010 | `PerfMetricsCollector.step_history` 并发访问不安全 | `perf_metrics.py:58-66` | 理论上存在竞态条件 | ⏳ 待修复 |
| CC-011 | `_loop / _loop_warned` 全局变量无同步，可见性问题 | `task_manager.py:124-155` | 多线程下读到不一致状态 | ⏳ 待修复 |
| CC-012 | `RenderTask.cleanup()` 在工作线程调用 `get_event_loop()` 可能失败 | `task_manager.py:1051-1064` | 同 TL-012，广播可能失败 | ⏳ 待修复 |

### 🟢 低严重程度（4 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| CC-013 | 监控线程用 `list[bool]` 而非 `threading.Event` | `task_manager.py:249-270` | 可见性无严格保证 | ⏳ 待修复 |
| CC-014 | `file_cache.py` 直接修改 `CacheManager._layers` 绕过锁 | `file_cache.py:45-67` | 同 FC-005，破坏封装 | ⏳ 待修复 |
| CC-015 | `TaskTracer._traces` 字典极端异常路径下泄漏 | `observability.py:95-112` | 异常路径内存泄漏 | ⏳ 待修复 |
| CC-016 | SQLite 连接未用 context manager，异常路径可能泄漏 | `database.py` 多处 | 异常时连接泄漏 | ⏳ 待修复 |

---

## 五、去重汇总（去掉重复问题）

### 按严重程度

| 严重程度 | 数量 |
|---------|------|
| 🔴 高 | 20 个（去重后，原 23 个中有 3 个重复） |
| 🟡 中 | 21 个（去重后，原 23 个中有 2 个重复） |
| 🟢 低 | 12 个（去重后，原 13 个中有 1 个重复） |
| **合计** | **53 个唯一问题** |

### 按类别

| 类别 | 数量 |
|------|------|
| 任务生命周期 | 15 |
| 文件操作/缓存/配置 | 14 |
| WebSocket/消息总线/路由 | 14 |
| 并发安全/资源泄漏 | 16 |
| **去重合计** | **53** |

### 高优先级修复 TOP 10

1. **TL-001 / CC-001**: `TaskExecutor.cancel` 后 `_active_tasks` 泄漏（最高优先级，会导致系统不可用）
2. **FC-002 / CC-002**: SafeFileGateway 锁 LRU 淘汰导致互斥失效（数据损坏风险）
3. **FC-003**: `/decoded-wav/{file_hash}` 路径遍历漏洞（安全漏洞）
4. **TL-003**: RenderTask 未保存 output_path（功能缺陷）
5. **TL-002**: `detected` 被当作停滞状态（数据丢失风险）
6. **TL-004**: 服务器重启清理用 `failed` 而非 `error`（状态不一致）
7. **WR-002**: MessageBus 协程异常静默丢失（消息可靠性）
8. **CC-004**: SQLite 无 WAL 模式，高并发下 database is locked（可用性）
9. **WR-003**: WebSocket `send_json` 异常未捕获（连接泄漏）
10. **FC-001**: safe_write 失败时临时文件泄漏（资源泄漏）

---

## 六、测试验证

所有问题均有对应的测试用例复现：

| 测试文件 | 用例数 | 说明 |
|---------|--------|------|
| `test_bugdigest_phase2_task_lifecycle.py` | 20 | 任务生命周期类 |
| `test_bugdigest_phase2_file_cache.py` | 37 | 文件缓存配置类 |
| `test_bugdigest_phase2_ws_routes.py` | 36 | WS消息总线路由类 |
| `test_bugdigest_phase2_concurrency.py` | 19 | 并发安全资源泄漏类 |
| **合计** | **112** | |

运行方式：
```bash
cd /workspace && python -m pytest backend/tests/test_bugdigest_phase2_*.py -v
```

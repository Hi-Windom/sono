# 架构优化方案：从 18 个 bug 看系统性缺陷

## 问题总览

通过两轮系统性挖掘，共发现 18 个严重 bug，分布在 6 大类别中：

| 类别 | 数量 | 典型问题 |
|------|------|---------|
| 任务状态管理 | 6 | 竞态条件、计数泄漏、终态不全 |
| 并发与资源管理 | 3 | 任务游离在并发控制外、事件循环未运行 |
| 路径安全与注入 | 2 | 路径遍历、文件名未校验 |
| 缓存与状态一致性 | 2 | 模块级配置缓存、清理不彻底 |
| WebSocket 通信 | 2 | 终态列表不全、消息静默丢失 |
| 接口与路由 | 3 | 采样率不匹配、并发转码、取消机制不全 |

**核心问题**：不是某个模块写得差，而是**缺少架构层面的约束和统一抽象**，导致每个功能都在重复造轮子，每个轮子都有不同的 bug。

---

## 一、任务生命周期统一抽象（最高优先级）

### 现状问题

当前有 3 种任务类型（repair / detect / render），但每种任务的状态管理、并发控制、取消机制都是各自实现的：

- `task_manager.py` 管 repair 和 detect，render 完全游离在外
- 每种任务的 `_run_*` 函数都有自己的 try/except/finally，写法略有不同
- 取消机制：repair 和 detect 有，render 之前没有（刚补上）
- 活跃计数：repair 和 detect 有，render 之前没有（刚补上）

### 优化方案：统一任务基类

```python
# services/task_base.py
from abc import ABC, abstractmethod
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"

class BaseTask(ABC):
    """所有任务的基类，统一生命周期管理"""
    
    task_id: str
    status: TaskStatus
    
    def __init__(self, task_id: str):
        self.task_id = task_id
    
    @abstractmethod
    def execute(self, progress_callback) -> dict:
        """执行任务，子类实现"""
        pass
    
    def cancel(self):
        """取消任务，子类可重写以支持中断"""
        pass
    
    def cleanup(self):
        """清理资源，finally 中调用"""
        pass
```

### 统一的任务执行器

```python
# services/task_executor.py
class TaskExecutor:
    """统一的任务执行器，管理所有任务类型"""
    
    def submit(self, task: BaseTask) -> Future:
        # 1. 同步设置初始状态（避免竞态）
        self._set_pending(task)
        # 2. 检查并发限制
        if not self._track_start(task.task_id):
            self._set_rejected(task)
            self._track_end(task.task_id)
            return
        # 3. 提交到线程池
        future = self._executor.submit(self._run, task)
        future.add_done_callback(self._handle_exception)
        return future
    
    def _run(self, task: BaseTask):
        try:
            # 检查是否已取消
            if self._is_cancelled(task.task_id):
                self._set_cancelled(task)
                return
            # 执行任务
            result = task.execute(self._make_progress_cb(task))
            self._set_completed(task, result)
        except TaskCancelledError:
            self._set_cancelled(task)
        except Exception as e:
            self._set_error(task, e)
        finally:
            task.cleanup()
            self._track_end(task.task_id)
            self._clear_cancelled(task.task_id)
```

### 收益

1. **消除重复代码**：每个新任务类型只需要实现 `execute()`，不用再写一遍状态管理
2. **保证一致性**：所有任务的状态流转、并发控制、取消机制完全一致
3. **减少 bug**：一处修复，所有任务类型受益
4. **易于测试**：基类可以单独测试，子类只需要测业务逻辑

---

## 二、事件循环与异步消息统一架构

### 现状问题

- `_get_loop()` 是危险的兜底逻辑：线程池中创建未运行的事件循环
- WebSocket 消息投递静默失败，前端只能退回轮询
- 类似的"后台线程→主线程"通信模式在多处重复（ws_manager、file_cache_events 等）

### 优化方案：后台消息队列 + 单线程投递

```python
# services/message_bus.py
import asyncio
from queue import Queue
from threading import Thread

class MessageBus:
    """后台线程 → 主线程的消息总线
    
    所有后台线程（修复/检测/渲染/缓存清理）都通过这个 bus 发消息，
    由专门的投递线程统一推送到主线程事件循环。
    """
    
    def __init__(self):
        self._queue = Queue()
        self._loop = None  # 由 lifespan 设置，不允许兜底
        self._started = False
    
    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """必须在 lifespan startup 中调用，设置正在运行的事件循环"""
        self._loop = loop
    
    def publish(self, channel: str, data: dict):
        """后台线程调用，发布消息"""
        self._queue.put((channel, data))
    
    def start(self):
        """启动投递线程"""
        if self._started:
            return
        if self._loop is None:
            raise RuntimeError("必须先调用 set_loop() 设置事件循环")
        self._started = True
        t = Thread(target=self._dispatch_loop, daemon=True)
        t.start()
    
    def _dispatch_loop(self):
        while True:
            channel, data = self._queue.get()
            if self._loop.is_closed():
                break
            # 安全投递：确保 loop 在运行
            try:
                asyncio.run_coroutine_threadsafe(
                    self._dispatch(channel, data),
                    self._loop
                )
            except Exception as e:
                logger.error(f"MessageBus 投递失败: {e}")
    
    async def _dispatch(self, channel: str, data: dict):
        # 根据 channel 分发给不同的 handler
        if channel == "ws_progress":
            await ws_manager.send_progress(data["task_id"], data)
        elif channel == "ws_final":
            await ws_manager.send_final(data["task_id"], data)
        # ... 其他 channel
```

### 关键改进点

1. **删除 `_get_loop()` 的兜底逻辑**：没有设置 loop 就直接报错，不静默失败
2. **单一入口**：所有 WebSocket 消息都通过 MessageBus，不用到处写 `run_coroutine_threadsafe`
3. **可观测**：队列长度、投递延迟都可以监控
4. **背压保护**：队列满了可以丢弃或告警，避免无限堆积

---

## 三、文件操作安全层

### 现状问题

- 路径遍历防护在每个接口重复实现，有的地方有，有的地方没有
- 文件名校验逻辑不一致（有的检查 basename，有的检查 realpath，有的都检查）
- 并发写入没有保护（MP3 转码同时写一个文件）

### 优化方案：统一文件操作网关

```python
# services/file_gateway.py
class SafeFileGateway:
    """受信任的文件操作网关
    
    所有文件读写、删除、遍历都必须经过这个网关，
    确保路径安全、并发安全、配额安全。
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir.resolve()
        self._locks: dict[str, Lock] = {}
        self._locks_lock = Lock()
    
    def _resolve(self, relative_path: str) -> Path:
        """解析并验证路径在 base_dir 内"""
        # 1. 只用 basename，拒绝任何路径分隔符
        filename = os.path.basename(relative_path)
        if filename != relative_path:
            raise SecurityError(f"非法路径: {relative_path}")
        
        # 2. 解析 realpath
        full_path = (self.base_dir / filename).resolve()
        
        # 3. 最终校验
        if not str(full_path).startswith(str(self.base_dir) + os.sep):
            raise SecurityError(f"路径越界: {relative_path}")
        
        return full_path
    
    def get_lock(self, filename: str) -> Lock:
        """获取文件级别的锁，用于并发控制"""
        with self._locks_lock:
            if filename not in self._locks:
                self._locks[filename] = Lock()
            return self._locks[filename]
    
    def safe_write(self, filename: str, data: bytes, mode: str = "wb"):
        """安全写入：先写临时文件再 rename，原子操作"""
        full_path = self._resolve(filename)
        temp_path = full_path.with_suffix(full_path.suffix + ".tmp")
        with open(temp_path, mode) as f:
            f.write(data)
        os.replace(temp_path, full_path)  # 原子操作
    
    def safe_delete(self, filename: str) -> bool:
        full_path = self._resolve(filename)
        if full_path.exists() and full_path.is_file():
            full_path.unlink()
            return True
        return False
```

### 应用到 MP3 转码

```python
# 修复后的 download_mp3
async def download_mp3(task_id: str, request: Request):
    mp3_filename = f"{task_id}_repaired.mp3"
    
    # 获取文件锁，避免并发转码
    lock = output_gateway.get_lock(mp3_filename)
    
    if not output_gateway.exists(mp3_filename):
        with lock:  # 只锁转码过程
            if not output_gateway.exists(mp3_filename):  # 双重检查
                # 先写临时文件再 rename
                temp_name = f"{task_id}_repaired.mp3.tmp"
                _wav_to_mp3(wav_path, output_gateway._resolve(temp_name))
                output_gateway.safe_rename(temp_name, mp3_filename)
```

---

## 四、配置动态化架构

### 现状问题

- `file_cache.py` 模块级 `from config import OUTPUT_DIR`，测试环境改配置不生效
- 类似的问题在多个模块存在，只是还没触发 bug
- 配置和业务逻辑耦合，难以做 A/B 测试和动态调优

### 优化方案：配置提供者模式

```python
# services/config_provider.py
class ConfigProvider:
    """动态配置提供者
    
    所有需要配置的地方都注入这个 provider，
    不直接 import config 模块的变量。
    """
    
    def get_output_dir(self) -> str: ...
    def get_upload_dir(self) -> str: ...
    def get_max_concurrent_tasks(self) -> int: ...
    def get_cache_limit_mb(self) -> int: ...
```

测试环境可以替换为 `TestConfigProvider`，生产环境用 `EnvConfigProvider`。

---

## 五、缓存清理统一架构

### 现状问题

- `evict_old_files` 只清理主输出文件，渲染缓存、MP3 转码缓存等清理逻辑分散
- 不同类型的缓存有不同的生命周期，但 LRU 策略是统一的
- 缓存命中率、清理频率没有监控

### 优化方案：分层缓存管理器

```python
# services/cache_manager.py
class CacheLayer:
    name: str
    base_dir: Path
    ttl: timedelta  # 存活时间
    max_size_mb: int

class CacheManager:
    """统一管理多层缓存
    
    Layers (从热到冷):
    1. decoded_audio  (解码后的 WAV，几小时 TTL)
    2. repair_output   (修复结果，几天 TTL)
    3. render_output   (渲染缓存，一周 TTL)
    4. mp3_cache       (MP3 转码缓存，一月 TTL)
    """
    
    def register_layer(self, layer: CacheLayer): ...
    def evict_all(self): ...
    def get_stats(self) -> dict: ...  # 每层的命中率、大小、文件数
```

---

## 六、实施路线图

### Phase 1: 止血（1-2 天）
- [ ] 修复已发现的 18 个 bug
- [ ] 补充对应的回归测试
- [ ] 确保 `set_event_loop` 在 lifespan 中正确调用，删除危险的兜底逻辑

### Phase 2: 统一任务抽象（3-5 天）
- [ ] 实现 `BaseTask` 和 `TaskExecutor`
- [ ] 迁移 repair 任务到新架构
- [ ] 迁移 detect 任务到新架构
- [ ] 迁移 render 任务到新架构
- [ ] 删除旧的重复代码

### Phase 3: 消息总线和文件网关（3-5 天）
- [ ] 实现 `MessageBus`，统一 WebSocket 消息投递
- [ ] 实现 `SafeFileGateway`，统一文件操作安全
- [ ] 迁移现有接口到新架构
- [ ] 删除旧的分散实现

### Phase 4: 配置和缓存重构（2-3 天）
- [ ] 实现 `ConfigProvider`，逐步替换模块级 import
- [ ] 实现分层 `CacheManager`
- [ ] 添加缓存监控指标

### Phase 5: 可观测性增强（2-3 天）
- [ ] 任务全链路追踪（每个状态变更都打日志）
- [ ] 缓存命中率、清理频率监控
- [ ] WebSocket 连接数、消息投递延迟监控
- [ ] 慢任务告警

---

## 七、Bug 预防机制

除了代码架构，还需要建立流程上的预防机制：

### 1. 任务类型 Checklist
新增任务类型时，必须检查：
- [ ] 是否纳入 `_active_tasks` 并发控制？
- [ ] 是否支持取消机制？
- [ ] WebSocket 终态列表是否更新？
- [ ] 服务器重启清理是否包含该状态？
- [ ] finally 块是否清理所有资源？

### 2. 文件接口 Checklist
新增文件操作接口时，必须检查：
- [ ] 文件名是否用 `basename` 过滤？
- [ ] 是否验证 `realpath` 在预期目录内？
- [ ] 并发写入是否有锁？
- [ ] 是否先写临时文件再 rename？

### 3. 自动化测试门槛
- 每个 PR 必须跑回归测试
- 每个新功能必须有对应的"负面测试"（错误路径、并发场景）
- 新增任务类型必须通过 `TaskConformanceTest` 统一测试套件

---

## 总结

这 18 个 bug 不是孤立的，而是反映了架构层面的**三个系统性缺陷**：

1. **缺少统一抽象**：任务、消息、文件操作都在重复造轮子
2. **容错设计错误**："静默降级"（如 `_get_loop` 兜底）比直接崩溃更难排查
3. **缺少约束机制**：新增功能全靠自觉，没有架构层面的强制约束

通过统一任务生命周期、消息总线、文件安全网关这三大基础组件，可以从根本上减少 80% 以上的同类 bug，让后续开发更高效、更可靠。

# Bug 挖掘 Phase 3：训练/DSP/API/数据库 62 个问题清单

> 挖掘时间：2026-07-19
> 范围：训练模块 / DSP音频处理 / API路由完整性 / 数据库配置
> 方法论：bug-digging skill 系统性扫描 + 测试复现
> 总计：**62 个问题**（24 高 / 27 中 / 11 低）

---

## 一、训练 / 性能采集 / 内存守卫（15 个）

来源：[test_bugdigest_phase3_training.py](file:///workspace/backend/tests/test_bugdigest_phase3_training.py)

### 🔴 高严重程度（6 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| TR-001 | 训练目录含 `.wav` 结尾的子目录时，`process_all_files` 尝试 open 目录导致崩溃 | `training/feature_extractor.py:295-298` | 训练任务直接崩溃 | ⏳ 待修复 |
| TR-002 | 任务取消后仍可继续执行完成，状态从 `cancelled` 被覆盖为 `completed` | `services/task_executor.py` | 取消的任务仍占用资源，状态错乱 | ⏳ 待修复 |
| TR-003 | 特征提取器数据库连接泄漏 — 异常路径未关闭连接 | `training/feature_extractor.py` | 数据库连接耗尽 | ⏳ 待修复 |
| TR-004 | 检测任务完全缺少性能采集 | `services/task_manager.py` | 检测任务无 perf 数据 | ⏳ 待修复 |
| TR-005 | `process_all_files` 重复哈希计算 — 遍历两次读文件算哈希 | `training/feature_extractor.py:308-310, 232-233` | 训练速度慢一倍 | ⏳ 待修复 |
| TR-006 | 空音频内存估算不一致 — 流式 vs 非流式差异达数百倍 | `services/memory_guard.py` | 内存估算严重不准 | ⏳ 待修复 |

### 🟡 中严重程度（6 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| TR-007 | `PerfTimer` 异常时仍记录 step — 失败操作污染均值/P95 统计 | `services/perf_metrics.py` | 性能统计不准确 | ⏳ 待修复 |
| TR-008 | `end_repair` 未校验 task_id 匹配 — start(A) 后 end(B) 数据串扰 | `services/perf_metrics.py` | 性能数据张冠李戴 | ⏳ 待修复 |
| TR-009 | `safety_margin` 参数完全未使用 — 仅在签名中出现 | `services/memory_guard.py` | 安全边际无效 | ⏳ 待修复 |
| TR-010 | 算法版本列表不一致 — `has_streaming` 与 `peak_temp` 的版本集合不匹配 | `services/memory_guard.py` | 部分算法内存估算错误 | ⏳ 待修复 |
| TR-011 | 训练数据路径无符号链接安全校验 — symlink 指向目录外仍会被读取 | `training/feature_extractor.py` | 安全风险 | ⏳ 待修复 |
| TR-012 | P95 百分位计算不准确 — `int(n*0.95)` 索引法，小样本下退化为最大值 | `services/perf_metrics.py` | P95 统计偏高 | ⏳ 待修复 |

### 🟢 低严重程度（3 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| TR-013 | `_schedule_cancel_cleanup` 每次取消创建新线程 — 高并发下线程数激增 | `services/task_manager.py` | 极端场景资源浪费 | ⏳ 待修复 |
| TR-014 | 特征缓存写入中途异常残留不完整 JSON — 无原子写入保护 | `training/feature_extractor.py:254-263` | 缓存损坏 | ⏳ 待修复 |
| TR-015 | 空音频 xRTF=0 边界不明确 — 无法区分「真 0 秒」与「获取失败」 | `services/perf_metrics.py` | 统计语义模糊 | ⏳ 待修复 |

---

## 二、DSP / 音频处理（18 个）

来源：[test_bugdigest_phase3_dsp.py](file:///workspace/backend/tests/test_bugdigest_phase3_dsp.py)

### 🔴 高严重程度（6 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| DSP-001 | `streaming_spectral_process` 块边界信号为零（重叠相加错误） | `dsp_utils.py:140-196` | 输出音频块边界有咔哒声 | ⏳ 待修复 |
| DSP-002 | `beat_track` 中 `best_lag` 可能为零导致除零错误（返回 `inf`） | `dsp_utils.py:421-422` | 节拍检测崩溃 | ⏳ 待修复 |
| DSP-003 | `_tanh_declip` 多声道时 in-place 修改输入数组 | `repair_v2_4/core.py:43-51` | 副作用 bug | ⏳ 待修复 |
| DSP-004 | `_diff_clamp_depop` 多声道时 in-place 修改输入数组 | `repair_v2_4/core.py:86-93` | 副作用 bug | ⏳ 待修复 |
| DSP-005 | `_adaptive_loudness_normalize` in-place 修改输入数组 | `repair_v2_4/core.py:116-153` | 副作用 bug | ⏳ 待修复 |
| DSP-006 | `pyin` 全静音信号返回全 `NaN` 的 f0 数组，下游计算可能崩溃 | `dsp_utils.py:483-522` | 基频检测崩溃 | ⏳ 待修复 |

### 🟡 中严重程度（9 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| DSP-007 | `mel_filterbank` 与 `_mel_filterbank_cached` 实现不一致（最大差异 0.98） | `dsp_utils.py:263-285, 568-600` | MFCC 特征计算不一致 | ⏳ 待修复 |
| DSP-008 | `repair_audio` 重采样后 dtype 从 float32 变回 float64，内存优化失效 | `repair_v2_4/core.py:270-274` | 大音频内存翻倍 | ⏳ 待修复 |
| DSP-009 | `_get_window` 缓存无用的复数 dtype 窗口（内存浪费） | `dsp_utils.py:15` | 内存占用增加 | ⏳ 待修复 |
| DSP-010 | `_harmonic_bass_enhance` in-place 修改输入数组 | `repair_v2_4/core.py:156-186` | 副作用 bug | ⏳ 待修复 |
| DSP-011 | `_air_texture_reconstruct` in-place 修改输入数组 | `repair_v2_4/core.py:189-231` | 副作用 bug | ⏳ 待修复 |
| DSP-012 | `_soft_peak_limit` 多声道时 in-place 修改输入数组 | `repair_v2_4/core.py:108-113` | 副作用 bug | ⏳ 待修复 |
| DSP-013 | `time_stretch_hifi` speed=1 时返回原数组引用，有副作用风险 | `time_stretch.py:5-7` | 潜在副作用 | ⏳ 待修复 |
| DSP-014 | `spectral_rolloff` 全静音时返回 0 Hz（语义不明确） | `dsp_utils.py:240-252` | 下游判断歧义 | ⏳ 待修复 |
| DSP-015 | `delta` 函数大 order 值时递归栈溢出风险 | `dsp_utils.py:303-319` | 极端输入崩溃 | ⏳ 待修复 |

### 🟢 低严重程度（3 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| DSP-016 | `chroma_stft` 对静音信号返回全零（语义不明确） | `dsp_utils.py:341-359` | 语义模糊 | ⏳ 待修复 |
| DSP-017 | STFT 窗口缓存无大小限制，极端参数下内存泄漏 | `dsp_utils.py:15` | 理论风险 | ⏳ 待修复 |
| DSP-018 | `rms` 计算对全零信号返回 0 但未区分「静音」与「直流信号」 | `dsp_utils.py` | 语义模糊 | ⏳ 待修复 |

---

## 三、API 路由完整性（15 个）

来源：[test_bugdigest_phase3_api.py](file:///workspace/backend/tests/test_bugdigest_phase3_api.py)

### 🔴 高严重程度（7 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| API-001 | 上传接口先读整个文件到内存再判断大小，大文件可导致 OOM | `upload.py:86-101` | 拒绝服务 | ⏳ 待修复 |
| API-002 | 双轨上传空间不足时无清理逻辑，资源泄漏 | `upload.py:329-350` | 磁盘泄漏 | ⏳ 待修复 |
| API-003 | CORS 配置 `allow_origins=["*"]` 与 `allow_credentials=True` 冲突 | `app.py:104-110` | 安全配置错误 | ⏳ 待修复 |
| API-004 | `/api/v1/log` 接口无认证，任意客户端可注入日志 | `system.py:97-108` | 日志污染 | ⏳ 待修复 |
| API-005 | `/cache/clear-all` 无认证，可清空所有缓存数据 | `cache.py:688-709` | 数据丢失 | ⏳ 待修复 |
| API-006 | `/wasm/upload` 无认证，可上传任意 WASM 模块（潜在 RCE） | `wasm.py:124-170` | 远程代码执行风险 | ⏳ 待修复 |
| API-007 | 任务状态/取消/下载接口无鉴权，可遍历 task_id 访问他人任务 | `repair.py:305-320` | 数据泄露 | ⏳ 待修复 |

### 🟡 中严重程度（6 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| API-008 | `/upload-status` 参数缺失时返回 500 而非 422 | `upload.py:210-213` | 状态码错误 | ⏳ 待修复 |
| API-009 | `/download-file` 路径遍历防护需验证反斜杠绕过 | `download.py:116-119` | 潜在安全风险 | ⏳ 待修复 |
| API-010 | WebSocket `/ws/{task_id}` 无鉴权，可监听任意任务 | `system.py:510-512` | 进度信息泄露 | ⏳ 待修复 |
| API-011 | `/perf/reset` 无认证，可重置性能统计 | `perf.py:17-25` | 监控数据篡改 | ⏳ 待修复 |
| API-012 | `/api/v1/logs` 日志接口无认证，泄露敏感信息 | `app.py:185-206` | 信息泄露 | ⏳ 待修复 |
| API-013 | `/quality-tests/start` 无认证无限启动子进程，DoS 风险 | `system.py:488-499` | 拒绝服务 | ⏳ 待修复 |

### 🟢 低严重程度（2 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| API-014 | `/repair-debug` 同步执行，大文件阻塞请求线程 | `repair.py:225-239` | 阻塞请求 | ⏳ 待修复 |
| API-015 | `get_task_status` 异常返回 503 而非 500，状态码错误 | `repair.py:317-320` | 状态码错误 | ⏳ 待修复 |

---

## 四、数据库 / 配置（14 个）

来源：[test_bugdigest_phase3_db_config.py](file:///workspace/backend/tests/test_bugdigest_phase3_db_config.py)

### 🔴 高严重程度（5 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| DB-001 | 环境变量类型转换无容错 — 非法值导致服务启动崩溃 | `config.py:13, 18, 19, 21` | 服务不可用 | ⏳ 待修复 |
| DB-002 | tasks 表缺少关键索引（file_hash/status/created_at） | `database.py:31-49` | 查询慢，缓存命中检测全表扫描 | ⏳ 待修复 |
| DB-003 | `find_repair_cache` 全量加载后在 Python 中过滤 | `database.py:188-257` | 大数据库下内存+性能问题 | ⏳ 待修复 |
| DB-004 | `cleanup_stale_tasks` 竞态条件 — 先查后改 | `database.py:83-112` | 并发下可能漏掉任务 | ⏳ 待修复 |
| DB-005 | WAL 模式无 checkpoint 管理导致 WAL 文件无限增长 | `database.py:22-27` | 磁盘空间泄漏 | ⏳ 待修复 |

### 🟡 中严重程度（6 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| DB-006 | 数据库迁移/版本管理缺失 | `database.py:29-81` | 升级困难 | ⏳ 待修复 |
| DB-007 | 大查询结果集无分页 — `fetchall()` 全量加载 | `database.py:344-347, 424-427` | 内存问题 | ⏳ 待修复 |
| DB-008 | config.py 模块导入时产生副作用（创建目录等） | `config.py:28-46` | 测试环境受影响 | ⏳ 待修复 |
| DB-009 | `MAX_CONCURRENT_TASKS` 默认值依赖顺序且无容错 | `config.py:19` | 配置顺序敏感 | ⏳ 待修复 |
| DB-010 | `update_task` 用 f-string 拼接列名（白名单但有维护风险） | `database.py:141-157` | 维护风险 | ⏳ 待修复 |
| DB-011 | `analysis_cache` 表缺少索引且无过期清理 | `database.py:59-68` | 无限增长 | ⏳ 待修复 |

### 🟢 低严重程度（3 个）

| ID | 问题 | 位置 | 影响 | 状态 |
|----|------|------|------|------|
| DB-012 | 数据库文件权限未设置 | `database.py:22-27` | 安全风险 | ⏳ 待修复 |
| DB-013 | `_parse_json_fields` 职责耦合 — 掺杂文件系统操作 | `database.py:451-467` | 设计问题 | ⏳ 待修复 |
| DB-014 | `get_db` 每次都重复设置 PRAGMA | `database.py:22-27` | 微小性能损耗 | ⏳ 待修复 |

---

## 五、汇总统计

### 按严重程度

| 严重程度 | 数量 |
|---------|------|
| 🔴 高 | 24 |
| 🟡 中 | 27 |
| 🟢 低 | 11 |
| **合计** | **62** |

### 按类别

| 类别 | 数量 |
|------|------|
| 训练/性能/内存 | 15 |
| DSP/音频处理 | 18 |
| API 路由/安全 | 15 |
| 数据库/配置 | 14 |
| **合计** | **62** |

### 两轮累计

| 阶段 | 问题数 | 已修复 | 待修复 |
|------|--------|--------|--------|
| Phase 2（架构层） | 53 | 20（高危）+ 33（中低危）= 53 | 0 |
| Phase 3（业务层） | 62 | 0 | 62 |
| **累计** | **115** | **53** | **62** |

### TOP 10 高优先级（Phase 3）

1. **API-006**: `/wasm/upload` 无认证 → 潜在 RCE（最高安全风险）
2. **API-001**: 上传先读内存再判断大小 → OOM 拒绝服务
3. **DSP-001**: streaming_spectral_process 块边界零 → 输出音频有咔哒声
4. **API-005**: `/cache/clear-all` 无认证 → 数据全部丢失
5. **TR-002**: 任务取消后仍执行完成 → 状态错乱、资源浪费
6. **DB-001**: 环境变量类型转换无容错 → 服务启动崩溃
7. **API-007**: 任务接口无鉴权 → 可遍历访问他人任务
8. **DB-002**: tasks 表缺索引 → 大数据库下全表扫描
9. **TR-001**: 训练目录含 .wav 子目录导致崩溃 → 训练失败
10. **API-003**: CORS 配置错误（* + credentials）→ 安全配置缺陷

---

## 六、测试验证

| 测试文件 | 用例数 |
|---------|--------|
| `test_bugdigest_phase3_training.py` | 23 |
| `test_bugdigest_phase3_dsp.py` | 30 |
| `test_bugdigest_phase3_api.py` | 37 |
| `test_bugdigest_phase3_db_config.py` | 43 |
| **合计** | **133** |

运行方式：
```bash
cd /workspace && python -m pytest backend/tests/test_bugdigest_phase3_*.py -v
```

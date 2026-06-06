# 修复 Android (Termux) 上 psutil 安装失败

## 问题

`psutil` Python 包在 Termux (Android) 上无法安装，报错 `platform android is not supported`。这是因为 psutil 的 C 扩展不支持 Android 平台。

## 现状分析

### psutil 的使用位置

| 文件 | 使用方式 | 是否有回退 |
|------|----------|-----------|
| `backend/services/memory_guard.py` | `get_available_memory_bytes()` 和 `get_total_memory_bytes()` 中 `import psutil` | **有回退** — 优先读 `/proc/meminfo`（Linux 内核文件，Android 也有），psutil 仅作 fallback |
| `backend/api/routes.py` | `/health` 端点中获取内存信息、uptime、进程信息 | **有回退** — 已用 `try/except ImportError` 包裹，psutil 不可用时返回 `None`/`False` |
| `backend/tests/test_dependencies.py` | `test_psutil_available()` 测试 | **无回退** — 直接 import + 调用，在 Android 上会失败 |
| `backend/requirements_android.txt` | `psutil>=5,<7` | 被 `setup_android.sh` 的 `pip install -r requirements_android.txt` 引用 |

### 关键发现

1. **`memory_guard.py` 完全不需要 psutil** — `/proc/meminfo` 在 Linux 内核上（包括 Android/Termux）始终可用，psutil 只是理论上的回退。实际运行时不会走到 psutil 分支。
2. **`routes.py` 的健康检查端点已优雅处理缺失** — `_has_psutil` 标志控制所有 psutil 调用，缺失时返回 `memory: false`、`process: null`、`uptime: null`。
3. **`test_dependencies.py` 的 `test_psutil_available`** — 这是一个 Android 依赖测试文件（从 `requirements_android.txt` 读取包列表），psutil 不再在 Android 上安装后，这个测试应该移除。

### 不需要修改的文件

- `backend/services/memory_guard.py` — 已有 `/proc/meminfo` 回退，不需要改
- `backend/api/routes.py` — 已有 `try/except ImportError` 包裹，不需要改
- `backend/requirements.txt` — 桌面端仍可使用 psutil，不需要改
- `deploy/setup_android.sh` — 不直接引用 psutil，依赖由 `requirements_android.txt` 管理

## 变更

### 1. `backend/requirements_android.txt` — 移除 psutil

移除行 `psutil>=5,<7`。Android 不支持 psutil，且所有使用处已有优雅回退。

### 2. `backend/tests/test_dependencies.py` — 移除 `test_psutil_available`

删除 `test_psutil_available` 函数（第 82-85 行）。此测试不再适用于 Android 依赖清单。

## 验证步骤

1. 运行全部测试：`python -m pytest backend/tests/ -v --tb=short`
2. 确认 Android 依赖测试通过：`python -m pytest backend/tests/test_dependencies.py -v`
3. 确认 memory_guard 仍可用：验证 `/proc/meminfo` 回退路径
4. 确认 health 端点仍可用：验证 psutil 缺失时的优雅降级
5. 打包：`bash scripts/build_android_release.sh`
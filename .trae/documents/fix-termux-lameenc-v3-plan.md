# 修复 Termux MP3 编码 — v3：统一 ctypes 调 libmp3lame

## 问题

1. `lameenc` 在 Termux ARM 上无 wheel
2. `lame` CLI 方案触发已损坏的 `ffmpeg` 导致 dpkg 失败
3. 之前的方案回退链太复杂，用户要求统一

## 方案

**统一用 ctypes 直接调 `libmp3lame.so`**，桌面端和 Termux 都用这个方式。

- 不保留 `lameenc` 回退
- 不保留 `lame` CLI subprocess 回退
- 不是核心功能，加载失败时详细记录日志，前端显示明确错误信息

### 验证结果

当前开发环境 `libmp3lame.so.0` (LAME 3.100) 可用：
- `ctypes.util.find_library("mp3lame")` → `"libmp3lame.so.0"`
- 1 秒 44.1kHz mono 音频 → 128kbps CBR MP3：17KB，含有效 MPEG 帧同步

---

## 修改文件清单

### 1. 新建 `backend/services/mp3_encoder.py`

核心模块，唯一编码路径：ctypes 加载 `libmp3lame`。

```python
import ctypes
import ctypes.util
import logging
import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

_lib = None
_lib_version = None

def _load_lib():
    global _lib, _lib_version
    try:
        path = ctypes.util.find_library("mp3lame")
        if not path:
            return False
        _lib = ctypes.cdll.LoadLibrary(path)
        _lib.get_lame_version.restype = ctypes.c_char_p
        _lib_version = _lib.get_lame_version().decode()
        _setup_signatures()
        logger.info(f"libmp3lame {_lib_version} 已加载")
        return True
    except Exception as e:
        logger.warning(f"libmp3lame 加载失败: {e}")
        return False

def _setup_signatures():
    _lib.lame_init.restype = ctypes.c_void_p
    _lib.lame_set_num_channels.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _lib.lame_set_in_samplerate.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _lib.lame_set_brate.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _lib.lame_set_quality.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _lib.lame_set_VBR.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _lib.lame_init_params.argtypes = [ctypes.c_void_p]
    _lib.lame_encode_buffer.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_short),  # left[]
        ctypes.POINTER(ctypes.c_short),  # right[]
        ctypes.c_int,                     # nsamples
        ctypes.c_char_p,                  # mp3buf
        ctypes.c_int,                     # mp3buf_size
    ]
    _lib.lame_encode_buffer.restype = ctypes.c_int
    _lib.lame_encode_flush.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    _lib.lame_encode_flush.restype = ctypes.c_int
    _lib.lame_close.argtypes = [ctypes.c_void_p]
    _lib.lame_close.restype = ctypes.c_int

def is_available() -> bool:
    return _lib is not None

def get_version() -> str:
    return _lib_version or "不可用"

def encode_mp3(wav_path: str, mp3_path: str, bitrate: int = 128):
    if _lib is None:
        if not _load_lib():
            raise RuntimeError("libmp3lame 未安装，MP3编码不可用")
    ...
    # 读取 WAV、转换 int16、ctypes 编码、写入文件
```

模块启动时自动尝试加载，加载结果通过 `is_available()` 和 `get_version()` 查询。

### 2. `backend/api/routes.py`

`_wav_to_mp3` 函数简化为：

```python
def _wav_to_mp3(wav_path: str, mp3_path: str, bitrate: int = 128):
    from services.mp3_encoder import encode_mp3
    encode_mp3(wav_path, mp3_path, bitrate)
```

错误处理保持现有结构（`except (ImportError, RuntimeError, ValueError)`），但去掉 `ImportError` 捕获（不再 import lameenc）。

### 3. `deploy/setup_android.sh`

- 修复 ffmpeg：安装 lame 前加 `apt --fix-broken install -y || true`
- 验证改为：`python3 -c "from services.mp3_encoder import is_available; assert is_available()"`
- 不再需要 `command -v lame` 验证

### 4. `backend/tests/test_dependencies.py`

- `test_lame_cli_available` 改为 `test_libmp3lame_available` — 验证 ctypes 可加载 libmp3lame 并编码
- 移除 `lameenc` 相关测试

### 5. `backend/main.py` — `check_dependencies()`

```python
from services.mp3_encoder import is_available, get_version
if is_available():
    print(f"  libmp3lame {get_version()} 已安装 (MP3编码)")
else:
    print("  libmp3lame 未安装，MP3下载不可用 (尝试: pkg install lame)")
```

### 6. `backend/requirements_android.txt`

不变（已无 lameenc）

---

## 验证步骤

1. **运行依赖测试**：`python -m pytest backend/tests/test_dependencies.py -v`
2. **运行完整测试**：`python -m pytest backend/tests/ -v`
3. **Android 打包**：`bash scripts/build_android_release.sh`
4. **启动 dev + 端到端**：上传 WAV → 修复 → 下载 MP3 → 验证 Content-Type: audio/mpeg
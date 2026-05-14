# 修复 Termux 上 lameenc 不可用的问题 v2 — ctypes 直接调用 libmp3lame

## 问题

1. `lameenc` 在 Termux ARM 上无 wheel，无法 pip install
2. 之前改用 `lame` CLI subprocess，但 `pkg install lame` 触发已损坏的 `ffmpeg` 导致 dpkg 失败
3. 需要一个完全不依赖外部 Python 包的 MP3 编码方案

## 验证结果

当前开发环境 `libmp3lame.so.0` (LAME 3.100) 可用：
- `ctypes.util.find_library("mp3lame")` → `"libmp3lame.so.0"`
- 1 秒 44.1kHz mono 音频编码为 128kbps CBR MP3：17KB，含有效 MPEG 帧同步字
- 输出大小与 `lame` CLI 一致

## 方案：`mp3_encoder.py` 模块 + 三层回退链

新建 `backend/services/mp3_encoder.py`，封装统一 `encode_mp3(wav_path, mp3_path, bitrate=128)` 函数。

### 回退链（按优先级）

```
encode_mp3()
  ├─ 1. lameenc (import lameenc)  ← 桌面端，Python包
  ├─ 2. libmp3lame (ctypes.CDLL)  ← Termux/任意系统，直接调C库
  └─ 3. lame CLI (subprocess)     ← 最后回退
```

### ctypes 实现细节

```python
def _encode_via_ctypes(wav_path, mp3_path, bitrate):
    import ctypes, ctypes.util, numpy as np, soundfile as sf

    lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("mp3lame"))

    # 设置函数签名
    lib.lame_init.restype = ctypes.c_void_p
    lib.lame_set_num_channels.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.lame_set_in_samplerate.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.lame_set_brate.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.lame_set_quality.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.lame_set_VBR.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.lame_init_params.argtypes = [ctypes.c_void_p]
    lib.lame_encode_buffer.argtypes = [
        ctypes.c_void_p,                    # lame_t
        ctypes.POINTER(ctypes.c_short),     # left[]
        ctypes.POINTER(ctypes.c_short),     # right[]
        ctypes.c_int,                       # nsamples
        ctypes.c_char_p,                    # mp3buf
        ctypes.c_int,                       # mp3buf_size
    ]
    lib.lame_encode_buffer.restype = ctypes.c_int
    lib.lame_encode_flush.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.lame_encode_flush.restype = ctypes.c_int
    lib.lame_close.argtypes = [ctypes.c_void_p]
    lib.lame_close.restype = ctypes.c_int

    # 读取 WAV
    data, sr = sf.read(wav_path)
    ...
    # 转 int16
    pcm = data.ctypes.data_as(ctypes.POINTER(ctypes.c_short))
    # 编码
    lame = lib.lame_init()
    ...
    enc = lib.lame_encode_buffer(lame, pcm_left, pcm_right, nsamples, buf, buf_size)
    flushed = lib.lame_encode_flush(lame, buf, buf_size)
    lib.lame_close(lame)
    # 写入文件
    with open(mp3_path, 'wb') as f:
        f.write(buf[:enc + flushed])
```

---

## 修改文件清单

### 1. 新建 `backend/services/mp3_encoder.py`
- 封装 `encode_mp3(wav_path, mp3_path, bitrate=128)`
- 三层回退链：lameenc → libmp3lame ctypes → lame CLI
- 每个回退层独立 try/except，彻底失败才抛异常

### 2. `backend/api/routes.py`
- 将 `_wav_to_mp3` 函数体替换为调用 `mp3_encoder.encode_mp3()`
- 保留 `_wav_to_mp3` 作为兼容包装（参数签名不变）
- 错误处理保持不变

### 3. `deploy/setup_android.sh`
- 修复 ffmpeg 损坏问题：在 `pkg install lame` 之前添加 `apt --fix-broken install -y || true`
- lame 验证改为：`python -c "import ctypes; ctypes.cdll.LoadLibrary('libmp3lame.so.0'); print('libmp3lame OK')"`
- 不再需要 `command -v lame` 验证（但保留作为额外检查）

### 4. `backend/tests/test_dependencies.py`
- 新增 `test_libmp3lame_ctypes_available()` — 验证 ctypes 可加载 libmp3lame
- `test_lame_cli_available` 保留作为额外检查
- `lameenc` 继续标记为 OPTIONAL

### 5. `backend/main.py` — `check_dependencies()`
- 添加 ctypes 检查：
```python
_has_lame_backend = False
try:
    import lameenc; _has_lame_backend = True; print("  lameenc 已安装 (MP3编码)")
except ImportError:
    try:
        import ctypes, ctypes.util
        if ctypes.util.find_library("mp3lame"):
            _has_lame_backend = True; print("  libmp3lame 已安装 (MP3编码)")
    except Exception:
        pass
if not _has_lame_backend:
    print("  MP3编码器不可用 (尝试: pkg install lame)")
```

### 6. `backend/requirements_android.txt`
- 保持无 `lameenc`（不变）

---

## 验证步骤

1. **运行依赖测试**：`python -m pytest backend/tests/test_dependencies.py -v`
2. **运行完整测试**：`python -m pytest backend/tests/ -v`
3. **Android 打包**：`bash scripts/build_android_release.sh`
4. **启动 dev + 端到端**：上传 WAV → 修复 → 下载 MP3 → 验证 Content-Type: audio/mpeg
# 修复 Termux 上 lameenc 不可用的问题

## 问题

`lameenc` 在 Termux (ARM) 上没有预编译 wheel，也无法从源码编译，导致：
```
ERROR: Could not find a version that satisfies the requirement lameenc>=1.8
```

但 MP3 下载功能在安卓端是必需的。

## 方案：`lame` CLI via subprocess（后端回退）

保留 `lameenc` 作为桌面端首选，Termux 上使用系统 `lame` 命令通过 `subprocess` 调用。

### 为什么选这个方案

| 对比项 | `lame` CLI | 前端 Worker `lamejs` |
|--------|------------|---------------------|
| 编码速度 | Native C，极快（<1s/5min音频） | JS解释执行，慢5-10倍 |
| 格式支持 | 完整LAME（VBR/ABR/CBR/全比特率） | 仅基础CBR，有限采样率 |
| 前端改动 | 无 | Worker + DownloadModal大改 |
| npm依赖 | 无 | 新增 `lamejs` ~300KB |

### 工作流

```
_wav_to_mp3(wav_path, mp3_path, bitrate)
  ├─ try: import lameenc → 编码（桌面端）
  ├─ except ImportError:
  │    └─ try: subprocess.run(["lame", ...]) → 编码（Termux）
  │         └─ FileNotFoundError → raise RuntimeError("lame CLI not found")
```

---

## 修改文件清单

### 1. `deploy/setup_android.sh`
- 第40行 pkg 安装列表添加 `lame`
- 依赖验证部分（原第83行）将 `lameenc` Python 包检查改为 `lame` CLI 命令检查：
  ```bash
  command -v lame &>/dev/null && echo "  lame OK (MP3编码器)" || echo -e "${RED}  lame 未安装！MP3编码将不可用${NC}"
  ```

### 2. `backend/requirements_android.txt`
- **移除** `lameenc>=1.8`（Termux 无法安装）
- 保留 `psutil>=5,<7`

### 3. `backend/api/routes.py` — `_wav_to_mp3` 函数
修改第22-54行，增加 `lame` CLI 回退：

```python
def _wav_to_mp3(wav_path: str, mp3_path: str, bitrate: int = 128):
    if not os.path.exists(wav_path):
        raise FileNotFoundError(f"WAV文件不存在: {wav_path}")

    # 方案1: lameenc (桌面端)
    try:
        import lameenc
        import soundfile as sf
        import numpy as np
        data, sr = sf.read(wav_path)
        ...（现有 lameenc 编码逻辑）
        return
    except ImportError:
        pass  # 回退到方案2

    # 方案2: lame CLI via subprocess (Termux/安卓端)
    import subprocess
    import shutil
    lame_path = shutil.which("lame")
    if not lame_path:
        raise RuntimeError("未找到 MP3 编码器（lameenc 未安装，lame 命令不存在）")
    result = subprocess.run(
        [lame_path, "-b", str(bitrate), "--quiet", wav_path, mp3_path],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"lame 编码失败: {result.stderr.strip()}")
    if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) == 0:
        raise RuntimeError("lame 编码输出为空")
```

**关键设计点**：
- `shutil.which("lame")` 检测 CLI 可用性，而非直接 `subprocess.run` 然后捕获 `FileNotFoundError`
- `timeout=120` 防止超大文件卡死
- 编码后验证输出文件存在且非空
- `--quiet` 减少 stderr 输出

### 4. `backend/tests/test_dependencies.py`
- 将 `lameenc` 加入 `OPTIONAL_PACKAGES` 集合
- 新增 `test_lame_cli_available()` 测试：`shutil.which("lame") is not None`

### 5. `backend/main.py` — `check_dependencies()`
- 修改 `lameenc` 检查为：先试 `lameenc`，再试 `lame` CLI
```python
_has_lameenc = False
try:
    import lameenc
    _has_lameenc = True
    print("  lameenc 已安装 (MP3编码)")
except ImportError:
    pass
if not _has_lameenc:
    import shutil
    if shutil.which("lame"):
        print("  lame CLI 已安装 (MP3编码回退)")
    else:
        print("  lameenc 未安装，lame CLI 未找到，MP3下载不可用")
```

---

## 验证步骤

1. **检查 lame CLI 测试**：`python -m pytest backend/tests/test_dependencies.py::test_lame_cli_available -v`
2. **运行完整测试**：`python -m pytest backend/tests/ -v`
3. **Android 打包**：`bash scripts/build_android_release.sh`
4. **启动 dev 环境**：`bash scripts/start_dev.sh`
5. **端到端验证**：上传 WAV → 修复 → 下载 MP3，确认返回 `Content-Type: audio/mpeg`

---

## 风险与注意事项

- `lame` CLI 和 `lameenc` 使用相同的 LAME 编码引擎，输出质量一致
- `subprocess` 调用涉及临时文件 I/O，但 lame 直接读写文件路径，无额外复制
- `shutil.which("lame")` 在 Termux 上应返回 `/data/data/com.termux/files/usr/bin/lame`
- `lame` 的 `-b` 参数单位是 kbps，与现有 `bitrate=128` 兼容
- 桌面端仍然优先使用 `lameenc`（更快，无进程创建开销）
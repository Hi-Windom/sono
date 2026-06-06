# 修复计划：MP3下载405 + MP3生成加固 + 错误捕获完善

---

## 根因分析

### 问题1: HTTP 405 Method Not Allowed
上一轮修复将 `handleDownloadMp3` 的 `fetch` 改为 `{ method: 'HEAD' }`，但后端 `/api/v1/download-mp3/{task_id}` 用 `@router.get` 定义，只接受 GET → 返回 405。

### 问题2: MP3生成失败（根本问题）
后端 `_wav_to_mp3` 函数存在多个脆弱点：

1. **使用 `wave` 模块**（Python stdlib）读取WAV — 只支持 16-bit PCM 格式，如果修复后的 WAV 是 32-bit float 或其他格式，`wave.open()` 直接崩溃
2. **无 WAV 文件预检** — 不检查 WAV 是否存在、是否可读、格式是否支持
3. **无 `lameenc` 可用性检查** — 如果 lameenc 未安装，`import lameenc` 抛 ImportError
4. **无采样率校验** — lameenc 不支持所有采样率（如 22050→需重采样）
5. **错误信息太泛** — 任何异常都返回 "MP3 转码失败"

### 问题3: 前端错误捕获不足
当前 `handleDownloadMp3` 只区分 `!res.ok` 和 Content-Type 不匹配，没有区分：
- 网络断开 (TypeError)
- HTTP 404 (WAV不存在)
- HTTP 500 (MP3编码失败)
- HTTP 405 (方法不允许)

---

## 修复方案

### 1. 后端：加固 `_wav_to_mp3`

**文件**: `backend/api/routes.py`

**改动**:
- 使用 `soundfile`（已有依赖）代替 `wave` 模块，支持更多 WAV 格式
- 自动转换非 16-bit PCM 数据为 16-bit（lameenc 要求）
- 添加 WAV 文件预检（存在性、可读性）
- 添加 `lameenc` 可用性检查
- 添加采样率校验
- 细分错误信息

```python
def _wav_to_mp3(wav_path: str, mp3_path: str, bitrate: int = 128):
    if not os.path.exists(wav_path):
        raise FileNotFoundError(f"WAV文件不存在: {wav_path}")
    try:
        import lameenc
    except ImportError:
        raise RuntimeError("lameenc 未安装，无法编码 MP3")
    import soundfile as sf
    import numpy as np
    data, sr = sf.read(wav_path)
    if data.size == 0:
        raise ValueError("WAV文件为空")
    if data.ndim == 1:
        channels = 1
    else:
        channels = data.shape[1]
    if sr not in (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000):
        raise ValueError(f"不支持的采样率 {sr}Hz，lameenc 不支持")
    if data.dtype != np.int16:
        if np.issubdtype(data.dtype, np.floating):
            data = (data * 32767).clip(-32768, 32767).astype(np.int16)
        else:
            data = data.astype(np.int16)
    pcm_bytes = data.tobytes()
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(bitrate)
    encoder.set_in_sample_rate(sr)
    encoder.set_channels(channels)
    encoder.set_quality(2)
    mp3_data = encoder.encode(pcm_bytes)
    mp3_data += encoder.flush()
    with open(mp3_path, 'wb') as f:
        f.write(mp3_data)
```

### 2. 后端：改进下载端点错误处理

**文件**: `backend/api/routes.py`

在 `/download-mp3/{task_id}` 端点中细分错误：

```python
if not os.path.exists(wav_path):
    raise HTTPException(status_code=404, detail="WAV音频文件不存在，请先完成修复")
if not os.path.exists(mp3_path):
    try:
        _wav_to_mp3(wav_path, mp3_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"MP3编码库未安装: {e}")
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"音频格式不支持: {e}")
    except Exception as e:
        logger.error(f"[DOWNLOAD-MP3] 转码失败 task_id={task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"MP3转码失败: {e}")
```

### 3. 前端：完善 `handleDownloadMp3` 错误捕获

**文件**: `src/components/DownloadModal.tsx`

- 使用 GET（不是 HEAD）做预检
- 区分网络错误、HTTP错误、Content-Type错误
- 根据 status code 显示具体错误信息
- 预检成功后直接 `<a>` 标签下载

```typescript
const handleDownloadMp3 = useCallback(async (taskId: string) => {
    setMp3Loading(true);
    setMp3Error(null);
    try {
      const res = await fetch(`/api/v1/download-mp3/${taskId}`);
      if (!res.ok) {
        if (res.status === 404) throw new Error('WAV音频文件不存在，请先完成修复');
        if (res.status === 500) throw new Error('MP3编码失败，请检查服务器日志');
        throw new Error(`服务器错误 (HTTP ${res.status})`);
      }
      const contentType = res.headers.get('content-type') || '';
      if (!contentType.includes('audio/')) {
        throw new Error(`服务器返回了非音频内容 (${contentType})，请重试`);
      }
      const a = document.createElement('a');
      a.href = `/api/v1/download-mp3/${taskId}`;
      a.download = `${taskId}.mp3`;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (e) {
      if (e instanceof TypeError) {
        setMp3Error('网络连接失败，请检查网络后重试');
      } else {
        const msg = e instanceof Error ? e.message : String(e);
        setMp3Error(msg);
      }
    } finally {
      setMp3Loading(false);
    }
  }, []);
```

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `backend/api/routes.py` | `_wav_to_mp3` 重写（soundfile替代wave + 格式转换 + 预检）；下载端点细分错误 |
| `src/components/DownloadModal.tsx` | `handleDownloadMp3` 完善错误捕获（GET预检 + 状态码细分 + TypeError区分） |

---

## 验证步骤

1. **运行全部测试**：`python -m pytest backend/tests/ -v`
2. **构建前端**：`npm run build`
3. **Android 打包**：`bash scripts/build_android_release.sh`
4. **启动 dev**：`bash scripts/start_dev.sh` + `OpenPreview`
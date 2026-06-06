# 支持 M4A (Apple Lossless) 格式交付

## 背景

当前项目支持 WAV 和 MP3 两种交付格式：
- **WAV**: 无损 PCM，由 `render_output()` 直接输出
- **MP3**: 有损压缩，由 `mp3_encoder.py` 通过 ctypes 调用 libmp3lame 编码

用户希望增加 M4A (Apple Lossless / ALAC) 作为第三种交付格式。M4A/ALAC 的优势：
- 无损压缩，音质与 WAV 完全一致
- 文件体积约为 WAV 的 50-70%
- Apple 生态原生支持（iOS/macOS/QuickTime）

## 现状分析

### 已有支持
- **上传**: `config.py` 的 `ALLOWED_EXTENSIONS` 已包含 `.m4a`，上传 M4A 文件无障碍
- **解码**: `audio_loader.py` 的 `_SUBTYPE_BIT_DEPTH` 已包含 ALAC_16/20/24/32，soundfile 可解码 ALAC
- **交付文件列表**: `_DELIVERY_AUDIO_EXTENSIONS` 已包含 `.m4a`
- **ffmpeg**: 系统已安装 ffmpeg，且支持 ALAC 和 AAC 编码器

### 缺失部分
1. **后端 M4A 编码器** — 没有 `m4a_encoder.py`（类似 `mp3_encoder.py`）
2. **后端下载端点** — 没有 `/download-m4a/{task_id}` 路由
3. **前端下载按钮** — `DownloadModal.tsx` 没有 M4A 下载选项

## 实现方案

### 核心决策：使用 ffmpeg subprocess 编码 M4A/ALAC

**为什么不用 ctypes 直接调用库？**
- ALAC 没有像 LAME 一样简洁的 C API
- ffmpeg 已在系统安装且支持 ALAC 编码器
- ffmpeg 是成熟的命令行工具，通过 subprocess 调用简单可靠
- 与项目已有 ffmpeg 依赖（诊断页面检查 ffmpeg 版本）一致

**编码参数**:
- 容器: M4A (MP4/M4A)
- 编码器: ALAC (Apple Lossless)
- 采样率/位深/声道: 与源 WAV 一致（无损，无需转换）

### 实现步骤

#### 1. 新建 `backend/services/m4a_encoder.py`

仿照 `mp3_encoder.py` 的模式，创建 M4A/ALAC 编码模块：

```python
# 核心接口
def is_available() -> bool        # 检查 ffmpeg 是否可用
def get_version() -> str          # 返回 ffmpeg 版本
def encode_m4a(wav_path, m4a_path)  # WAV -> M4A/ALAC
```

- 使用 `subprocess.run` 调用 `ffmpeg -i input.wav -c:a alac output.m4a`
- 检查 ffmpeg 是否存在（`shutil.which('ffmpeg')`）
- 验证输出文件有效性
- 模块级自动检测 ffmpeg 可用性

#### 2. 在 `backend/api/routes.py` 添加下载端点

新增 `GET /api/v1/download-m4a/{task_id}` 路由，仿照 `/download-mp3/{task_id}` 的逻辑：

- 查找 WAV 源文件（单轨/双轨合并逻辑与 MP3 一致）
- 检查是否已有缓存的 M4A 文件（`{task_id}_repaired.m4a`）
- 若无缓存，调用 `m4a_encoder.encode_m4a()` 编码
- 支持 Range 请求（断点续传 + 多线程下载）
- Content-Type: `audio/mp4`（M4A 的标准 MIME 类型）
- 下载完成后**不删除** M4A 缓存（与 MP3 不同，ALAC 无损值得缓存复用）

#### 3. 修改前端 `DownloadModal.tsx`

在每个下载区域（合并轨/人声轨/伴奏轨/单轨）添加 M4A 下载按钮：

- 新增 `handleDownloadM4a` 回调函数，调用 `/api/v1/download-m4a/{taskId}`
- 新增 `m4aLoading` 和 `m4aError` 状态
- 按钮样式：使用橙色/琥珀色主题，与 WAV（青色）和 MP3（绿色）区分
- 按钮文案：`⬇ 下载 M4A (ALAC无损)`
- 按钮排列：WAV | M4A | MP3，从左到右按品质排列

#### 4. 更新前端文件名生成

- `handleDownloadM4a` 中下载文件名后缀改为 `.m4a`
- 双轨导出的文件名模板中增加 `.m4a` 替换逻辑

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/services/m4a_encoder.py` | 新建 | M4A/ALAC 编码模块 |
| `backend/api/routes.py` | 修改 | 新增 `/download-m4a/{task_id}` 端点 |
| `src/components/DownloadModal.tsx` | 修改 | 新增 M4A 下载按钮和逻辑 |

## 不需要变更的文件

- `backend/config.py` — `ALLOWED_EXTENSIONS` 已包含 `.m4a`
- `backend/services/audio_loader.py` — 已支持 ALAC 解码
- `src/components/AudioUploader.tsx` — 已使用 `audio/*` accept
- `backend/services/render.py` — 渲染仍输出 WAV，M4A 是交付格式转换

## 测试要点

1. M4A 编码：WAV → M4A/ALAC 转码正确，文件可播放
2. 下载端点：单轨/双轨/Range 请求均正常
3. 前端：M4A 按钮交互正确，loading/error 状态正常
4. 兼容性：ffmpeg 不可用时优雅降级（按钮禁用 + 提示）
5. 缓存：M4A 文件缓存复用，不重复编码

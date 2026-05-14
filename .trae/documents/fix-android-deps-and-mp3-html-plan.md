# 修复安卓端依赖缺失 + MP3 返回 HTML 问题

## 问题总结

### 问题 1：`requirements_android.txt` 缺少 `lameenc`
- `backend/requirements.txt` 包含 `lameenc>=1.8`，但 `backend/requirements_android.txt` **没有**
- `deploy/setup_android.sh` 第67行使用 `requirements_android.txt` 安装依赖，**不是** `requirements.txt`
- 导致安卓端 `_wav_to_mp3()` 调用 `import lameenc` 时失败

### 问题 2：`setup_android.sh` 依赖验证漏掉 `lameenc`
- 第76-82行验证了 numpy, scipy, pydantic, fastapi, miniaudio, soundfile, pytest
- **没有验证 `lameenc`**，部署时无法发现缺少此关键依赖

### 问题 3：缺少自动化依赖测试
- 没有测试验证所有必需依赖可正常 import
- `backend/check_deps.py` 检查的是 `requirements.txt`（完整清单），不适用于安卓端
- `backend/main.py` 的 `check_dependencies()` 也未检查 `lameenc`

### 问题 4：`SERVE_STATIC=1` 模式下 catch-all 路由可能拦截 API 请求
- `app.py` 第151行 `@app.get("/{full_path:path}")` 会拦截所有未匹配的 GET 请求并返回 `index.html`（`text/html`）
- 当 API 路由因缺少依赖返回 500 时，若路由匹配异常，catch-all 可能返回 HTML
- 前端收到 `Content-Type: text/html` 而不是 `audio/mpeg`，报错"服务器返回了非音频内容"

### 问题 5：前端 `handleDownloadMp3` 的 `<a>` 标签下载方式存在隐患
- 先用 `fetch` 检查响应，再用 `<a>` 标签触发第二次 GET 请求
- 如果后端 catch-all 返回 HTML，`fetch` 检查会失败，但 `<a>` 标签下载也可能拿到 HTML

---

## 修改方案

### 1. `backend/requirements_android.txt` — 添加缺失依赖

添加 `lameenc>=1.8` 和 `psutil>=5,<7`：
- `lameenc`：MP3 编码必需，当前 `_wav_to_mp3` 的核心依赖
- `psutil`：内存监控需要
- `numpy` 和 `scipy` 已在 `setup_android.sh` 中通过 `pkg install python-numpy python-scipy` 预装，不需要重复添加到 pip 清单
- `noisereduce` 在 `setup_android.sh` 第152行已注明 Termux 不支持，跳过

### 2. `deploy/setup_android.sh` — 添加 `lameenc` 验证

在第76-82行的依赖验证块中，添加 `lameenc` 检查：
```bash
python -c "import lameenc; print(f'  lameenc OK')" 2>/dev/null || echo -e "${RED}  lameenc 未安装！MP3编码将不可用${NC}"
```

### 3. 新增 `backend/tests/test_dependencies.py` — 自动化依赖检查测试

创建自动化测试，验证所有必需的 Python 包均可正常 import：
- 读取 `requirements_android.txt`，逐一尝试 `import` 每个包
- 对 `lameenc` 做额外验证：确认 `lameenc.Encoder` 可用
- 对 `soundfile` 做额外验证：确认可读取 WAV
- 明确标记哪些是必需（测试失败） vs 可选（测试跳过）
- 测试命名：`test_android_requirements_all_importable`

### 4. `backend/app.py` — catch-all 路由添加 API 路径保护

在第151行的 `serve_spa` 函数中，在返回 `index.html` 之前检查路径前缀：
- 如果 `full_path` 以 `api/` 开头 → 返回 `JSONResponse(status_code=404, content={"detail": "API endpoint not found"})`
- 确保 API 请求即使落入 catch-all，也返回 JSON 而非 HTML

### 5. `backend/main.py` — `check_dependencies()` 添加 `lameenc` 检查

在第12-39行的 `check_dependencies()` 中，添加 `lameenc` 验证：
```python
try:
    import lameenc
    print("  lameenc 已安装 (MP3编码)")
except ImportError:
    print("  lameenc 未安装，MP3下载不可用 (pip install lameenc)")
```

### 6. 前端 `DownloadModal.tsx` — `handleDownloadMp3` 改进

当前流程：`fetch` 检查 → 成功后用 `<a>` 标签再次请求

改进为：当 `fetch` 检查成功（200 + audio Content-Type）后，不创建 `<a>` 标签发起二次请求，而是直接用 `fetch` 返回的 `Response` 创建 blob 下载：
- 移除第二次 GET 请求（消除二次请求被 catch-all 拦截的风险）
- 直接用 `res.blob()` 获取音频数据
- 用 `URL.createObjectURL(blob)` 创建临时下载链接

这样前端就只发一次请求，拿到正确数据后直接 blob 下载。

---

## 修改文件清单

| # | 文件 | 修改类型 | 说明 |
|---|------|---------|------|
| 1 | `backend/requirements_android.txt` | 修改 | 添加 `lameenc>=1.8` 和 `psutil>=5,<7` |
| 2 | `deploy/setup_android.sh` | 修改 | 添加 `lameenc` 验证检查 |
| 3 | `backend/tests/test_dependencies.py` | **新建** | 自动化依赖完整性测试 |
| 4 | `backend/app.py` | 修改 | catch-all 路由添加 API 路径保护 |
| 5 | `backend/main.py` | 修改 | `check_dependencies()` 添加 `lameenc` 检查 |
| 6 | `src/components/DownloadModal.tsx` | 修改 | `handleDownloadMp3` 改用 blob 下载，消除二次请求 |

---

## 验证步骤

1. **运行依赖测试**：`cd /workspace && python -m pytest backend/tests/test_dependencies.py -v`
2. **运行全部已有测试**：`cd /workspace && python -m pytest backend/tests/ -v`（确保不破坏现有功能）
3. **Android 打包**：`bash scripts/build_android_release.sh`（确认打包成功）
4. **启动开发环境**：`bash scripts/start_dev.sh` + `OpenPreview`（验证 MP3 下载功能正常）
5. **手动验证**：
   - 上传一个 WAV 文件，完成修复
   - 点击"下载 MP3"
   - 确认返回的是 `.mp3` 文件，不是 `.mp3.html`
   - 确认 MP3 文件可以正常播放

---

## 风险与注意事项

- `lameenc` 在 Termux 上需要 `clang` 和 `rust` 编译。`setup_android.sh` 已安装这些（第40-41行），所以 pip 安装应该可以
- `numpy` 和 `scipy` 在 Termux 上通过 pkg 预装，**不**添加到 `requirements_android.txt`，避免 pip 尝试覆盖 pkg 版本
- catch-all 路由的 API 路径保护是防御性措施，即使路由顺序正确也不会产生副作用
- 前端 blob 下载方式在超大文件时可能占用较多内存，但 MP3 文件通常很小（<50MB），风险可控
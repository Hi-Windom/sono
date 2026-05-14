# 修复计划：下载MP3结果为.mp3.html（第二轮修复）

---

## 根因分析

### 核心问题
`handleDownloadMp3`（DownloadModal.tsx L114-138）使用 `fetch` → `res.blob()` → `URL.createObjectURL(blob)` → `a.download` 的方式下载。此机制存在关键缺陷：

**当后端返回非 `audio/mpeg` 内容时**（如代理错误页、中间件干扰、后端错误页等），`res.blob()` 创建了一个 `text/html` 类型的 blob。浏览器看到 `a.download = '{taskId}.mp3'` 但 blob 内容为 HTML，**自动追加 `.html`** → 文件名变为 `{taskId}.mp3.html`。

### 之前修复为什么没生效
之前的修复只改了：
1. ✅ 后端 Content-Disposition 添加 `filename` 回退（routes.py 3处）
2. ✅ CacheManagerPage `handleDownloadDelivery` 添加 `download` 属性

但 `handleDownloadMp3` 的核心下载机制未改变，它仍然使用 blob 方式，仍然受 Content-Type 不匹配影响。

### 为什么 HEAD 预检 + 直接 `<a>` 下载更好
- **HEAD 请求**：只获取响应头，不下载内容，可提前检查 Content-Type 和状态码
- **直接 `<a>` 标签**：浏览器原生下载，download 属性提供文件名，不受 blob Content-Type 影响
- **后端 Content-Disposition 作为回退**：即使 download 属性不被支持，Content-Disposition 也能提供文件名

---

## 修改文件

### 1. `src/components/DownloadModal.tsx` — 重写 `handleDownloadMp3`

**改动前**（L114-138）：
```typescript
const handleDownloadMp3 = useCallback(async (taskId: string) => {
    setMp3Loading(true);
    setMp3Error(null);
    try {
        const res = await fetch(`/api/v1/download-mp3/${taskId}`);
        if (!res.ok) throw new Error(`MP3 下载失败: HTTP ${res.status}`);
        const blob = await res.blob();
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = `${taskId}.mp3`;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            URL.revokeObjectURL(blobUrl);
            document.body.removeChild(a);
        }, 5000);
    } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setMp3Error(msg);
    } finally {
        setMp3Loading(false);
    }
}, []);
```

**改动后**：
```typescript
const handleDownloadMp3 = useCallback(async (taskId: string) => {
    setMp3Loading(true);
    setMp3Error(null);
    try {
        const res = await fetch(`/api/v1/download-mp3/${taskId}`, { method: 'HEAD' });
        if (!res.ok) throw new Error(`MP3 下载失败: HTTP ${res.status}`);
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
        const msg = e instanceof Error ? e.message : String(e);
        setMp3Error(msg);
    } finally {
        setMp3Loading(false);
    }
}, []);
```

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `src/components/DownloadModal.tsx` | `handleDownloadMp3` 改为 HEAD 预检 + 直接 `<a>` 下载 |

---

## 验证步骤

1. **运行测试**：`python -m pytest backend/tests/test_api_and_db.py::TestDownloadContentDisposition -v`
2. **构建前端**：`npm run build`
3. **Android 打包**：`bash scripts/build_android_release.sh`
4. **启动 dev**：`bash scripts/start_dev.sh` + `OpenPreview`
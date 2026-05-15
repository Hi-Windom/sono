# 修复计划：MP3 下载 405 Method Not Allowed

## 根因

上一轮修复将 `handleDownloadMp3` 的 `fetch` 改为 `{ method: 'HEAD' }`，但后端 `/api/v1/download-mp3/{task_id}` 端点用 `@router.get` 定义，**只接受 GET 请求** → 返回 405 Method Not Allowed。

## 修复方案

`handleDownloadMp3` 使用 **GET** 请求（默认）做预检，检查状态码和 Content-Type，然后通过直接 `<a>` 标签触发下载。预检 GET 的响应体不会被消费，浏览器会自动回收。

### `src/components/DownloadModal.tsx`

```typescript
const handleDownloadMp3 = useCallback(async (taskId: string) => {
    setMp3Loading(true);
    setMp3Error(null);
    try {
      const res = await fetch(`/api/v1/download-mp3/${taskId}`);
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

## 修改文件

| 文件 | 修改内容 |
|------|---------|
| `src/components/DownloadModal.tsx` | `fetch` 去掉 `{ method: 'HEAD' }`，恢复默认 GET |

## 验证步骤

1. 构建前端：`npm run build`
2. Android 打包：`bash scripts/build_android_release.sh`
3. 启动 dev：`bash scripts/start_dev.sh` + `OpenPreview`
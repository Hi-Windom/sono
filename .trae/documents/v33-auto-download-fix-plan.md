# v3.3 自动下载修复计划

## 问题

用户说"根本没有自动下载"，之前的修复思路错了。秒下不是设置状态显示弹窗，而是**直接触发下载**。

## 现状分析

`DownloadModal.tsx` 中的 `handleDownload` 函数（L152-230）执行实际下载：
- fetch 文件
- 显示进度
- 创建 Blob URL
- 触发 `<a>.click()` 下载

但这个函数在组件内部，无法从外部调用。

## 修复方案

### 方案：提取下载函数

将 `handleDownload` 逻辑提取为独立工具函数，渲染完成后直接调用。

#### 步骤 1：创建独立下载函数

新建 `src/utils/download.ts`：

```typescript
export async function downloadFile(
  url: string, 
  filename: string,
  onProgress?: (progress: number) => void
): Promise<void> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`下载失败: HTTP ${res.status}`);
  
  const contentLength = parseInt(res.headers.get('Content-Length') || '0', 10);
  const reader = res.body?.getReader();
  if (!reader) throw new Error('ReadableStream not supported');
  
  const chunks: Uint8Array[] = [];
  let loaded = 0;
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    loaded += value.length;
    if (contentLength > 0) {
      onProgress?.(loaded / contentLength);
    }
  }
  
  const blob = new Blob(chunks, { type: 'audio/wav' });
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(blobUrl);
    document.body.removeChild(a);
  }, 5000);
}
```

#### 步骤 2：单轨渲染完成后直接下载

`useAudioProcessor.ts` `applySettings` 中：

```typescript
renderAndDownload(...).then(result => {
  if (result?.downloadUrl) {
    // 直接触发下载，不显示弹窗
    downloadFile(result.downloadUrl, result.fileName);
  }
});
```

#### 步骤 3：双轨渲染完成后直接下载

`RepairPage.tsx` `onComplete` 和 `handleUseDualCache` 中：

```typescript
const result = await renderAndDownload(...);
if (result) {
  // 直接触发下载
  downloadFile(result.downloadUrl, result.fileName);
}
```

#### 步骤 4：清理错误的弹窗代码

- 移除 `RepairPage.tsx` 中之前添加的 `instantDownloadInfo` 设置代码
- 移除 `useEffect` 监听 `autoRenderInfo` 的代码
- 保留 `handleSwitchToSingleTrack` 中的清理逻辑（还是有用的）

## 文件变更

| 文件 | 操作 |
|------|------|
| `src/utils/download.ts` | 新建：提取 `downloadFile` 函数 |
| `src/hooks/useAudioProcessor.ts` | 单轨渲染完成后调用 `downloadFile` |
| `src/pages/RepairPage.tsx` | 双轨渲染完成后调用 `downloadFile`，清理错误代码 |

## 注意事项
1. 下载是异步的，需要处理错误
2. 大文件下载需要时间，可能需要进度提示（可以用 toast 或简单的 console.log）
3. 双轨模式下可能需要下载多个文件（vocal + accompaniment + merged）
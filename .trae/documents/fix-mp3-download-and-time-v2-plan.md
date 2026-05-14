# 修复计划：MP3下载为.mp3.html + 前端时间显示错误

---

## Bug 1: 下载MP3结果是.mp3.html

### 根因

**后端**：3个下载端点（`download_audio`、`download_file`、`download_mp3`）的 Content-Disposition 只使用了 RFC 5987 的 `filename*` 格式，**缺少 `filename` 回退参数**：

```python
disposition = f"attachment; filename*=UTF-8''{encoded_name}"
```

部分浏览器（尤其是移动端浏览器）不支持 `filename*` 格式，回退时使用 URL 路径作为文件名。URL 为 `/api/v1/download-mp3/{taskId}`（无扩展名），浏览器默认追加 `.html`。

**前端**：`CacheManagerPage.tsx` 的 `handleDownloadDelivery`（L266-274）创建 `<a>` 标签时**没有设置 `download` 属性**，且使用了 `target="_blank"`，浏览器在新标签页中打开 URL，依赖 Content-Disposition 确定文件名。

### 修复方案

1. **`backend/api/routes.py`** — 3个下载端点的 Content-Disposition 都同时添加 `filename`（ASCII回退）和 `filename*`（Unicode支持）：
   ```python
   disposition = f'attachment; filename="{download_name}"; filename*=UTF-8\'\'{encoded_name}'
   ```
   - L1405：`download_audio` 端点
   - L1479：`download_file` 端点
   - L1563：`download_mp3` 端点

2. **`src/pages/CacheManagerPage.tsx`** — `handleDownloadDelivery` 添加 `download` 属性并移除 `target="_blank"`：
   ```typescript
   a.download = filename;
   // 移除 a.target = '_blank' 和 a.rel = 'noopener noreferrer'
   ```

---

## Bug 2: 前端时间显示差几个小时

### 根因

**后端**：SQLite 的 `CURRENT_TIMESTAMP` 返回 UTC 时间，格式为 `"2026-05-14 03:00:00"`（空格分隔，无时区信息）。

**前端**：使用 `new Date("2026-05-14 03:00:00").toLocaleString('zh-CN')` 解析此字符串，行为因浏览器而异：
- Chrome/V8：将空格分隔格式视为 UTC → 显示为 UTC+8 → **正确**
- Firefox/SpiderMonkey：将空格分隔格式视为本地时间 → 显示 UTC 原值 → **差8小时**

### 受影响的位置

| 文件 | 行号 | 代码 | 时间来源 |
|------|------|------|---------|
| `src/pages/ComparePage.tsx` | 615 | `new Date(task.created_at).toLocaleString('zh-CN')` | 后端 SQLite `CURRENT_TIMESTAMP` |
| `src/pages/CacheManagerPage.tsx` | 624 | `new Date(entry.created_at).toLocaleString()` | 后端 SQLite `CURRENT_TIMESTAMP` |
| `src/pages/CacheManagerPage.tsx` | 52 | `new Date(dateString)` (formatDateTime) | 后端 SQLite `CURRENT_TIMESTAMP` |
| `src/components/AIRepairPanel.tsx` | 644 | `new Date(selectedCache.mtime).toLocaleString('zh-CN')` | 后端文件 mtime |

**不受影响的**：`completedAt`（DownloadModal.tsx L479）使用 `new Date().toISOString()`（ISO 8601 格式带 Z），解析正确。

### 修复方案

**方案选择**：在后端修复（源头修复，所有前端消费者受益）。

1. **`backend/api/routes.py`** — 返回 `created_at` 等时间字段时，将 SQLite 的空格分隔格式转为 ISO 8601（追加 `Z`）：
   - L2206：`"created_at": row["created_at"]` → `"created_at": _format_ts(row["created_at"])`
   - 同时检查其他返回 `created_at`/`updated_at` 的 API 端点

2. **`backend/database.py`** — 添加工具函数 `_format_timestamp(ts)`：
   ```python
   def _format_timestamp(ts: str | None) -> str | None:
       if ts is None:
           return None
       # SQLite CURRENT_TIMESTAMP 返回 "2026-05-14 03:00:00" (UTC)
       # 转为 ISO 8601: "2026-05-14T03:00:00Z"
       ts_str = str(ts).replace(" ", "T")
       if not ts_str.endswith("Z") and "+" not in ts_str and "Z" not in ts_str:
           ts_str += "Z"
       return ts_str
   ```

3. **`backend/tests/test_api_and_db.py`** — 添加测试验证时间格式：
   - 上传文件后检查返回的 `created_at` 是否以 `Z` 结尾
   - 验证任务列表的 `created_at` 格式

---

## 测试完善

### 现有测试问题
- `test_api_and_db.py` 有测试但未覆盖下载 Content-Disposition 格式
- `test_mp3_upload.py` 有上传测试但未验证 Content-Disposition
- 无时间格式测试

### 新增/修改的测试

1. **`backend/tests/test_api_and_db.py`** 追加：
   - `test_download_content_disposition` — 调用 `/api/v1/download/{task_id}` 验证 Content-Disposition 包含 `filename=` 和 `filename*=`
   - `test_download_mp3_content_disposition` — 调用 `/api/v1/download-mp3/{task_id}` 验证 Content-Disposition 格式
   - `test_timestamp_format` — 上传后检查返回时间以 `Z` 结尾
   - `test_task_list_timestamp` — 任务列表的 `created_at` 以 `Z` 结尾

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `backend/api/routes.py` | 3处 Content-Disposition 添加 `filename` 回退；时间字段添加 `_format_timestamp()` 转换 |
| `backend/database.py` | 新增 `_format_timestamp()` 工具函数 |
| `src/pages/CacheManagerPage.tsx` | `handleDownloadDelivery` 添加 `download` 属性 |
| `backend/tests/test_api_and_db.py` | 追加下载 Content-Disposition 和时间格式测试 |

---

## 验证步骤

1. **运行测试**：`python -m pytest backend/tests/test_api_and_db.py -v`
2. **运行全部测试**：`python -m pytest backend/tests/ -v`
3. **构建前端**：`npm run build`
4. **Android 打包**：`bash scripts/build_android_release.sh`
5. **启动 dev**：`bash scripts/start_dev.sh` + `OpenPreview`
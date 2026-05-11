# Sono 缓存架构技术文档

## 概述

本文档详细描述 Sono 音频修复系统中使用的所有缓存机制，包括后端数据缓存和前端状态缓存。记录架构设计、实现细节以及开发过程中的经验教训。

---

## 一、后端数据缓存

### 1.1 修复结果缓存 (Repair Result Cache)

**目的**：避免对相同文件和相同参数重复执行修复计算

**数据模型**：
```
(file_hash + repair_params) → (output_path + output_size + repair_result + detection_results)
```

**存储位置**：SQLite `tasks` 表
- `file_hash`: 文件内容哈希 (SHA-256)
- `params`: JSON 序列化的修复参数
- `output_path`: 修复后文件路径
- `output_size`: 文件大小（用于完整性校验）
- `repair_result`: 修复元数据
- `detection_result`: 原始文件AI检测结果
- `repaired_detection_result`: 修复后文件AI检测结果

**查询实现**：`backend/database.py::find_repair_cache()`

```python
def find_repair_cache(file_hash: str, params: dict) -> TaskDict | None:
    # 1. 查询所有同 hash 的任务（按时间倒序）
    # 2. 验证 output_path 存在且大小 > 10KB
    # 3. JSON 规范化比较参数（sort_keys）
    # 4. 返回第一个匹配项
```

**API 端点**：`POST /api/v1/cache/lookup`

**关键设计决策**：
- ❌ **不依赖 `status` 字段**：早期实现错误地加了 `status='completed'` 过滤，导致任务状态变化时缓存失效
- ✅ **依赖输出文件存在性**：真正的完成标志是输出文件存在且大小合理
- ✅ **JSON 规范化比较**：使用 `json.dumps(params, sort_keys=True)` 确保参数比较不受键顺序影响

---

### 1.2 文件上传缓存 (Upload Deduplication)

**目的**：相同文件只上传一次

**流程**：
1. 前端计算文件 hash
2. `POST /api/v1/check-hash` 查询后端
3. 如果存在且任务有效，复用现有 task_id
4. 否则执行上传

**实现**：`backend/api/routes.py::check_hash()`

---

### 1.3 AI 检测缓存

**目的**：避免对相同文件重复执行 AI 检测

**存储**：`tasks` 表的 `detection_result` 和 `repaired_detection_result` 字段

**触发条件**：
- 原始文件检测：上传后首次检测
- 修复后检测：修复完成后自动检测

---

### 1.4 音频特征缓存 (Training Features)

**目的**：训练数据特征提取结果持久化

**存储**：`backend/storage/training_features/{hash}.json`

**使用场景**：算法版本升级时，复用已提取的特征进行重新训练

---

## 二、前端状态缓存

### 2.1 IndexedDB 会话持久化

**目的**：页面刷新后恢复用户工作流

**存储位置**：`src/utils/sessionDB.ts`

**存储内容**：
```typescript
interface SessionData {
  file: File | null;           // 音频文件（Blob）
  fileName: string;
  fileSize: number;
  fileHash: string;            // 文件内容哈希
  taskId: string;              // 后端任务ID
  backendAvailable: boolean;
  hasBeenProcessed: boolean;
  wavInfo: string;             // WAV头信息JSON
  repairResult: string;        // 修复结果JSON
}
```

**恢复时机**：`useAudioProcessor.ts` 中的 `useEffect`，在 `backendAvailable` 变为 true 时触发

**关键问题与修复**：

#### 问题：替换文件后被旧会话覆盖
**现象**：用户上传新文件后，系统自动恢复旧会话，导致新文件丢失

**根因**：
```javascript
// loadAudioFile 中上传成功后设置 backendAvailable = true
setBackendAvailable(true);

// 触发会话恢复 useEffect
useEffect(() => {
  if (backendAvailable && pendingSessionRef.current) {
    restoreSession(pendingSessionRef.current); // 恢复旧会话！
  }
}, [backendAvailable]);
```

**修复**：上传新文件后清除 pending 会话并标记已恢复
```javascript
pendingSessionRef.current = null;
sessionRestoredRef.current = true;
```

---

### 2.2 React State 缓存

**目的**：避免重复计算，提升渲染性能

**实现**：`useMemo` 和 `useCallback`

**关键缓存**：
- `currentParams`：当前修复参数（用于缓存键）
- `currentParamsForCache`：映射到后端的参数格式
- `formatBytes`：文件大小格式化

---

### 2.3 音频缓冲区缓存

**存储位置**：`useAudioProcessor.ts` 中的 state

```typescript
audioBuffer: AudioBuffer | null;        // 原始音频
backendProcessedBuffer: AudioBuffer | null;  // 修复后音频
```

**生命周期**：
- 加载新文件时重置
- 修复完成后填充
- 页面刷新后从 IndexedDB 恢复（需重新解码）

---

## 三、缓存一致性策略

### 3.1 写入时验证

**后端**：
- 修复完成后验证输出文件大小 > 10KB
- 无效输出不写入缓存

**前端**：
- 缓存命中后二次确认（用户弹窗）
- 用户可选择重新执行修复

### 3.2 读取时验证

```python
# 1. 文件存在性检查
if not os.path.exists(output_path):
    return None

# 2. 文件大小检查（防止损坏）
if size < 10240:
    return None

# 3. 参数精确匹配
if json.dumps(stored_params, sort_keys=True) != json.dumps(params, sort_keys=True):
    return None
```

### 3.3 清理策略

**自动清理**：
- 任务管理器定期清理过期任务
- 输出文件与数据库记录同步删除

**手动清理**：
- `CacheManager` 组件提供手动清除功能

---

## 四、经验教训

### ❌ 错误1：缓存查询依赖任务状态

**早期实现**：
```python
# 错误！
rows = conn.execute(
    "SELECT * FROM tasks WHERE file_hash = ? AND status = 'completed'",
    (file_hash,)
).fetchall()
```

**问题**：任务状态会变化（completed → repairing），导致缓存时灵时不灵

**正确做法**：
```python
# 正确！查所有任务，用输出文件存在性判断
rows = conn.execute(
    "SELECT * FROM tasks WHERE file_hash = ? ORDER BY updated_at DESC",
    (file_hash,)
).fetchall()
# 然后验证 output_path 存在且 size > 10KB
```

---

### ❌ 错误2：前端 hash 计算与后端不一致

**问题**：前端用 `arrayBuffer` 计算 hash，后端可能读取文件时编码不同

**解决**：统一使用原始二进制内容计算 SHA-256

---

### ❌ 错误3：会话恢复覆盖新文件

**问题**：上传新文件后，`backendAvailable` 变化触发旧会话恢复

**解决**：上传成功后清除 `pendingSessionRef`，阻止恢复逻辑

---

### ❌ 错误4：嵌套条件逻辑导致代码难以维护

**早期 `applySettings` 实现**：
```javascript
if (hasCachedResult) {
    if (useCache) {
        backendSkipped = true;
    } else {
        needsNewTask = true;
    }
}

if (!currentTaskId || needsNewTask) {
    // 上传...
}

// Promise 结果处理还要判断 backendSkipped
if (backendSkipped) {
    // 特殊处理...
}
```

**重构后**：扁平双路径
```javascript
// 路径A：缓存查询
const cache = await lookupRepairCache(hash, params);
if (cache.found && userConfirm()) {
    setStates(cache.data);
    return;  // 直接返回，不进 Promise 链
}

// 路径B：正常修复
uploadAndRepair();
```

---

### ✅ 最佳实践1：数据驱动缓存

缓存应该是纯数据映射，与业务逻辑状态解耦：
```
(fileHash + params) → (outputFile)
```
而不是：
```
(fileHash + params + taskStatus + ...) → (outputFile)
```

---

### ✅ 最佳实践2：参数规范化

使用 JSON `sort_keys` 确保参数比较不受键顺序影响：
```python
json.dumps(params, sort_keys=True, ensure_ascii=False)
```

---

### ✅ 最佳实践3：完整性校验

缓存命中后验证文件大小，防止文件损坏或部分写入：
```python
if size < 10240:  # 10KB 阈值
    return None  # 视为无效缓存
```

---

### ✅ 最佳实践4：用户确认

缓存命中后给用户选择权：
- 使用缓存结果（快速）
- 重新执行修复（可能参数有细微差别）

---

## 五、调试工具

### 5.1 后端日志

**端点**：`GET /api/v1/logs?lines=2000`

**关键日志标记**：
- `[cache-lookup]`：缓存查询过程
- `[/upload]`：文件上传
- `[applySettings]`：修复流程

### 5.2 前端日志

**控制台输出**：`writeLog()` 函数写入 IndexedDB，同时输出到 console

---

## 六、相关文件

| 文件 | 说明 |
|------|------|
| `backend/database.py` | 数据库操作，含 `find_repair_cache()` |
| `backend/api/routes.py` | API 端点，含 `/cache/lookup` |
| `src/services/backendApi.ts` | 前端 API 调用 |
| `src/hooks/useAudioProcessor.ts` | 核心状态管理，含缓存逻辑 |
| `src/utils/sessionDB.ts` | IndexedDB 会话存储 |

---

## 七、版本历史

- **v1.0**：基础修复结果缓存（有 status 过滤 bug）
- **v2.0**：重构为纯数据驱动缓存，去掉 status 依赖
- **v2.1**：修复文件替换后会话覆盖问题

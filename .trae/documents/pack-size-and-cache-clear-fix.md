# 打包体积优化 & 缓存清除后上传识别修复

## 摘要

两个独立问题：

1. **打包体积优化**：`release_android.tar.gz` 当前 1.9M，后端源码（.py 文件）约 1.3M。改为只打包 .pyc 编译文件，同时清理不必要的文件（tests/、sono.db 等），可显著减小体积。

2. **缓存清除后上传识别修复**：用户通过 CacheManagerPage 调用 `POST /cache/clear-all` 后，所有任务记录和上传文件被删除。但前端 localStorage 中持久化的文件哈希仍然存在，导致：
   - 页面刷新后，持久化的哈希让前端认为文件仍有效，点击修复时调用 `repairDualFromHash` → 后端 `find_task_by_hash` 返回 None → 404 "人声音频不存在"
   - 重新选择相同文件时，`handleDualTrackFileReplace` 因哈希匹配跳过上传 → 修复时同样失败
   - 用户看到"人声音频不存在"错误感到困惑（"讽刺"）

---

## 当前状态分析

### Issue 1: 打包体积

**构建脚本** (`scripts/build_android_release.sh`):
- 复制整个 `backend/` 目录
- 运行 `compileall` 生成 .pyc
- 然后**删除所有 `__pycache__`**（.pyc 文件丢失）
- 保留所有 .py 源文件
- 删除 `training/`、`storage/`、`.venv`、日志文件

**当前打包内容**（未压缩大小）:
| 内容 | 大小 |
|------|------|
| backend/（.py 源文件） | 1.3M |
| backend/tests/ | 448K |
| backend/sono.db（开发数据库） | ~100K+ |
| backend/services/dsp_native/Makefile, .c 文件 | 少量 |
| backend/services/repair/QUALITY_RULES.md | 少量 |
| dist/（前端构建产物） | 5.4M |
| deploy 脚本 | 少量 |

**关键发现**：
- `__pycache__` 总大小也是约 1.3M（与 .py 相当），但当前脚本删除了它们
- `tests/`（448K）和 `sono.db` 不应出现在发布包中
- 构建脚本中 `rm -rf "$PKG_DIR/backend/__pycache__"` 已经覆盖所有子目录，后续的 `api/__pycache__` 和 `services/__pycache__` 是冗余的

### Issue 2: 缓存清除后上传识别

**缓存清除流程**（`POST /cache/clear-all`，routes.py:2369）:
1. 删除 `UPLOAD_DIR` 和 `OUTPUT_DIR` 中的所有文件
2. 执行 `DELETE FROM tasks` 清空数据库
3. 返回释放的字节数

**前端状态持久化**（`repairSessionStore`，localStorage）:
- `dualTrackVocalFileHash`、`dualTrackAccompanimentFileHash` 等通过 zustand persist 保存在 localStorage
- 页面刷新后这些哈希仍然存在

**问题场景 A：刷新后直接点击修复**
1. 页面挂载（RepairPage.tsx:507-553）：
   - `lookupDualRepairCache` → 失败（DB 无记录）
   - `fetchFileInfoByHash` → 失败（DB 无记录）
   - 但哈希仍然保留在 store 中
2. 用户点击"修复" → `handleDualTrackRepair`
3. 缓存查询失败 → 走 `repairDualFromHash` 分支
4. 后端 `find_task_by_hash` 返回 None → 404 "人声音频不存在，请重新上传"
5. 前端 catch 到错误，显示"双轨修复失败: 人声音频不存在，请重新上传"

**问题场景 B：重新选择相同文件后点击修复**
1. 用户重新选择相同文件 → `handleDualTrackFileReplace`（RepairPage.tsx:288）
2. 哈希匹配（line 311）→ 跳过上传，仅清除 task_id
3. 用户点击"修复" → 同场景 A 步骤 3-5

**根本原因**：
- 前端用哈希匹配作为"文件已存在"的判断依据，但哈希只证明文件内容相同，不证明后端仍有该文件的记录
- 缓存清除后，后端没有恢复文件记录的途径

---

## 修改方案

### Issue 1: 打包体积优化

**目标**：减小 `release_android.tar.gz` 体积

**修改文件**：`scripts/build_android_release.sh`

**具体改动**：

1. **删除 `backend/tests/`**（节省 ~448K 未压缩）
   - 在清理阶段添加 `rm -rf "$PKG_DIR/backend/tests"`

2. **删除 `backend/sono.db`**（开发数据库，不应进入发布包）
   - 在清理阶段添加 `rm -f "$PKG_DIR/backend/sono.db"`

3. **删除非必要的开发文件**
   - `rm -f "$PKG_DIR/backend/services/dsp_native/Makefile"`
   - `rm -f "$PKG_DIR/backend/services/dsp_native/dsp_core.c"`
   - `rm -f "$PKG_DIR/backend/services/repair/QUALITY_RULES.md"`
   - `rm -f "$PKG_DIR/backend/watchdog.sh"`

4. **保留 `__pycache__`，删除 .py 源文件**（用户核心需求）
   - 删除 `rm -rf "$PKG_DIR/backend/__pycache__"` 等行
   - 添加：保留 `__pycache__` 目录，删除所有 .py 文件（除 `main.py`）
   - 使用 `find "$PKG_DIR/backend" -name '*.py' -not -name 'main.py' -delete`
   - 注意：`__pycache__` 中的 .pyc 文件是 Python 版本相关的，需确保目标设备 Python 版本一致

5. **清理冗余的 `__pycache__` 删除命令**
   - 当前有 3 行：`backend/__pycache__`、`backend/api/__pycache__`、`backend/services/__pycache__`
   - 第一行已递归覆盖所有子目录，后两行冗余

**预期效果**：
- 移除 tests/（448K）、sono.db（~100K）、开发文件（~50K）
- .pyc 替代 .py（大小相近，但满足用户"不打包源码"的需求）
- 总体预计减少 ~500-700K 未压缩大小，压缩后预计减少 ~200-300K

### Issue 2: 缓存清除后上传识别修复

**目标**：缓存清除后，前端能正确检测到后端状态已失效，引导用户重新上传

**涉及文件**：
- `backend/api/routes.py` — 新增检查端点
- `src/services/backendApi.ts` — 新增 API 调用
- `src/pages/RepairPage.tsx` — 修复上传和修复流程

#### 2.1 新增后端端点 `POST /check-hashes`

**位置**：`backend/api/routes.py`

**功能**：接收文件哈希列表，返回每个哈希是否在 DB 中存在有效任务记录

```python
class CheckHashesRequest(BaseModel):
    hashes: list[str]

@router.post("/check-hashes")
async def check_file_hashes(request: CheckHashesRequest):
    """检查文件哈希是否在 DB 中有有效记录"""
    from database import get_db
    conn = get_db()
    result = {}
    for h in request.hashes:
        row = conn.execute(
            "SELECT id, original_path FROM tasks WHERE file_hash = ? AND original_path != '' LIMIT 1",
            (h,)
        ).fetchone()
        if row and os.path.exists(row["original_path"]):
            result[h] = {"exists": True, "task_id": row["id"]}
        else:
            result[h] = {"exists": False}
    conn.close()
    return {"results": result}
```

#### 2.2 前端新增 `checkFileHashes` API 函数

**位置**：`src/services/backendApi.ts`

```typescript
export async function checkFileHashes(hashes: string[]): Promise<Record<string, boolean>> {
  const res = await fetch('/api/v1/check-hashes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hashes }),
  });
  if (!res.ok) throw new Error('检查文件哈希失败');
  const data = await res.json();
  const result: Record<string, boolean> = {};
  for (const [hash, info] of Object.entries(data.results)) {
    result[hash] = (info as any).exists;
  }
  return result;
}
```

#### 2.3 修复页面挂载时的状态验证

**位置**：`src/pages/RepairPage.tsx`，mount useEffect（~line 507）

**改动**：在现有缓存查询和文件信息查询之后，添加哈希有效性检查

```typescript
// 在 mount useEffect 末尾添加：
try {
  const hashStatus = await checkFileHashes([dualTrackVocalFileHash, dualTrackAccompanimentFileHash]);
  if (cancelled) return;
  const vocalExists = hashStatus[dualTrackVocalFileHash];
  const accExists = hashStatus[dualTrackAccompanimentFileHash];
  if (!vocalExists || !accExists) {
    console.warn('[双轨] mount 检测到后端文件已失效，清除持久化状态');
    sessionActions.clearDualTrack();
    // 不清除本地 File 对象（用户可能仍持有），但清除哈希和元数据
  }
} catch (e) {
  console.warn('[双轨] mount 哈希检查失败', e);
}
```

#### 2.4 修复文件替换时的哈希跳过逻辑

**位置**：`src/pages/RepairPage.tsx`，`handleDualTrackFileReplace`（~line 310-330）

**改动**：在跳过上传前，先调用后端检查哈希是否有效

```typescript
// 替换原有的简单哈希比较跳过逻辑：
if (type === 'vocal' && newVocalHash === dualTrackVocalFileHash) {
  // 先检查后端是否仍有此文件记录
  try {
    const hashStatus = await checkFileHashes([newVocalHash]);
    if (hashStatus[newVocalHash]) {
      console.log('人声音频未变化且后端仍有记录，跳过重新上传');
      setDualTrackTaskId(null);
      setDualTrackVocalTaskId(null);
      setDualTrackAccompanimentTaskId(null);
      setIsProcessing(false);
      setProcessingStep('');
      setProcessingProgress(0);
      return;
    }
  } catch {}
  // 后端无记录，继续执行上传（不 return）
  console.log('人声音频未变化但后端无记录，重新上传');
}
// 伴奏同理
```

#### 2.5 修复 `repairDualFromHash` 404 时的错误提示

**位置**：`src/pages/RepairPage.tsx`，`handleDualTrackRepair`（~line 436-448）

**改动**：捕获 404 错误，显示更友好的提示

```typescript
} else if (hasHashes) {
  try {
    const result = await repairDualFromHash(...);
    // ... 现有逻辑
  } catch (error: any) {
    if (error?.message?.includes('人声音频不存在') || error?.message?.includes('404')) {
      setBackendError('后端缓存已清除，请重新上传音频文件');
      sessionActions.clearDualTrack();
    } else {
      setBackendError(error instanceof Error ? error.message : '双轨修复失败');
    }
    setIsProcessing(false);
  }
}
```

---

## 假设与决策

1. **Python 版本兼容性**：.pyc 文件包含 Python 版本信息（如 `cpython-312`）。假设目标设备（Termux）使用相同 Python 版本。如果版本不同，`setup_android.sh` 中 `pip install` 后 Python 会重新创建 .pyc。

2. **`main.py` 保留为源码**：入口文件保留 .py 源码，因为 Python 需要它作为启动入口。其他模块通过 `__pycache__` 中的 .pyc 加载。

3. **`checkFileHashes` 失败时的行为**：如果网络错误导致检查失败，保守处理——不清除状态（避免误清除），但也不跳过上传（让用户重新上传）。

4. **不修改 `cache/clear-all` 的行为**：缓存清除仍然删除所有文件和 DB 记录。这是用户主动操作，应当彻底。修复的是前端对缓存清除后的状态检测。

---

## 验证步骤

### Issue 1 验证
```bash
# 重新打包
bash scripts/build_android_release.sh
# 检查产物大小
ls -lh release_android.tar.gz
# 检查包内容（确认没有 .py 文件，有 .pyc 文件）
tar -tzf release_android.tar.gz | head -30
# 检查是否包含 tests/ 和 sono.db
tar -tzf release_android.tar.gz | grep -E 'tests/|sono.db' || echo "已正确排除"
```

### Issue 2 验证
```bash
# 启动开发环境
bash scripts/start_dev.sh
```
1. 上传双轨文件 → 修复成功
2. 打开 CacheManagerPage → 点击"清空所有后端缓存"
3. 返回修复页面 → 刷新页面
4. 验证：持久化哈希被清除，页面显示"请重新上传"
5. 重新选择相同文件 → 验证：文件被重新上传（不跳过）
6. 修复成功
7. 再次清空缓存 → 不刷新页面 → 直接点击修复
8. 验证：显示"后端缓存已清除，请重新上传音频文件"
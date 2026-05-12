# 修复 render_filename 列缺失 + 测试排查 + 构建打包

## 摘要

上一轮已修复数据库 schema 缺失 `render_filename`/`render_result` 列的根因（ALTER TABLE 迁移），并创建了 17 个集成测试。当前剩余 **1 个测试失败** (`test_cache_lookup_ignores_deleted_output`)，需排查修复后完成全量验证和 Android 打包。

## 当前状态分析

### 已完成的修复
| 问题 | 状态 | 修改文件 |
|------|------|----------|
| `no such column: render_filename` | ✅ 已修复 | `backend/database.py` — 添加 ALTER TABLE 迁移 |
| `_run_render` 用 `_ws_send_progress` 而非 `_ws_send_final` | ✅ 已修复 | `backend/api/routes.py` |
| WS 端点不识别 `render_completed` 终态 | ✅ 已修复 | `backend/api/routes.py` |
| WS 路径不匹配 | ✅ 已修复 | `src/services/backendApi.ts` |
| `window.confirm()` 替换为 RepairCacheModal | ✅ 已完成 | 新建 `RepairCacheModal.tsx` + 集成 |
| 集成测试从 0 到 17 个 | ⚠️ 16/17 通过 | `backend/tests/test_api_and_db.py` |

### 剩余问题
**唯一失败测试**: `test_cache_lookup_ignores_deleted_output`
- 位置: `test_api_and_db.py:L175-184`
- 现象: 删除 output 文件后调用 `lookup_repair_cache` 仍返回 `found: True`
- 预期: 应返回 `found: False`
- `find_repair_cache` 逻辑 (database.py:L171-173) 有 `os.path.exists` 检查，理论上应跳过已删文件

## 实施计划

### Step 1: 排查并修复最后一个失败测试

**目标**: 确定 `test_cache_lookup_ignores_deleted_output` 失败根因并修复

**排查方向**:
1. 单独运行该测试，观察详细日志输出
2. 在 `find_repair_cache` 中确认 L171 的 `os.path.exists(output_path)` 是否真的对已删除文件返回 False
3. 检查是否存在 DB 中多条记录导致匹配到其他行的情况
4. 确认 `fresh_db` fixture 的函数作用域隔离是否生效

**可能结论及处理方式**:
- **情况 A**: `find_repair_cache` 逻辑正确，测试有 bug（如路径构造错误、fixture 数据泄漏）→ 修正测试
- **情况 B**: `find_repair_cache` 存在实际 bug（如 output_path 为空时跳过存在性检查）→ 修复 database.py
- **情况 C**: 测试预期本身有误（如设计上允许返回缓存元数据即使文件不存在）→ 调整测试断言

### Step 2: 运行全量测试验证无回归

```bash
# 运行新集成测试
cd /workspace && python -m pytest backend/tests/test_api_and_db.py -v

# 运行原有质量测试
cd /workspace && python -m pytest backend/tests/test_repair_quality.py -v
```

**通过标准**: 全部测试用例通过，无 skip / fail / error

### Step 3: 构建前端

```bash
npm run build
```

**通过标准**: TypeScript 编译无错误，生成 `dist/` 目录

### Step 4: 打包 Android 发布包

```bash
bash scripts/build_android_release.sh
```

**通过标准**: 脚本成功执行，生成 `release_android.tar.gz`

## 涉及文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/tests/test_api_and_db.py` | **修改** | 修复 `test_cache_lookup_ignores_deleted_output` 或调整断言 |
| `backend/database.py` | 可能修改 | 如果发现 find_repair_cache 实际 bug |

## 验证步骤

1. `python -m pytest backend/tests/test_api_and_db.py -v` → 17/17 passed
2. `python -m pytest backend/tests/test_repair_quality.py -v` → all passed
3. `npm run build` → exit 0, dist/ 生成
4. `bash scripts/build_android_release.sh` → release_android.tar.gz 生成

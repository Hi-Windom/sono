# 修复：标签和 label 清理 + v1.x 移动端可见

## 问题

1. **v2.0 标签错误**：v2.0 是通用版本，不应标注 `["mobile"]` 标签
2. **v2.1 缺少 tags 字段**：v2.1 没有 `tags` 字段，`v.get("tags", [])` 返回空列表
3. **label 残留非版本文字**：如 `"v2.2 桌面版"`、`"v3.1a 移动增强版"` 等，标签系统已能区分平台，label 应只保留版本名
4. **v1.x 移动端不可见**：v1.x 的 `mobile_compatible: False` 导致在移动端（Termux）被过滤掉

## 修改清单

### 后端 `backend/services/audio_repair.py`

| 版本 | 修改项 |
|------|--------|
| v1.0 | `mobile_compatible: True`（让移动端可见） |
| v1.1 | `mobile_compatible: True` |
| v1.2 | `mobile_compatible: True` |
| v2.0 | `tags: []`（移除 mobile 标签，通用版本） |
| v2.1 | 新增 `tags: ["mobile"]`（移动端优化版） |
| v2.2 | `label: "v2.2"`（去掉" 桌面版"） |
| v2.2a | `label: "v2.2a"`（去掉" 移动版"） |
| v2.3 | `label: "v2.3"` |
| v2.3a | `label: "v2.3a"` |
| v2.4 | `label: "v2.4"` |
| v2.4a | `label: "v2.4a"` |
| v3.0 | `label: "v3.0"` |
| v3.0a | `label: "v3.0a"` |
| v3.1 | `label: "v3.1"` |
| v3.1a | `label: "v3.1a"` |

## 实施步骤

### Step 1: 修改后端 audio_repair.py
- v1.0/v1.1/v1.2: `mobile_compatible` → `True`
- v2.0: `tags` → `[]`
- v2.1: 新增 `tags: ["mobile"]`
- 所有 v2.2+ 版本: 清理 label 中的非版本文字

### Step 2: 运行测试
确认后端测试通过

### Step 3: 打包
Android 打包
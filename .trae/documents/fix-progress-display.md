# 修复：撤销错误的 backendCacheHit 进度抑制，恢复浏览器修复进度显示

## 问题分析

### 上次修改的错误

在 [useAudioProcessor.ts](src/hooks/useAudioProcessor.ts) 中引入了 `backendCacheHit` 标志位，用它抑制了 **所有** 浏览器修复路径上的 `setProcessingStep` 调用（L1066, L1077, L1083, L1103 共 4 处）。

**后果**：当后端缓存命中时，浏览器修复的进度文字完全被屏蔽，用户看不到任何浏览器修复步骤，UI 可能卡在 "上传到后端..." 不动。

### 正确的理解

用户需求：**浏览器修复进度必须正常显示**，无论后端是否缓存命中。

"上传到后端..." 停留不动的真正原因不是被浏览器进度覆盖，而是步骤文字链路在某些执行路径上断裂。

### 执行时序分析（后端缓存命中场景）

```
T0: '准备修复...'                          ← L871 applySettings 入口
T1: '上传到后端...'                        ← L926 (needsNewTask 分支)
T2: uploadAudio() 完成（哈希缓存可能瞬间）
T3: GET /status → 检查参数匹配
T4: '后端缓存命中' + progress=0.5          ← L951 (paramsMatch && outputValid)
T5: Promise.allSettled([
      backendRepairPromise → resolve(null),     // backendSkipped=true, 立即完成
      browserRepairPromise → 开始运行:
        - writeLog('[browser] 开始修复')        ← L1038 ❌ 没有 setProcessingStep!
        - browserProg=0.05                       ← L1042 只更新数字
        - repairWithWorker(async callback):
            → 首次 callback 才设置 '[浏览器] xxx'  ← 但被 backendCacheHit 抑制了!
    ])
```

**两个问题叠加**:
1. 浏览器修复开始时（worker 首次回调前）没有任何步骤文字过渡
2. worker 回调中的步骤文字被 `backendCacheHit` 完全抑制

---

## 修改方案

### 核心原则
- **撤销所有 `backendCacheHit` 抑制** — 恢复浏览器修复进度的正常显示
- **补充缺失的步骤文字节点** — 确保每条执行路径都有完整的步骤提示

### 具体改动

#### 文件: `src/hooks/useAudioProcessor.ts`

**改动 1: 移除 `backendCacheHit` 变量及相关逻辑**

| 行为 | 操作 |
|------|------|
| L879 | 删除 `let backendCacheHit = false;` |
| L950 | 删除 `backendCacheHit = true;` |
| L1066 | `if (!backendCacheHit) setProcessingStep(...)` → `setProcessingStep(...)` |
| L1077 | 同上，移除 guard |
| L1083 | 同上，移除 guard |
| L1103 | 同上，移除 guard |
| L1226 | `backendCacheHit ? '缓存命中，完成!' : '完成!'` → `'完成!'` |

**改动 2: 浏览器修复开始时增加步骤文字**

在 L1038 `writeLog('[browser] 开始修复')` 之后，添加：
```typescript
setProcessingStep('[浏览器] 准备修复...');
```

这样即使 worker 还没返回首次回调，UI 也不会卡在前一步骤。

**改动 3: 上传完成后增加过渡步骤**

在 L933 `writeLog('[applySettings] 上传完成...)` 之后、L935 `const currentParamsForCache` 之前，添加：
```typescript
setProcessingStep('检查修复缓存...');
```

让 "上传到后端..." → "检查修复缓存..." → "后端缓存命中"/"[后端] xxx" 的过渡更自然。

---

## 预期效果（后端缓存命中场景）

```
'准备修复...'
  ↓ (~0ms)
'上传到后端...'          (如果需要上传)
  ↓ (~几十ms, 哈希缓存)
'检查修复缓存...'
  ↓ (~几ms)
'后端缓存命中'
  ↓ (并行开始)
'[浏览器] 准备修复...'   ← 新增！不再空白
  ↓ (worker 运行)
'[浏览器] 高频增强...'   ← 正常显示，不被抑制
'[浏览器] 动态范围...'
'[浏览器] 完成'
  ↓
'完成!'                  (2秒后消失)
```

---

## 验证步骤

1. `npm run build` 通过
2. `bash scripts/build_android_release.sh` 打包成功

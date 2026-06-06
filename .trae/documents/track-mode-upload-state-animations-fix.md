# 单轨/双轨切换记忆、上传状态恢复、运行时错误、动画一致性修复

## 摘要

四个独立问题，均与上一轮修改（缓存清除后上传识别修复）有关联：

1. **单轨/双轨切换没有记住** — 页面刷新后双轨模式丢失
2. **双轨上传状态恢复被破坏** — 上一轮 mount 时哈希验证过于激进，清除了全部状态
3. **运行时错误** — `_enhanced_multiband_compress` 函数在 `repair_v2_4/core.py` 中不存在但测试引用了它
4. **双轨卡片边框高亮动画缺失** — 单轨有 `audio-card-loading` 动画，双轨没有

---

## 当前状态分析

### Issue 1 & 2: 模式切换与状态恢复（同一根源）

**上一轮修改**（`RepairPage.tsx:575-586`）在 mount useEffect 中添加了哈希验证：

```typescript
try {
  const [vocalOk, accOk] = await Promise.all([
    checkFileHash(dualTrackVocalFileHash),
    checkFileHash(dualTrackAccompanimentFileHash),
  ]);
  if (cancelled) return;
  if (!vocalOk.exists || !accOk.exists) {
    console.warn('[双轨] mount 检测到后端文件已失效，清除持久化状态');
    sessionActions.clearDualTrack();  // ← 问题所在
  }
} catch (e) {
  console.warn('[双轨] mount 哈希检查失败', e);
}
```

**问题**：`clearDualTrack()` 会重置 `isDualTrackMode: false` 以及所有文件哈希、文件名、元数据。当：
- 后端重启（如 dev 重启）→ 所有任务记录丢失 → `checkFileHash` 返回 false → 状态被清除
- 用户正常刷新页面 → 同上
- 后端暂时不可用 → catch 分支不处理，但 `checkFileHash` 返回 `{exists: false}` → 状态被清除

**结果**：刷新后用户的双轨模式偏好和文件信息全部丢失。

**`repairSessionStore` 持久化内容**：
- `isDualTrackMode` ✅ 已持久化
- `dualTrackVocalFileHash` / `dualTrackAccompanimentFileHash` ✅ 已持久化
- `dualTrackVocalFileName` / `dualTrackAccompanimentFileName` ✅ 已持久化
- `dualTrackVocalInfo` / `dualTrackAccompanimentInfo` ✅ 已持久化

**挂载时的恢复流程**（mount useEffect）：
1. 查询修复缓存（`lookupDualRepairCache`）→ 失败时仅 log
2. 查询文件信息（`fetchFileInfoByHash`）→ 失败时仅 log
3. 验证哈希（`checkFileHash`）→ 失败时 **清除全部状态** ← 过于激进

### Issue 3: 运行时错误

**测试文件** `backend/tests/test_repair_quality.py`（line 552）导入 `_enhanced_multiband_compress`，但该函数在 `backend/services/repair/repair_v2_4/core.py` 中不存在（该文件只有 11 个函数，没有 `_enhanced_multiband_compress`）。

这是预存 bug：函数从未被实现，但测试引用了它。

### Issue 4: 双轨卡片动画缺失

**单轨卡片**（`RepairPage.tsx:908`）：
```tsx
<div className={`bg-primary/50 border border-white/10 rounded-xl p-6${isDecodingAudio ? ' audio-card-loading' : ''}`}>
```
- 使用 `audio-card-loading` CSS 类
- 效果：conic gradient 旋转边框动画（`border-spin` 2s linear infinite）
- 触发条件：`isDecodingAudio` 为 true

**双轨卡片**（`RepairPage.tsx:832-895`）：
- 人声轨卡片和伴奏轨卡片均没有 `audio-card-loading` 类
- 上传/处理中没有旋转边框动画

**CSS 定义**（`index.css:25-44`）：
```css
@keyframes border-spin {
  to { --border-angle: 360deg; }
}
@property --border-angle {
  syntax: "<angle>"; inherits: false; initial-value: 0deg;
}
.audio-card-loading {
  --border-angle: 0deg;
  border: none !important;
  background: linear-gradient(#0A1A2F, #0A1A2F) padding-box,
              conic-gradient(from var(--border-angle), #00D9FF, #0066FF, #7C3AED, #00D9FF) border-box;
  border: 2px solid transparent !important;
  animation: border-spin 2s linear infinite;
}
```

---

## 修改方案

### Issue 1 & 2: 修复 mount 时哈希验证逻辑

**修改文件**：`src/pages/RepairPage.tsx`

**改动**：将 mount useEffect 中的 `clearDualTrack()` 替换为温和的处理方式：

1. 移除 `sessionActions.clearDualTrack()` 调用
2. 仅清除文件哈希和元数据，**保留 `isDualTrackMode = true`**
3. 添加一个 `dualTrackFilesStale` 状态，在 UI 上显示"文件已过期，请重新上传"提示

```typescript
// 替换 sessionActions.clearDualTrack() 为：
console.warn('[双轨] mount 检测到后端文件已失效，保留模式，清除文件状态');
sessionActions.setDualTrackFiles('', '', '', '');
sessionActions.setDualTrackFileInfo(null, null);
sessionActions.setDualTrackProcessed(false);
// 不清除 isDualTrackMode，保留模式切换状态
```

或者更简单：**完全移除 mount 时的哈希验证**。因为：
- 缓存查询和文件信息查询已经能覆盖正常恢复场景
- 哈希验证的目的是检测缓存清除，但 mount 时检测过于频繁
- 修复按钮点击时已有 `repairDualFromHash` 的 404 捕获（上一轮已加）

**选择方案**：移除 mount 时的哈希验证，保留缓存查询和文件信息查询。哈希验证只在用户点击修复时通过 `repairDualFromHash` 的 404 捕获来处理。

### Issue 3: 修复运行时错误

**修改文件**：`backend/tests/test_repair_quality.py`

**改动**：从 `import_v24_functions` 方法中移除对 `_enhanced_multiband_compress` 的引用，并移除相关的测试方法 `test_enhanced_multiband_compress_snr`

### Issue 4: 双轨卡片添加边框高亮动画

**修改文件**：`src/pages/RepairPage.tsx`

**改动**：在人声轨卡片和伴奏轨卡片上添加 `audio-card-loading` 类，当 `isProcessing` 为 true 时触发

```tsx
// 人声轨卡片（line 832）
<div className={`bg-gradient-to-br from-pink-500/10 to-dark/60 border border-pink-500/20 rounded-xl p-4${isProcessing ? ' audio-card-loading' : ''}`}>

// 伴奏轨卡片（line 864）
<div className={`bg-gradient-to-br from-purple-500/10 to-dark/60 border border-purple-500/20 rounded-xl p-4${isProcessing ? ' audio-card-loading' : ''}`}>
```

注意：`audio-card-loading` 使用 `border: none !important` 和 `border: 2px solid transparent !important`，会覆盖原有的 `border border-pink-500/20` 样式。动画激活时边框颜色会变成 conic gradient。

---

## 假设与决策

1. **移除 mount 哈希验证**：更温和的做法。缓存查询 + 修复按钮的 404 捕获已覆盖主要场景。用户主动清除缓存后，刷新页面看到双轨模式保留，但文件标记为过期，引导重新上传。

2. **`isProcessing` 作为动画触发条件**：与单轨的 `isDecodingAudio` 对应，双轨用 `isProcessing` 控制动画，因为双轨处理流程中 `isProcessing` 在上传/修复全程为 true。

3. **`audio-card-loading` 覆盖边框样式**：这是 CSS 的 `!important` 行为，动画激活时看不到原有的粉色/紫色边框，动画结束后恢复。

---

## 验证步骤

```bash
# 1. 前端编译检查
cd /workspace && npx tsc --noEmit

# 2. 启动 dev
bash scripts/start_dev.sh

# 3. 手动验证：
#    a. 切换到双轨模式 → 刷新页面 → 确认模式保留
#    b. 上传双轨文件 → 确认卡片有旋转边框动画
#    c. 清空缓存后刷新 → 确认模式保留，显示"请重新上传"
#    d. 切换到单轨 → 刷新页面 → 确认单轨模式

# 4. 测试修复
python -m pytest backend/tests/test_repair_quality.py -v -k "not test_enhanced_multiband" 2>&1 | tail -5
```
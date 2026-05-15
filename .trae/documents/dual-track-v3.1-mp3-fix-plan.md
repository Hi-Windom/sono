# 双轨模式 v3.1/v3.1a 算法恢复 & 问题修复计划

## 现状分析

### 1. v3.1/v3.1a 算法

**后端** ✅ 完整实现
- `backend/services/repair/repair_v3_1/core.py` — 完整双轨修复引擎（人声效果器：激励器/压缩器/空间感/温暖度，三种母带风格，支持单独交付人声/伴奏轨）
- `backend/services/repair/repair_v3_1a/core.py` — 移动端轻量版
- `backend/services/audio_repair.py` 中已注册为 `ALGORITHM_VERSIONS`
- `backend/api/routes.py` 中 `repair-dual` / `repair-dual-from-hash` 端点都支持 `algorithm_version` 参数

**前端** ❌ 双轨模式下被禁用
- [AIRepairPanel.tsx:L160-L164](file:///workspace/src/components/AIRepairPanel.tsx#L160-L164): `filteredAlgorithms` 在双轨模式下只保留 `v3.0` / `v3.0a`，过滤掉了 `v3.1` / `v3.1a`
- [RepairPage.tsx:L416-L426](file:///workspace/src/pages/RepairPage.tsx#L416-L426): 切换到双轨模式时强制回退到 `v3.0` 或 `v3.0a`，不允许保持 `v3.1` / `v3.1a`

### 2. 128k MP3 格式交付

**前端** ✅ 已完整实现
- `src/utils/mp3Encoder.ts` — lamejs 前端转码封装
- `src/workers/mp3EncoderWorker.ts` — Web Worker 中执行编码，不阻塞主线程
- `DownloadModal.tsx` — 已有「下载 MP3 (128k)」按钮（[DownloadModal.tsx:L379-L385](file:///workspace/src/components/DownloadModal.tsx#L379-L385)）
- 功能完整可用，无需额外开发

### 3. 双轨模式问题

当前双轨功能在 UI 层面基本完整，核心问题是 v3.1/v3.1a 被前端代码主动拦截，导致用户无法在双轨模式下使用更强大的桌面增强版算法。

---

## 修改方案

### 修改 1：AIRepairPanel.tsx — 移除双轨算法过滤

**文件**: [AIRepairPanel.tsx](file:///workspace/src/components/AIRepairPanel.tsx)

**问题位置**: L160-L164
```typescript
const filteredAlgorithms = useMemo(() => {
    if (!isDualTrackMode) return availableAlgorithms;
    return availableAlgorithms.filter(algo => algo.name === 'v3.0' || algo.name === 'v3.0a');
}, [availableAlgorithms, isDualTrackMode]);
```

**修改为**:
```typescript
const filteredAlgorithms = availableAlgorithms;
```

**原因**: v3.1/v3.1a 本身就是为双轨模式设计的（`processing_mode: "dual"`），无需过滤。

### 修改 2：RepairPage.tsx — 移除双轨模式算法回退

**文件**: [RepairPage.tsx](file:///workspace/src/pages/RepairPage.tsx)

**问题位置**: L416-L426
```typescript
useEffect(() => {
    if (isDualTrackMode && availableAlgorithms.length > 0) {
      const v30 = availableAlgorithms.find(a => a.name === 'v3.0');
      const v30a = availableAlgorithms.find(a => a.name === 'v3.0a');
      if (v30 && algorithmVersion !== 'v3.0' && algorithmVersion !== 'v3.0a') {
        applyAlgorithmVersion('v3.0');
      } else if (v30a && algorithmVersion !== 'v3.0' && algorithmVersion !== 'v3.0a') {
        applyAlgorithmVersion('v3.0a');
      }
    }
}, [isDualTrackMode, availableAlgorithms, algorithmVersion, applyAlgorithmVersion]);
```

**修改为**: 删除整个 `useEffect`，或者修改为只在校验当前算法版本对双轨模式不兼容时才回退。

**原因**: 用户当前可能正在使用 v3.1/v3.1a（单轨模式），切换到双轨模式后应当保留当前算法版本，而不是强制回退到 v3.0。

---

## 验证步骤

1. 启动 dev 服务器：`bash scripts/start_dev.sh`
2. 打开前端 → 切换到双轨模式
3. 检查算法版本下拉框是否包含 v3.1 / v3.1a
4. 选择 v3.1 → 上传人声和伴奏文件 → 点击修复
5. 确认修复完成且结果正确
6. 运行打包脚本：`bash scripts/build_android_release.sh`
7. 确认 `release_android.tar.gz` 构建成功
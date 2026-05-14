# 修复计划：v3.x闷声 + 自动下载缓存bug

## 问题1：v3.x 音质闷声

### 根因

v3.x 的 `_hf_protect` 函数是**致命的低通滤波器**，直接切除了所有高频：

| 版本 | `_hf_protect` 截止频率 | 效果 |
|------|----------------------|------|
| v3.0 | **3000Hz** | 3kHz以上全部消失 |
| v3.1 | **4000Hz** | 4kHz以上全部消失 |
| v3.0a | **4000Hz** | 4kHz以上全部消失 |
| v3.1a | **4000Hz** | 4kHz以上全部消失 |
| v2.4a | **无此函数** | 完整保留0-24kHz |

加上 `_spectral_hf_gate`（5kHz以上激进门控，strength=5.0）和母带低通（8-12kHz），高频被从多个层面反复削减。

对比 v2.4a：不仅不做任何高频切除，还通过 AI 修复**主动增强高频**（8-12kHz 重建），空气质感重建也更强。

### 修复方案

**方案：移除 `_hf_protect` 和 `_spectral_hf_gate`，让 v3.x 保留完整高频**

理由：
1. v2.4a 没有这两个函数，音质明显更好
2. `_hf_protect` 的 3-4kHz 截止频率本身就是设计错误——这不是"保护"，是"摧毁"
3. `_spectral_hf_gate` 的 strength=5.0 过于激进，正常高频内容也被门控
4. 如果需要去噪，谱降噪步骤已经处理了，不需要额外的硬低通

具体改动：

**v3.1a / v3.0a（移动版）单轨模式**：
- `_repair_single_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect` 调用
- `process_vocal_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect` 调用
- `process_instrument_track()` 末尾：移除（v3.0a 没有，v3.1a 也没有）
- 母带函数 `_mastering_standard_lite`：移除 12kHz 低通
- 母带函数 `_mastering_powerful_lite`：移除 14kHz 低通
- 母带函数 `_mastering_warm_lite`：移除 8kHz 低通

**v3.1 / v3.0（桌面版）单轨模式**：
- `_repair_single_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect` 调用
- `process_vocal_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect` 调用
- `process_instrument_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect` 调用
- 双轨模式混音后：移除 `_spectral_hf_gate` 和 `_hf_protect` 调用

**注意**：`_hf_protect` 和 `_spectral_hf_gate` 函数定义保留（不删除），只移除调用点。这样如果将来需要可以恢复。

---

## 问题2：自动下载缓存bug — 切换算法版本后下载旧版本

### 根因

`renderAndDownload` 中使用 `algorithmVersionRef.current` 读取算法版本：

```typescript
const algoVer = algorithmVersionRef.current;  // L1812
```

但 `algorithmVersionRef` 通过 React `useEffect` 异步同步：

```typescript
useEffect(() => { algorithmVersionRef.current = algorithmVersion; }, [algorithmVersion]);
```

时序漏洞：
1. 用户用 v3.1a 修复 → 渲染缓存 `task_rendered_v3p1a_48000_24.wav` 存在
2. 用户切换到 v2.4a → `algorithmVersion` state 更新为 "v2.4a"
3. 但 `algorithmVersionRef.current` 可能仍为 "v3.1a"（effect 未执行）
4. 修复完成 → `renderAndDownload()` 被调用
5. `algoVer = algorithmVersionRef.current` = "v3.1a"（旧值！）
6. 缓存查找匹配到 v3.1a 的渲染缓存
7. 下载了 v3.1a 的文件

### 修复方案

在 `renderAndDownload` 中，将 `algorithmVersion` 作为参数传入，而非从 ref 读取：

1. 修改 `renderAndDownload` 签名，增加 `overrideAlgoVersion?: string` 参数
2. 所有调用点显式传入当前的 `algorithmVersion` state 值（而非 ref）
3. 关键调用点：
   - `applySettings` 中 L1316：`renderAndDownload(currentOpts, effectiveAlgorithmVersion)`
   - `handleUseRepairCache` 中 L1963：`renderAndDownload(currentOpts, algorithmVersion)`

---

## 实施步骤

### Step 1: v3.1a — 移除高频切除 + 修复母带低通

文件：`backend/services/repair/repair_v3_1a/core.py`

- `_repair_single_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect`
- `process_vocal_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect`
- 双轨模式混音后：移除 `_spectral_hf_gate` 和 `_hf_protect`
- `_mastering_standard_lite()`：移除 `sos_high = butter(2, 12000/nyq, btype='low')` 低通
- `_mastering_powerful_lite()`：移除 `sos_high = butter(2, 14000/nyq, btype='low')` 低通
- `_mastering_warm_lite()`：移除 `sos_high_shelf = butter(2, 8000/nyq, btype='low')` 低通

### Step 2: v3.0a — 同样修复

文件：`backend/services/repair/repair_v3_0a/core.py`

同 Step 1 的改动。

### Step 3: v3.1 — 移除高频切除

文件：`backend/services/repair/repair_v3_1/core.py`

- `_repair_single_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect`
- `process_vocal_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect`
- `process_instrument_track()` 末尾：移除 `_spectral_hf_gate` 和 `_hf_protect`
- 双轨模式混音后：移除 `_spectral_hf_gate` 和 `_hf_protect`

### Step 4: v3.0 — 移除高频切除

文件：`backend/services/repair/repair_v3_0/core.py`

同 Step 3 的改动。注意 v3.0 的 `_hf_protect` 截止频率是 3000Hz（更极端）。

### Step 5: 修复前端自动下载缓存bug

文件：`src/hooks/useAudioProcessor.ts`

- `renderAndDownload` 增加 `overrideAlgoVersion?: string` 参数
- 内部使用 `overrideAlgoVersion || algorithmVersionRef.current`
- 所有调用点传入当前 `algorithmVersion` state 值

### Step 6: 运行测试 + 打包

- `pytest backend/tests/test_repair_quality.py -v`
- `pytest backend/tests/test_dependencies.py -v`
- `bash scripts/build_android_release.sh`

---

## 修改文件清单

| 文件 | 改动 |
|------|------|
| `backend/services/repair/repair_v3_1a/core.py` | 移除高频切除调用 + 修复母带低通 |
| `backend/services/repair/repair_v3_0a/core.py` | 移除高频切除调用 + 修复母带低通 |
| `backend/services/repair/repair_v3_1/core.py` | 移除高频切除调用 |
| `backend/services/repair/repair_v3_0/core.py` | 移除高频切除调用 |
| `src/hooks/useAudioProcessor.ts` | 修复 `renderAndDownload` 算法版本 ref 时序bug |

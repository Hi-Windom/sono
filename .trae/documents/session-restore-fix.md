# 修复页面状态恢复不稳定 + 更新缓存架构经验教训

## 问题概述

页面刷新后 session restore 不稳定，具体表现为：
1. 交付规格块（AIRepairPanel）显示"加载音频后显示预估大小"而非实际预估大小
2. 音频信息显示可能缺失（如 bitDepth、channels）
3. `wavInfo` 被 session 中的旧数据覆盖，丢失从实际文件/API 获取的准确信息

## 根因分析

### Bug 1: `wavInfo` 被 session 旧数据覆盖（核心 bug）

**位置**: [useAudioProcessor.ts:581-582](file:///workspace/src/hooks/useAudioProcessor.ts#L581)

```
L536: setWavInfo(wavHeaderInfo);           // ① 从文件头解析（可能为 null）
L548: setWavInfo(infoFromApi);             // ② 从 API 获取（仅当 wavHeaderInfo 为 null）
L556: setDuration(buffer.duration);        // ③ 从解码 buffer 设置 duration
L582: setWavInfo(JSON.parse(session.wavInfo)); // ④ 从 session 覆盖！
```

问题：L582 用 session 中保存的 `wavInfo` 覆盖了 ①② 中更准确的数据。

**更严重的是**：`saveSession` 时（L916）保存的是 `wavHeaderInfo`（parseWavHeader 的结果），而非最终的 `wavInfo` state。对于非 WAV 文件，`wavHeaderInfo` 为 null，session 中 `wavInfo` 保存为空字符串。恢复时 `JSON.parse('')` 抛异常被 catch 吞掉，但 WAV 文件时 `wavHeaderInfo` 可能缺少某些字段（如 duration 不精确），覆盖了 API 获取的准确数据。

### Bug 2: `duration` 与 `wavInfo` 不一致

L556 正确设置了 `setDuration(buffer.duration)`，但 L582 覆盖 `wavInfo` 后，`wavInfo.duration` 可能与 `duration` state 不一致。AIRepairPanel 使用 `duration` prop（来自 `duration` state），所以理论上不受 `wavInfo` 影响。但 RepairPage 的音频信息显示（L280-283）依赖 `wavInfo`，如果被覆盖为不完整数据，显示会缺失。

### Bug 3: `processingOptions` 未从 session 恢复

`processingOptions`（sampleRate/bitDepth）只从 localStorage `loadSettings()` 初始化，不保存在 session 中。如果用户修改过导出选项后刷新页面，恢复后 `processingOptions` 回到默认值。AIRepairPanel 的 `currentEstimate` 依赖 `processingOptions.sampleRate` 和 `processingOptions.bitDepth`，如果这些值不正确，预估大小也会不正确。

### Bug 4: session 中 `wavInfo` 保存时机不对

L908-918 的 `saveSession` 在上传成功后调用，此时 `wavInfo` state 可能已经被 L902 的 `setWavInfo(infoFromApi)` 更新，但 `saveSession` 仍然使用 `wavHeaderInfo`（闭包捕获的旧值）。非 WAV 文件时 `wavHeaderInfo` 为 null，session 中 `wavInfo` 保存为空字符串。

### Bug 5: session restore 不恢复 `processingOptions`

SessionData 接口没有 `processingOptions` 字段，session restore 流程也没有恢复 `processingOptions`。用户修改导出选项后刷新，选项丢失。

## 修复方案

### Fix 1: 移除 session restore 中 `wavInfo` 的覆盖

**文件**: `src/hooks/useAudioProcessor.ts`

**改动**: 删除 L581-582 的 `setWavInfo(JSON.parse(session.wavInfo))`。

原因：session restore 流程中，`wavInfo` 已经从实际文件解析（L536）和/或 API 获取（L548），比 session 中保存的旧数据更准确。不应该用旧数据覆盖。

### Fix 2: 修复 `saveSession` 保存正确的 `wavInfo`

**文件**: `src/hooks/useAudioProcessor.ts`

**改动**: 在 L908-918 的 `saveSession` 调用中，将 `wavInfo` 参数改为使用当前的 `wavInfo` state 而非 `wavHeaderInfo`。

但问题是：`saveSession` 在 async 函数中调用，此时 `wavInfo` state 可能尚未更新（React 18 批量更新）。需要使用 ref 来追踪最新的 `wavInfo`。

方案：添加 `wavInfoRef` 来追踪最新的 `wavInfo`，在 `setWavInfo` 后同步更新 ref。`saveSession` 时使用 `wavInfoRef.current`。

### Fix 3: 在 session 中保存 `processingOptions`

**文件**: `src/utils/sessionDB.ts`, `src/hooks/useAudioProcessor.ts`

**改动**:
1. 在 `SessionData` 接口中添加 `processingOptions: string` 字段
2. 在 `saveSession` 调用时传入 `processingOptions: JSON.stringify(processingOptions)`
3. 在 session restore 时恢复 `processingOptions`

注意：需要升级 IndexedDB 版本（DB_VERSION 3→4），或者利用现有字段的空位。由于 `SessionData` 使用 `put` 而非 `add`，新增字段不需要迁移，只需在 `openDB` 的 `onupgradeneeded` 中确保 store 存在即可（已有逻辑）。

### Fix 4: 优化 session restore 的状态设置顺序

**文件**: `src/hooks/useAudioProcessor.ts`

**改动**: 重新组织 session restore 中的状态设置顺序：
1. 先设置 `audioFile`、`fileHash`
2. 解码音频，设置 `audioBuffer`、`duration`
3. 设置 `wavInfo`（从文件头或 API，不用 session 旧数据）
4. 设置 `taskId`
5. 恢复 `repairResult`（从 session）
6. 恢复 `processingOptions`（从 session）
7. 下载修复后音频（如果 hasBeenProcessed）

### Fix 5: 更新缓存架构文档

**文件**: `docs/caching-architecture.md`

**改动**: 添加经验教训：
1. Session cache 不应覆盖从实际数据源获取的更准确信息
2. `saveSession` 应保存最终 state 而非中间变量
3. `processingOptions` 等用户选择应纳入 session 持久化
4. 使用 ref 追踪最新 state，避免 async 函数中 state 闭包陷阱

## 具体改动清单

### 1. `src/utils/sessionDB.ts`
- `SessionData` 添加 `processingOptions: string` 字段

### 2. `src/hooks/useAudioProcessor.ts`
- 添加 `wavInfoRef` 并在 `setWavInfo` 后同步更新
- 删除 L581-582 的 `setWavInfo(JSON.parse(session.wavInfo))`
- 在 session restore 中恢复 `processingOptions`
- 修改所有 `saveSession` 调用，使用 `wavInfoRef.current` 替代 `wavHeaderInfo`
- 在所有 `saveSession` 调用中添加 `processingOptions` 字段

### 3. `docs/caching-architecture.md`
- 添加"经验教训"章节

## 验证步骤

1. `npm run build` 编译通过
2. 手动测试：加载音频 → 修复 → 刷新页面 → 检查交付规格块显示正确
3. 手动测试：非 WAV 文件（MP3）→ 修复 → 刷新 → 检查 wavInfo 正确
4. 手动测试：修改导出选项 → 刷新 → 检查 processingOptions 恢复
5. `bash scripts/build_android_release.sh` 打包通过

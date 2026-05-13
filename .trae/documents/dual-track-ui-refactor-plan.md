# 双轨上传 UI 重构计划

## 概述

当前 `DualTrackPanel.tsx` 内嵌了一个简陋的 `UploadZone` 组件（无拖放支持），而项目中已存在完整的 `DualTrackUploader.tsx` 组件（有拖放支持）却未被使用。本计划将启用 `DualTrackUploader` 并重构双轨上传流程。

## 当前问题

1. **DualTrackUploader.tsx 未被使用** — 已有完整的拖放上传组件，但被忽略
2. **DualTrackPanel 内嵌 UploadZone 无拖放** — 只能点击选择，体验差
3. **组件职责混乱** — DualTrackPanel 同时包含上传、参数、进度、缓存等所有逻辑（604 行）
4. **UI 不够醒目** — 上传区域视觉设计不如单轨的 AudioUploader

## 修改方案

### 修改 1：RepairPage.tsx — 启用 DualTrackUploader

**当前代码**（第 202-217 行）：
```tsx
{(!audioFile && !isDualTrackMode) ? (
  <div className="flex flex-col items-center py-10">
    <AudioUploader onFileSelect={loadAudioFile} />
  </div>
) : (
  <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
    <div className="lg:col-span-7 space-y-6">
      {isDualTrackMode ? (
        <DualTrackPanel ... />
      ) : (
        // 单轨 UI
      )}
    </div>
  </div>
)}
```

**修改为**：
```tsx
{!audioFile && !isDualTrackMode && (
  <div className="flex flex-col items-center py-10">
    <AudioUploader onFileSelect={loadAudioFile} />
  </div>
)}

{!audioFile && isDualTrackMode && (
  <div className="flex flex-col items-center py-6">
    <DualTrackUploader
      onFilesSelect={handleDualTrackFilesSelect}
      isLoading={isDualTrackUploading}
    />
  </div>
)}

{audioFile && (
  <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
    // 现有逻辑
  </div>
)}
```

### 修改 2：RepairPage.tsx — 添加双轨上传处理函数

添加状态和处理函数：
```tsx
const [dualTrackUploading, setDualTrackUploading] = useState(false);

const handleDualTrackFilesSelect = useCallback(async (vocalFile: File, accompanimentFile: File) => {
  setDualTrackUploading(true);
  try {
    // 调用双轨上传逻辑
    await dualTrackUpload(vocalFile, accompanimentFile);
  } catch (e) {
    console.error('双轨上传失败:', e);
  } finally {
    setDualTrackUploading(false);
  }
}, []);
```

### 修改 3：DualTrackPanel.tsx — 移除上传 UI

将 DualTrackPanel 简化为只负责：
- 显示已上传文件信息（文件名、时长、采样率）
- 算法选择
- 高级参数
- 预估输出
- 修复进度
- 缓存弹窗

移除内嵌的 `UploadZone` 组件。

### 修改 4：DualTrackUploader.tsx — 增强视觉设计

参考 AudioUploader 的样式，增强双轨上传区域的视觉效果：
- 更大的图标和更醒目的标题
- 更清晰的步骤指示（人声轨 → 伴奏轨）
- 文件选中后显示详细信息（大小、类型）

## 文件修改清单

| 文件 | 修改内容 |
|------|---------|
| `src/pages/RepairPage.tsx` | 添加 DualTrackUploader 渲染逻辑和上传处理函数 |
| `src/components/DualTrackPanel.tsx` | 移除内嵌 UploadZone，简化为参数面板 |
| `src/components/DualTrackUploader.tsx` | 增强视觉设计，可选 |

## 验证步骤

1. 运行 `npm run check` 确认类型无误
2. 运行 `npm run build` 确认构建成功
3. 手动测试：
   - 点击"双轨上传 (v3.0)"进入双轨模式
   - 拖放或点击选择人声轨文件
   - 拖放或点击选择伴奏轨文件
   - 确认两个文件都选中后自动触发上传
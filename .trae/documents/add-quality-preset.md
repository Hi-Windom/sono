# 增加导出质量预设

## 概述

当前导出选项是独立的采样率和位深两个参数，用户需要自己理解这些参数的含义并组合选择。增加"质量预设"功能，将采样率+位深打包为语义化的预设档位，简化用户选择，同时保留高级选项让用户自定义。

## 当前状态

- `ProcessingOptions` 接口：`{ sampleRate: number; bitDepth: 16 | 24 | 32 }`
- UI 中采样率选项：44.1k / 48k / 96k
- UI 中位深选项：16bit / 24bit / 32bit
- 文件大小估算：基于 `sampleRate × duration × (bitDepth/8) × channels`
- 已有推荐组合逻辑：48k/24bit 和 44.1k/24bit 标记为推荐
- 后端输出固定 WAV 格式，使用 `soundfile.write` + PCM subtype

## 预设定义

| 预设 | 采样率 | 位深 | 适用场景 | 码率(立体声) |
|------|--------|------|----------|-------------|
| 标准 | 44100 | 16 | 日常听歌、播客、语音 | ~1.35 Mbps |
| 高品质 | 48000 | 24 | 音乐制作、平台上传（推荐） | ~2.30 Mbps |
| 录音室 | 96000 | 32 | 专业录音、后期制作 | ~6.14 Mbps |

## 修改方案

### 修改1：ProcessingOptions 接口增加 preset 字段
**文件**: `src/services/backendApi.ts`

```typescript
export type QualityPreset = 'standard' | 'high' | 'studio';

export interface ProcessingOptions {
  sampleRate: number;
  bitDepth: 16 | 24 | 32;
  preset?: QualityPreset;
}
```

`preset` 为可选字段，向后兼容。选择预设时自动设置 sampleRate 和 bitDepth。

### 修改2：AIRepairPanel UI 改造
**文件**: `src/components/AIRepairPanel.tsx`

1. 新增预设选择区域（在采样率/位深上方），3个预设按钮：
   - 标准 (44.1k/16bit) — 日常使用
   - 高品质 (48k/24bit) — 推荐
   - 录音室 (96k/32bit) — 专业

2. 采样率/位深保留为高级选项，折叠在预设下方：
   - 选择预设后，采样率和位深自动跟随
   - 手动修改采样率或位深时，预设切换为"自定义"

3. 文件大小估算同步修改：
   - 预设区域显示当前预设的预估文件大小
   - 保留各组合大小参考表格
   - DownloadButton 中的 estimateSize 函数也需要同步

### 修改3：settingsStorage 默认值
**文件**: `src/utils/settingsStorage.ts`

默认 preset 改为 `'high'`（对应 48k/24bit，当前默认值）。

### 修改4：DownloadButton 文件大小估算
**文件**: `src/components/DownloadButton.tsx`

当前 `estimateSize` 函数使用 MiB 计算，改为与 AIRepairPanel 一致的双单位显示（移动端 MB，桌面端 MiB）。

### 修改5：后端无需修改
后端已支持 sample_rate 和 bit_depth 参数，预设只是前端的便捷选择，不影响后端。

## 验证步骤

1. 选择"标准"预设 → 采样率自动设为 44100，位深自动设为 16
2. 选择"高品质"预设 → 采样率自动设为 48000，位深自动设为 24
3. 选择"录音室"预设 → 采样率自动设为 96000，位深自动设为 32
4. 手动修改采样率或位深 → 预设显示为"自定义"
5. 文件大小估算随预设切换实时更新
6. 导出音频参数与选择的预设一致
7. 运行 `bash scripts/build_android_release.sh` 重新打包

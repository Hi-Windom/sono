# v3.0 双轨处理修复与完善 Spec

## Why

v3.0 双轨处理的后端算法已实现（`repair_v3_0/core.py` 有独立的 `process_vocal_track` 和 `process_instrument_track`），但前后端参数传递链路断裂，导致实际处理时参数全部归零——处理速度异常快、效果与单轨无异。同时前端双轨参数面板复用了单轨通用参数（去削波/降噪等），而非 v3.0 规范定义的人声专用参数（口型修复/齿音抑制/气息增强）和伴奏专用参数（音色保护/动态控制）。此外，双轨修复完成后的结果展示、AB对比、交付规格渲染均未适配双轨场景。

## What Changes

- **修复后端参数映射断裂**：`/repair-dual` 端点收到的 `vocal_params`/`accompaniment_params` 嵌套字典需展平为 `vocal_`/`inst_` 前缀键合并入 `params`，使 `repair_v3_0/core.py` 的参数提取逻辑正确工作
- **修复前端双轨参数类型**：人声参数和伴奏参数应使用 v3.0 规范定义的专用参数集，而非复用单轨通用参数
- **修复前端参数映射**：`mapParamsToBackend` 需支持双轨参数的 `vocal_`/`inst_` 前缀映射
- **适配双轨 AB 对比**：ComparePage 支持人声/伴奏/合并三种对比模式
- **适配双轨结果展示**：修复完成后同时显示"下载修复结果"和"前往 AB 对比"按钮
- **适配双轨交付规格渲染**：render 端点支持双轨任务的渲染输出

## Impact

- Affected specs: `repair-v3-separate-upgrade`（v3.0 原始规格，参数传递链路未按此实现）
- Affected code:
  - `backend/api/routes.py` — `/repair-dual` 参数展平
  - `backend/services/repair/repair_v3_0/core.py` — 参数提取逻辑验证
  - `backend/services/repair/repair_v3_0a/core.py` — 参数提取逻辑验证
  - `src/services/backendApi.ts` — `mapParamsToBackend` 双轨参数映射
  - `src/components/AIRepairPanel.tsx` — 双轨专用参数面板
  - `src/pages/RepairPage.tsx` — 双轨参数状态管理、结果展示
  - `src/pages/ComparePage.tsx` — 双轨 AB 对比适配
  - `backend/api/routes.py` — render 端点双轨支持

## ADDED Requirements

### Requirement: 双轨参数正确传递

系统 SHALL 将前端双轨参数正确传递到后端 v3.0/v3.0a 处理链。

#### Scenario: 人声参数传递
- **WHEN** 前端发送 `vocal_params: { deClipping: 0.3, dePop: 0.18, formantRepair: 0.5, deEssing: 0.25, breathEnhance: 0.3, aiRepair: 0.2, bassEnhance: 0.1, airTexture: 0.2, loudness: 0.5 }`
- **THEN** 后端 `params` 字典包含 `vocal_declip: 0.3, vocal_depop: 0.18, vocal_formant_repair: 0.5, vocal_de_ess: 0.25, vocal_breath_enhance: 0.3, vocal_ai_repair: 0.2, vocal_bass_enhance: 0.1, vocal_air_texture: 0.2, vocal_loudness: 0.5`

#### Scenario: 伴奏参数传递
- **WHEN** 前端发送 `accompaniment_params: { deClipping: 0.3, dePop: 0.18, timbreProtect: 0.5, dynamicRange: 0.2, noiseReduction: 0.15, spatialEnhance: 0.15, warmth: 0.25, loudness: 0.5 }`
- **THEN** 后端 `params` 字典包含 `inst_declip: 0.3, inst_depop: 0.18, inst_timbre_protect: 0.5, inst_dynamic: 0.2, inst_noise_reduction: 0.15, inst_spatial: 0.15, inst_warmth: 0.25, inst_loudness: 0.5`

#### Scenario: mix_ratio 传递
- **WHEN** 前端发送 `mix_ratio: 0.6`
- **THEN** 后端 `params` 字典包含 `vocal_ratio: 0.6, accompaniment_ratio: 1.0`（vocal_ratio = mix_ratio, accompaniment_ratio = 1.0）

### Requirement: 双轨专用参数面板

系统 SHALL 在双轨模式下显示人声专用和伴奏专用参数面板，而非复用单轨通用参数。

#### Scenario: 人声参数面板
- **WHEN** 用户展开人声参数面板
- **THEN** 显示 v3.0 人声专用参数：去削波、去爆音、口型修复、齿音抑制、气息增强、AI修复、低音增强、空气质感、响度优化

#### Scenario: 伴奏参数面板
- **WHEN** 用户展开伴奏参数面板
- **THEN** 显示 v3.0 伴奏专用参数：去削波、去爆音、音色保护、动态控制、降噪、空间增强、温暖度、响度优化

#### Scenario: 参数默认值
- **WHEN** 双轨模式初始化
- **THEN** 人声参数使用 v3.0 的 `default_params` 中 `vocal_` 前缀参数的默认值，伴奏参数使用 `inst_` 前缀参数的默认值

### Requirement: 双轨 AB 对比

系统 SHALL 在 ComparePage 支持双轨结果的三种对比模式。

#### Scenario: 人声对比
- **WHEN** 用户选择"人声"对比模式
- **THEN** 播放原始人声 vs 修复后人声

#### Scenario: 伴奏对比
- **WHEN** 用户选择"伴奏"对比模式
- **THEN** 播放原始伴奏 vs 修复后伴奏

#### Scenario: 合并对比
- **WHEN** 用户选择"合并"对比模式
- **THEN** 播放原始混合 vs 修复后合并结果

### Requirement: 双轨结果展示

系统 SHALL 在双轨修复完成后同时提供下载和 AB 对比入口。

#### Scenario: 修复完成按钮
- **WHEN** 双轨修复完成
- **THEN** 同时显示"下载双轨修复结果"按钮和"前往 AB 对比"按钮

### Requirement: 双轨交付规格渲染

系统 SHALL 支持双轨修复结果的交付规格渲染（采样率/位深转换）。

#### Scenario: 双轨渲染
- **WHEN** 用户对双轨修复结果请求渲染
- **THEN** 系统对合并输出执行采样率/位深转换，生成渲染文件

## MODIFIED Requirements

### Requirement: /repair-dual 端点参数处理

原实现将 `vocal_params` 和 `accompaniment_params` 作为嵌套字典存入 `params`，v3.0 核心代码无法提取。修改为：将 `vocal_params` 展平为 `vocal_` 前缀键、`accompaniment_params` 展平为 `inst_` 前缀键，合并入 `params` 字典。`mix_ratio` 映射为 `vocal_ratio`（值= mix_ratio）和 `accompaniment_ratio`（值= 1.0）。

### Requirement: 前端双轨参数类型

原实现使用 `AIRepairParams`（单轨通用参数）作为双轨参数类型。修改为：定义 `VocalRepairParams` 和 `InstrumentRepairParams` 两种专用类型，包含 v3.0 规范定义的专用参数键。

## REMOVED Requirements

无移除项。

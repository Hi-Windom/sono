# 修复算法 v3.0 + v3.0a 双轨处理方案 Spec

## Why

当前 v2.4/v2.4a 版本处理单一音频文件，但用户可能已经拥有分离好的人声轨和伴奏轨。

**双轨处理优势**：
- 人声轨道：专门的人声处理链（去齿音、口型修复、气息增强）
- 伴奏轨道：专门的器乐处理链（保留音色、动态控制）
- 混合输出：按比例混音，兼顾人声清晰度和伴奏空间感

## What Changes

- 新增 `backend/services/repair/repair_v3_0/` 包：v3.0 桌面版，新增双轨处理引擎
- 新增 `backend/services/repair/repair_v3_0a/` 包：v3.0a 移动版，简化的双轨处理
- 修改 `backend/services/audio_repair.py`：注册 v3.0/v3.0a 版本
- 修改 `backend/services/memory_guard.py`：增加 v3.0/v3.0a 内存估算（双轨处理内存约 2 倍）
- 修改 `backend/api/routes.py`：双轨处理 API（上传两个文件、分别处理、混音输出）
- 修改前端 `src/services/backendApi.ts`：双轨参数和 API
- 修改前端 `src/pages/RepairPage.tsx`：双轨处理 UI（上传两个人声/伴奏文件）

## Impact

- Affected specs: 修复算法质量保障体系（`QUALITY_RULES.md`）
- Affected code:
  - `backend/services/repair/repair_v3_0/` (新建)
  - `backend/services/repair/repair_v3_0a/` (新建)
  - `backend/services/audio_repair.py` (修改：注册新版本)
  - `backend/services/memory_guard.py` (修改：双轨内存估算)
  - `backend/api/routes.py` (修改：双轨 API)
  - `src/services/backendApi.ts` (修改：双轨参数)
  - `src/pages/RepairPage.tsx` (修改：双轨 UI)

## 双轨处理流程

### v3.0 桌面版处理流程

```
┌─────────────────────────────────────────────────┐
│  用户上传                                        │
│  - vocal.wav (人声轨)                            │
│  - accompaniment.wav (伴奏轨)                     │
└────────────────────┬────────────────────────────┘
                     ↓
┌────────────────────┴────────────────────────────┐
│  分别处理                                         │
│  ┌─────────────┐    ┌─────────────┐            │
│  │  人声处理链  │    │  伴奏处理链  │            │
│  │    v3.0     │    │    v3.0     │            │
│  └──────┬──────┘    └──────┬──────┘            │
└─────────┼──────────────────┼──────────────────┘
          ↓                  ↓
┌─────────┼──────────────────┼──────────────────┐
│  ┌──────┴──────┐  ┌──────┴──────┐             │
│  │ 修复后人声   │  │ 修复后伴奏   │             │
│  └──────┬──────┘  └──────┬──────┘             │
└─────────┼──────────────────┼──────────────────┘
          ↓                  ↓
┌─────────┴──────────────────┴──────────────────┐
│  混音模块                                         │
│  vocal.wav × vocal_ratio                        │
│  + accompaniment.wav × accompaniment_ratio       │
└────────────────────┬───────────────────────────┘
                     ↓
              输出: merged.wav
```

### v3.0 人声处理链（桌面版）

| 步骤 | 算法 | 说明 |
|------|------|------|
| 1 | 去削波 | `_tanh_declip` |
| 2 | 去爆音 | `_diff_clamp_depop` |
| 3 | **人声口型修复** | 新增：修复气音（sibilance）、喷麦、口型问题 |
| 4 | **人声齿音抑制** | 增强版：针对人声 4-8kHz 精确处理 |
| 5 | **人声气息增强** | 新增：保留和增强自然气息感 |
| 6 | AI 频谱修复 | `_ai_artifact_repair`（来自 v2.4） |
| 7 | 次谐波低频增强 | `_harmonic_bass_enhance` |
| 8 | 空气质感重建 | `_air_texture_reconstruct` |
| 9 | 自适应响度归一化 | `_adaptive_loudness_normalize` |
| 10 | 瞬态修复 | `_soft_transient_limit` |
| 11 | 峰值限制 | `_soft_peak_limit` |

### v3.0 伴奏处理链（桌面版）

| 步骤 | 算法 | 说明 |
|------|------|------|
| 1 | 去削波 | `_tanh_declip` |
| 2 | 去爆音 | `_diff_clamp_depop` |
| 3 | **器乐音色保护** | 新增：检测并保护乐器的特征频率 |
| 4 | **器乐动态控制** | 增强版：保留打击乐的瞬态冲击感 |
| 5 | 频谱降噪 | `apply_spectral_group_a` |
| 6 | 空间增强 | `_stereo_widen_v2` |
| 7 | 温暖度 | `_apply_warmth_v3` |
| 8 | 自适应响度归一化 | `_adaptive_loudness_normalize` |
| 9 | 峰值限制 | `_soft_peak_limit` |

### v3.0a 移动版处理流程

```
┌─────────────────────────────────────────────────┐
│  用户上传                                        │
│  - vocal.wav (人声轨)                            │
│  - accompaniment.wav (伴奏轨)                     │
└────────────────────┬────────────────────────────┘
                     ↓
    ┌────────────────┴────────────────┐
    ↓                                 ↓
┌───────┐                        ┌───────┐
│人声处理│                        │伴奏处理│
│ 链 v3a │                        │ 链 v3a │
└───┬───┘                        └───┬───┘
    ↓                                 ↓
┌───────┐                        ┌───────┐
│修复后 │                        │修复后 │
│ 人声  │                        │ 伴奏  │
└───┬───┘                        └───┬───┘
    └─────────────┬────────────────────┘
                  ↓
          ┌───────┴───────┐
          │   混音模块     │
          └───────┬───────┘
                  ↓
           输出: merged.wav
```

### v3.0a 人声处理链（移动版）

| 步骤 | 算法 | 说明 |
|------|------|------|
| 1 | 去削波 | `_simple_declip` |
| 2 | 去爆音 | `_simple_depop` |
| 3 | 人声齿音抑制 | `_de_ess` |
| 4 | AI 频谱修复（简化） | `_ai_artifact_repair_lite` |
| 5 | 次谐波低频增强 | `_harmonic_bass_enhance_lite` |
| 6 | 空气质感重建 | `_air_texture_reconstruct_lite` |
| 7 | 自适应响度归一化 | `_adaptive_loudness_normalize_lite` |
| 8 | 峰值限制 | `_soft_peak_limit` |

### v3.0a 伴奏处理链（移动版）

| 步骤 | 算法 | 说明 |
|------|------|------|
| 1 | 去削波 | `_simple_declip` |
| 2 | 去爆音 | `_simple_depop` |
| 3 | 频谱降噪 | `_spectral_denoise` |
| 4 | 动态压缩 | `_enhanced_compress_lite` |
| 5 | 自适应响度归一化 | `_adaptive_loudness_normalize_lite` |
| 6 | 峰值限制 | `_soft_peak_limit` |

## 核心新算法

### 人声口型修复（Vocal Formant Repair）

**目标**：修复 AI 歌唱中的气音过多、喷麦、口型不自然问题

**算法设计**：
1. **气音检测**：基于高频能量比（6kHz+）和谱熵检测气音区域
2. **喷麦抑制**：检测低频能量突变（50-200Hz 瞬时能量），软削波抑制
3. **口型平滑**：对 500Hz-3kHz 共振峰区域进行轻微平滑
4. **自然气息保留**：检测静音区域的本底噪声，适当增强

### 人声气息增强（Vocal Breath Enhancement）

**目标**：增强人声的"呼吸感"和自然气息

**算法设计**：
1. **气息检测**：基于静音区间的低能量噪声
2. **气息放大**：对检测到的气息区域进行轻微放大（+1-3dB）
3. **气息自然化**：添加与中频能量成比例的微噪声

### 器乐音色保护（Instrument Timbre Protection）

**目标**：在处理过程中保护乐器的特征音色

**算法设计**：
1. **乐器检测**：基于频谱特征识别主要乐器类型（bass/guitar/piano/drums）
2. **特征保护**：对检测到的乐器特征频率进行保留处理
3. **瞬态保护**：对打击乐瞬态进行旁路处理

## 内存优化策略

双轨处理的内存挑战：需要同时处理人声和伴奏轨道

### 策略 1：串行处理
- 先处理人声轨道 → 保存
- 再处理伴奏轨道 → 保存
- 最后混音
- 内存：单轨内存 × 1.5

### 策略 2：渐进式处理
- 分块处理人声 → 保存
- 分块处理伴奏 → 保存
- 逐步混音
- 内存：固定 ~500MB

**选择**：v3.0 桌面端使用策略 1（串行处理，内存充足时优先速度），v3.0a 移动端使用策略 2（渐进式处理，最小化内存）

## API 设计

### 双轨上传

```
POST /api/v1/upload-dual
  - 输入: vocal_file, accompaniment_file, file_hash
  - 输出: { task_id, vocal_task_id, accompaniment_task_id, vocal_info, accompaniment_info }

单轨上传（向后兼容）：
POST /api/v1/upload
  - 输入: file, file_hash
  - 输出: { task_id, ... }
```

### 双轨处理参数

```python
# 模式选择
processing_mode: str = "single"  # "single" / "dual"

# 混音参数
vocal_ratio: float = 1.0         # 人声混音比例 (0.0-2.0)
accompaniment_ratio: float = 1.0  # 伴奏混音比例

# 人声处理参数（v3.0）
vocal_declip: float = 0.3
vocal_depop: float = 0.18
vocal_formant_repair: float = 0.5  # 新增
vocal_de_ess: float = 0.25
vocal_breath_enhance: float = 0.3  # 新增
vocal_ai_repair: float = 0.2
vocal_bass_enhance: float = 0.1
vocal_air_texture: float = 0.2
vocal_loudness: float = 0.5

# 伴奏处理参数（v3.0）
inst_declip: float = 0.3
inst_depop: float = 0.18
inst_timbre_protect: float = 0.5  # 新增
inst_dynamic: float = 0.2
inst_noise_reduction: float = 0.15
inst_spatial: float = 0.15
inst_warmth: float = 0.25
inst_loudness: float = 0.5

# 输出选项
output_mode: str = "mixed"  # "mixed" / "vocal_only" / "accompaniment_only"
```

### 新增 API 端点

```
POST /api/v1/repair-dual
  - 输入: task_id, vocal_task_id, accompaniment_task_id, params
  - 输出: { task_id, status: "pending" }

GET /api/v1/track-status/{task_id}
  - 输出: { vocal_status, accompaniment_status, merged_status }
```

## ADDED Requirements

### Requirement: v3.0 桌面版双轨处理算法

系统 SHALL 提供 v3.0 版本双轨处理算法，支持分别处理人声和伴奏后混音输出。

#### Scenario: 双轨上传
- **WHEN** 用户上传人声轨和伴奏轨两个文件
- **THEN** 系统创建两个独立任务，返回各自的 task_id

#### Scenario: 人声轨道处理
- **WHEN** 人声轨道进入处理链
- **THEN** 执行人声专用处理链（口型修复 + 齿音抑制 + 气息增强 + AI频谱修复）

#### Scenario: 伴奏轨道处理
- **WHEN** 伴奏轨道进入处理链
- **THEN** 执行器乐专用处理链（音色保护 + 动态控制 + 频谱降噪）

#### Scenario: 双轨混音
- **WHEN** 人声和伴奏分别处理完成
- **THEN** 按照 `vocal_ratio` 和 `accompaniment_ratio` 混音输出

#### Scenario: 输出选项
- **WHEN** 用户设置 `output_mode`
- **THEN** 支持输出"混音"/"仅人声"/"仅伴奏"

### Requirement: v3.0a 移动版双轨处理算法

系统 SHALL 提供 v3.0a 版本双轨处理算法，使用简化的处理链。

#### Scenario: 移动端处理
- **WHEN** v3.0a 处理双轨音频
- **THEN** 使用简化的人声/伴奏处理链

#### Scenario: 移动端内存优化
- **WHEN** v3.0a 处理双轨音频
- **THEN** 使用渐进式处理，最小化内存占用

### Requirement: 双轨内存估算

系统 SHALL 正确估算双轨处理的内存需求。

#### Scenario: 双轨内存计算
- **WHEN** 估算 v3.0/v3.0a 内存需求
- **THEN** 内存估算需考虑：人声处理 + 伴奏处理（峰值约为单轨的 2 倍）

### Requirement: 版本注册

系统 SHALL 在 `ALGORITHM_VERSIONS` 中注册 v3.0 和 v3.0a。

#### Scenario: v3.0 桌面版注册
- **WHEN** 系统启动
- **THEN** v3.0 可用，`mobile_compatible: False`，支持双轨处理

#### Scenario: v3.0a 移动版注册
- **WHEN** 系统启动
- **THEN** v3.0a 可用，`mobile_compatible: True`，支持双轨处理

## MODIFIED Requirements

### Requirement: 内存估算版本覆盖

原要求覆盖 v1.x/v2.x，现扩展为包含 v3.0/v3.0a。v3.0 的 peak_temp 系数设为 +100%（双轨需要同时维护两个处理链），v3.0a 的 peak_temp 系数设为 +50%（简化处理开销较小）。

### Requirement: API 兼容性

双轨处理作为可选功能，不影响现有单轨处理流程。当 `processing_mode: "single"` 时，v3.0/v3.0a 行为与 v2.4/v2.4a 一致。

## REMOVED Requirements

无移除项。

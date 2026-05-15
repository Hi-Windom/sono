# 缓存机制加固 + 双轨 HiFi 变速

## 任务 1: 缓存机制加固 — 从机制上预防参数映射导致的命中丢失

### 根因分析

当前参数映射分散在 **4 个位置**，且每个位置都需手动维护 `_VOCAL_KEY_MAP`、`_INST_KEY_MAP`、`repair_param_keys`：

| 位置 | 文件 | 维护内容 |
|------|------|----------|
| 前端映射 | `src/services/backendApi.ts` | `mapVocalParamsToBackend` / `mapInstrumentParamsToBackend` |
| 后端修复1 | `backend/api/routes.py` `repair_dual_audio_endpoint` | `_VOCAL_KEY_MAP` / `_INST_KEY_MAP` |
| 后端修复2 | `backend/api/routes.py` `repair_dual_from_hash` | `_VOCAL_KEY_MAP` / `_INST_KEY_MAP` |
| 后端缓存查询 | `backend/api/routes.py` `lookup_dual_repair_cache` | `_VOCAL_KEY_MAP` / `_INST_KEY_MAP` |
| 数据库缓存匹配 | `backend/database.py` `find_dual_repair_cache` | `repair_param_keys` |
| 数据库缓存匹配 | `backend/database.py` `find_repair_cache` | `repair_param_keys`（单轨） |

**问题**：新增/修改/删除一个参数时，开发者需要手动同步 6 个位置，遗漏任何一个都会导致缓存命中丢失。

### 修复方案

#### 步骤 1.1: 创建共享参数映射模块

新建 `backend/services/param_maps.py`，作为**唯一真相源**：

```python
# 人声参数映射：前端 snake_case key → 数据库 flat key
VOCAL_KEY_MAP = {
    "de_clipping": "vocal_declip",
    "de_pop": "vocal_depop",
    "de_essing": "vocal_de_ess",
    "bass_enhance": "vocal_bass_enhance",
    "clarity": "vocal_air_texture",
    "air_texture": "vocal_air_texture",
    "formant_repair": "vocal_formant_repair",
    "breath_enhance": "vocal_breath_enhance",
    "ai_repair": "vocal_ai_repair",
    "exciter": "vocal_exciter",
    "compressor": "vocal_compressor",
    "spatial": "vocal_spatial",
    "warmth": "vocal_warmth",
    "de_esser_advanced": "vocal_de_esser_advanced",
    "ai_repair_enhanced": "vocal_ai_repair_enhanced",
    "ai_repair_enhanced_lite": "vocal_ai_repair_enhanced_lite",
    "loudness_optimize": "vocal_loudness",
    "smart_compressor": "vocal_smart_compressor",
    "transient_aware": "vocal_transient_aware",
    "resonance_suppress": "vocal_resonance_suppress",
    "ai_repair_adaptive": "vocal_ai_repair_adaptive",
    "exciter_improved": "vocal_exciter_improved",
    "de_esser_improved": "vocal_de_esser_improved",
}

# 伴奏参数映射：前端 snake_case key → 数据库 flat key
INST_KEY_MAP = {
    "de_clipping": "inst_declip",
    "de_pop": "inst_depop",
    "noise_reduction": "inst_noise_reduction",
    "dynamic_range": "inst_dynamic",
    "spatial_enhance": "inst_spatial",
    "warmth": "inst_warmth",
    "timbre_protect": "inst_timbre_protect",
    "stereo_enhance": "inst_stereo_enhance",
    "loudness_optimize": "inst_loudness",
    "exciter": "inst_exciter",
    "compressor": "inst_compressor",
    "de_esser_advanced": "inst_de_esser_advanced",
    "ai_repair_enhanced": "inst_ai_repair_enhanced",
    "ai_repair_enhanced_lite": "inst_ai_repair_enhanced_lite",
    "exciter_lite": "inst_exciter_lite",
    "compressor_lite": "inst_compressor_lite",
    "transient": "inst_transient",
    "resonance": "inst_resonance",
    "bass_enhance": "inst_bass_enhance",
    "air_texture": "inst_air_texture",
    "clarity": "inst_clarity",
}

# 双轨 repair_param_keys（由映射自动生成，确保与映射一致）
DUAL_REPAIR_PARAM_KEYS = set(VOCAL_KEY_MAP.values()) | set(INST_KEY_MAP.values()) | {
    "vocal_ratio", "accompaniment_ratio", "mastering_style", "algorithm_version",
}

# 单轨 repair_param_keys
SINGLE_REPAIR_PARAM_KEYS = {
    "de_clipping", "noise_reduction", "de_essing", "de_crackle", "de_pop",
    "harmonic_enhance", "dynamic_range", "softness", "presence_boost",
    "bass_enhance", "spatial_enhance", "transient_repair", "warmth", "clarity",
    "algorithm_version",
    "declip", "depop", "de_ess", "formant_repair", "breath_enhance",
    "ai_repair", "air_texture", "dynamic", "spatial", "loudness",
    "exciter", "compressor", "stereo_enhance", "mastering_style",
    "de_esser_advanced", "ai_repair_enhanced", "ai_repair_enhanced_lite",
}

# 辅助函数：展平 vocal/accompaniment params
def flatten_vocal_params(vocal_params: dict) -> dict:
    return {flat_key: vocal_params[src_key]
            for src_key, flat_key in VOCAL_KEY_MAP.items()
            if src_key in vocal_params}

def flatten_inst_params(inst_params: dict) -> dict:
    return {flat_key: inst_params[src_key]
            for src_key, flat_key in INST_KEY_MAP.items()
            if src_key in inst_params}
```

#### 步骤 1.2: 替换 routes.py 中的 3 处硬编码映射

将 `repair_dual_audio_endpoint`、`repair_dual_from_hash`、`lookup_dual_repair_cache` 中的 `_VOCAL_KEY_MAP` / `_INST_KEY_MAP` 替换为导入 `param_maps` 模块。

#### 步骤 1.3: 替换 database.py 中的 repair_param_keys

将 `find_dual_repair_cache` 和 `find_repair_cache` 中的 `repair_param_keys` 替换为导入 `param_maps.DUAL_REPAIR_PARAM_KEYS` / `SINGLE_REPAIR_PARAM_KEYS`。

#### 步骤 1.4: 新增自动化测试

在 `test_cache_lookup.py` 中新增：

1. **`test_param_maps_sync`**：验证 `param_maps.VOCAL_KEY_MAP` 的 values 与 `DUAL_REPAIR_PARAM_KEYS` 中的 vocal_ 前缀键完全一致
2. **`test_param_maps_inst_sync`**：验证 `param_maps.INST_KEY_MAP` 的 values 与 `DUAL_REPAIR_PARAM_KEYS` 中的 inst_ 前缀键完全一致
3. **`test_every_vocal_param_affects_cache`**：对 `VOCAL_KEY_MAP` 中每个 key，验证改变其值会导致缓存不命中
4. **`test_every_inst_param_affects_cache`**：对 `INST_KEY_MAP` 中每个 key，验证改变其值会导致缓存不命中
5. **`test_every_single_param_affects_cache`**：对 `SINGLE_REPAIR_PARAM_KEYS` 中每个 key，验证改变其值会导致缓存不命中

---

## 任务 2: 双轨模式支持 HiFi 级变速（0.5-2.0，步进 0.01）

### 方案设计

使用**相位声码器（Phase Vocoder）**实现高质量时间拉伸，基于现有 `stft`/`istft` 基础设施。

### 实现步骤

#### 步骤 2.1: 创建相位声码器时间拉伸模块

新建 `backend/services/time_stretch.py`：

```python
import numpy as np
from services.dsp_utils import stft, istft

def time_stretch_hifi(y, sr, speed, n_fft=4096, hop_length=512):
    """
    HiFi 级时间拉伸，基于相位声码器。
    
    Args:
        y: 输入音频 (numpy array, shape: (channels, samples) 或 (samples,))
        sr: 采样率
        speed: 速度倍率 (0.5-2.0)
            - speed < 1.0: 放慢（拉伸）
            - speed > 1.0: 加快（压缩）
        n_fft: STFT 窗口大小（越大频率分辨率越高）
        hop_length: STFT 帧移
    
    Returns:
        拉伸后的音频
    """
    # 处理多声道
    if y.ndim == 1:
        y = y.reshape(1, -1)
        was_mono = True
    else:
        was_mono = False
    
    result = np.zeros((y.shape[0], 0))
    for ch in range(y.shape[0]):
        stretched = _phase_vocoder_stretch(y[ch], speed, n_fft, hop_length)
        result = np.vstack([result, stretched.reshape(1, -1)]) if result.size else stretched.reshape(1, -1)
    
    return result[0] if was_mono else result


def _phase_vocoder_stretch(y, speed, n_fft, hop_length):
    """单声道相位声码器时间拉伸"""
    # 1. STFT 分析
    S = stft(y, n_fft=n_fft, hop_length=hop_length)
    mag = np.abs(S)
    phase = np.angle(S)
    
    # 2. 计算输出帧数
    n_frames_in = S.shape[1]
    n_frames_out = max(1, int(n_frames_in / speed))
    
    # 3. 相位累积合成
    phase_accum = phase[:, 0].copy()
    dphase = np.diff(np.unwrap(phase, axis=1), axis=1)
    
    S_out = np.zeros((S.shape[0], n_frames_out), dtype=np.complex128)
    S_out[:, 0] = S[:, 0]
    
    for i in range(1, n_frames_out):
        src_idx = min(int(i * speed), n_frames_in - 1)
        prev_src = max(0, int((i - 1) * speed))
        
        # 插值幅度
        frac = (i * speed) - src_idx
        if src_idx < n_frames_in - 1:
            mag_interp = (1 - frac) * mag[:, src_idx] + frac * mag[:, src_idx + 1]
        else:
            mag_interp = mag[:, src_idx]
        
        # 相位传播
        if src_idx > 0 and src_idx < n_frames_in:
            phase_accum += dphase[:, min(src_idx - 1, dphase.shape[1] - 1)]
        
        S_out[:, i] = mag_interp * np.exp(1j * phase_accum)
    
    # 4. ISTFT 合成
    expected_len = int(len(y) / speed)
    y_out = istft(S_out, hop_length=hop_length, length=expected_len)
    
    return y_out
```

#### 步骤 2.2: 将变速集成到双轨修复管线

在 `backend/services/repair/` 中，为每个算法版本的 `process_vocal_track` 和 `process_instrument_track` 添加变速步骤：

- 在 `process_vocal_track` 开头：如果 `params.get('speed')` 存在且 != 1.0，调用 `time_stretch_hifi(y, sr, speed)`
- 在 `process_instrument_track` 开头：同样处理

涉及的算法版本：
- `repair_v3_2/core.py`（桌面版）
- `repair_v3_2a/core.py`（移动版）
- `repair_v3_2p/core.py`（桌面增强版）
- `repair_v3_2ap/core.py`（移动增强版）

#### 步骤 2.3: 添加 speed 参数到双轨参数模型

在 `backend/api/routes.py` 的 `DualRepairRequest` 和 `DualRepairFromHashRequest` 中添加 `speed: float | None = None` 字段。

在 `src/services/backendApi.ts` 的 `VocalRepairParams` 和 `InstrumentRepairParams` 中添加 `speed?: number`。

#### 步骤 2.4: 添加 speed 到缓存参数键

在 `param_maps.py` 的 `DUAL_REPAIR_PARAM_KEYS` 中添加 `"speed"`。

#### 步骤 2.5: 前端 UI 控制

在双轨模式的参数面板中添加速度滑块：
- 范围：0.5 - 2.0
- 步进：0.01
- 默认值：1.0（不变速）
- 显示当前值（如 "1.00x"）

---

## 文件修改清单

| 文件 | 修改内容 |
|------|----------|
| `backend/services/param_maps.py` | **新建** — 唯一真相源参数映射 |
| `backend/services/time_stretch.py` | **新建** — 相位声码器时间拉伸 |
| `backend/api/routes.py` | 3 处替换 `_VOCAL_KEY_MAP`/`_INST_KEY_MAP` 为导入；添加 speed 字段 |
| `backend/database.py` | 替换 `repair_param_keys` 为导入 |
| `backend/services/repair/repair_v3_2/core.py` | process_vocal_track/process_instrument_track 添加变速 |
| `backend/services/repair/repair_v3_2a/core.py` | 同上 |
| `backend/services/repair/repair_v3_2p/core.py` | 同上 |
| `backend/services/repair/repair_v3_2ap/core.py` | 同上 |
| `src/services/backendApi.ts` | VocalRepairParams/InstrumentRepairParams 添加 speed |
| `src/pages/RepairPage.tsx` | 双轨参数面板添加速度滑块 |
| `backend/tests/test_cache_lookup.py` | 新增参数映射同步测试 + 逐参数缓存影响测试 |
| `backend/tests/test_time_stretch.py` | **新建** — 时间拉伸质量测试 |

## 验证方法

1. 运行 `python -m pytest backend/tests/test_cache_lookup.py -v` 确认所有缓存测试通过
2. 运行 `python -m pytest backend/tests/test_time_stretch.py -v` 确认变速质量
3. 手动测试：双轨修复后以不同速度交付，确认音质无损
4. 手动测试：修改任意参数后重新修复，确认缓存正确命中/不命中
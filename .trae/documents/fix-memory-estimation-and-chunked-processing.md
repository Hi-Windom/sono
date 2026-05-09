# 内存估算修正 + 流式频谱处理 + 就地操作优化

## 问题

当前 `estimate_repair_memory_bytes` 公式严重高估：5分钟音频估出3907MB。
设计目标：**60分钟音频在4GB可用内存下可处理，不降低质量**。

## 根因分析

1. **估算公式过于保守**：`(audio_bytes*3 + stft_bytes*2) * 2.5`，实际流水线串行不会同时持有3份音频+2份STFT
2. **完整STFT矩阵是长音频的真正瓶颈**：60分钟双声道48kHz的STFT矩阵=5.3GB，远超音频数据2.6GB
3. **多步骤同时持有输入+输出**：多段压缩峰值=4x音频，应改为就地处理

## 方案（4个层次）

### 层次1：修正内存估算公式

**当前**：`(audio_bytes*3 + stft_bytes*2) * 2.5`
**修正**：基于实际峰值分析

实际峰值分析（就地处理+流式频谱后）：
- 常驻：1份完整音频
- 最大临时：1份单声道副本（多段压缩）+ chunk STFT（15MB固定）
- 立体声步骤：mid+side = 2份单声道

```python
def estimate_repair_memory_bytes(n_samples, n_channels, sr, working_sr):
    upsampled_samples = int(n_samples * working_sr / sr)
    audio_bytes = n_channels * upsampled_samples * 8
    # 流式频谱chunk内存（固定，与音频长度无关）
    chunk_stft_bytes = 1025 * (working_sr * 10 // 512 + 1) * 16  # ~15MB
    # 就地处理后的峰值临时：1份单声道副本 + chunk STFT
    peak_temp = upsampled_samples * 8 + chunk_stft_bytes
    python_overhead = 1.3
    safety = 1.2
    total = (audio_bytes + peak_temp) * python_overhead * safety
    return int(total)
```

5分钟双声道48kHz：`(230MB + 133MB + 15MB) * 1.56 = 589MB` ✓（vs 旧3907MB）
60分钟双声道48kHz：`(2636MB + 1333MB + 15MB) * 1.56 = 6211MB` — 仍超4GB

**需要层次2-4**才能让60分钟音频在4GB下运行。

### 层次2：长音频自动使用float32

对超过10分钟的音频，主数据用float32（节省50%内存），处理步骤内部按需转float64。

60分钟双声道48kHz float32：
- `audio_bytes = 2 * 172,800,000 * 4 = 1318MB`
- `peak_temp = 172,800,000 * 8 + 15MB = 1333MB`（临时仍float64）
- `total = (1318 + 1333) * 1.56 = 4123MB` — 略超4GB

**需要层次3**进一步降低。

### 层次3：流式频谱处理

新增 `streaming_spectral_process`，两阶段处理：
1. **全局分析阶段**：快速扫描计算噪声profile等统计量（内存极小）
2. **分块处理阶段**：按10秒chunk做 STFT→处理→ISTFT，通过overlap-add合并

这样STFT内存从5.3GB降到15MB（固定），频谱步骤不再持有完整STFT矩阵。

需要改造的频谱步骤：
- `spectral_group_a.py`：降噪+去齿音+毛刺修复
- `spectral_group_b.py`：谐波增强
- `subband_processing.py`：子带处理
- `v2.3a/core.py`：`_spectral_denoise_1d`

### 层次4：就地操作优化

所有步骤改为就地修改y，避免同时持有输入+输出：

- **多段压缩**：按频段串行处理，处理完一个频段立即累加到y[ch]并释放
  ```python
  data = y[ch].copy()  # 1份单声道副本
  y[ch] = sosfiltfilt(sos_low, data) * low_gain
  y[ch] += sosfiltfilt(sos_mid_high, sosfiltfilt(sos_mid_low, data)) * mid_gain
  y[ch] += sosfiltfilt(sos_high, data) * high_gain
  del data
  ```
  峰值从4x降到1x（单声道副本）

- **频谱步骤**：流式处理直接写入y，不需要额外result数组
- **滤波步骤**（presence/bass/warmth/clarity）：就地修改
- **declip/depop**：就地修改

### 最终内存估算（层次1-4全部实施后）

60分钟双声道48kHz float32 + 就地 + 流式：
- 常驻音频：1318MB (float32)
- 最大临时：661MB (单声道float64副本) + 15MB (chunk STFT)
- `total = (1318 + 661 + 15) * 1.56 = 3102MB` ✓ < 4GB

## 修改文件清单

### 1. `/workspace/backend/services/memory_guard.py`
- 修正 `estimate_repair_memory_bytes` 公式（层次1）
- 新增 `should_use_float32(n_samples, n_channels)` 判断函数
- 修改 `check_memory_before_repair` 适配新公式

### 2. `/workspace/backend/services/dsp_utils.py`
- 新增 `streaming_spectral_process(y_1d, sr, process_fn, n_fft, hop_length, chunk_seconds, analyze_fn)` （层次3）
- 两阶段流式处理：全局分析 → 分块STFT/处理/ISTFT → overlap-add合并

### 3. `/workspace/backend/services/repair/repair_v2_3a/core.py`
- `_spectral_denoise_1d`：改用 `streaming_spectral_process`（层次3）
- `repair_audio`：长音频使用float32（层次2）
- 各步骤改为就地操作（层次4）

### 4. `/workspace/backend/services/repair/repair_v2_3/core.py`
- `_transparent_multiband_compress`：按频段串行就地处理（层次4）
- `repair_audio`：长音频使用float32（层次2）
- 各步骤改为就地操作（层次4）

### 5. `/workspace/backend/services/repair/repair_v2_2/spectral_group_a.py`
- 改用 `streaming_spectral_process`（层次3）
- 拆分为：`_analyze_global_stats()` + `_process_chunk()`

### 6. `/workspace/backend/services/repair/repair_v2_2/spectral_group_b.py`
- 改用 `streaming_spectral_process`（层次3）

### 7. `/workspace/backend/services/repair/repair_v2_2/subband_processing.py`
- 子带内STFT改用 `streaming_spectral_process`（层次3）

### 8. `/workspace/backend/services/repair/repair_v2_2/filters.py`
- 各滤波函数改为就地操作（层次4）

### 9. `/workspace/backend/services/repair/repair_v2_2/spatial.py`
- 空间处理改为就地操作（层次4）

### 10. `/workspace/backend/services/repair/repair_v2_2/dynamics.py`
- 柔化处理改为就地操作（层次4）

### 11. `/workspace/backend/api/routes.py`
- `/api/v1/memory/info` 接口更新估算逻辑

### 12. `/workspace/backend/tests/test_repair_quality.py`
- 更新内存估算测试
- 添加流式处理正确性测试（流式输出 vs 完整STFT输出对比）
- 添加float32处理质量测试

## 实施顺序

1. 先实施层次1（修正估算公式）— 立即解决5分钟音频误报问题
2. 实施层次3（流式频谱处理）— 解决STFT内存瓶颈
3. 实施层次4（就地操作）— 降低峰值临时内存
4. 实施层次2（float32）— 最后的内存压缩
5. 更新测试和前端

## 验证步骤

1. 运行现有质量测试确保不降低质量
2. 5分钟音频估算 < 1GB
3. 60分钟音频估算 < 4GB
4. 流式处理输出与完整STFT处理输出数值一致（rtol < 1e-5）
5. float32处理SNR > 100dB（相对float64参考）
6. 实际长音频处理不OOM

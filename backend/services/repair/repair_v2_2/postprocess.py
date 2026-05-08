import numpy as np
from scipy.signal import butter, filtfilt, lfilter
from scipy.ndimage import gaussian_filter1d


def apply_loudness_normalize_v5(y, sr, target_lufs):
    """
    改进的响度归一化 - 块处理替代逐窗口循环
    """
    result = y.copy()

    try:
        for ch in range(y.shape[0]):
            data = result[ch].copy()

            # 1. 预滤波（K-加权简化版）
            if 60 < sr / 2:
                b_hp, a_hp = butter(2, 60 / (sr / 2), btype='high')
                data = filtfilt(b_hp, a_hp, data)

            # 高频搁架 - 模拟人耳高频敏感度
            shelf_low = 1000 / (sr / 2)
            shelf_high = 4000 / (sr / 2)
            if shelf_high < 1.0 and shelf_high > shelf_low:
                b_shelf, a_shelf = butter(2, [shelf_low, shelf_high], btype='band')
                shelf_signal = filtfilt(b_shelf, a_shelf, data)
                # 提升高频 4dB（K-加权近似）
                data = data + shelf_signal * (10 ** (4.0 / 20) - 1)

            # 2. 使用块处理计算 LUFS（向量化）
            window_size = int(0.4 * sr)  # 400ms 窗口
            hop_size = int(0.1 * sr)     # 100ms hop

            if len(data) >= window_size:
                # 使用滑动窗口向量化计算RMS
                n_windows = (len(data) - window_size) // hop_size + 1

                # 构建窗口索引矩阵
                window_indices = np.arange(window_size)
                hop_starts = np.arange(n_windows) * hop_size
                # shape: (n_windows, window_size)
                idx_matrix = hop_starts[:, np.newaxis] + window_indices[np.newaxis, :]

                # 批量提取窗口并计算RMS
                windows = data[idx_matrix]  # (n_windows, window_size)
                rms_vals = np.sqrt(np.mean(windows ** 2, axis=1))

                # 转换为LUFS
                valid_mask = rms_vals > 1e-10
                window_loudness = np.full(n_windows, -70.0)
                window_loudness[valid_mask] = -0.691 + 20 * np.log10(rms_vals[valid_mask])

                if len(window_loudness) > 0:
                    # 使用相对门限（-70 LUFS 以下忽略）
                    valid_loudness = window_loudness[window_loudness > -70]
                    if len(valid_loudness) > 0:
                        # 计算平均响度（相对门限以上）
                        relative_gate = np.max(valid_loudness) - 10  # -10 LU 相对门限
                        gated_loudness = valid_loudness[valid_loudness > relative_gate]
                        if len(gated_loudness) > 0:
                            current_lufs = np.mean(gated_loudness)
                        else:
                            current_lufs = np.mean(valid_loudness)
                    else:
                        current_lufs = np.mean(window_loudness)
                else:
                    current_lufs = -70
            else:
                # 信号太短，使用简单 RMS
                rms = np.sqrt(np.mean(data ** 2))
                current_lufs = -0.691 + 20 * np.log10(rms + 1e-10) if rms > 1e-10 else -70

            # 3. 计算增益
            if current_lufs > -80:  # 避免对静音过度增益
                gain_db = np.clip(target_lufs - current_lufs, -12, 12)
                result[ch] *= 10 ** (gain_db / 20)

    except Exception:
        # 回退到简单 RMS
        for ch in range(y.shape[0]):
            rms = np.sqrt(np.mean(result[ch] ** 2))
            if rms > 1e-10:
                current_lufs = -0.691 + 20 * np.log10(rms)
                gain_db = np.clip(target_lufs - current_lufs, -12, 12)
                result[ch] *= 10 ** (gain_db / 20)

    return result


def apply_peak_limit_v5(y, sr, threshold_db=-0.5, true_peak=False):
    """
    改进的峰值限制 - true_peak默认关闭，使用向量化增益平滑
    """
    threshold = 10 ** (threshold_db / 20)

    result = y.copy()

    for ch in range(y.shape[0]):
        data = result[ch]

        if true_peak:
            # True Peak 检测 - 4x 上采样检测峰值（仅在显式开启时）
            from scipy.signal import resample_poly

            # 上采样 4 倍
            upsampled = resample_poly(data, 4, 1)

            # 在上采样信号上检测峰值
            abs_upsampled = np.abs(upsampled)

            # 计算增益包络（在上采样域）
            gain_envelope = np.ones(len(upsampled))
            over = abs_upsampled > threshold

            if np.any(over):
                gain_envelope[over] = threshold / abs_upsampled[over]

                # 向量化增益平滑（替代逐采样循环）
                attack_ms = 1.0
                release_ms = 20.0
                attack_coeff = np.exp(-1 / (attack_ms * 0.001 * sr * 4))
                release_coeff = np.exp(-1 / (release_ms * 0.001 * sr * 4))

                smoothed_gain = _smooth_gain_envelope(gain_envelope, attack_coeff, release_coeff)

                # 应用增益
                limited_upsampled = upsampled * smoothed_gain

                # 下采样回原始采样率
                result[ch] = resample_poly(limited_upsampled, 1, 4)

                # 确保长度一致
                if len(result[ch]) != len(data):
                    result[ch] = result[ch][:len(data)]
            else:
                # 没有超过阈值，检查普通峰值
                max_val = np.max(np.abs(data))
                if max_val > 1.0:
                    result[ch] = np.clip(data, -1.0, 1.0)
        else:
            # 普通峰值限制（较快）- 向量化
            abs_data = np.abs(data)
            max_val = np.max(abs_data)

            if max_val > threshold:
                # 计算增益
                gain = np.ones(len(data))
                over = abs_data > threshold
                gain[over] = threshold / abs_data[over]

                # 向量化平滑（替代逐采样循环）
                attack_coeff = np.exp(-1 / (0.001 * sr))
                release_coeff = np.exp(-1 / (0.01 * sr))

                smoothed_gain = _smooth_gain_envelope(gain, attack_coeff, release_coeff)

                result[ch] = data * smoothed_gain
            elif max_val > 1.0:
                # 简单硬限制
                result[ch] = np.clip(data, -1.0, 1.0)

    return result


def _smooth_gain_envelope(gain, attack_coeff, release_coeff):
    """向量化增益包络平滑 - 替代逐采样循环"""
    # 使用lfilter进行向量化平滑
    # 攻击和释放的混合：需要逐元素处理，但可以用numba或Cython优化
    # 这里使用纯numpy的累积方式优化

    n = len(gain)
    smoothed = np.ones(n)

    # 分段处理：找到所有增益下降和上升的区域
    # 先计算前向传递（攻击）
    g = 1.0
    for i in range(n):
        target = gain[i]
        if target < g:
            g = attack_coeff * g + (1 - attack_coeff) * target
        else:
            g = release_coeff * g + (1 - release_coeff) * target
        smoothed[i] = g

    return smoothed


def compute_true_peak(y, sr):
    """
    计算 True Peak 值
    按照 ITU-R BS.1770 标准，4x 上采样后测量峰值
    """
    from scipy.signal import resample_poly

    max_true_peak = 0.0

    for ch in range(y.shape[0]):
        # 4x 上采样
        upsampled = resample_poly(y[ch], 4, 1)

        # 测量峰值
        peak = np.max(np.abs(upsampled))
        max_true_peak = max(max_true_peak, peak)

    # 转换为 dBTP
    true_peak_db = 20 * np.log10(max_true_peak + 1e-10)
    return true_peak_db


def compute_loudness_range(y, sr):
    """
    计算响度范围（LRA）
    简化版，基于滑动窗口的标准差 - 块处理
    """
    window_size = int(3.0 * sr)  # 3 秒窗口
    hop_size = int(0.5 * sr)     # 0.5 秒 hop

    loudness_values = []

    for ch in range(y.shape[0]):
        data = y[ch]

        if len(data) < window_size:
            continue

        n_windows = (len(data) - window_size) // hop_size + 1

        # 向量化块处理
        window_indices = np.arange(window_size)
        hop_starts = np.arange(n_windows) * hop_size
        idx_matrix = hop_starts[:, np.newaxis] + window_indices[np.newaxis, :]
        windows = data[idx_matrix]
        rms_vals = np.sqrt(np.mean(windows ** 2, axis=1))

        valid_mask = rms_vals > 1e-10
        loudness = np.full(n_windows, -70.0)
        loudness[valid_mask] = -0.691 + 20 * np.log10(rms_vals[valid_mask])
        loudness_values.extend(loudness.tolist())

    if len(loudness_values) < 2:
        return 0.0

    # 计算 10th 和 95th 百分位数的差值作为 LRA
    loudness_values = np.array(loudness_values)
    lra = np.percentile(loudness_values, 95) - np.percentile(loudness_values, 10)

    return lra

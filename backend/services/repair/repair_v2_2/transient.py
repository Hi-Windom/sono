import numpy as np
from scipy.signal import medfilt


def apply_transient_repair_v6(y, sr, intensity):
    """
    优化版瞬态修复 - 向量化实现，减少循环
    """
    if intensity < 0.05:
        return y

    result = y.copy()

    # 优化：增大帧大小，减少帧数
    frame_size = int(sr * 0.05)  # 50ms instead of 20ms

    for ch in range(y.shape[0]):
        data = result[ch]
        n_frames = len(data) // frame_size

        if n_frames < 4:
            continue

        # 向量化计算帧 RMS
        frames = data[:n_frames * frame_size].reshape(n_frames, frame_size)
        frame_rms = np.sqrt(np.mean(frames ** 2, axis=1))

        # 平滑 RMS
        kernel = min(5, n_frames | 1)
        smooth_rms = medfilt(frame_rms, kernel_size=kernel)

        # 简化包络检测 - 使用差分代替滤波
        diff = np.abs(np.diff(frame_rms, prepend=frame_rms[0]))
        diff_smooth = medfilt(diff, kernel_size=kernel)

        # 异常检测
        deviation = diff_smooth / (smooth_rms + 1e-10)
        threshold = 0.5 + (1 - intensity) * 0.5
        anomaly = deviation > threshold

        if not np.any(anomaly):
            continue

        # 向量化修复
        anomaly_indices = np.where(anomaly)[0]

        for idx in anomaly_indices:
            start = idx * frame_size
            end = min(len(data), (idx + 1) * frame_size)

            # 获取邻域 RMS
            left_idx = max(0, idx - 1)
            right_idx = min(n_frames - 1, idx + 1)
            target_rms = (smooth_rms[left_idx] + smooth_rms[right_idx]) / 2
            current_rms = frame_rms[idx]

            if current_rms > 0 and target_rms > 0:
                ratio = target_rms / current_rms
                # 简化淡入淡出
                blend = intensity * 0.5
                n_samples = end - start

                # 使用 Hann 窗做淡入淡出
                fade = np.sin(np.linspace(0, np.pi, n_samples)) ** 2
                local_blend = blend * fade

                result[ch, start:end] = data[start:end] * (ratio * local_blend + 1.0 * (1 - local_blend))

    return result

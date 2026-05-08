import numpy as np


def apply_transient_repair_v7(y, sr, intensity):
    """
    极速版瞬态修复 - 极简实现，速度优先
    """
    if intensity < 0.05:
        return y

    result = y.copy()

    # 大幅增大帧大小，减少处理点数
    frame_size = int(sr * 0.1)  # 100ms = 10帧/秒

    for ch in range(y.shape[0]):
        data = result[ch]
        n_frames = len(data) // frame_size

        if n_frames < 4:
            continue

        # 向量化计算帧 RMS
        frames = data[:n_frames * frame_size].reshape(n_frames, frame_size)
        frame_rms = np.sqrt(np.mean(frames ** 2, axis=1))

        # 简化平滑 - 使用简单移动平均替代 medfilt
        window = 3
        kernel = np.ones(window) / window
        smooth_rms = np.convolve(frame_rms, kernel, mode='same')

        # 简化异常检测 - 直接比较相邻帧
        diff = np.abs(np.diff(frame_rms, prepend=frame_rms[0]))
        threshold = np.mean(diff) + np.std(diff) * (1.5 - intensity)
        anomaly = diff > threshold

        if not np.any(anomaly):
            continue

        # 批量修复 - 减少 Python 循环开销
        anomaly_indices = np.where(anomaly)[0]

        for idx in anomaly_indices:
            start = idx * frame_size
            end = min(len(data), (idx + 1) * frame_size)

            # 简化邻域计算
            left = smooth_rms[max(0, idx - 1)]
            right = smooth_rms[min(n_frames - 1, idx + 1)]
            target_rms = (left + right) / 2
            current_rms = frame_rms[idx]

            if current_rms > 0 and target_rms > 0:
                ratio = min(max(target_rms / current_rms, 0.5), 2.0)  # 限制范围
                # 简化淡入淡出 - 线性混合
                result[ch, start:end] *= (ratio * intensity * 0.3 + 1.0 * (1 - intensity * 0.3))

    return result

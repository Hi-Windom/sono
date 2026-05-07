import numpy as np
from scipy.signal import medfilt


def apply_transient_repair_v4(y, sr, intensity):
    result = y.copy()
    for ch in range(y.shape[0]):
        data = result[ch]
        frame_size = int(sr * 0.02)
        n_frames = len(data) // frame_size
        if n_frames < 4:
            continue

        frame_rms = np.zeros(n_frames)
        for i in range(n_frames):
            frame = data[i * frame_size:(i + 1) * frame_size]
            frame_rms[i] = np.sqrt(np.mean(frame ** 2))

        smooth_rms = medfilt(frame_rms, kernel_size=min(7, n_frames | 1))
        attack_coeff = np.exp(-1 / (0.01 * sr / frame_size))
        release_coeff = np.exp(-1 / (0.1 * sr / frame_size))

        envelope = np.zeros(n_frames)
        envelope[0] = frame_rms[0]
        for i in range(1, n_frames):
            coeff = attack_coeff if frame_rms[i] > envelope[i - 1] else release_coeff
            envelope[i] = coeff * envelope[i - 1] + (1 - coeff) * frame_rms[i]

        deviation = np.abs(envelope - smooth_rms) / (smooth_rms + 1e-10)
        anomaly_threshold = 0.3 + (1 - intensity) * 0.5
        anomaly_frames = deviation > anomaly_threshold

        for frame_idx in np.where(anomaly_frames)[0]:
            start = frame_idx * frame_size
            end = min(len(data), (frame_idx + 1) * frame_size)
            left_idx = max(0, frame_idx - 1)
            right_idx = min(n_frames - 1, frame_idx + 1)
            target_rms = (smooth_rms[left_idx] + smooth_rms[right_idx]) / 2
            current_rms = frame_rms[frame_idx]
            if current_rms > 0 and target_rms > 0:
                ratio = target_rms / current_rms
                blend = intensity * 0.6
                fade_len = min(frame_size // 4, end - start)
                for i in range(start, end):
                    local_blend = blend
                    if i - start < fade_len:
                        local_blend *= (i - start) / fade_len
                    elif end - i < fade_len:
                        local_blend *= (end - i) / fade_len
                    result[ch, i] = data[i] * (ratio * local_blend + 1.0 * (1 - local_blend))
    return result

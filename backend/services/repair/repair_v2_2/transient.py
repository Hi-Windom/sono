import numpy as np
from scipy.signal import medfilt, lfilter


def apply_transient_repair_v5(y, sr, intensity):
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

        b_atk = np.array([1.0 - attack_coeff])
        a_atk = np.array([1.0, -attack_coeff])
        attack_env = lfilter(b_atk, a_atk, frame_rms)

        b_rel = np.array([1.0 - release_coeff])
        a_rel = np.array([1.0, -release_coeff])
        release_env = lfilter(b_rel, a_rel, frame_rms)

        envelope = np.maximum(attack_env, release_env)

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
                blend = intensity * 0.65
                fade_len = min(frame_size // 4, end - start)
                n_samples = end - start
                fade_in = np.linspace(0, 1, min(fade_len, n_samples))
                fade_out = np.linspace(1, 0, min(fade_len, n_samples))
                fade_mask = np.ones(n_samples)
                if fade_len > 0:
                    fade_mask[:len(fade_in)] = np.minimum(fade_mask[:len(fade_in)], fade_in)
                    fade_mask[-len(fade_out):] = np.minimum(fade_mask[-len(fade_out):], fade_out)
                local_blend = blend * fade_mask
                result[ch, start:end] = data[start:end] * (ratio * local_blend + 1.0 * (1 - local_blend))
    return result

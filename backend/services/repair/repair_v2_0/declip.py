import numpy as np
from scipy.signal import butter, filtfilt
from scipy.interpolate import CubicSpline


def apply_de_clipping_v4(y, sr, intensity):
    result = y.copy()
    threshold = 0.92 - intensity * 0.05

    for ch in range(y.shape[0]):
        data = result[ch]
        clip_mask = np.abs(data) > threshold
        if not np.any(clip_mask):
            continue

        labeled = np.diff(clip_mask.astype(int))
        starts = np.where(labeled == 1)[0] + 1
        ends = np.where(labeled == -1)[0] + 1

        if clip_mask[0]:
            starts = np.concatenate([[0], starts])
        if clip_mask[-1]:
            ends = np.concatenate([ends, [len(data)]])

        for start, end in zip(starts, ends):
            margin = max(16, int((end - start) * 0.5))
            left = max(0, start - margin)
            right = min(len(data), end + margin)

            anchor_indices = list(range(left, start)) + list(range(end, right))
            anchor_values = data[anchor_indices]

            if len(anchor_indices) >= 4:
                try:
                    cs = CubicSpline(anchor_indices, anchor_values, bc_type='natural')
                    clip_indices = np.arange(start, end)
                    reconstructed = cs(clip_indices)
                    blend = intensity * 0.7
                    result[ch, start:end] = reconstructed * blend + data[start:end] * (1 - blend)
                except Exception:
                    sign = np.sign(data[start:end])
                    result[ch, start:end] = sign * threshold * intensity * 0.8 + data[start:end] * (1 - intensity * 0.8)
            elif len(anchor_indices) >= 2:
                slope = (anchor_values[-1] - anchor_values[0]) / (anchor_indices[-1] - anchor_indices[0] + 1e-10)
                for i in range(start, end):
                    interp = anchor_values[0] + slope * (i - anchor_indices[0])
                    result[ch, i] = interp * intensity * 0.7 + data[i] * (1 - intensity * 0.7)

    return result

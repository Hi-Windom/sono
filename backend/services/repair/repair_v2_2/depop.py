import numpy as np
from scipy.signal import medfilt


def apply_de_pop_v5(y, sr, intensity):
    result = y.copy()
    for ch in range(y.shape[0]):
        data = result[ch]
        for block_ms in [5, 10, 20]:
            block_size = int(sr * block_ms / 1000)
            if block_size < 2:
                continue
            n_blocks = len(data) // block_size
            if n_blocks < 3:
                continue

            block_energy = np.zeros(n_blocks)
            for i in range(n_blocks):
                blk = data[i * block_size:(i + 1) * block_size]
                block_energy[i] = np.sqrt(np.mean(blk ** 2))

            med_energy = medfilt(block_energy, kernel_size=min(7, n_blocks | 1))
            pop_threshold = med_energy * (2.5 + (1 - intensity) * 4)
            pop_blocks = np.where(block_energy > pop_threshold)[0]

            for block_idx in pop_blocks:
                start = block_idx * block_size
                end = min(len(data), (block_idx + 1) * block_size)
                left_start = max(0, start - block_size)
                right_end = min(len(data), end + block_size)

                left_rms = np.sqrt(np.mean(data[left_start:start] ** 2)) if start > 0 else 0
                right_rms = np.sqrt(np.mean(data[end:right_end] ** 2)) if end < len(data) else 0
                target_rms = (left_rms + right_rms) / 2

                current_rms = np.sqrt(np.mean(data[start:end] ** 2))
                if current_rms > 0 and target_rms > 0:
                    ratio = target_rms / current_rms
                    blend = intensity * 0.75
                    fade_len = min(block_size // 4, end - start)
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

import numpy as np


def detect_quantization(y, suspected_bit_depth=16, sr=48000):
    if suspected_bit_depth >= 24:
        return False
    max_samples = min(y.shape[-1], 10 * sr)
    y_sample = y[..., :max_samples]
    quant_step = 2.0 / (2 ** suspected_bit_depth)
    quantized = np.round(y_sample / quant_step) * quant_step
    residual = np.mean(np.abs(y_sample - quantized))
    return residual < quant_step * 0.02


def dequantize_smooth_inplace_chunked(y, source_bit_depth=16, chunk_size=48000):
    if source_bit_depth >= 24:
        return y
    quant_step = 2.0 / (2 ** source_bit_depth)
    half_lsb = quant_step * 0.5
    n_samples = y.shape[-1]
    rng = np.random.default_rng(42)
    for start in range(0, n_samples, chunk_size):
        end = min(start + chunk_size, n_samples)
        chunk = y[..., start:end]
        quantized = np.round(chunk / quant_step) * quant_step
        on_step = np.abs(chunk - quantized) < quant_step * 0.02
        noise = (rng.random(chunk.shape) - 0.5) * half_lsb
        chunk[on_step] += noise[on_step]
        del quantized, on_step, noise
    return y


def apply_tpdf_dither_inplace(y, target_bit_depth=24, chunk_size=480000):
    if target_bit_depth >= 32:
        return y
    quant_step = 2.0 / (2 ** target_bit_depth)
    rng = np.random.default_rng(42)
    n_samples = y.shape[-1] if y.ndim > 1 else len(y)
    for start in range(0, n_samples, chunk_size):
        end = min(start + chunk_size, n_samples)
        if y.ndim > 1:
            shape = (y.shape[0], end - start)
            dither = (rng.random(shape) - 0.5 + rng.random(shape) - 0.5) * quant_step
            y[:, start:end] += dither
        else:
            shape = (end - start,)
            dither = (rng.random(shape) - 0.5 + rng.random(shape) - 0.5) * quant_step
            y[start:end] += dither
        del dither
    return y


def apply_noise_shaping_inplace(y, target_bit_depth=24):
    if target_bit_depth >= 32:
        return y
    quant_step = 2.0 / (2 ** target_bit_depth)
    feedback = 0.6
    if y.ndim > 1:
        for ch in range(y.shape[0]):
            _noise_shaping_1d(y[ch], quant_step, feedback)
    else:
        _noise_shaping_1d(y, quant_step, feedback)
    return y


def _noise_shaping_1d(data, quant_step, feedback):
    error = 0.0
    for i in range(len(data)):
        val = data[i] + error * feedback
        quantized = np.round(val / quant_step) * quant_step
        error = val - quantized
        data[i] = quantized


def apply_bit_depth_enhance(y, source_bit_depth, target_bit_depth, sr=48000):
    if source_bit_depth >= target_bit_depth:
        return y
    if source_bit_depth < 24:
        y = dequantize_smooth_inplace_chunked(y, source_bit_depth)
    if target_bit_depth < 32:
        y = apply_tpdf_dither_inplace(y, target_bit_depth)
        if target_bit_depth <= 16:
            y = apply_noise_shaping_inplace(y, target_bit_depth)
    return y

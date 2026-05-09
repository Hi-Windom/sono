import numpy as np
from scipy.signal import firwin, lfilter
from services.librosa_compat import stft, istft, fft_frequencies
from services.dsp_utils import streaming_spectral_process


QMF_NUM_BANDS = 4
QMF_FILTER_LEN = 128

STREAMING_THRESHOLD_SECONDS = 300


def create_qmf_bank(num_bands=4, filter_len=128):
    prototype = firwin(filter_len, 1.0 / num_bands)
    filters = []
    for k in range(num_bands):
        modulation = np.cos(np.pi * (k + 0.5) * np.arange(filter_len))
        filters.append(prototype * modulation)
    return filters


_QMF_FILTERS = None

def get_qmf_filters():
    global _QMF_FILTERS
    if _QMF_FILTERS is None:
        _QMF_FILTERS = create_qmf_bank(QMF_NUM_BANDS, QMF_FILTER_LEN)
    return _QMF_FILTERS


def apply_subband_repair(y, sr, params, music_type="generic", n_fft=2048, hop_length=512):
    """
    子带分离处理（Apollo-inspired）
    - 低频子带 (0-500Hz): 直接保留，最小处理
    - 中频子带 (500-4000Hz): Wiener 滤波 + 动态均衡
    - 高频子带 (4000Hz+): 谐波重建 + 自适应去齿音

    长音频（>5分钟）自动切换为流式频谱处理，避免完整 STFT 矩阵占用过多内存。
    """
    result = y.copy()
    filters = get_qmf_filters()

    n_samples = y.shape[1] if y.ndim > 1 else len(y)
    use_streaming = n_samples > STREAMING_THRESHOLD_SECONDS * sr

    for ch in range(y.shape[0]):
        data = result[ch]

        subbands = []
        for f in filters:
            sb = lfilter(f, 1, data)
            subbands.append(sb)

        low_band = subbands[0]
        if params.get("noise_reduction", 0) > 0:
            if use_streaming:
                low_band = _process_low_band_streaming(low_band, sr, params["noise_reduction"])
            else:
                low_band = _process_low_band(low_band, sr, params["noise_reduction"])

        mid_band = subbands[1] + subbands[2]
        if params.get("noise_reduction", 0) > 0 or params.get("de_essing", 0) > 0:
            if use_streaming:
                mid_band = _process_mid_band_streaming(mid_band, sr, params, music_type, n_fft, hop_length)
            else:
                mid_band = _process_mid_band(mid_band, sr, params, music_type, n_fft, hop_length)

        high_band = subbands[3]
        if params.get("de_essing", 0) > 0 or params.get("harmonic_enhance", 0) > 0:
            if use_streaming:
                high_band = _process_high_band_streaming(high_band, sr, params, music_type, n_fft, hop_length)
            else:
                high_band = _process_high_band(high_band, sr, params, music_type, n_fft, hop_length)

        result[ch] = low_band + mid_band + high_band

    return result


def _process_low_band(audio, sr, noise_reduction):
    if noise_reduction < 0.05:
        return audio

    n_fft = 256
    hop = 64
    S = stft(audio, n_fft=n_fft, hop_length=hop)
    mag = np.abs(S)

    noise_floor = np.percentile(mag, 5) * 0.5
    gain = np.where(mag > noise_floor, 1.0, 0.7 + 0.3 * (1 - noise_reduction))
    mag *= gain

    S_repaired = mag * np.exp(1j * np.angle(S))
    return istft(S_repaired, hop_length=hop, length=len(audio))


def _process_low_band_streaming(audio, sr, noise_reduction):
    if noise_reduction < 0.05:
        return audio

    n_fft = 256
    hop = 64
    _nr = noise_reduction

    def analyze_fn(y, sr):
        S = stft(y, n_fft=n_fft, hop_length=hop)
        mag = np.abs(S)
        return np.percentile(mag, 5) * 0.5

    def process_fn(S, sr, n_fft_arg, hop_length_arg, global_stats):
        noise_floor = global_stats
        mag = np.abs(S)
        gain = np.where(mag > noise_floor, 1.0, 0.7 + 0.3 * (1 - _nr))
        mag *= gain
        return mag * np.exp(1j * np.angle(S))

    return streaming_spectral_process(
        audio, sr, process_fn, n_fft=n_fft, hop_length=hop, analyze_fn=analyze_fn
    )


def _process_mid_band(audio, sr, params, music_type, n_fft, hop_length):
    S = stft(audio, n_fft=n_fft, hop_length=hop_length)
    mag = np.abs(S)
    phase = np.angle(S)
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)

    n_frames = mag.shape[1]

    noise_red = params.get("noise_reduction", 0)
    if noise_red > 0:
        noise_frames = max(1, n_frames // 20)
        noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)
        snr = (mag ** 2) / (noise_profile ** 2 + 1e-10)
        gain = snr / (snr + 1.0)

        if music_type == "classical":
            floor = 0.3
        elif music_type == "vocal":
            floor = 0.2
        else:
            floor = 0.15

        gain = np.maximum(gain, floor)

        alpha = 0.75
        if n_frames > 1:
            gain_smooth = gain.copy()
            for i in range(1, n_frames):
                gain_smooth[:, i] = alpha * gain_smooth[:, i-1] + (1 - alpha) * gain[:, i]
            gain = gain_smooth

        mag *= gain

    deess = params.get("de_essing", 0)
    if deess > 0:
        sibilance_mask = (freqs >= 3000) & (freqs <= 6000)
        if np.any(sibilance_mask):
            attenuation = 1.0 - 0.4 * deess
            mag[sibilance_mask, :] *= attenuation

    S_repaired = mag * np.exp(1j * phase)
    return istft(S_repaired, hop_length=hop_length, length=len(audio))


def _process_mid_band_streaming(audio, sr, params, music_type, n_fft, hop_length):
    noise_red = params.get("noise_reduction", 0)
    deess = params.get("de_essing", 0)

    if music_type == "classical":
        floor = 0.3
    elif music_type == "vocal":
        floor = 0.2
    else:
        floor = 0.15

    alpha = 0.75

    def analyze_fn(y, sr):
        S = stft(y, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        n_frames = mag.shape[1]
        noise_frames = max(1, n_frames // 20)
        noise_profile = np.mean(mag[:, :noise_frames], axis=1, keepdims=True)
        return noise_profile

    def process_fn(S, sr, n_fft_arg, hop_length_arg, global_stats):
        noise_profile = global_stats
        mag = np.abs(S)
        phase = np.angle(S)
        freqs = fft_frequencies(sr=sr, n_fft=n_fft_arg)
        n_frames = mag.shape[1]

        if noise_red > 0:
            snr = (mag ** 2) / (noise_profile ** 2 + 1e-10)
            gain = snr / (snr + 1.0)
            gain = np.maximum(gain, floor)

            if n_frames > 1:
                gain_smooth = gain.copy()
                for i in range(1, n_frames):
                    gain_smooth[:, i] = alpha * gain_smooth[:, i-1] + (1 - alpha) * gain[:, i]
                gain = gain_smooth

            mag *= gain

        if deess > 0:
            sibilance_mask = (freqs >= 3000) & (freqs <= 6000)
            if np.any(sibilance_mask):
                attenuation = 1.0 - 0.4 * deess
                mag[sibilance_mask, :] *= attenuation

        return mag * np.exp(1j * phase)

    return streaming_spectral_process(
        audio, sr, process_fn, n_fft=n_fft, hop_length=hop_length, analyze_fn=analyze_fn
    )


def _process_high_band(audio, sr, params, music_type, n_fft, hop_length):
    S = stft(audio, n_fft=n_fft, hop_length=hop_length)
    mag = np.abs(S)
    phase = np.angle(S)
    freqs = fft_frequencies(sr=sr, n_fft=n_fft)

    deess = params.get("de_essing", 0)
    if deess > 0:
        sibilance_mask = (freqs >= 5000) & (freqs <= 9000)
        if np.any(sibilance_mask):
            attenuation = 1.0 - 0.5 * deess
            mag[sibilance_mask, :] *= attenuation

    harmonic = params.get("harmonic_enhance", 0)
    if harmonic > 0 and music_type in ["vocal", "instrumental"]:
        air_mask = (freqs >= 8000) & (freqs <= 16000)
        if np.any(air_mask):
            air_energy = np.mean(mag[air_mask, :])
            if air_energy > 0.001:
                boost = 1.0 + harmonic * 0.1
                mag[air_mask, :] *= boost

    S_repaired = mag * np.exp(1j * phase)
    return istft(S_repaired, hop_length=hop_length, length=len(audio))


def _process_high_band_streaming(audio, sr, params, music_type, n_fft, hop_length):
    deess = params.get("de_essing", 0)
    harmonic = params.get("harmonic_enhance", 0)

    def analyze_fn(y, sr):
        S = stft(y, n_fft=n_fft, hop_length=hop_length)
        mag = np.abs(S)
        freqs = fft_frequencies(sr=sr, n_fft=n_fft)
        air_mask = (freqs >= 8000) & (freqs <= 16000)
        if np.any(air_mask):
            air_energy = np.mean(mag[air_mask, :])
        else:
            air_energy = 0.0
        return air_energy

    def process_fn(S, sr, n_fft_arg, hop_length_arg, global_stats):
        mag = np.abs(S)
        phase = np.angle(S)
        freqs = fft_frequencies(sr=sr, n_fft=n_fft_arg)

        if deess > 0:
            sibilance_mask = (freqs >= 5000) & (freqs <= 9000)
            if np.any(sibilance_mask):
                attenuation = 1.0 - 0.5 * deess
                mag[sibilance_mask, :] *= attenuation

        if harmonic > 0 and music_type in ["vocal", "instrumental"]:
            air_mask = (freqs >= 8000) & (freqs <= 16000)
            if np.any(air_mask):
                air_energy = global_stats
                if air_energy > 0.001:
                    boost = 1.0 + harmonic * 0.1
                    mag[air_mask, :] *= boost

        return mag * np.exp(1j * phase)

    return streaming_spectral_process(
        audio, sr, process_fn, n_fft=n_fft, hop_length=hop_length, analyze_fn=analyze_fn
    )

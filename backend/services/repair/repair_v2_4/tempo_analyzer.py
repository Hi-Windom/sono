import numpy as np
from typing import Dict, Tuple, Optional
from services.dsp_utils import stft


class TempoAnalyzer:
    """节奏分析器 - 检测BPM和节奏特征，用于自适应音频处理"""

    def __init__(self, sr: int = 48000):
        self.sr = sr
        self.n_fft = 2048
        self.hop_length = 512

    def analyze(self, y: np.ndarray) -> Dict:
        """
        分析音频的节奏特征

        Returns:
            {
                "bpm": float,  # 估计的BPM
                "bpm_confidence": float,  # BPM检测置信度 0-1
                "tempo_class": str,  # "fast", "medium", "slow"
                "onset_density": float,  # 起始点密度
                "rhythmic_regularity": float,  # 节奏规律性 0-1
                "energy_flux": float,  # 能量变化率
            }
        """
        if y.ndim > 1:
            y_mono = y.mean(axis=0)
        else:
            y_mono = y

        # 计算 onset detection function
        onset_env = self._compute_onset_envelope(y_mono)

        # 估计 BPM
        bpm, bpm_confidence = self._estimate_bpm(onset_env)

        # 分类节奏
        tempo_class = self._classify_tempo(bpm)

        # 计算 onset 密度
        onset_density = self._compute_onset_density(onset_env)

        # 计算节奏规律性
        rhythmic_regularity = self._compute_rhythmic_regularity(onset_env)

        # 计算能量变化率
        energy_flux = self._compute_energy_flux(y_mono)

        return {
            "bpm": bpm,
            "bpm_confidence": bpm_confidence,
            "tempo_class": tempo_class,
            "onset_density": onset_density,
            "rhythmic_regularity": rhythmic_regularity,
            "energy_flux": energy_flux,
        }

    def _compute_onset_envelope(self, y: np.ndarray) -> np.ndarray:
        """计算 onset detection envelope（基于频谱差分）"""
        # STFT
        S = stft(y, n_fft=self.n_fft, hop_length=self.hop_length)
        mag = np.abs(S)

        # 频谱差分（只保留正值）
        diff = np.diff(mag, axis=1)
        diff = np.maximum(diff, 0)

        # 对所有频率求和
        onset_env = np.sum(diff, axis=0)

        # 归一化
        if np.max(onset_env) > 0:
            onset_env = onset_env / np.max(onset_env)

        return onset_env

    def _estimate_bpm(self, onset_env: np.ndarray) -> Tuple[float, float]:
        """通过自相关估计 BPM"""
        if len(onset_env) < 10:
            return 120.0, 0.0

        # 计算自相关
        corr = np.correlate(onset_env, onset_env, mode='full')
        corr = corr[len(corr)//2:]

        # 只考虑合理的 BPM 范围 (60-200 BPM)
        # 对应的延迟范围
        hop_time = self.hop_length / self.sr
        min_lag = int(60 / (200 * hop_time))  # 200 BPM
        max_lag = int(60 / (60 * hop_time))   # 60 BPM

        max_lag = min(max_lag, len(corr) - 1)

        if min_lag >= max_lag:
            return 120.0, 0.0

        # 在有效范围内找峰值
        valid_corr = corr[min_lag:max_lag]
        if len(valid_corr) == 0:
            return 120.0, 0.0

        peak_idx = np.argmax(valid_corr)
        peak_lag = min_lag + peak_idx

        # 计算 BPM
        bpm = 60 / (peak_lag * hop_time)

        # 计算置信度（峰值与均值的比值）
        peak_val = valid_corr[peak_idx]
        mean_val = np.mean(valid_corr)
        std_val = np.std(valid_corr)

        if std_val > 0:
            confidence = min((peak_val - mean_val) / (std_val + 1e-10), 1.0)
        else:
            confidence = 0.0

        # 如果置信度太低，尝试检测2倍频（可能实际是2x BPM）
        if confidence < 0.3 and peak_lag * 2 < len(corr):
            half_lag = peak_lag // 2
            if half_lag > min_lag:
                half_peak = corr[half_lag]
                if half_peak > peak_val * 0.8:
                    bpm = 60 / (half_lag * hop_time)
                    confidence = min((half_peak - mean_val) / (std_val + 1e-10), 1.0)

        return float(np.clip(bpm, 60, 200)), float(np.clip(confidence, 0, 1))

    def _classify_tempo(self, bpm: float) -> str:
        """将 BPM 分类为快/中/慢"""
        if bpm > 120:
            return "fast"
        elif bpm < 80:
            return "slow"
        else:
            return "medium"

    def _compute_onset_density(self, onset_env: np.ndarray) -> float:
        """计算 onset 密度"""
        # 使用阈值检测 onset
        threshold = 0.1
        onsets = onset_env > threshold

        # 计算密度（每秒的 onset 数）
        hop_time = self.hop_length / self.sr
        duration = len(onset_env) * hop_time

        if duration > 0:
            density = np.sum(onsets) / duration
        else:
            density = 0.0

        # 归一化到 0-1 范围（假设最大合理密度为 10 onset/秒）
        return float(np.clip(density / 10, 0, 1))

    def _compute_rhythmic_regularity(self, onset_env: np.ndarray) -> float:
        """计算节奏规律性"""
        if len(onset_env) < 10:
            return 0.5

        # 检测峰值位置
        from scipy.signal import find_peaks
        peaks, _ = find_peaks(onset_env, height=0.1, distance=5)

        if len(peaks) < 3:
            return 0.5

        # 计算峰值间隔
        intervals = np.diff(peaks)

        # 规律性 = 1 - 变异系数
        mean_interval = np.mean(intervals)
        std_interval = np.std(intervals)

        if mean_interval > 0:
            cv = std_interval / mean_interval
            regularity = 1.0 - min(cv, 1.0)
        else:
            regularity = 0.5

        return float(regularity)

    def _compute_energy_flux(self, y: np.ndarray) -> float:
        """计算能量变化率"""
        # 分帧计算能量
        frame_len = int(self.sr * 0.05)  # 50ms 帧
        hop_len = int(self.sr * 0.025)   # 25ms hop

        if len(y) < frame_len:
            return 0.5

        frames = np.lib.stride_tricks.sliding_window_view(y, frame_len)[::hop_len]
        energies = np.mean(frames ** 2, axis=1)

        # 计算能量变化
        energy_diff = np.diff(energies)
        energy_flux = np.mean(np.abs(energy_diff))

        # 归一化
        mean_energy = np.mean(energies)
        if mean_energy > 0:
            normalized_flux = energy_flux / mean_energy
        else:
            normalized_flux = 0.0

        return float(np.clip(normalized_flux, 0, 1))


def get_tempo_params(tempo_info: Dict) -> Dict:
    """
    根据节奏信息生成处理参数

    Returns:
        用于自适应音频处理的参数字典
    """
    tempo_class = tempo_info.get("tempo_class", "medium")
    bpm_confidence = tempo_info.get("bpm_confidence", 0.5)
    onset_density = tempo_info.get("onset_density", 0.5)

    params = {
        # 压缩器参数
        "compressor_attack_ms": 10.0,  # 默认 attack
        "compressor_release_ms": 100.0,  # 默认 release
        "compressor_knee_db": 6.0,  # 默认 knee

        # EQ 参数
        "presence_boost_db": 0.0,  # 默认不提升
        "air_boost_db": 0.0,  # 默认不提升
        "stereo_width": 1.0,  # 默认不调整

        # 瞬态处理
        "transient_emphasis": 0.0,  # 默认不强调
        "transient_preservation": 0.5,  # 默认中等保护

        # 细节增强
        "detail_high_freq": 0.0,  # 高频细节
        "detail_spatial": 0.0,  # 空间感
    }

    if tempo_class == "fast":
        # 快节奏：更快响应，强调瞬态，轻微 presence 提升
        params["compressor_attack_ms"] = 5.0
        params["compressor_release_ms"] = 60.0
        params["compressor_knee_db"] = 3.0
        params["presence_boost_db"] = 1.5
        params["transient_emphasis"] = 0.3
        params["transient_preservation"] = 0.7
        params["detail_high_freq"] = 0.2

    elif tempo_class == "slow":
        # 慢节奏：更慢响应，强调空间感和空气感
        params["compressor_attack_ms"] = 20.0
        params["compressor_release_ms"] = 200.0
        params["compressor_knee_db"] = 9.0
        params["air_boost_db"] = 2.0
        params["stereo_width"] = 1.15
        params["transient_emphasis"] = 0.0
        params["transient_preservation"] = 0.8
        params["detail_spatial"] = 0.4

    else:  # medium
        # 中节奏：平衡设置
        params["compressor_attack_ms"] = 10.0
        params["compressor_release_ms"] = 120.0
        params["compressor_knee_db"] = 6.0
        params["presence_boost_db"] = 0.5
        params["air_boost_db"] = 0.5
        params["stereo_width"] = 1.05
        params["transient_preservation"] = 0.6

    # 根据置信度调整（低置信度时趋于默认）
    if bpm_confidence < 0.5:
        # 混合默认和自适应参数
        for key in params:
            default_val = {
                "compressor_attack_ms": 10.0,
                "compressor_release_ms": 100.0,
                "compressor_knee_db": 6.0,
                "presence_boost_db": 0.0,
                "air_boost_db": 0.0,
                "stereo_width": 1.0,
                "transient_emphasis": 0.0,
                "transient_preservation": 0.5,
                "detail_high_freq": 0.0,
                "detail_spatial": 0.0,
            }.get(key, params[key])

            params[key] = default_val + (params[key] - default_val) * bpm_confidence * 2

    return params

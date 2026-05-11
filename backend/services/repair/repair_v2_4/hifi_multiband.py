import numpy as np
from scipy.signal import butter, sosfiltfilt
from functools import lru_cache
from typing import Dict, Optional


class HifiMultibandCompressor:
    """
    HiFi 多段压缩器 - 针对高保真音频优化的多段压缩

    特点：
    - 使用线性相位分频（保持相位一致性）
    - BPM自适应参数（attack/release根据节奏调整）
    - 音乐性压缩曲线（柔和knee）
    - 自适应分频点（基于音乐类型）
    """

    def __init__(self, sr: int, music_type: str = "generic", tempo_params: Optional[Dict] = None):
        self.sr = sr
        self.music_type = music_type
        self.tempo_params = tempo_params or {}

        # 根据音乐类型设置分频点
        self._setup_crossover_frequencies()

        # 设计分频滤波器（使用线性相位sosfiltfilt）
        self._design_filters()

    def _setup_crossover_frequencies(self):
        """根据音乐类型设置分频点"""
        nyq = self.sr / 2

        if self.music_type == "vocal":
            # 人声：重点在中频
            self.low_cross = 250
            self.high_cross = 4000
        elif self.music_type == "electronic":
            # 电子音乐：低频延伸，高频明亮
            self.low_cross = 200
            self.high_cross = 5000
        elif self.music_type == "classical":
            # 古典：更宽的中频
            self.low_cross = 300
            self.high_cross = 3500
        elif self.music_type == "bass_heavy":
            # 重低音：更低的低-中分频
            self.low_cross = 150
            self.high_cross = 4000
        else:
            # 默认
            self.low_cross = 250
            self.high_cross = 4000

        # 确保不超出奈奎斯特频率
        self.low_cross = min(self.low_cross, nyq * 0.45)
        self.high_cross = min(self.high_cross, nyq * 0.9)

        if self.low_cross >= self.high_cross:
            self.low_cross = nyq * 0.1
            self.high_cross = nyq * 0.45

    @lru_cache(maxsize=16)
    def _get_filter_sos(self, sr: int, low_cross: int, high_cross: int):
        """缓存滤波器系数"""
        nyq = sr / 2
        w_low = low_cross / nyq
        w_high = high_cross / nyq

        # 使用4阶Butterworth，sosfiltfilt提供线性相位
        sos_low = butter(4, w_low, btype='low', output='sos')
        sos_mid_low = butter(4, w_low, btype='high', output='sos')
        sos_mid_high = butter(4, w_high, btype='low', output='sos')
        sos_high = butter(4, w_high, btype='high', output='sos')

        return sos_low, sos_mid_low, sos_mid_high, sos_high

    def _design_filters(self):
        """设计分频滤波器"""
        self.sos_low, self.sos_mid_low, self.sos_mid_high, self.sos_high = \
            self._get_filter_sos(self.sr, int(self.low_cross), int(self.high_cross))

    def process(self, y: np.ndarray, amount: float) -> np.ndarray:
        """
        处理音频

        Args:
            y: 输入音频 (n_channels, n_samples) 或 (n_samples,)
            amount: 压缩强度 0-1

        Returns:
            处理后的音频
        """
        if amount <= 0:
            return y

        # 处理单声道
        if y.ndim == 1:
            return self._process_mono(y, amount)

        # 处理立体声/多声道
        result = np.zeros_like(y)
        for ch in range(y.shape[0]):
            result[ch] = self._process_mono(y[ch], amount)
        return result

    def _process_mono(self, y: np.ndarray, amount: float) -> np.ndarray:
        """处理单声道音频"""
        # 分频（使用sosfiltfilt保持线性相位）
        low_band = sosfiltfilt(self.sos_low, y)
        mid_low = sosfiltfilt(self.sos_mid_low, y)
        mid_band = sosfiltfilt(self.sos_mid_high, mid_low)
        high_band = sosfiltfilt(self.sos_high, y)

        # 分别处理每个频段
        low_processed = self._process_band(
            low_band, amount,
            threshold_db=-20.0,
            ratio=2.0,
            makeup_db=2.0
        )

        mid_processed = self._process_band(
            mid_band, amount,
            threshold_db=-18.0,
            ratio=1.8,
            makeup_db=1.0
        )

        high_processed = self._process_band(
            high_band, amount,
            threshold_db=-16.0,
            ratio=1.5,
            makeup_db=0.5
        )

        # 混合
        result = low_processed + mid_processed + high_processed

        # 峰值限制
        peak = np.max(np.abs(result))
        if peak > 0.95:
            result *= 0.95 / peak

        return result

    def _process_band(self, x: np.ndarray, amount: float,
                      threshold_db: float, ratio: float, makeup_db: float) -> np.ndarray:
        """
        处理单个频段

        使用基于包络的压缩，支持BPM自适应参数
        """
        if amount <= 0:
            return x

        # 计算 RMS 包络
        window_size = int(self.sr * 0.01)  # 10ms 窗口
        if window_size < 2:
            window_size = 2

        # 使用滑动窗口计算 RMS
        rms = self._compute_rms_envelope(x, window_size)

        # 转换为 dB
        rms_db = 20 * np.log10(rms + 1e-10)

        # 获取BPM自适应参数
        attack_ms = self.tempo_params.get("compressor_attack_ms", 10.0)
        release_ms = self.tempo_params.get("compressor_release_ms", 100.0)
        knee_db = self.tempo_params.get("compressor_knee_db", 6.0)

        # 计算增益衰减
        gain_reduction_db = np.zeros_like(rms_db)

        for i in range(len(rms_db)):
            over_db = rms_db[i] - threshold_db

            if over_db < -knee_db / 2:
                # 低于阈值，无压缩
                gain_reduction_db[i] = 0.0
            elif over_db < knee_db / 2:
                # 在knee范围内，平滑过渡
                # 使用二次函数实现soft knee
                t = (over_db + knee_db / 2) / knee_db
                gain_reduction_db[i] = -(knee_db / 2) * t * t / ratio
            else:
                # 高于阈值，完全压缩
                gain_reduction_db[i] = -(over_db + (ratio - 1) * knee_db / 2) / ratio + knee_db / 2

        # 平滑增益变化（attack/release）
        gain_reduction_db = self._smooth_gain(
            gain_reduction_db,
            attack_ms,
            release_ms
        )

        # 应用增益
        gain = 10 ** (gain_reduction_db / 20.0)

        # 插值到原始采样率
        gain_interp = np.interp(
            np.linspace(0, len(gain) - 1, len(x)),
            np.arange(len(gain)),
            gain
        )

        # 应用 makeup gain
        makeup_linear = 10 ** (makeup_db * amount / 20.0)

        return x * gain_interp * makeup_linear

    def _compute_rms_envelope(self, x: np.ndarray, window_size: int) -> np.ndarray:
        """计算 RMS 包络"""
        hop_size = window_size // 2
        n_frames = (len(x) - window_size) // hop_size + 1

        if n_frames <= 0:
            return np.array([np.sqrt(np.mean(x ** 2))])

        rms = np.zeros(n_frames)
        for i in range(n_frames):
            start = i * hop_size
            end = start + window_size
            frame = x[start:end]
            rms[i] = np.sqrt(np.mean(frame ** 2))

        return rms

    def _smooth_gain(self, gain_db: np.ndarray, attack_ms: float, release_ms: float) -> np.ndarray:
        """
        平滑增益变化（模拟 attack/release）

        使用一阶低通滤波器模拟压缩器的响应时间
        """
        hop_time_ms = 5.0  # 假设 5ms hop（基于 _compute_rms_envelope 的 hop_size）

        # 计算时间常数
        attack_coef = np.exp(-hop_time_ms / attack_ms) if attack_ms > 0 else 0
        release_coef = np.exp(-hop_time_ms / release_ms) if release_ms > 0 else 0

        smoothed = np.zeros_like(gain_db)
        smoothed[0] = gain_db[0]

        for i in range(1, len(gain_db)):
            if gain_db[i] < smoothed[i - 1]:
                # 增益减小（压缩开始）- 使用 attack 时间
                smoothed[i] = attack_coef * smoothed[i - 1] + (1 - attack_coef) * gain_db[i]
            else:
                # 增益恢复 - 使用 release 时间
                smoothed[i] = release_coef * smoothed[i - 1] + (1 - release_coef) * gain_db[i]

        return smoothed


def apply_hifi_multiband_compress(y: np.ndarray, sr: int, amount: float,
                                   music_type: str = "generic",
                                   tempo_params: Optional[Dict] = None) -> np.ndarray:
    """
    便捷函数：应用 HiFi 多段压缩

    Args:
        y: 输入音频
        sr: 采样率
        amount: 压缩强度 0-1
        music_type: 音乐类型
        tempo_params: 节奏参数（可选）

    Returns:
        处理后的音频
    """
    compressor = HifiMultibandCompressor(sr, music_type, tempo_params)
    return compressor.process(y, amount)

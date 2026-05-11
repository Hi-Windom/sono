import numpy as np
from scipy.signal import butter, sosfiltfilt
from typing import Dict, Optional
from services.dsp_utils import stft, istft


class AdaptiveDetailEnhance:
    """
    自适应细节增强器 - 基于BPM的细节增强

    特点：
    - 高BPM: 强调瞬态清晰度，轻微高频提升（"有力""不糊"）
    - 低BPM: 强调空间感和空气感（"通透""华丽"）
    - 使用并行处理（dry/wet mix）保持自然度
    """

    def __init__(self, sr: int, tempo_params: Optional[Dict] = None):
        self.sr = sr
        self.tempo_params = tempo_params or {}

        # 设计滤波器
        self._design_filters()

    def _design_filters(self):
        """设计处理所需的滤波器"""
        nyq = self.sr / 2

        # 高频细节滤波器 (4kHz+)
        high_freq = min(4000, nyq * 0.45)
        self.sos_high = butter(4, high_freq / nyq, btype='high', output='sos')

        # 空气感滤波器 (10kHz+)
        air_freq = min(10000, nyq * 0.9)
        if air_freq < nyq * 0.95:
            self.sos_air = butter(4, air_freq / nyq, btype='high', output='sos')
        else:
            self.sos_air = None

        # 瞬态强调滤波器（带通，突出打击感）
        transient_low = 2000
        transient_high = min(8000, nyq * 0.9)
        if transient_high > transient_low:
            self.sos_transient = butter(4, [transient_low / nyq, transient_high / nyq],
                                        btype='band', output='sos')
        else:
            self.sos_transient = None

    def process(self, y: np.ndarray, amount: float = 0.3) -> np.ndarray:
        """
        处理音频

        Args:
            y: 输入音频 (n_channels, n_samples) 或 (n_samples,)
            amount: 增强强度 0-1

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
        # 获取BPM自适应参数
        detail_high_freq = self.tempo_params.get("detail_high_freq", 0.0)
        detail_spatial = self.tempo_params.get("detail_spatial", 0.0)
        transient_emphasis = self.tempo_params.get("transient_emphasis", 0.0)
        stereo_width = self.tempo_params.get("stereo_width", 1.0)

        # 原始信号（dry）
        dry = y.copy()
        wet = np.zeros_like(y, dtype=np.float64)

        # 1. 高频细节增强
        if detail_high_freq > 0:
            high_detail = sosfiltfilt(self.sos_high, y)
            # 使用轻度饱和增强细节感
            high_enhanced = self._gentle_saturation(high_detail, amount * detail_high_freq)
            wet += high_enhanced * 0.3

        # 2. 空气感增强（仅慢节奏）
        if detail_spatial > 0 and self.sos_air is not None:
            air_detail = sosfiltfilt(self.sos_air, y)
            # 使用非常轻柔的处理
            air_enhanced = air_detail * (1.0 + amount * detail_spatial * 0.5)
            wet += air_enhanced * 0.2

        # 3. 瞬态强调（仅快节奏）
        if transient_emphasis > 0 and self.sos_transient is not None:
            transient_detail = sosfiltfilt(self.sos_transient, y)
            # 检测瞬态并强调
            transient_enhanced = self._emphasize_transients(
                transient_detail, amount * transient_emphasis
            )
            wet += transient_enhanced * 0.4

        # 4. 混合 dry/wet
        # 使用并行处理保持自然度
        wet_gain = amount * 0.4  # 最大 40% wet 信号
        result = dry * (1.0 - wet_gain) + wet * wet_gain

        # 5. 峰值限制
        peak = np.max(np.abs(result))
        if peak > 0.98:
            result *= 0.98 / peak

        return result.astype(y.dtype)

    def _gentle_saturation(self, x: np.ndarray, amount: float) -> np.ndarray:
        """
        轻度饱和处理 - 增加谐波但不刺耳

        使用 tanh 曲线，但非常保守
        """
        if amount <= 0:
            return x

        # 归一化到合适范围
        max_val = np.max(np.abs(x))
        if max_val < 1e-10:
            return x

        # 使用非常柔和的 tanh
        drive = 0.5 * amount  # 驱动量很小
        normalized = x / max_val * drive
        saturated = np.tanh(normalized) * max_val / drive

        # 混合原始和处理后
        return x * (1.0 - amount * 0.3) + saturated * (amount * 0.3)

    def _emphasize_transients(self, x: np.ndarray, amount: float) -> np.ndarray:
        """
        强调瞬态 - 让快节奏音乐更"有力"

        使用微分+峰值检测来定位瞬态
        """
        if amount <= 0:
            return x

        # 计算包络
        window_size = int(self.sr * 0.005)  # 5ms
        if window_size < 2:
            window_size = 2

        # 绝对值包络
        abs_x = np.abs(x)

        # 简单的移动平均平滑
        kernel = np.ones(window_size) / window_size
        envelope = np.convolve(abs_x, kernel, mode='same')

        # 检测包络变化（瞬态位置）
        envelope_diff = np.diff(envelope, prepend=envelope[0])
        transient_mask = envelope_diff > 0

        # 创建瞬态强调增益
        gain = np.ones_like(x)
        gain[transient_mask] = 1.0 + amount * 0.3  # 最大 30% 提升

        # 平滑增益变化
        gain = np.convolve(gain, kernel, mode='same')

        return x * gain


def apply_adaptive_detail_enhance(y: np.ndarray, sr: int, amount: float = 0.3,
                                   tempo_params: Optional[Dict] = None) -> np.ndarray:
    """
    便捷函数：应用自适应细节增强

    Args:
        y: 输入音频
        sr: 采样率
        amount: 增强强度 0-1
        tempo_params: 节奏参数（可选）

    Returns:
        处理后的音频
    """
    enhancer = AdaptiveDetailEnhance(sr, tempo_params)
    return enhancer.process(y, amount)


class StereoEnhancer:
    """
    立体声增强器 - 用于低BPM音乐的空间感增强
    """

    def __init__(self, sr: int, width: float = 1.1):
        self.sr = sr
        self.width = width

    def process(self, y: np.ndarray) -> np.ndarray:
        """
        处理立体声音频

        Args:
            y: 立体声音频 (2, n_samples)

        Returns:
            处理后的立体声音频
        """
        if y.ndim != 2 or y.shape[0] != 2:
            return y

        if self.width <= 1.0:
            return y

        left = y[0].astype(np.float64)
        right = y[1].astype(np.float64)

        # 转换为 M/S（中/侧）
        mid = (left + right) / 2.0
        side = (left - right) / 2.0

        # 增强 side 信号
        side_gain = self.width
        side_enhanced = side * side_gain

        # 转换回 L/R
        left_new = mid + side_enhanced
        right_new = mid - side_enhanced

        # 归一化（防止电平变化）
        original_peak = max(np.max(np.abs(left)), np.max(np.abs(right)))
        new_peak = max(np.max(np.abs(left_new)), np.max(np.abs(right_new)))

        if new_peak > 0 and original_peak > 0:
            normalize_gain = original_peak / new_peak
            left_new *= normalize_gain
            right_new *= normalize_gain

        result = np.zeros_like(y)
        result[0] = left_new
        result[1] = right_new

        return result


def apply_stereo_enhance(y: np.ndarray, sr: int, width: float = 1.1) -> np.ndarray:
    """
    便捷函数：应用立体声增强

    Args:
        y: 立体声音频
        sr: 采样率
        width: 宽度因子 (>1 增加宽度)

    Returns:
        处理后的音频
    """
    enhancer = StereoEnhancer(sr, width)
    return enhancer.process(y)

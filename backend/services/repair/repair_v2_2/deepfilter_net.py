"""
DeepFilterNet 封装 - 高性能降噪
使用 DeepFilterNet2 模型，比实时快 50 倍
"""

import numpy as np
import logging

logger = logging.getLogger(__name__)

# 尝试导入 DeepFilterNet
try:
    from df import enhance, init_df
    DEEPFILTER_AVAILABLE = True
    logger.info("DeepFilterNet loaded successfully")
except ImportError:
    DEEPFILTER_AVAILABLE = False
    logger.warning("DeepFilterNet not available, falling back to Wiener filter")


class DeepFilterNetDenoiser:
    """DeepFilterNet 降噪器封装"""

    def __init__(self, model_name: str = "DeepFilterNet2"):
        """
        初始化 DeepFilterNet 降噪器

        Args:
            model_name: 模型名称，可选 "DeepFilterNet", "DeepFilterNet2", "DeepFilterNet3"
        """
        self.model = None
        self.df_state = None
        self.sr = 48000  # DeepFilterNet 只支持 48kHz

        if DEEPFILTER_AVAILABLE:
            try:
                self.model, self.df_state, _ = init_df(model_name)
                logger.info(f"DeepFilterNet initialized with model: {model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize DeepFilterNet: {e}")
                self.model = None

    def is_available(self) -> bool:
        """检查 DeepFilterNet 是否可用"""
        return DEEPFILTER_AVAILABLE and self.model is not None

    def process(self, audio: np.ndarray, sr: int, intensity: float = 1.0) -> np.ndarray:
        """
        处理音频

        Args:
            audio: 输入音频，shape (channels, samples) 或 (samples,)
            sr: 采样率
            intensity: 处理强度 0-1，用于混合原始和处理后的音频

        Returns:
            处理后的音频
        """
        if not self.is_available():
            logger.warning("DeepFilterNet not available, returning original audio")
            return audio

        # 处理单声道/多声道
        if audio.ndim == 1:
            audio = audio.reshape(1, -1)
            was_mono = True
        else:
            was_mono = False

        result = np.zeros_like(audio)

        for ch in range(audio.shape[0]):
            try:
                # DeepFilterNet 需要 48kHz
                if sr != self.sr:
                    from scipy.signal import resample_poly
                    audio_48k = resample_poly(audio[ch], self.sr, sr)
                else:
                    audio_48k = audio[ch]

                # 确保是 float32
                audio_48k = audio_48k.astype(np.float32)

                # DeepFilterNet 处理
                enhanced = enhance(self.model, self.df_state, audio_48k)

                # 如果重采样了，需要恢复原始采样率
                if sr != self.sr:
                    enhanced = resample_poly(enhanced, sr, self.sr)

                # 确保长度一致
                if len(enhanced) > len(audio[ch]):
                    enhanced = enhanced[:len(audio[ch])]
                elif len(enhanced) < len(audio[ch]):
                    enhanced = np.pad(enhanced, (0, len(audio[ch]) - len(enhanced)))

                # 混合（根据强度）
                result[ch] = enhanced * intensity + audio[ch] * (1 - intensity)

            except Exception as e:
                logger.error(f"DeepFilterNet processing error for channel {ch}: {e}")
                result[ch] = audio[ch]

        if was_mono:
            result = result[0]

        return result


# 全局降噪器实例（延迟初始化）
_denoiser_instance = None


def get_denoiser() -> DeepFilterNetDenoiser:
    """获取全局降噪器实例"""
    global _denoiser_instance
    if _denoiser_instance is None:
        _denoiser_instance = DeepFilterNetDenoiser()
    return _denoiser_instance


def apply_deepfilter_denoise(y: np.ndarray, sr: int, intensity: float = 1.0) -> np.ndarray:
    """
    便捷函数：应用 DeepFilterNet 降噪

    Args:
        y: 输入音频
        sr: 采样率
        intensity: 处理强度

    Returns:
        降噪后的音频
    """
    denoiser = get_denoiser()
    return denoiser.process(y, sr, intensity)

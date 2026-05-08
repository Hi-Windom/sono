import numpy as np
from typing import Dict, Tuple, Optional
from services.librosa_compat import stft, fft_frequencies


class MusicTypeDetector:
    """音乐类型检测器 - 基于频谱特征自动识别音乐类型"""

    MUSIC_TYPES = ["vocal", "instrumental", "electronic", "classical", "pop", "generic"]

    def __init__(self, sr: int = 48000):
        self.sr = sr
        self.n_fft = 2048
        self.hop_length = 512

    def detect(self, y: np.ndarray) -> Tuple[str, float, Dict]:
        """
        检测音乐类型

        Returns:
            music_type: 音乐类型字符串
            confidence: 检测置信度 0-1
            features: 特征字典
        """
        if y.ndim == 1:
            y = y.reshape(1, -1)

        features = self._extract_features(y)

        vocal_score = self._calc_vocal_score(features)
        electronic_score = self._calc_electronic_score(features)
        classical_score = self._calc_classical_score(features)
        pop_score = self._calc_pop_score(features)
        instrumental_score = self._calc_instrumental_score(features)

        scores = {
            "vocal": vocal_score,
            "instrumental": instrumental_score,
            "electronic": electronic_score,
            "classical": classical_score,
            "pop": pop_score,
        }

        music_type = max(scores, key=scores.get)
        confidence = scores[music_type]

        if confidence < 0.5:
            music_type = "generic"
            confidence = 0.5

        return music_type, confidence, features

    def _extract_features(self, y: np.ndarray) -> Dict:
        """提取频谱特征 - 优化：缓存STFT结果避免重复计算"""
        features = {}

        mono = y[0] if y.shape[0] > 0 else y
        # 只计算一次STFT
        S = stft(mono, n_fft=self.n_fft, hop_length=self.hop_length)
        mag = np.abs(S)
        freqs = fft_frequencies(sr=self.sr, n_fft=self.n_fft)

        # 预计算帧能量，多个特征复用
        frame_energy = np.sum(mag, axis=0)
        frame_energy_safe = frame_energy + 1e-10

        features["spectral_centroid"] = self._spectral_centroid(mag, freqs, frame_energy_safe)
        features["spectral_bandwidth"] = self._spectral_bandwidth(mag, freqs, frame_energy_safe)
        features["spectral_contrast"] = self._spectral_contrast(mag, freqs)
        features["spectral_rolloff"] = self._spectral_rolloff(mag, freqs)
        features["zero_crossing_rate"] = self._zero_crossing_rate(mono)
        features["rms"] = self._rms(mono)
        features["vocal_band_energy"] = self._vocal_band_energy(mag, freqs)
        features["harmonic_ratio"] = self._harmonic_ratio(mag, freqs)
        features["rhythmic_regularity"] = self._rhythmic_regularity(frame_energy)

        return features

    def _spectral_centroid(self, mag: np.ndarray, freqs: np.ndarray, frame_energy: np.ndarray) -> float:
        """频谱质心 - 使用预计算的帧能量"""
        centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / frame_energy
        return np.mean(centroid)

    def _spectral_bandwidth(self, mag: np.ndarray, freqs: np.ndarray, frame_energy: np.ndarray) -> float:
        """频谱带宽 - 复用质心计算结果"""
        centroid = np.sum(freqs[:, np.newaxis] * mag, axis=0) / frame_energy
        bandwidth = np.sum(np.abs(freqs[:, np.newaxis] - centroid) * mag, axis=0) / frame_energy
        return np.mean(bandwidth)

    def _spectral_contrast(self, mag: np.ndarray, freqs: np.ndarray) -> float:
        """频谱对比度 - 向量化计算"""
        bands = [(200, 1000), (1000, 4000), (4000, 8000), (8000, 16000)]
        contrasts = []
        for low, high in bands:
            mask = (freqs >= low) & (freqs < high)
            if np.any(mask):
                band_mag = mag[mask, :]
                peak = np.max(band_mag, axis=0)
                valley = np.min(band_mag, axis=0)
                contrast = np.mean(np.log(peak + 1e-10) - np.log(valley + 1e-10))
                contrasts.append(contrast)
        return np.mean(contrasts) if contrasts else 0.0

    def _spectral_rolloff(self, mag: np.ndarray, freqs: np.ndarray) -> float:
        """频谱滚降频率 - 向量化"""
        total_energy = np.sum(mag, axis=0)
        cumsum = np.cumsum(mag, axis=0)
        threshold = 0.85 * total_energy
        rolloff_idx = np.argmax(cumsum >= threshold, axis=0)
        return np.mean(freqs[rolloff_idx])

    def _zero_crossing_rate(self, y: np.ndarray) -> float:
        """零交叉率"""
        return np.mean(np.abs(np.diff(np.sign(y)))) / 2

    def _rms(self, y: np.ndarray) -> float:
        """RMS 能量"""
        return np.sqrt(np.mean(y ** 2))

    def _vocal_band_energy(self, mag: np.ndarray, freqs: np.ndarray) -> float:
        """人声频段能量占比 (200Hz - 4kHz)"""
        vocal_mask = (freqs >= 200) & (freqs <= 4000)
        vocal_energy = np.sum(mag[vocal_mask, :] ** 2)
        total_energy = np.sum(mag ** 2)
        return vocal_energy / (total_energy + 1e-10)

    def _harmonic_ratio(self, mag: np.ndarray, freqs: np.ndarray) -> float:
        """谐波比例 - 向量化峰值检测和谐波匹配"""
        n_frames = min(100, mag.shape[1])
        if n_frames < 1:
            return 0.5

        # 向量化峰值检测：使用滑动窗口最大值
        min_dist = 5
        # 对前100帧进行批量处理
        frames = mag[:, :n_frames]

        # 计算每个点是否是局部峰值
        # 使用卷积方式：比较当前点与左右min_dist范围内的最大值
        padded = np.pad(frames, ((min_dist, min_dist), (0, 0)), mode='edge')
        left_max = np.zeros_like(frames)
        right_max = np.zeros_like(frames)

        for d in range(1, min_dist + 1):
            left_max = np.maximum(left_max, padded[min_dist - d:min_dist - d + frames.shape[0], :])
            right_max = np.maximum(right_max, padded[min_dist + d:min_dist + d + frames.shape[0], :])

        is_peak = (frames > left_max) & (frames > right_max)

        # 阈值：大于均值2倍
        mean_vals = np.mean(frames, axis=0, keepdims=True)
        is_peak &= frames > mean_vals * 2

        frame_harmonics = []
        for i in range(n_frames):
            peak_indices = np.where(is_peak[:, i])[0]
            if len(peak_indices) < 3:
                continue

            # 将频率bin索引转换为近似频率比
            fundamental = peak_indices[0]
            ratios = peak_indices[1:] / (fundamental + 1e-10)

            # 向量化谐波匹配
            harmonic_targets = np.array([2, 3, 4, 5])
            # 检查每个ratio是否接近任意谐波目标
            diffs = np.abs(ratios[:, np.newaxis] - harmonic_targets[np.newaxis, :])
            harmonic_count = np.sum(np.any(diffs < 0.1, axis=1))
            frame_harmonics.append(harmonic_count / len(peak_indices))

        return np.mean(frame_harmonics) if frame_harmonics else 0.5

    def _rhythmic_regularity(self, frame_energy: np.ndarray) -> float:
        """节奏规律性 - 复用预计算的帧能量"""
        if len(frame_energy) < 10:
            return 0.5
        diff = np.diff(frame_energy)
        regularity = 1.0 - np.std(diff) / (np.mean(np.abs(diff)) + 1e-10)
        return np.clip(regularity, 0, 1)

    def _calc_vocal_score(self, features: Dict) -> float:
        """计算人声得分"""
        score = 0.0

        vocal_band = features["vocal_band_energy"]
        score += vocal_band * 0.3

        centroid = features["spectral_centroid"]
        if 800 < centroid < 3000:
            score += 0.25

        bandwidth = features["spectral_bandwidth"]
        if 1500 < bandwidth < 4000:
            score += 0.2

        zcr = features["zero_crossing_rate"]
        if zcr < 0.1:
            score += 0.15

        harmonic = features["harmonic_ratio"]
        if harmonic > 0.3:
            score += 0.1

        return min(score, 1.0)

    def _calc_electronic_score(self, features: Dict) -> float:
        """计算电子音乐得分"""
        score = 0.0

        rhythmic = features["rhythmic_regularity"]
        score += rhythmic * 0.3

        centroid = features["spectral_centroid"]
        if centroid > 3000:
            score += 0.2

        contrast = features["spectral_contrast"]
        if contrast > 15:
            score += 0.25

        bandwidth = features["spectral_bandwidth"]
        if bandwidth > 3000:
            score += 0.15

        rolloff = features["spectral_rolloff"]
        if rolloff > 8000:
            score += 0.1

        return min(score, 1.0)

    def _calc_classical_score(self, features: Dict) -> float:
        """计算古典音乐得分"""
        score = 0.0

        dynamic_range = np.std(features["rms"]) if isinstance(features["rms"], np.ndarray) else 0.1
        score += min(dynamic_range * 2, 0.25)

        harmonic = features["harmonic_ratio"]
        if harmonic > 0.5:
            score += 0.25

        contrast = features["spectral_contrast"]
        if 10 < contrast < 20:
            score += 0.2

        centroid = features["spectral_centroid"]
        if 500 < centroid < 2500:
            score += 0.15

        rhythmic = features["rhythmic_regularity"]
        if rhythmic < 0.6:
            score += 0.15

        return min(score, 1.0)

    def _calc_pop_score(self, features: Dict) -> float:
        """计算流行音乐得分"""
        score = 0.0

        vocal_band = features["vocal_band_energy"]
        if 0.4 < vocal_band < 0.7:
            score += 0.25

        rhythmic = features["rhythmic_regularity"]
        if 0.4 < rhythmic < 0.8:
            score += 0.25

        centroid = features["spectral_centroid"]
        if 1500 < centroid < 4000:
            score += 0.2

        bandwidth = features["spectral_bandwidth"]
        if 2000 < bandwidth < 4500:
            score += 0.15

        contrast = features["spectral_contrast"]
        if 8 < contrast < 18:
            score += 0.15

        return min(score, 1.0)

    def _calc_instrumental_score(self, features: Dict) -> float:
        """计算纯器乐得分"""
        score = 0.0

        vocal_band = features["vocal_band_energy"]
        if vocal_band < 0.5:
            score += 0.3

        harmonic = features["harmonic_ratio"]
        if harmonic > 0.4:
            score += 0.25

        centroid = features["spectral_centroid"]
        if centroid > 1000:
            score += 0.2

        contrast = features["spectral_contrast"]
        if contrast > 10:
            score += 0.15

        zcr = features["zero_crossing_rate"]
        if zcr > 0.05:
            score += 0.1

        return min(score, 1.0)


def detect_music_type(y: np.ndarray, sr: int = 48000) -> Tuple[str, float, Dict]:
    """便捷函数：检测音乐类型"""
    detector = MusicTypeDetector(sr=sr)
    return detector.detect(y)

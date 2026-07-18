import time
import json
import logging
import threading
from collections import defaultdict, deque
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PerfTimer:
    def __init__(self, name: str, metadata: Optional[dict] = None):
        self.name = name
        self.metadata = metadata or {}
        self.start_time = 0.0
        self.end_time = 0.0
        self.duration_ms = 0.0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        PerfMetricsCollector.get_instance().record_step(
            self.name, self.duration_ms, self.metadata
        )
        return False


class PerfMetricsCollector:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.step_history = defaultdict(lambda: deque(maxlen=1000))
        self.repair_history = deque(maxlen=100)
        self.detect_history = deque(maxlen=100)
        self.upload_history = deque(maxlen=100)
        self.download_history = deque(maxlen=100)
        self.current_repair_steps = {}
        self._thread_local = threading.local()
        self._data_lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _get_thread_steps(self):
        if not hasattr(self._thread_local, 'steps'):
            self._thread_local.steps = {}
        return self._thread_local.steps

    def record_step(self, step_name: str, duration_ms: float, metadata: Optional[dict] = None):
        with self._data_lock:
            self.step_history[step_name].append({
                'duration_ms': duration_ms,
                'timestamp': time.time(),
                'metadata': metadata or {}
            })
        steps = self._get_thread_steps()
        steps[step_name] = duration_ms
        logger.debug(f"[perf] {step_name}: {duration_ms:.2f}ms")

    def start_repair(self, task_id: str):
        self._thread_local.steps = {}
        self._thread_local.start_time = time.perf_counter()
        self._thread_local.task_id = task_id

    def end_repair(self, task_id: str, size_samples: int, algorithm_version: str) -> dict:
        end_time = time.perf_counter()
        start_time = getattr(self._thread_local, 'start_time', end_time)
        steps = getattr(self._thread_local, 'steps', {})
        total_time_ms = (end_time - start_time) * 1000

        duration_seconds = total_time_ms / 1000
        audio_duration_seconds = size_samples / 48000
        xrtf = audio_duration_seconds / duration_seconds if duration_seconds > 0 else 0

        result = {
            'task_id': task_id,
            'total_time_ms': total_time_ms,
            'size_samples': size_samples,
            'algorithm_version': algorithm_version,
            'xrtf': round(xrtf, 2),
            'breakdown_by_step': {k: round(v, 2) for k, v in steps.items()},
            'timestamp': time.time()
        }

        with self._data_lock:
            self.repair_history.append(result)
        logger.info(f"[perf] repair completed: task_id={task_id} total={total_time_ms:.1f}ms xRTF={xrtf:.2f}x")
        return result

    def start_detect(self, task_id: str):
        self._thread_local.steps = {}
        self._thread_local.start_time = time.perf_counter()
        self._thread_local.task_id = task_id

    def end_detect(self, task_id: str, detector_version: str) -> dict:
        end_time = time.perf_counter()
        start_time = getattr(self._thread_local, 'start_time', end_time)
        steps = getattr(self._thread_local, 'steps', {})
        total_time_ms = (end_time - start_time) * 1000

        result = {
            'task_id': task_id,
            'total_time_ms': total_time_ms,
            'detector_version': detector_version,
            'breakdown_by_step': {k: round(v, 2) for k, v in steps.items()},
            'timestamp': time.time()
        }

        with self._data_lock:
            self.detect_history.append(result)
        logger.info(f"[perf] detect completed: task_id={task_id} total={total_time_ms:.1f}ms")
        return result

    def record_upload(self, file_size: int, duration_ms: float):
        with self._data_lock:
            self.upload_history.append({
                'file_size': file_size,
                'duration_ms': duration_ms,
                'timestamp': time.time()
            })

    def record_download(self, file_size: int, duration_ms: float):
        with self._data_lock:
            self.download_history.append({
                'file_size': file_size,
                'duration_ms': duration_ms,
                'timestamp': time.time()
            })

    def get_summary(self) -> dict:
        def calc_stats(history, key='total_time_ms'):
            if not history:
                return {'count': 0, 'avg_ms': 0, 'min_ms': 0, 'max_ms': 0, 'p50_ms': 0, 'p95_ms': 0}
            values = sorted([h[key] for h in history])
            n = len(values)
            return {
                'count': n,
                'avg_ms': round(sum(values) / n, 2),
                'min_ms': round(values[0], 2),
                'max_ms': round(values[-1], 2),
                'p50_ms': round(values[n // 2], 2),
                'p95_ms': round(values[int(n * 0.95)] if n > 0 else 0, 2),
            }

        def calc_xrtf_stats(history):
            if not history:
                return {'avg': 0, 'min': 0, 'max': 0}
            values = [h.get('xrtf', 0) for h in history if h.get('xrtf', 0) > 0]
            if not values:
                return {'avg': 0, 'min': 0, 'max': 0}
            return {
                'avg': round(sum(values) / len(values), 2),
                'min': round(min(values), 2),
                'max': round(max(values), 2),
            }

        with self._data_lock:
            repair_history = list(self.repair_history)
            detect_history = list(self.detect_history)
            upload_history = list(self.upload_history)
            download_history = list(self.download_history)
            step_history_snapshot = {}
            for step, hist in self.step_history.items():
                step_history_snapshot[step] = list(hist)

        by_version = defaultdict(list)
        for h in repair_history:
            ver = h.get('algorithm_version', 'unknown')
            by_version[ver].append(h)

        version_stats = {}
        for ver, hist in by_version.items():
            stats = calc_stats(hist)
            stats['xrtf'] = calc_xrtf_stats(hist)
            version_stats[ver] = stats

        step_stats = {}
        for step, hist in step_history_snapshot.items():
            durations = [h['duration_ms'] for h in hist]
            if durations:
                durations.sort()
                n = len(durations)
                step_stats[step] = {
                    'count': n,
                    'avg_ms': round(sum(durations) / n, 2),
                    'min_ms': round(durations[0], 2),
                    'max_ms': round(durations[-1], 2),
                    'p50_ms': round(durations[n // 2], 2),
                    'p95_ms': round(durations[int(n * 0.95)] if n > 0 else 0, 2),
                }

        return {
            'repair': {
                'overall': calc_stats(repair_history),
                'xrtf': calc_xrtf_stats(repair_history),
                'by_version': version_stats,
                'recent_count': len(repair_history),
            },
            'detect': {
                'overall': calc_stats(detect_history),
                'recent_count': len(detect_history),
            },
            'upload': {
                'overall': calc_stats([{'total_time_ms': h['duration_ms']} for h in upload_history]),
                'recent_count': len(upload_history),
            },
            'download': {
                'overall': calc_stats([{'total_time_ms': h['duration_ms']} for h in download_history]),
                'recent_count': len(download_history),
            },
            'steps': step_stats,
            'generated_at': time.time(),
        }


def perf_timer(name: str, metadata: Optional[dict] = None):
    return PerfTimer(name, metadata)


def get_perf_collector() -> PerfMetricsCollector:
    return PerfMetricsCollector.get_instance()

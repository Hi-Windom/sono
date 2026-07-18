from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from typing import Optional


class SecurityError(ValueError):
    pass


class SafeFileGateway:
    _MAX_LOCKS = 1000

    def __init__(self, base_dir: str):
        self._base_dir = os.path.realpath(base_dir)
        os.makedirs(self._base_dir, exist_ok=True)
        self._locks: OrderedDict[str, threading.Lock] = OrderedDict()
        self._global_lock = threading.Lock()

    @property
    def base_dir(self) -> str:
        return self._base_dir

    def resolve(self, filename: str) -> str:
        if not filename or "\\" in filename or "/" in filename:
            raise SecurityError(f"Invalid filename: {filename!r}")
        basename = os.path.basename(filename)
        if not basename or basename != filename or basename in (".", ".."):
            raise SecurityError(f"Invalid filename: {filename!r}")
        full_path = os.path.realpath(os.path.join(self._base_dir, basename))
        if not full_path.startswith(self._base_dir + os.sep):
            raise SecurityError(f"Path traversal detected: {filename!r}")
        return full_path

    def get_lock(self, filename: str) -> threading.Lock:
        basename = os.path.basename(filename)
        with self._global_lock:
            if basename in self._locks:
                self._locks.move_to_end(basename)
                return self._locks[basename]
            if len(self._locks) >= self._MAX_LOCKS:
                keys_to_evict = []
                for key in self._locks:
                    lock = self._locks[key]
                    if lock.acquire(blocking=False):
                        lock.release()
                        keys_to_evict.append(key)
                        if len(keys_to_evict) >= len(self._locks) - self._MAX_LOCKS + 1:
                            break
                for key in keys_to_evict:
                    del self._locks[key]
            lock = threading.Lock()
            self._locks[basename] = lock
            return lock

    def exists(self, filename: str) -> bool:
        try:
            full_path = self.resolve(filename)
        except SecurityError:
            return False
        return os.path.isfile(full_path)

    def safe_write(self, filename: str, data: bytes, mode: str = "wb") -> None:
        full_path = self.resolve(filename)
        lock = self.get_lock(filename)
        with lock:
            temp_path = full_path + ".tmp"
            try:
                with open(temp_path, mode) as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp_path, full_path)
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass

    def safe_rename(self, temp_filename: str, final_filename: str) -> None:
        temp_path = self.resolve(temp_filename)
        final_path = self.resolve(final_filename)
        temp_lock = self.get_lock(temp_filename)
        final_lock = self.get_lock(final_filename)
        first_lock, second_lock = (temp_lock, final_lock) if id(temp_lock) < id(final_lock) else (final_lock, temp_lock)
        with first_lock:
            with second_lock:
                if not os.path.isfile(temp_path):
                    raise FileNotFoundError(f"File not found: {temp_filename}")
                os.replace(temp_path, final_path)

    def safe_delete(self, filename: str) -> bool:
        try:
            full_path = self.resolve(filename)
        except SecurityError:
            return False
        lock = self.get_lock(filename)
        with lock:
            if os.path.isfile(full_path):
                os.remove(full_path)
                return True
            return False

    def get_size(self, filename: str) -> int:
        full_path = self.resolve(filename)
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"File not found: {filename}")
        return os.path.getsize(full_path)

    def list_files(self) -> list[str]:
        if not os.path.isdir(self._base_dir):
            return []
        result = []
        for fname in os.listdir(self._base_dir):
            full_path = os.path.join(self._base_dir, fname)
            if os.path.isfile(full_path):
                result.append(fname)
        return result

    def get_dir_size(self) -> int:
        total = 0
        if not os.path.isdir(self._base_dir):
            return 0
        for dirpath, _, filenames in os.walk(self._base_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total += os.path.getsize(fp)
        return total


def _get_config():
    import config
    return config.OUTPUT_DIR, config.UPLOAD_DIR


_output_gateway: Optional[SafeFileGateway] = None
_upload_gateway: Optional[SafeFileGateway] = None
_gateway_lock = threading.Lock()


def get_output_gateway() -> SafeFileGateway:
    global _output_gateway
    OUTPUT_DIR, _ = _get_config()
    with _gateway_lock:
        if _output_gateway is None or _output_gateway.base_dir != os.path.realpath(OUTPUT_DIR):
            _output_gateway = SafeFileGateway(OUTPUT_DIR)
        return _output_gateway


def get_upload_gateway() -> SafeFileGateway:
    global _upload_gateway
    _, UPLOAD_DIR = _get_config()
    with _gateway_lock:
        if _upload_gateway is None or _upload_gateway.base_dir != os.path.realpath(UPLOAD_DIR):
            _upload_gateway = SafeFileGateway(UPLOAD_DIR)
        return _upload_gateway


class _LazyGatewayProxy:
    def __init__(self, getter):
        self._getter = getter

    def __getattr__(self, name):
        gateway = self._getter()
        return getattr(gateway, name)


output_gateway = _LazyGatewayProxy(get_output_gateway)
upload_gateway = _LazyGatewayProxy(get_upload_gateway)

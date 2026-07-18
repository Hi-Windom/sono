from abc import ABC, abstractmethod


class ConfigProvider(ABC):
    @abstractmethod
    def get_output_dir(self) -> str:
        pass

    @abstractmethod
    def get_upload_dir(self) -> str:
        pass

    @abstractmethod
    def get_max_concurrent_tasks(self) -> int:
        pass

    @abstractmethod
    def get_source_file_cache_limit_mb(self) -> float:
        pass

    @abstractmethod
    def get_mobile_mode(self) -> bool:
        pass

    @abstractmethod
    def get_default_algorithm_version(self) -> str:
        pass

    @abstractmethod
    def get_stuck_threshold_seconds(self) -> int:
        pass


class EnvConfigProvider(ConfigProvider):
    def get_output_dir(self) -> str:
        import config
        return config.OUTPUT_DIR

    def get_upload_dir(self) -> str:
        import config
        return config.UPLOAD_DIR

    def get_max_concurrent_tasks(self) -> int:
        import config
        return config.MAX_CONCURRENT_TASKS

    def get_source_file_cache_limit_mb(self) -> float:
        import config
        return config.SOURCE_FILE_CACHE_LIMIT / (1024 * 1024)

    def get_mobile_mode(self) -> bool:
        import config
        return config.MOBILE_MODE

    def get_default_algorithm_version(self) -> str:
        import os
        return os.getenv("DEFAULT_ALGORITHM_VERSION", "v2.4a")

    def get_stuck_threshold_seconds(self) -> int:
        import os
        return int(os.getenv("STUCK_THRESHOLD_SECONDS", "30"))


class DictConfigProvider(ConfigProvider):
    def __init__(self, config_dict: dict):
        self._config = config_dict

    def get_output_dir(self) -> str:
        return self._config["output_dir"]

    def get_upload_dir(self) -> str:
        return self._config["upload_dir"]

    def get_max_concurrent_tasks(self) -> int:
        return self._config["max_concurrent_tasks"]

    def get_source_file_cache_limit_mb(self) -> float:
        return self._config["source_file_cache_limit_mb"]

    def get_mobile_mode(self) -> bool:
        return self._config["mobile_mode"]

    def get_default_algorithm_version(self) -> str:
        return self._config["default_algorithm_version"]

    def get_stuck_threshold_seconds(self) -> int:
        return self._config["stuck_threshold_seconds"]


_provider: ConfigProvider | None = None


def get_config_provider() -> ConfigProvider:
    global _provider
    if _provider is None:
        _provider = EnvConfigProvider()
    return _provider


def set_config_provider(provider: ConfigProvider) -> None:
    global _provider
    _provider = provider

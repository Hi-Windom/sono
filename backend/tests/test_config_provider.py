import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from services.config_provider import (
    ConfigProvider,
    EnvConfigProvider,
    DictConfigProvider,
    get_config_provider,
    set_config_provider,
)


class TestEnvConfigProvider:
    def test_get_output_dir(self):
        provider = EnvConfigProvider()
        result = provider.get_output_dir()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_upload_dir(self):
        provider = EnvConfigProvider()
        result = provider.get_upload_dir()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_max_concurrent_tasks(self):
        provider = EnvConfigProvider()
        result = provider.get_max_concurrent_tasks()
        assert isinstance(result, int)
        assert result > 0

    def test_get_source_file_cache_limit_mb(self):
        provider = EnvConfigProvider()
        result = provider.get_source_file_cache_limit_mb()
        assert isinstance(result, float)
        assert result > 0

    def test_get_mobile_mode(self):
        provider = EnvConfigProvider()
        result = provider.get_mobile_mode()
        assert isinstance(result, bool)

    def test_get_default_algorithm_version(self):
        provider = EnvConfigProvider()
        result = provider.get_default_algorithm_version()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_stuck_threshold_seconds(self):
        provider = EnvConfigProvider()
        result = provider.get_stuck_threshold_seconds()
        assert isinstance(result, int)
        assert result > 0

    def test_env_config_provider_not_cached(self):
        import config
        provider = EnvConfigProvider()
        original_value = config.MAX_CONCURRENT_TASKS
        try:
            config.MAX_CONCURRENT_TASKS = 999
            assert provider.get_max_concurrent_tasks() == 999
        finally:
            config.MAX_CONCURRENT_TASKS = original_value


class TestDictConfigProvider:
    def test_dict_config_provider_all_values(self):
        config_dict = {
            "output_dir": "/tmp/output",
            "upload_dir": "/tmp/upload",
            "max_concurrent_tasks": 10,
            "source_file_cache_limit_mb": 512.0,
            "mobile_mode": True,
            "default_algorithm_version": "v3.0",
            "stuck_threshold_seconds": 60,
        }
        provider = DictConfigProvider(config_dict)
        assert provider.get_output_dir() == "/tmp/output"
        assert provider.get_upload_dir() == "/tmp/upload"
        assert provider.get_max_concurrent_tasks() == 10
        assert provider.get_source_file_cache_limit_mb() == 512.0
        assert provider.get_mobile_mode() is True
        assert provider.get_default_algorithm_version() == "v3.0"
        assert provider.get_stuck_threshold_seconds() == 60

    def test_dict_config_provider_mobile_mode_false(self):
        config_dict = {
            "output_dir": "/tmp/out",
            "upload_dir": "/tmp/up",
            "max_concurrent_tasks": 5,
            "source_file_cache_limit_mb": 256.0,
            "mobile_mode": False,
            "default_algorithm_version": "v2.4a",
            "stuck_threshold_seconds": 30,
        }
        provider = DictConfigProvider(config_dict)
        assert provider.get_mobile_mode() is False


class TestGlobalSingleton:
    def test_default_provider_is_env_config_provider(self):
        import services.config_provider as cp
        original = cp._provider
        try:
            cp._provider = None
            provider = get_config_provider()
            assert isinstance(provider, EnvConfigProvider)
        finally:
            cp._provider = original

    def test_set_and_get_config_provider(self):
        original = get_config_provider()
        try:
            test_dict = {
                "output_dir": "/test/out",
                "upload_dir": "/test/up",
                "max_concurrent_tasks": 7,
                "source_file_cache_limit_mb": 100.0,
                "mobile_mode": True,
                "default_algorithm_version": "v1.0",
                "stuck_threshold_seconds": 15,
            }
            dict_provider = DictConfigProvider(test_dict)
            set_config_provider(dict_provider)
            current = get_config_provider()
            assert current is dict_provider
            assert current.get_max_concurrent_tasks() == 7
            assert current.get_default_algorithm_version() == "v1.0"
        finally:
            set_config_provider(original)

    def test_switch_between_providers(self):
        original = get_config_provider()
        try:
            dict_a = {
                "output_dir": "/a/out",
                "upload_dir": "/a/up",
                "max_concurrent_tasks": 1,
                "source_file_cache_limit_mb": 10.0,
                "mobile_mode": False,
                "default_algorithm_version": "va",
                "stuck_threshold_seconds": 10,
            }
            dict_b = {
                "output_dir": "/b/out",
                "upload_dir": "/b/up",
                "max_concurrent_tasks": 2,
                "source_file_cache_limit_mb": 20.0,
                "mobile_mode": True,
                "default_algorithm_version": "vb",
                "stuck_threshold_seconds": 20,
            }
            provider_a = DictConfigProvider(dict_a)
            provider_b = DictConfigProvider(dict_b)

            set_config_provider(provider_a)
            assert get_config_provider().get_default_algorithm_version() == "va"

            set_config_provider(provider_b)
            assert get_config_provider().get_default_algorithm_version() == "vb"

            set_config_provider(provider_a)
            assert get_config_provider().get_default_algorithm_version() == "va"
        finally:
            set_config_provider(original)

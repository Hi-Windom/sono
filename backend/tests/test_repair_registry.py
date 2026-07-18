import sys
import os
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TESTING"] = "1"


class TestRepairRegistryModules:
    def test_repair_modules_dict_exists(self):
        from services.repair_registry import _REPAIR_MODULES
        assert isinstance(_REPAIR_MODULES, dict)
        assert len(_REPAIR_MODULES) > 0

    def test_all_versions_have_module_paths(self):
        from services.repair_registry import _REPAIR_MODULES
        for version, module_path in _REPAIR_MODULES.items():
            assert isinstance(version, str)
            assert isinstance(module_path, str)
            assert module_path.startswith("services.repair.repair_")

    def test_known_versions_exist(self):
        from services.repair_registry import _REPAIR_MODULES
        known_versions = [
            "v2.0", "v2.1", "v2.2", "v2.2a",
            "v2.3", "v2.3a", "v2.4", "v2.4a",
            "v3.0", "v3.0a", "v3.1", "v3.1a",
            "v3.2", "v3.2+", "v3.2a", "v3.2a+",
            "v4.0a", "v4.0a+",
        ]
        for v in known_versions:
            assert v in _REPAIR_MODULES, f"Version {v} should exist in registry"

    def test_get_repair_fn_returns_none_for_unknown_version(self):
        from services.repair_registry import _get_repair_fn
        result = _get_repair_fn("nonexistent_version")
        assert result is None

    def test_get_repair_fn_returns_callable_for_known_version(self):
        from services.repair_registry import _get_repair_fn
        fn = _get_repair_fn("v2.4a")
        assert fn is not None
        assert callable(fn)

    def test_get_repair_fn_caches_results(self):
        from services.repair_registry import _get_repair_fn, _REPAIR_FN_CACHE
        fn1 = _get_repair_fn("v2.4a")
        fn2 = _get_repair_fn("v2.4a")
        assert fn1 is fn2
        assert "v2.4a" in _REPAIR_FN_CACHE


class TestParamDefinitions:
    def test_param_definitions_exists(self):
        from services.repair_registry import PARAM_DEFINITIONS
        assert isinstance(PARAM_DEFINITIONS, dict)
        assert len(PARAM_DEFINITIONS) > 0

    def test_each_param_has_required_fields(self):
        from services.repair_registry import PARAM_DEFINITIONS
        for param_name, definition in PARAM_DEFINITIONS.items():
            assert "key" in definition, f"{param_name} missing 'key'"
            assert "label" in definition, f"{param_name} missing 'label'"
            assert "min" in definition, f"{param_name} missing 'min'"
            assert "max" in definition, f"{param_name} missing 'max'"
            assert "step" in definition, f"{param_name} missing 'step'"

    def test_common_params_exist(self):
        from services.repair_registry import PARAM_DEFINITIONS
        common_params = [
            "de_clipping", "noise_reduction", "de_essing",
            "de_pop", "bass_enhance", "clarity",
            "warmth", "loudness_optimize",
        ]
        for p in common_params:
            assert p in PARAM_DEFINITIONS, f"Common param {p} should exist"

    def test_vocal_params_exist(self):
        from services.repair_registry import PARAM_DEFINITIONS
        vocal_params = [
            "vocal_declip", "vocal_depop", "vocal_de_ess",
            "vocal_ai_repair", "vocal_loudness", "vocal_ratio",
        ]
        for p in vocal_params:
            assert p in PARAM_DEFINITIONS, f"Vocal param {p} should exist"

    def test_inst_params_exist(self):
        from services.repair_registry import PARAM_DEFINITIONS
        inst_params = [
            "inst_declip", "inst_depop", "inst_dynamic",
            "inst_noise_reduction", "inst_loudness", "accompaniment_ratio",
        ]
        for p in inst_params:
            assert p in PARAM_DEFINITIONS, f"Inst param {p} should exist"


class TestAlgorithmVersions:
    def test_algorithm_versions_exists(self):
        from services.repair_registry import ALGORITHM_VERSIONS
        assert isinstance(ALGORITHM_VERSIONS, dict)
        assert len(ALGORITHM_VERSIONS) > 0

    def test_each_version_has_required_fields(self):
        from services.repair_registry import ALGORITHM_VERSIONS
        for version, info in ALGORITHM_VERSIONS.items():
            assert "name" in info, f"{version} missing 'name'"
            assert "label" in info, f"{version} missing 'label'"
            assert "description" in info, f"{version} missing 'description'"
            assert "mobile_compatible" in info, f"{version} missing 'mobile_compatible'"
            assert "supports_dual_track" in info, f"{version} missing 'supports_dual_track'"
            assert "repair_version" in info, f"{version} missing 'repair_version'"
            assert "default_params" in info, f"{version} missing 'default_params'"
            assert "modes" in info, f"{version} missing 'modes'"

    def test_each_mode_has_required_fields(self):
        from services.repair_registry import ALGORITHM_VERSIONS
        for version, info in ALGORITHM_VERSIONS.items():
            for mode in info["modes"]:
                assert "name" in mode, f"{version} mode missing 'name'"
                assert "description" in mode, f"{version} mode missing 'description'"
                assert "params" in mode, f"{version} mode missing 'params'"

    def test_mobile_versions_are_mobile_compatible(self):
        from services.repair_registry import ALGORITHM_VERSIONS
        mobile_versions = ["v2.0", "v2.1", "v2.2a", "v2.3a", "v2.4a", "v3.0a", "v3.1a"]
        for v in mobile_versions:
            assert ALGORITHM_VERSIONS[v]["mobile_compatible"], f"{v} should be mobile compatible"

    def test_desktop_versions_not_mobile_compatible(self):
        from services.repair_registry import ALGORITHM_VERSIONS
        desktop_versions = ["v2.2", "v2.3", "v2.4", "v3.0", "v3.1"]
        for v in desktop_versions:
            if v in ALGORITHM_VERSIONS:
                assert not ALGORITHM_VERSIONS[v]["mobile_compatible"], f"{v} should not be mobile compatible"

    def test_dual_track_versions_support_dual_track(self):
        from services.repair_registry import ALGORITHM_VERSIONS
        dual_versions = ["v3.0", "v3.0a", "v3.1", "v3.1a"]
        for v in dual_versions:
            assert ALGORITHM_VERSIONS[v]["supports_dual_track"], f"{v} should support dual track"

    def test_single_track_versions_no_dual_track(self):
        from services.repair_registry import ALGORITHM_VERSIONS
        single_versions = ["v2.0", "v2.1", "v2.2", "v2.2a", "v2.3", "v2.3a", "v2.4", "v2.4a"]
        for v in single_versions:
            if v in ALGORITHM_VERSIONS:
                assert not ALGORITHM_VERSIONS[v]["supports_dual_track"], f"{v} should not support dual track"

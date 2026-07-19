"""反模式测试：严禁版本降级欺诈。

核心原则：用户选了什么版本，就用什么版本的结果。
失败了就报错，不能偷偷换个版本的结果还说是这个版本的。
"""
import os
import re
import inspect

import pytest


REPAIR_DIR = os.path.join(os.path.dirname(__file__), "..", "services", "repair")
VERSION_DIRS = ["repair_v2_2", "repair_v2_3", "repair_v2_4", "repair_v3_2", "repair_v3_2a",
                "repair_v4_0", "repair_v4_0a", "repair_v4_0ap"]


def _get_core_files():
    files = []
    for vdir in VERSION_DIRS:
        core_path = os.path.join(REPAIR_DIR, vdir, "core.py")
        if os.path.exists(core_path):
            files.append((vdir, core_path))
    return files


class TestNoVersionFallbackFraud:
    """严禁版本降级欺诈：用户选v4就得是v4的结果，不能失败了偷偷换成v3。"""

    @pytest.mark.parametrize("vdir,core_path", _get_core_files())
    def test_no_fallback_keyword_in_source(self, vdir, core_path):
        """源代码中不得出现 fallback 降级到其他版本的关键词。"""
        with open(core_path, "r", encoding="utf-8") as f:
            source = f.read()

        forbidden_patterns = [
            r"fallback.*v\d",
            r"降级.*v\d",
            r"v\d.*fallback",
            r"fallback_reason",
            r"fallback:v",
        ]

        for pattern in forbidden_patterns:
            assert not re.search(pattern, source), (
                f"{vdir} 中存在版本降级欺诈关键词 '{pattern}'：\n"
                f"用户选了这个版本，就必须用这个版本的结果。失败了就报错，不能偷偷换版本。"
            )

    @pytest.mark.parametrize("vdir,core_path", _get_core_files())
    def test_no_import_other_version_repair_entry(self, vdir, core_path):
        """不得导入其他版本的 repair_single_track / repair_audio 作为降级目标。"""
        with open(core_path, "r", encoding="utf-8") as f:
            source = f.read()

        other_versions = [v for v in VERSION_DIRS if v != vdir]
        for other_v in other_versions:
            pattern = rf"from.*{other_v}.*import.*repair_(single_track|audio)"
            if re.search(pattern, source):
                # 检查是否有 try/except 降级包装
                if "try:" in source and f"_v32a_repair" in source:
                    pytest.fail(
                        f"{vdir} 导入了 {other_v} 的修复入口且存在降级模式。\n"
                        f"版本之间可以复用 DSP 原语，但入口函数必须是独立的，失败就报错。"
                    )

    @pytest.mark.parametrize("vdir,core_path", _get_core_files())
    def test_algorithm_version_is_constant(self, vdir, core_path):
        """algorithm_version 必须是常量，不能动态拼接 fallback 标签。"""
        with open(core_path, "r", encoding="utf-8") as f:
            source = f.read()

        forbidden_dynamic = [
            r'algorithm_version.*=.*f".*fallback',
            r'algorithm_version.*\+.*fallback',
            r'algorithm_version.*%.*fallback',
        ]

        for pattern in forbidden_dynamic:
            assert not re.search(pattern, source), (
                f"{vdir} 中 algorithm_version 被动态拼接了 fallback 标签。\n"
                f"版本号必须是固定常量，是什么版本就是什么版本。"
            )

    def test_all_version_tags_are_static(self):
        """有 VERSION_TAG 的模块，其值必须是静态常量，不得包含 fallback。"""
        for vdir, core_path in _get_core_files():
            with open(core_path, "r", encoding="utf-8") as f:
                source = f.read()

            match = re.search(r'^VERSION_TAG\s*=\s*"([^"]+)"', source, re.MULTILINE)
            if not match:
                continue

            tag = match.group(1)
            assert "fallback" not in tag.lower(), (
                f"{vdir} 的 VERSION_TAG 包含 fallback，这是版本欺诈。"
            )

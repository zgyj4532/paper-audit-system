import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from python_service.paper_audit.services.rules.engine import check_text_rules


def test_gbt_format_rules_cover_common_thesis_defects():
    text = (
        "Abstract:This paper studies panoramic simulation.\n"
        "Keywords:VirtualReality;ImageStitchingFusion; Unity3D;PanoramaTechnology\n"
        "杨笛航. 全景视频图像融合与拼接算法研究D]. 浙江:浙江大学,2017.\n"
        "彭凤婷. 基于多全景相机拼接的虚拟现实和实景交互系统[[D]. 四川:电子科技大学,2017."
    )

    issues = check_text_rules(text, focus_areas=("format", "reference"))
    rule_ids = {issue.get("rule_id") for issue in issues}

    assert "FORMAT-004" in rule_ids
    assert "FORMAT-006" in rule_ids
    assert "FORMAT-005" in rule_ids
    assert "REF-002" in rule_ids
    assert "REF-003" in rule_ids


def test_gbt_rules_still_detect_reference_section_problems():
    text = (
        "参考文献\n"
        "杨笛航. 全景视频图像融合与拼接算法研究D]. 浙江:浙江大学,2017.\n"
        "彭凤婷. 基于多全景相机拼接的虚拟现实和实景交互系统[[D]. 四川:电子科技大学,2017."
    )

    issues = check_text_rules(text, focus_areas=("reference",))
    assert any(issue.get("issue_type") == "reference" for issue in issues)
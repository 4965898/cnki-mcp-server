"""测试 citation 模块的引文格式化"""

import pytest

from cnki_mcp.citation import (
    format_citation_impl,
    format_citation_all_styles_impl,
    SUPPORTED_STYLES,
    format_gbt7714,
    format_apa,
    format_mla,
    format_chicago,
    format_vancouver,
)
from cnki_mcp.exceptions import CitationError


def test_gbt7714_basic():
    result = format_gbt7714(
        title="人工智能在医学影像中的应用",
        authors=["张三", "李四", "王五"],
        source="中国医学杂志",
        year="2025",
        volume="46",
        issue="3",
        pages="1-15",
        doi="10.1234/test",
    )
    assert "人工智能在医学影像中的应用" in result
    assert "中国医学杂志" in result
    assert "2025" in result
    assert "46" in result
    assert "DOI" in result
    assert result.endswith(".")


def test_apa_basic():
    result = format_apa(
        title="Deep Learning in Medical Imaging",
        authors=["Smith, John", "Doe, Jane"],
        source="Journal of Medicine",
        year="2025",
        volume="46",
        issue="3",
        pages="1-15",
        doi="10.1234/test",
    )
    assert "2025" in result
    assert "Journal of Medicine" in result
    assert "10.1234/test" in result


def test_mla_basic():
    result = format_mla(
        title="AI in Healthcare",
        authors=["Smith, John", "Doe, Jane"],
        source="Medical Journal",
        year="2025",
    )
    assert "AI in Healthcare" in result
    assert "Medical Journal" in result
    assert "2025" in result


def test_chicago_basic():
    result = format_chicago(
        title="Machine Learning in Radiology",
        authors=["Smith, John"],
        source="Radiology Journal",
        year="2025",
        volume="46",
        pages="100-120",
    )
    assert "Machine Learning in Radiology" in result
    assert "Radiology Journal" in result


def test_vancouver_basic():
    result = format_vancouver(
        title="Clinical AI Applications",
        authors=["Smith, John", "Doe, Jane", "Lee, Kim"],
        source="The Lancet",
        year="2025",
        volume="400",
        issue="1",
        pages="50-60",
    )
    assert "Clinical AI Applications" in result
    assert "The Lancet" in result
    assert "2025" in result


def test_format_citation_impl_all_styles():
    for style in SUPPORTED_STYLES:
        result = format_citation_impl(
            title="测试论文",
            authors="张三,李四",
            source="测试期刊",
            year="2025",
            style=style,
        )
        assert result["style"] == style
        assert len(result["citation"]) > 0
        assert "测试论文" in result["citation"]


def test_format_citation_invalid_style():
    with pytest.raises(CitationError):
        format_citation_impl(
            title="test",
            authors="Smith",
            source="Journal",
            year="2025",
            style="invalid_style",
        )


def test_format_citation_empty_authors():
    with pytest.raises(CitationError):
        format_citation_impl(
            title="test",
            authors="",
            source="Journal",
            year="2025",
            style="gbt7714",
        )


# ==================== GB/T 7714-2025 ====================


def test_gbt7714_2025_cn_journal_matches_standard_example():
    r = format_citation_impl(
        title="互联网药品可信交易环境中主体资质审核备案模式",
        authors="于潇,刘义,柴跃廷,冯文杰",
        source="清华大学学报(自然科学版)",
        year="2012", volume="52", issue="11", pages="1518-1523",
    )
    assert r["citation"] == (
        "于潇，刘义，柴跃廷，等.互联网药品可信交易环境中主体资质审核备案模式[J]. "
        "清华大学学报(自然科学版)，2012，52（11）：1518-1523."
    )
    assert r["style"] == "gbt7714-2025"


def test_gbt7714_2025_online_first():
    r = format_citation_impl(
        title="惯性增强动力吸振器-浮置板轨道低频减振性能研究",
        authors="张群,程志宝,石志飞", source="铁道学报", year="2024",
        online_date="2024-05-09",
        access_url="https://kns.cnki.net/kcms/detail/11.2104.u.20240507.1737.002.html",
    )
    assert "[J/OL]" in r["citation"]
    assert "铁道学报，2024-05-09" in r["citation"]
    assert r["citation"].endswith(".html.")


def test_gbt7714_2025_en_journal_et_al():
    r = format_citation_impl(
        title="The genome of Eucalyptus grandis",
        authors="Myburg A A,Grattapaglia D,Tuskan G A,Elaine C",
        source="Nature", year="2014", volume="510", pages="356-362",
        doi="10.1038/nature13308",
        access_url="https://www.nature.com/articles/nature13308.pdf",
    )
    c = r["citation"]
    assert "et al. The genome" in c
    assert "et al.." not in c
    assert "DOI:10.1038/nature13308." in c


def test_gbt7714_2025_thesis():
    r = format_citation_impl(
        title="土壤湿度反演方法研究", authors="王琦", source="", year="2022",
        pages="87", doc_type="thesis", place="武汉", publisher="武汉大学",
    )
    assert r["citation"] == "王琦.土壤湿度反演方法研究[D]. 武汉：武汉大学，2022：87."


def test_gbt7714_2025_conference():
    r = format_citation_impl(
        title="手卫生干预效果研究", authors="李妍,王莹",
        source="中华预防医学会医院感染控制分会第31次全国医院感染学术年会",
        year="2022", pages="2", doc_type="conference",
    )
    assert "[C]//中华预防医学会" in r["citation"]
    assert "2022：2." in r["citation"]


def test_gbt7714_2025_book():
    r = format_citation_impl(
        title="创建系统学", authors="钱学森", source="", year="2001",
        pages="19", doc_type="book", place="太原", publisher="山西科学技术出版社",
    )
    assert r["citation"] == "钱学森.创建系统学[M]. 太原：山西科学技术出版社，2001：19."


def test_gbt7714_2025_author_limit():
    r3 = format_citation_impl(title="题名", authors="甲,乙,丙", source="刊", year="2024")
    r4 = format_citation_impl(title="题名", authors="甲,乙,丙,丁", source="刊", year="2024")
    assert "甲，乙，丙." in r3["citation"]
    assert "甲，乙，丙，等." in r4["citation"]


def test_all_styles_impl():
    r = format_citation_all_styles_impl(
        title="国家翻译实践的理论建构", authors="任文,袁丽梅",
        source="中国翻译", year="2022", volume="43", issue="5", pages="5-14",
    )
    assert set(r["citations"].keys()) == {"gbt7714-2025", "gbt7714", "apa", "mla", "chicago", "vancouver"}
    assert all(r["citations"].values())


def test_legacy_gbt7714_still_works():
    r = format_citation_impl(
        title="测试论文", authors="张三,李四", source="测试学报",
        year="2020", volume="1", issue="2", pages="3-4", style="gbt7714",
    )
    assert r["style"] == "gbt7714"
    assert "2020, 1(2): 3-4" in r["citation"]


def test_default_style_is_2025():
    r = format_citation_impl(title="t", authors="a", source="s", year="2024")
    assert r["style"] == "gbt7714-2025"

"""
CNKI 引文格式化工具。

支持 6 种引文风格：
- gbt7714-2025: GB/T 7714-2025（中国国家标准，默认）— 支持期刊/学位论文/会议/图书/报纸，
  自动区分 [J] 与 [J/OL]（网络首发/在线资源），中文文献全角标点、西文文献半角标点
- gbt7714: GB/T 7714-2015（旧版国家标准，向后兼容保留）
- apa: APA 7th Edition
- mla: MLA 9th Edition
- chicago: Chicago Notes & Bibliography
- vancouver: Vancouver/ICMJE

依据：GB/T 7714-2025《信息与文献 参考文献著录规则》
- 8.5.3 连续出版物（期刊）中的析出文献
- 8.7.2 学位论文
- 8.6.3 会议录析出
- 7.8 获取和访问路径、7.9 永久标识符（DOI）
- 7.1.2 责任者不超过 3 个全部照录，超过 3 个著录前 3 个后加"，等"/"et al."

纯逻辑模块，不需要浏览器。
"""

import re

from cnki_mcp.exceptions import CitationError

SUPPORTED_STYLES = [
    "gbt7714-2025", "gbt7714", "apa", "mla", "chicago", "vancouver",
]

# 别名归一：都映射到 SUPPORTED_STYLES 中的规范名
STYLE_ALIASES = {
    "gbt7714-2025": "gbt7714-2025",
    "gbt7714-25": "gbt7714-2025",
    "gbt2025": "gbt7714-2025",
    "gbt7714": "gbt7714",
    "gbt7714-2015": "gbt7714",
    "apa": "apa",
    "mla": "mla",
    "chicago": "chicago",
    "vancouver": "vancouver",
}

# 文献类型（GB/T 7714-2025 第 8 章及附录 A）
DOC_TYPES = {
    "journal": "journal",
    "期刊": "journal",
    "期刊论文": "journal",
    "j": "journal",
    "thesis": "thesis",
    "学位论文": "thesis",
    "d": "thesis",
    "conference": "conference",
    "会议": "conference",
    "会议论文": "conference",
    "c": "conference",
    "book": "book",
    "图书": "book",
    "m": "book",
    "newspaper": "newspaper",
    "报纸": "newspaper",
    "n": "newspaper",
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _is_cjk(text: str) -> bool:
    """判断文本是否为中文文献（含 CJK 字符即视为中文）"""
    return bool(text and _CJK_RE.search(text))


def _join_author_title(author_str: str, title: str, cjk: bool) -> str:
    """作者与题名连接：中文文献句点后无空格（等.题名），西文句点后有空格（et al. Title）"""
    if cjk:
        return f"{author_str}.{title}"
    return f"{author_str}. {title}"


def _format_authors_gbt7714_2025(authors: list[str], cjk: bool) -> str:
    """GB/T 7714-2025 作者格式（7.1.2）：≤3 个全部照录，>3 个取前 3 加"等"/"et al."
    中文用全角逗号分隔，西文用半角逗号+空格。"""
    if not authors:
        return ""
    names = [a.split("(")[0].strip() for a in authors]  # 去除机构后缀
    names = [n for n in names if n]
    if cjk:
        sep, suffix = "，", "，等"
        if len(names) <= 3:
            return sep.join(names)
        return sep.join(names[:3]) + suffix
    else:
        # 西文"et al"不带句点，由著录符号"."统一补足，避免 "et al.." 双句点
        if len(names) <= 3:
            return ", ".join(names)
        return ", ".join(names[:3]) + ", et al"


def _format_authors_gbt7714(authors: list[str]) -> str:
    """GB/T 7714-2015 作者格式：作者1,作者2,作者3,等"""
    if not authors:
        return ""
    names = [a.split("(")[0].strip() for a in authors]  # 去除机构后缀
    names = [n for n in names if n]
    if len(names) <= 3:
        return ",".join(names)
    return ",".join(names[:3]) + ",等"


def _format_authors_apa(authors: list[str]) -> str:
    """APA 7 作者格式：LastName, F. M., & LastName, F. M."""
    if not authors:
        return ""
    names = [a.split("(")[0].strip() for a in authors]
    names = [n for n in names if n]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} & {names[1]}"
    if len(names) <= 20:
        return ", ".join(names[:-1]) + f", & {names[-1]}"
    return ", ".join(names[:19]) + f", ... {names[-1]}"


def _format_authors_mla(authors: list[str]) -> str:
    """MLA 9 作者格式：LastName, FirstName, and FirstName LastName"""
    if not authors:
        return ""
    names = [a.split("(")[0].strip() for a in authors]
    names = [n for n in names if n]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{names[0]}, et al."


def _format_authors_chicago(authors: list[str]) -> str:
    """Chicago 作者格式：LastName, FirstName, and FirstName LastName"""
    return _format_authors_mla(authors)


def _format_authors_vancouver(authors: list[str]) -> str:
    """Vancouver 作者格式：LastName AB, LastName CD"""
    if not authors:
        return ""
    names = [a.split("(")[0].strip() for a in authors]
    names = [n for n in names if n]
    if not names:
        return ""
    if len(names) <= 6:
        return ", ".join(names)
    return ", ".join(names[:6]) + ", et al."


# ==================== GB/T 7714-2025 ====================


def _type_tag(base: str, access_url: str, online_date: str) -> str:
    """文献类型标识：电子资源（有获取路径或在线出版日期）须加载体标识 /OL（7.3、附录A）"""
    if access_url or online_date:
        return f"[{base}/OL]"
    return f"[{base}]"


def _tail_2025(doi: str, access_url: str, cjk: bool) -> str:
    """获取和访问路径（7.8）+ 永久标识符（7.9）尾部。
    顺序：先路径后 DOI（标准示例 9/10）。"""
    tail = ""
    if access_url:
        tail += f" {access_url}."
    if doi:
        tail += f" DOI:{doi}."
    return tail


def format_gbt7714_2025_journal(
    title: str,
    authors: list[str],
    source: str,
    year: str,
    volume: str = "",
    issue: str = "",
    pages: str = "",
    doi: str = "",
    access_url: str = "",
    online_date: str = "",
) -> str:
    """GB/T 7714-2025 期刊析出文献（8.5.3）：
    主要责任者. 题名[J/OL]. 刊名, 年, 卷(期): 页码. 获取和访问路径. 永久标识符.
    网络首发（有在线日期、无卷期页码）：题名[J/OL]. 刊名, 在线出版日期. 获取和访问路径.
    """
    cjk = _is_cjk(title) or _is_cjk(source)
    author_str = _format_authors_gbt7714_2025(authors, cjk)
    tag = _type_tag("J", access_url, online_date)

    if cjk:
        comma, colon, lparen, rparen = "，", "：", "（", "）"
    else:
        comma, colon, lparen, rparen = ", ", ": ", "(", ")"

    citation = _join_author_title(author_str, title, cjk) + f"{tag}. {source}"
    if volume or issue or pages:
        # 常规著录：年, 卷(期): 页码
        if year:
            citation += f"{comma}{year}"
        if volume:
            citation += f"{comma}{volume}"
            if issue:
                citation += f"{lparen}{issue}{rparen}"
        elif issue:
            citation += f"{lparen}{issue}{rparen}"
        if pages:
            citation += f"{colon}{pages}"
        citation += "."
    elif online_date:
        # 网络首发：仅著录在线出版日期（8.5.3 示例 4）
        citation += f"{comma}{online_date}."
    elif year:
        citation += f"{comma}{year}."
    else:
        citation += "."

    citation += _tail_2025(doi, access_url, cjk)
    return citation


def format_gbt7714_2025_thesis(
    title: str,
    authors: list[str],
    place: str,
    institution: str,
    year: str,
    pages: str = "",
    doi: str = "",
    access_url: str = "",
) -> str:
    """GB/T 7714-2025 学位论文（8.7.2）：
    主要责任者. 题名[D/OL]. 学位授予单位所在地: 学位授予单位, 学位授予年: 引文页码. 获取和访问路径. 永久标识符.
    """
    cjk = _is_cjk(title)
    author_str = _format_authors_gbt7714_2025(authors, cjk)
    tag = _type_tag("D", access_url, "")
    if cjk:
        # 8.7.2 示例1: 王琦.题名[D]. 武汉：武汉大学，2022：87.
        body = f"{institution}，{year}"
        if pages:
            body += f"：{pages}"
        citation = _join_author_title(author_str, title, cjk) + f"{tag}. {place}：{body}."
    else:
        # 8.7.2 示例4: Cairns B R. Title [D]. Berkeley: University of California, 1965: 15.
        body = f"{institution}, {year}"
        if pages:
            body += f": {pages}"
        citation = _join_author_title(author_str, title, cjk) + f"{tag}. {place}: {body}."
    citation += _tail_2025(doi, access_url, cjk)
    return citation


def format_gbt7714_2025_conference(
    title: str,
    authors: list[str],
    proceedings: str,
    year: str,
    pages: str = "",
    doi: str = "",
    access_url: str = "",
) -> str:
    """GB/T 7714-2025 会议论文（8.6.3）：
    主要责任者. 题名[C/OL]//会议名称, 会议年份: 引文页码. 获取和访问路径. 永久标识符.
    """
    cjk = _is_cjk(title) or _is_cjk(proceedings)
    author_str = _format_authors_gbt7714_2025(authors, cjk)
    tag = _type_tag("C", access_url, "")
    citation = _join_author_title(author_str, title, cjk) + f"{tag}//{proceedings}"
    if cjk:
        if year:
            citation += f"，{year}"
        if pages:
            citation += f"：{pages}"
    else:
        if year:
            citation += f", {year}"
        if pages:
            citation += f": {pages}"
    citation += "."
    citation += _tail_2025(doi, access_url, cjk)
    return citation


def format_gbt7714_2025_book(
    title: str,
    authors: list[str],
    place: str,
    publisher: str,
    year: str,
    pages: str = "",
    doi: str = "",
    access_url: str = "",
) -> str:
    """GB/T 7714-2025 图书（8.2.2）：
    主要责任者. 题名[M/OL]. 出版地: 出版者, 出版年: 引文页码. 获取和访问路径. 永久标识符.
    """
    cjk = _is_cjk(title)
    author_str = _format_authors_gbt7714_2025(authors, cjk)
    tag = _type_tag("M", access_url, "")
    # 8.2.2 / 7.7 示例: 钱学森.创建系统学[M].太原：山西科学技术出版社，2001：19.
    # 出版地与出版者间用冒号，出版者与出版年间用逗号
    if cjk:
        seg = "：".join(x for x in [place, publisher] if x)
        if year:
            seg += f"，{year}"
        if pages:
            seg += f"：{pages}"
        citation = _join_author_title(author_str, title, cjk) + f"{tag}. {seg}."
    else:
        seg = ": ".join(x for x in [place, publisher] if x)
        if year:
            seg += f", {year}"
        if pages:
            seg += f": {pages}"
        citation = _join_author_title(author_str, title, cjk) + f"{tag}. {seg}."
    citation += _tail_2025(doi, access_url, cjk)
    return citation


def format_gbt7714_2025_newspaper(
    title: str,
    authors: list[str],
    source: str,
    pub_date: str,
    edition: str = "",
    doi: str = "",
    access_url: str = "",
) -> str:
    """GB/T 7714-2025 报纸析出文献（8.5.1.4）：
    主要责任者. 题名[N]. 报纸名, 出版日期(版次).
    """
    cjk = _is_cjk(title) or _is_cjk(source)
    author_str = _format_authors_gbt7714_2025(authors, cjk)
    tag = _type_tag("N", access_url, "")
    lparen, rparen = ("（", "）") if cjk else ("(", ")")
    citation = _join_author_title(author_str, title, cjk) + f"{tag}. {source}"
    if pub_date:
        if edition:
            citation += f"，{pub_date}{lparen}{edition}{rparen}." if cjk else f", {pub_date}{lparen}{edition}{rparen}."
        else:
            citation += f"，{pub_date}." if cjk else f", {pub_date}."
    else:
        citation += "."
    citation += _tail_2025(doi, access_url, cjk)
    return citation


# ==================== GB/T 7714-2015（兼容保留） ====================


def format_gbt7714(
    title: str,
    authors: list[str],
    source: str,
    year: str,
    volume: str = "",
    issue: str = "",
    pages: str = "",
    doi: str = "",
) -> str:
    """GB/T 7714-2015 期刊论文格式"""
    author_str = _format_authors_gbt7714(authors)
    citation = f"{author_str}. {title}[J]. {source}"
    if year:
        citation += f", {year}"
    if volume:
        citation += f", {volume}"
        if issue:
            citation += f"({issue})"
    if pages:
        citation += f": {pages}"
    citation += "."
    if doi:
        citation += f" DOI:{doi}."
    return citation


def format_apa(
    title: str,
    authors: list[str],
    source: str,
    year: str,
    volume: str = "",
    issue: str = "",
    pages: str = "",
    doi: str = "",
) -> str:
    """APA 7th Edition 期刊论文格式"""
    author_str = _format_authors_apa(authors)
    citation = f"{author_str} ({year}). {title}. *{source}*"
    if volume:
        citation += f", *{volume}*"
        if issue:
            citation += f"({issue})"
    if pages:
        citation += f", {pages}"
    citation += "."
    if doi:
        citation += f" https://doi.org/{doi}"
    return citation


def format_mla(
    title: str,
    authors: list[str],
    source: str,
    year: str,
    volume: str = "",
    issue: str = "",
    pages: str = "",
    doi: str = "",
) -> str:
    """MLA 9th Edition 期刊论文格式"""
    author_str = _format_authors_mla(authors)
    citation = f'{author_str}. "{title}." *{source}*'
    if volume:
        citation += f", vol. {volume}"
    if issue:
        citation += f", no. {issue}"
    if year:
        citation += f", {year}"
    if pages:
        citation += f", pp. {pages}"
    citation += "."
    if doi:
        citation += f" doi:{doi}."
    return citation


def format_chicago(
    title: str,
    authors: list[str],
    source: str,
    year: str,
    volume: str = "",
    issue: str = "",
    pages: str = "",
    doi: str = "",
) -> str:
    """Chicago Notes & Bibliography 期刊论文格式"""
    author_str = _format_authors_chicago(authors)
    citation = f'{author_str}. "{title}." *{source}* {volume}'
    if issue:
        citation += f", no. {issue}"
    if year:
        citation += f" ({year})"
    if pages:
        citation += f": {pages}"
    citation += "."
    if doi:
        citation += f" https://doi.org/{doi}."
    return citation


def format_vancouver(
    title: str,
    authors: list[str],
    source: str,
    year: str,
    volume: str = "",
    issue: str = "",
    pages: str = "",
    doi: str = "",
) -> str:
    """Vancouver/ICMJE 期刊论文格式"""
    author_str = _format_authors_vancouver(authors)
    citation = f"{author_str}. {title}. {source}."
    if year:
        citation += f" {year}"
    if volume:
        citation += f";{volume}"
        if issue:
            citation += f"({issue})"
    if pages:
        citation += f":{pages}"
    citation += "."
    if doi:
        citation += f" doi:{doi}."
    return citation


FORMATTERS = {
    "gbt7714": format_gbt7714,
    "apa": format_apa,
    "mla": format_mla,
    "chicago": format_chicago,
    "vancouver": format_vancouver,
}


def format_citation_impl(
    title: str,
    authors: str,
    source: str,
    year: str,
    volume: str = "",
    issue: str = "",
    pages: str = "",
    doi: str = "",
    style: str = "gbt7714-2025",
    doc_type: str = "journal",
    access_url: str = "",
    online_date: str = "",
    place: str = "",
    publisher: str = "",
) -> dict:
    """引文格式化核心逻辑

    gbt7714-2025 风格新增参数：
        doc_type: journal/期刊, thesis/学位论文, conference/会议, book/图书, newspaper/报纸
        access_url: 获取和访问路径（有值时标识变 [X/OL]）
        online_date: 网络首发在线出版日期（YYYY-MM-DD）
        place: 出版地 / 学位授予单位所在地
        publisher: 出版者（图书）/ 学位授予单位（学位论文）
    """
    style = style.lower().strip()
    style = STYLE_ALIASES.get(style, style)
    if style not in SUPPORTED_STYLES:
        raise CitationError(
            f"不支持的引文风格: {style}。支持: {', '.join(SUPPORTED_STYLES)}"
        )

    author_list = [a.strip() for a in authors.split(",") if a.strip()]
    if not author_list:
        raise CitationError("作者列表不能为空")

    if style == "gbt7714-2025":
        dt = DOC_TYPES.get(doc_type.lower().strip(), "journal")
        if dt == "thesis":
            citation = format_gbt7714_2025_thesis(
                title=title.strip(), authors=author_list, place=place.strip(),
                institution=publisher.strip(), year=year.strip(),
                pages=pages.strip(), doi=doi.strip(), access_url=access_url.strip(),
            )
        elif dt == "conference":
            citation = format_gbt7714_2025_conference(
                title=title.strip(), authors=author_list, proceedings=source.strip(),
                year=year.strip(), pages=pages.strip(), doi=doi.strip(),
                access_url=access_url.strip(),
            )
        elif dt == "book":
            citation = format_gbt7714_2025_book(
                title=title.strip(), authors=author_list, place=place.strip(),
                publisher=publisher.strip(), year=year.strip(),
                pages=pages.strip(), doi=doi.strip(), access_url=access_url.strip(),
            )
        elif dt == "newspaper":
            citation = format_gbt7714_2025_newspaper(
                title=title.strip(), authors=author_list, source=source.strip(),
                pub_date=year.strip(), edition=issue.strip(), doi=doi.strip(),
                access_url=access_url.strip(),
            )
        else:  # journal
            citation = format_gbt7714_2025_journal(
                title=title.strip(), authors=author_list, source=source.strip(),
                year=year.strip(), volume=volume.strip(), issue=issue.strip(),
                pages=pages.strip(), doi=doi.strip(), access_url=access_url.strip(),
                online_date=online_date.strip(),
            )
    elif style == "gbt7714" and doc_type.lower().strip() in ("thesis", "学位论文", "d"):
        # 2015 版学位论文（8.7.2 旧版惯例：[D]. 城市: 学校, 年.）
        cjk = _is_cjk(title)
        author_str = _format_authors_gbt7714(author_list)
        sep_place = "：" if cjk else ": "
        seg = sep_place.join(x for x in [place.strip(), publisher.strip(), year.strip()] if x)
        citation = f"{author_str}. {title.strip()}[D]. {seg}."
    else:
        formatter = FORMATTERS[style]
        citation = formatter(
            title=title.strip(),
            authors=author_list,
            source=source.strip(),
            year=year.strip(),
            volume=volume.strip(),
            issue=issue.strip(),
            pages=pages.strip(),
            doi=doi.strip(),
        )

    return {
        "citation": citation,
        "style": style,
        "doc_type": DOC_TYPES.get(doc_type.lower().strip(), "journal") if style.startswith("gbt7714") else "journal",
    }


def format_citation_all_styles_impl(
    title: str,
    authors: str,
    source: str,
    year: str,
    volume: str = "",
    issue: str = "",
    pages: str = "",
    doi: str = "",
    doc_type: str = "journal",
    access_url: str = "",
    online_date: str = "",
    place: str = "",
    publisher: str = "",
) -> dict:
    """一次生成全部支持风格的引文（论文写作高频场景）"""
    citations = {}
    for st in SUPPORTED_STYLES:
        try:
            r = format_citation_impl(
                title=title, authors=authors, source=source, year=year,
                volume=volume, issue=issue, pages=pages, doi=doi,
                style=st, doc_type=doc_type, access_url=access_url,
                online_date=online_date, place=place, publisher=publisher,
            )
            citations[st] = r["citation"]
        except CitationError:
            citations[st] = None
    return {
        "title": title.strip(),
        "citations": citations,
        "count": sum(1 for v in citations.values() if v),
    }

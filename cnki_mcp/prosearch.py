"""CNKI 专业检索式搜索（实验性）。

支持知网专业检索语法，例如:
    TI='人工智能' AND KY='教育'
    SU='翻译' OR AB='翻译史'
    AU='张三' AND AF='北京大学'

字段代码: SU 主题, TKA 篇关摘, KY 关键词, TI 篇名, FT 全文, AU 作者,
FI 第一作者, RP 通讯作者, AF 单位, FU 基金, AB 摘要, RF 参考文献,
CLC 分类号, LY 文献来源, DOI

注意: 专业检索依赖知网高级检索页面的前端结构，若知网改版可能失效。
"""

import asyncio
import random
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from cnki_mcp.config import SELECTOR_RESULT_ROWS
from cnki_mcp.exceptions import SearchError
from cnki_mcp.search import _check_cnki_accessible, parse_paper_row_async
from cnki_mcp.utils import dismiss_popups

ADV_SEARCH_URL = "https://kns.cnki.net/kns8s/AdvSearch?classid=WD0FTY92"

# 专业检索标签、输入框、提交按钮的多候选选择器
SELECTOR_EXPERT_TAB = [
    'li:has-text("专业检索")',
    '#gravSearchTab',
    'a:has-text("专业检索")',
    'text=专业检索',
]
SELECTOR_EXPERT_INPUT = [
    "textarea#expertvalue",
    "textarea#expert-input",
    "textarea.expert-input",
    "#expertSearchBox textarea",
    ".expert-search textarea",
]
SELECTOR_EXPERT_SUBMIT = [
    'input.btn-search',
    'button.btn-search',
    'button:has-text("检 索")',
    'button:has-text("检索")',
    'input[value="检索"]',
]


async def _click_first(page: Page, selectors: list[str], timeout: int = 5000) -> bool:
    """依次尝试多个选择器，点击第一个可见的元素"""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


async def _fill_first(page: Page, selectors: list[str], value: str) -> bool:
    """依次尝试多个选择器，向第一个可见的输入框填值"""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.fill(value)
                return True
        except Exception:
            continue
    return False


async def professional_search_impl(
    page: Page,
    expr: str,
    pages: int = 1,
) -> dict[str, Any]:
    """执行知网专业检索式查询并返回结果列表（实验性）"""
    expr = expr.strip()
    if not expr:
        raise SearchError("专业检索式不能为空")

    await page.goto(ADV_SEARCH_URL, wait_until="domcontentloaded")
    await asyncio.sleep(random.uniform(1.5, 2.5))
    await dismiss_popups(page)
    await _check_cnki_accessible(page)

    # 切换到"专业检索"标签页
    if not await _click_first(page, SELECTOR_EXPERT_TAB):
        raise SearchError(
            "未找到'专业检索'标签页，知网高级检索页面结构可能已变更。"
            "可改用 search_cnki 工具进行普通搜索。"
        )
    await asyncio.sleep(random.uniform(0.8, 1.5))

    # 填入专业检索式
    if not await _fill_first(page, SELECTOR_EXPERT_INPUT, expr):
        raise SearchError(
            "未找到专业检索式输入框，知网高级检索页面结构可能已变更。"
            "检索式语法示例: TI='人工智能' AND KY='教育'"
        )
    await asyncio.sleep(random.uniform(0.3, 0.8))

    # 提交检索
    if not await _click_first(page, SELECTOR_EXPERT_SUBMIT):
        raise SearchError("未找到检索提交按钮，知网页面结构可能已变更。")
    await asyncio.sleep(random.uniform(3, 5))

    # 验证码检测
    if "verify" in page.url:
        return {
            "isError": True,
            "error": "CNKI 触发了验证码，请稍后再试或手动完成验证",
            "error_type": "CaptchaError",
            "expr": expr,
            "total_papers": 0,
            "papers": [],
        }

    all_papers: list[dict[str, Any]] = []
    for page_num in range(1, pages + 1):
        try:
            await page.wait_for_selector(SELECTOR_RESULT_ROWS, timeout=15_000)
            rows = page.locator(SELECTOR_RESULT_ROWS)
            count = await rows.count()
            for i in range(count):
                try:
                    paper = await parse_paper_row_async(rows.nth(i))
                    if paper.get("title"):
                        paper["page"] = page_num
                        all_papers.append(paper)
                except Exception:
                    pass
        except PlaywrightTimeout:
            pass
        except Exception:
            pass

        if page_num < pages:
            try:
                next_btn = page.locator("#PageNext")
                if await next_btn.count() > 0 and await next_btn.is_enabled():
                    await next_btn.click()
                    await asyncio.sleep(random.uniform(1.5, 2.5))
                else:
                    break
            except Exception:
                break

    return {
        "expr": expr,
        "total_pages": pages,
        "total_papers": len(all_papers),
        "papers": all_papers,
    }

"""批量工具：批量论文详情 + CNKI 连通性检查。"""

import asyncio
import random
from typing import Any

from playwright.async_api import Page

from cnki_mcp.detail import get_paper_detail_impl
from cnki_mcp.search import _check_cnki_accessible


async def batch_paper_details_impl(
    page: Page,
    urls: list[str],
    interval: tuple[float, float] = (1.5, 2.5),
) -> dict[str, Any]:
    """批量获取论文详情。

    逐条调用 get_paper_detail_impl，条目间随机限速避免触发反爬。
    单条失败不影响其余条目。
    """
    results: list[dict[str, Any]] = []
    success = 0
    for i, url in enumerate(urls):
        url = (url or "").strip()
        if not url:
            continue
        item: dict[str, Any] = {"index": i, "url": url}
        if "cnki" not in url.lower():
            item.update({"ok": False, "error": "URL 不含 cnki，已跳过"})
            results.append(item)
            continue
        try:
            detail = await get_paper_detail_impl(page, url)
            if detail.get("isError"):
                item.update({"ok": False, "error": detail.get("error", "")})
            else:
                item.update({"ok": True, "detail": detail})
                success += 1
        except Exception as e:
            item.update({"ok": False, "error": str(e)[:200]})
        results.append(item)
        if i < len(urls) - 1:
            await asyncio.sleep(random.uniform(*interval))

    return {
        "total": len(urls),
        "success_count": success,
        "fail_count": len(results) - success,
        "results": results,
    }


async def check_cnki_access_impl(page: Page) -> dict[str, Any]:
    """检查 CNKI 连通性与反爬状态。

    返回 accessible 状态与诊断信息，不抛异常（便于作为体检工具使用）。
    """
    try:
        await page.goto("https://www.cnki.net/", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        try:
            await _check_cnki_accessible(page)
        except Exception as e:
            return {"accessible": False, "status": "blocked", "detail": str(e)[:300]}
        content = await page.content()
        if "verify" in page.url:
            return {"accessible": False, "status": "captcha", "detail": "触发验证码"}
        has_search = await page.locator("#txt_SearchText").count() > 0
        return {
            "accessible": True,
            "status": "ok",
            "search_box_found": has_search,
            "content_length": len(content),
            "url": page.url,
        }
    except Exception as e:
        return {"accessible": False, "status": "error", "detail": str(e)[:300]}

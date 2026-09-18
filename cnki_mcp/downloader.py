"""批量下载 CNKI 论文 PDF（供机构订阅用户在授权网络内使用）。

合规与自我保护设计：
- 每日下载配额：默认 100 篇/日（包库常见限额），本地持久化计数，
  超限自动停止；可用环境变量 CNKI_DAILY_LIMIT 调整。
- 下载间隔：每篇之间随机 8~15 秒，降低对机构出口与知网侧的冲击。
- 权限预检：check_download_permission_impl 检测当前网络是否具有下载权限，
  不真正下载文件。
- 本工具仅供已获授权的用户下载订阅内容用于个人研究，请遵守所在机构与
  知网的使用协议；严禁用于批量再分发。

纯浏览器交互模块，需 Playwright Page。
"""

import asyncio
import json
import os
import random
import re
import time
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from cnki_mcp.config import BROWSER_TIMEOUT
from cnki_mcp.exceptions import CNKIError
from cnki_mcp.utils import dismiss_popups

# 详情页 PDF / CAJ 下载按钮多候选选择器（知网 2025 前端验证 + 历史版本回退）
SELECTOR_PDF_DOWNLOAD = [
    "a#pdfDown",
    "a.btn-dlpdf",
    "li.btn-dlpdf a",
    'a[href*="download"][title*="PDF"]',
    'a:has-text("PDF下载")',
    'a:has-text("PDF 下载")',
    'a:has-text("整本PDF下载")',
    'a[id*="pdf"]',
]
SELECTOR_CAJ_DOWNLOAD = [
    "a#cajDown",
    "a.btn-dlcaj",
    "li.btn-dlcaj a",
    'a:has-text("CAJ下载")',
    "a:has-text(\"CAJ 下载\")",
    'a[href*="cajDown"]',
]

_QUOTA_DIR = os.path.join(os.path.expanduser("~"), ".cnki-mcp")
_QUOTA_FILE = os.path.join(_QUOTA_DIR, "download_quota.json")
_DEFAULT_DAILY_LIMIT = 100


def _daily_limit() -> int:
    try:
        return max(1, int(os.environ.get("CNKI_DAILY_LIMIT", _DEFAULT_DAILY_LIMIT)))
    except ValueError:
        return _DEFAULT_DAILY_LIMIT


class QuotaManager:
    """每日下载配额：~/.cnki-mcp/download_quota.json 本地持久化计数"""

    def __init__(self) -> None:
        self.limit = _daily_limit()

    def _load(self) -> dict:
        try:
            with open(_QUOTA_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        today = time.strftime("%Y-%m-%d")
        if data.get("date") != today:
            return {"date": today, "count": 0}
        return data

    def _save(self, data: dict) -> None:
        os.makedirs(_QUOTA_DIR, exist_ok=True)
        with open(_QUOTA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def used_today(self) -> int:
        return self._load().get("count", 0)

    def remaining(self) -> int:
        return max(0, self.limit - self.used_today())

    def consume(self, n: int = 1) -> dict:
        data = self._load()
        data["count"] = data.get("count", 0) + n
        data["limit"] = self.limit
        self._save(data)
        return {"used_today": data["count"], "limit": self.limit,
                "remaining": max(0, self.limit - data["count"])}


def _sanitize_filename(name: str, max_len: int = 80) -> str:
    """Windows 文件名安全化"""
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip(" ._")
    return name[:max_len] if name else "untitled"


def _build_filename(style: str, index: int, detail: dict, url: str) -> str:
    """按模板生成文件名（不含扩展名）"""
    title = _sanitize_filename(detail.get("title") or "untitled")
    authors = detail.get("authors") or []
    first = str(authors[0]) if authors else "unknown"
    first = first.split("(")[0].split("（")[0].strip()  # 剥离机构后缀（半角/全角括号）
    first = _sanitize_filename(first) if first else "unknown"
    year = str(detail.get("year") or detail.get("date") or "")[:4] or "0000"
    if style == "author":
        base = f"{first}_{title}"
    elif style == "year":
        base = f"{year}_{title}"
    else:
        base = f"{index:03d}_{title}"
    return base


async def _find_download_button(page: Page, selectors: list[str]):
    """按优先级寻找可见的下载按钮"""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return loc
        except Exception:
            continue
    return None


async def _looks_like_no_permission(page: Page) -> str | None:
    """下载失败时判断是否因无权限（跳转登录/验证码/提示页）"""
    url = page.url
    if any(k in url.lower() for k in ("login", "sso", "signin", "ips.tif")):
        return "跳转到登录页，当前网络可能不在机构授权 IP 范围内"
    content = await page.content()
    if "verify" in url:
        return "触发验证码"
    for kw in ("请登录", "未登录", "非法请求", "没有权限", "不支持包库"):
        if kw in content:
            return f"页面提示: {kw}"
    return None


async def download_single_impl(
    page: Page,
    url: str,
    dest_path: str,
) -> dict[str, Any]:
    """下载单篇 PDF（或可选 CAJ）。dest_path 为完整目标文件路径。"""
    await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    await asyncio.sleep(random.uniform(1.5, 2.5))
    await dismiss_popups(page)

    detail_title = ""
    try:
        t = page.locator("h1").first
        if await t.count() > 0:
            detail_title = ((await t.text_content()) or "").strip()[:100]
    except Exception:
        pass

    pdf_btn = await _find_download_button(page, SELECTOR_PDF_DOWNLOAD)
    caj_btn = await _find_download_button(page, SELECTOR_CAJ_DOWNLOAD)
    if not pdf_btn and not caj_btn:
        return {"ok": False, "reason": "no_button",
                "detail": "详情页未找到 PDF/CAJ 下载按钮（网络首发文章或纯 OA 页面可能无下载入口）",
                "title": detail_title}

    btn = pdf_btn or caj_btn
    fmt = "pdf" if pdf_btn else "caj"
    try:
        async with page.expect_download(timeout=BROWSER_TIMEOUT + 30_000) as dl_info:
            await btn.click()
        download = await dl_info.value
        await download.save_as(dest_path)
        size = os.path.getsize(dest_path)
        if size < 1024:
            os.remove(dest_path)
            return {"ok": False, "reason": "empty_file",
                    "detail": f"下载文件仅 {size} 字节，疑似权限拦截页", "title": detail_title}
        return {"ok": True, "format": fmt, "path": dest_path, "size": size, "title": detail_title}
    except PlaywrightTimeout:
        reason = await _looks_like_no_permission(page)
        return {"ok": False, "reason": "timeout_or_denied",
                "detail": reason or "下载超时（60s），可能是网络慢或被拦截", "title": detail_title}
    except Exception as e:
        reason = await _looks_like_no_permission(page)
        return {"ok": False, "reason": "error",
                "detail": reason or str(e)[:200], "title": detail_title}


async def download_papers_impl(
    page: Page,
    urls: list[str],
    output_dir: str,
    max_count: int | None = None,
    filename_style: str = "index",
    allow_caj: bool = False,
    interval: tuple[float, float] = (8.0, 15.0),
) -> dict[str, Any]:
    """批量下载论文 PDF 到指定文件夹。

    - 每日配额（默认 100）硬限制，跨进程持久化，超限自动停止
    - 每篇之间随机限速（默认 8~15 秒）
    - 单篇失败不影响其余；CAJ-only 文献默认跳过并在结果中标注
    """
    os.makedirs(output_dir, exist_ok=True)
    quota = QuotaManager()
    remaining_quota = quota.remaining()
    if remaining_quota <= 0:
        return {
            "isError": True,
            "error": f"今日下载配额已用完（{_daily_limit()} 篇/日，已用 {quota.used_today()}）。"
                     f"配额文件: {_QUOTA_FILE}，明日自动重置；如需调整限额设 CNKI_DAILY_LIMIT 环境变量。",
            "error_type": "QuotaExceeded",
            "used_today": quota.used_today(),
        }

    plan = len(urls)
    if max_count is not None:
        plan = min(plan, max_count)
    plan = min(plan, remaining_quota)

    results: list[dict[str, Any]] = []
    ok_count = 0
    for i, url in enumerate(urls[:plan]):
        url = (url or "").strip()
        if not url:
            continue
        item: dict[str, Any] = {"index": i + 1, "url": url}
        if "cnki" not in url.lower():
            item.update({"ok": False, "reason": "skip", "detail": "URL 不含 cnki，已跳过"})
            results.append(item)
            continue

        # 先快速打开详情页判断有无 PDF 按钮（避免对无权限页浪费 expect_download）
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(random.uniform(1.5, 2.5))
            await dismiss_popups(page)
            pdf_btn = await _find_download_button(page, SELECTOR_PDF_DOWNLOAD)
            caj_btn = await _find_download_button(page, SELECTOR_CAJ_DOWNLOAD)
        except Exception as e:
            item.update({"ok": False, "reason": "error", "detail": f"详情页打开失败: {str(e)[:150]}"})
            results.append(item)
            continue

        if not pdf_btn and (not caj_btn or not allow_caj):
            item.update({
                "ok": False, "reason": "no_pdf_button",
                "detail": "无 PDF 下载入口" + ("（有 CAJ，可设 allow_caj=true 下载）" if caj_btn else "（网络首发/OA 页面或无权限）"),
            })
            results.append(item)
            continue

        # 生成文件名
        detail_title = ""
        try:
            t = page.locator("h1").first
            if await t.count() > 0:
                detail_title = ((await t.text_content()) or "").strip()
        except Exception:
            pass
        fname = _build_filename(filename_style, len(results) + 1,
                                {"title": detail_title, "authors": [], "year": ""}, url)
        dest = os.path.join(output_dir, fname + (".pdf" if pdf_btn else ".caj"))
        if os.path.exists(dest) and os.path.getsize(dest) > 1024:
            item.update({"ok": True, "skipped": True, "format": "pdf" if pdf_btn else "caj",
                         "path": dest, "detail": "文件已存在，跳过下载"})
            results.append(item)
            continue

        btn = pdf_btn or caj_btn
        fmt = "pdf" if pdf_btn else "caj"
        try:
            async with page.expect_download(timeout=BROWSER_TIMEOUT + 30_000) as dl_info:
                await btn.click()
            download = await dl_info.value
            await download.save_as(dest)
            size = os.path.getsize(dest)
            if size < 1024:
                os.remove(dest)
                item.update({"ok": False, "reason": "empty_file",
                             "detail": f"仅 {size} 字节，疑似权限拦截页（若持续出现请用 check_download_permission 排查）"})
            else:
                quota.consume(1)
                ok_count += 1
                item.update({"ok": True, "format": fmt, "path": dest, "size": size})
        except PlaywrightTimeout:
            reason = await _looks_like_no_permission(page)
            item.update({"ok": False, "reason": "timeout_or_denied",
                         "detail": reason or "下载超时，疑似无权限或网络问题"})
        except Exception as e:
            reason = await _looks_like_no_permission(page)
            item.update({"ok": False, "reason": "error", "detail": reason or str(e)[:200]})
        results.append(item)

        if i < plan - 1 and not results[-1].get("skipped"):
            await asyncio.sleep(random.uniform(*interval))

    fail = len(results) - ok_count
    return {
        "output_dir": os.path.abspath(output_dir),
        "total": len(urls),
        "attempted": len(results),
        "success_count": ok_count,
        "fail_count": fail,
        "quota": quota._load(),
        "daily_limit": _daily_limit(),
        "results": results,
    }


async def check_download_permission_impl(page: Page, probe_url: str = "") -> dict[str, Any]:
    """检测当前网络是否具有知网下载权限（不真正下载文件）。

    原理：打开一篇详情页，检查 PDF 下载按钮是否存在；再访问知网 IP 登记页
    判断是否识别出机构。
    """
    out: dict[str, Any] = {}
    # 1. IP 机构识别
    try:
        await page.goto("https://ni.cnki.net/wspsearch/ifspage?korder=ip",
                        wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(1.5)
        content = await page.content()
        import re as _re
        m = _re.search(r"(<title>|机构名[:：]|欢迎您[,，])\s*([^<\n]{2,60})", content)
        out["ip_page_title"] = (await page.title())[:100]
        out["ip_page_url"] = page.url
    except Exception as e:
        out["ip_page_error"] = str(e)[:150]

    # 2. 详情页下载按钮探测
    probe = probe_url or "https://kns.cnki.net/kcms2/article/abstract?v=PLACEHOLDER"
    if probe_url:
        try:
            await page.goto(probe_url, wait_until="domcontentloaded", timeout=60_000)
            await asyncio.sleep(2)
            await dismiss_popups(page)
            pdf_btn = await _find_download_button(page, SELECTOR_PDF_DOWNLOAD)
            caj_btn = await _find_download_button(page, SELECTOR_CAJ_DOWNLOAD)
            out["probe_url"] = probe_url
            out["pdf_button_found"] = bool(pdf_btn)
            out["caj_button_found"] = bool(caj_btn)
            out["likely_authorized"] = bool(pdf_btn or caj_btn)
            out["note"] = "找到下载按钮通常代表当前 IP 已获机构授权；如需确证可实测下载一篇（download_papers_pdf 会拦截空文件）"
        except Exception as e:
            out["probe_error"] = str(e)[:150]
    else:
        out["note"] = "未提供 probe_url（详情页链接），仅完成 IP 页探测；建议传入一篇有 PDF 权限文献的详情页 URL 做实检"
    return out

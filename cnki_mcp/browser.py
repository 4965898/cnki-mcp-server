"""
AsyncPlaywright 浏览器池管理。

特性:
- 懒初始化：首次调用时才启动浏览器
- 实例复用：多次调用共享同一 browser 实例
- 共享 BrowserContext：同一 context 内创建 Page，Cookie 互通
- 空闲超时关闭（600s）
- asyncio.Lock 保护并发访问
"""

import asyncio
import os
import random
import subprocess
import sys
import time
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from cnki_mcp.config import (
    BROWSER_TIMEOUT,
    IDLE_TIMEOUT,
    USER_AGENTS,
)
from cnki_mcp.exceptions import BrowserError


def _get_proxy_settings() -> Optional[dict]:
    """从环境变量读取代理配置，返回 Playwright proxy 字典"""
    proxy_url = (
        os.environ.get("CNKI_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("all_proxy")
        or os.environ.get("ALL_PROXY")
    )
    if not proxy_url:
        return None
    # Playwright 不支持 socks5h，统一替换为 socks5
    if proxy_url.startswith("socks5h://"):
        proxy_url = proxy_url.replace("socks5h://", "socks5://", 1)
    username = os.environ.get("CNKI_PROXY_USERNAME") or os.environ.get("PROXY_USERNAME")
    password = os.environ.get("CNKI_PROXY_PASSWORD") or os.environ.get("PROXY_PASSWORD")
    proxy: dict = {"server": proxy_url}
    if username:
        proxy["username"] = username
    if password:
        proxy["password"] = password

    # NO_PROXY 绕过列表
    no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
    if no_proxy:
        # 将 no_proxy 格式转换为 Playwright bypass 格式（逗号分隔的 glob 模式）
        bypass_list = _parse_no_proxy(no_proxy)
        if bypass_list:
            proxy["bypass"] = ",".join(bypass_list)

    return proxy


def _parse_no_proxy(no_proxy: str) -> list[str]:
    """解析 NO_PROXY 环境变量，返回 Playwright/Chromium 兼容的 bypass glob 列表"""
    # NO_PROXY 格式: 逗号、空格或分号分隔的主机名/IP/CIDR
    entries = [e.strip().strip('"').strip("'") for e in no_proxy.replace(",", " ").replace(";", " ").split()]
    patterns: list[str] = []
    for entry in entries:
        if not entry:
            continue
        entry = entry.lstrip(".")
        # 已经是带通配符的 glob，直接使用
        if "*" in entry:
            patterns.append(entry)
        # IP 地址或 CIDR，直接使用
        elif entry[0].isdigit():
            patterns.append(entry)
        # 域名，添加 * 前缀匹配所有子域
        else:
            patterns.append(f"*{entry}")
    return patterns


def _get_browser_launch_options() -> dict:
    """按优先级解析浏览器启动选项（默认使用本机已有资源，避免额外下载）：

    1. CNKI_BROWSER_EXECUTABLE: 显式指定浏览器可执行文件路径（executable_path）
    2. CNKI_BROWSER_CHANNEL:   使用系统已安装浏览器的 channel（如 chrome / msedge / chrome-beta）
    3. 未设置时使用 Playwright 默认 Chromium（优先复用 %LOCALAPPDATA%/ms-playwright 已有缓存）
    """
    opts: dict = {}
    exe = os.environ.get("CNKI_BROWSER_EXECUTABLE", "").strip()
    if exe:
        if not os.path.exists(exe):
            raise BrowserError(f"CNKI_BROWSER_EXECUTABLE 指定的浏览器不存在: {exe}")
        opts["executable_path"] = exe
        return opts
    channel = os.environ.get("CNKI_BROWSER_CHANNEL", "").strip()
    if channel:
        opts["channel"] = channel
    return opts


class AsyncBrowserPool:
    """异步 Playwright 浏览器池（共享 BrowserContext，Cookie 互通）"""

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._last_used: float = 0
        self._lock = asyncio.Lock()

    async def _ensure_browser(self) -> Browser:
        """确保浏览器实例可用"""
        if self._browser is not None:
            if time.time() - self._last_used > IDLE_TIMEOUT:
                await self._close_browser()
            elif not self._browser.is_connected():
                self._browser = None
                self._context = None

        proxy = _get_proxy_settings()
        if self._browser is None:
            chromium_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-infobars",
                "--disable-extensions",
            ]

            launch_opts = _get_browser_launch_options()

            try:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    proxy=proxy,
                    args=chromium_args,
                    **launch_opts,
                )
            except Exception as e:
                if "Executable doesn't exist" in str(e) or "playwright" in str(e).lower():
                    await self._install_browser()
                    self._playwright = await async_playwright().start()
                    self._browser = await self._playwright.chromium.launch(
                        headless=True,
                        proxy=proxy,
                        args=chromium_args,
                        **launch_opts,
                    )
                else:
                    raise BrowserError(f"浏览器启动失败: {e}") from e

            if self._browser is None:
                raise BrowserError("浏览器启动失败")

            # 创建共享的 BrowserContext
            self._context = await self._browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
                proxy=proxy,
            )
            await self._context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
            """)

        self._last_used = time.time()
        return self._browser

    async def _install_browser(self) -> None:
        """安装 Playwright Chromium。

        默认【不自动下载】（避免额外占用磁盘/流量）：若本机已有 Playwright 缓存内核
        或通过 CNKI_BROWSER_CHANNEL/CNKI_BROWSER_EXECUTABLE 复用系统浏览器，则不会走到这里。
        确需下载时请设置环境变量 CNKI_AUTO_INSTALL=1，或手动运行: playwright install chromium
        """
        if os.environ.get("CNKI_AUTO_INSTALL", "").strip().lower() not in ("1", "true", "yes"):
            raise BrowserError(
                "未找到可用的 Playwright Chromium 内核。请任选其一：\n"
                "1) 设置 CNKI_BROWSER_CHANNEL=chrome（或 msedge）复用系统已安装的浏览器（推荐，零下载）；\n"
                "2) 设置 CNKI_BROWSER_EXECUTABLE 指向浏览器可执行文件路径；\n"
                "3) 设置 CNKI_AUTO_INSTALL=1 允许自动下载 Chromium（约 300MB）；\n"
                "4) 手动运行: playwright install chromium"
            )
        env = os.environ.copy()
        # Ubuntu 26.04+ Playwright 尚未官方支持，fallback 到 Ubuntu 24.04 的 Chromium 构建
        if not env.get("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE"):
            env["PLAYWRIGHT_HOST_PLATFORM_OVERRIDE"] = "ubuntu24.04-x64"
        try:
            subprocess.check_call(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1200,
                env=env,
            )
        except subprocess.CalledProcessError as e:
            raise BrowserError(
                "Playwright Chromium 安装失败。请手动运行: playwright install chromium"
            ) from e

    async def new_page(self) -> Page:
        """创建新 Page（共享 Context，Cookie 互通）"""
        async with self._lock:
            await self._ensure_browser()

        assert self._context is not None
        page = await self._context.new_page()
        page.set_default_timeout(BROWSER_TIMEOUT)
        return page

    async def navigate_to_cnki(self, page: Page) -> None:
        """导航到 CNKI 首页（含弹窗处理）"""
        await page.goto("https://www.cnki.net/", wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1, 2))
        await self._dismiss_popups(page)

    async def _dismiss_popups(self, page: Page) -> bool:
        """尝试关闭 CNKI 弹窗/遮罩"""
        dismiss_selectors = [
            "#close",
            ".close",
            'div[class*="popup"] a:has-text("关闭")',
            'div[class*="modal"] button:has-text("关闭")',
            'div[class*="layui-layer"] a[class*="layui-layer-close"]',
        ]
        for selector in dismiss_selectors:
            try:
                elem = page.locator(selector).first
                if await elem.count() > 0 and await elem.is_visible():
                    await elem.click()
                    await asyncio.sleep(0.5)
                    return True
            except Exception:
                continue
        return False

    async def _close_browser(self) -> None:
        """关闭浏览器实例和上下文"""
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    async def close(self) -> None:
        """关闭浏览器池"""
        async with self._lock:
            await self._close_browser()

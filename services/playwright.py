from asyncio import Semaphore
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from playwright.async_api import Browser, Page, async_playwright

from core.config import cfg
from core.i18n import _
from models.metas import SingletonMeta

__all__ = ("browser", "BrowserManager")


class BrowserManager(metaclass=SingletonMeta):
    __slots__ = ("_semaphore", "playwright", "browser")

    def __init__(self):
        match cfg.memory_level:
            case "low":
                self._semaphore = Semaphore(1)
            case "medium":
                self._semaphore = Semaphore(5)
            case "high":
                self._semaphore = Semaphore(64)
        self.playwright = None
        self.browser: Browser = None

    async def start(self):
        self.playwright = await async_playwright().start()
        args = ["--no-sandbox", "--disable-setuid-sandbox"]
        if cfg.memory_level == "low":
            args += [
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-software-rasterizer",
            ]
        self.browser = await self.playwright.chromium.launch(headless=True, args=args)

    async def close(self):
        if self.browser:
            with suppress(Exception):
                await self.browser.close()
            self.browser = None
        if self.playwright:
            with suppress(Exception):
                await self.playwright.stop()
            self.playwright = None

    @asynccontextmanager
    async def acquire_page(self) -> AsyncGenerator[Page, None]:
        async with self._semaphore:
            page = await self.browser.new_page()
            try:
                await page.set_viewport_size({"width": 1920, "height": 1080})
                await page.set_extra_http_headers({"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6"})
                yield page
            finally:
                await page.close()


class DisabledPlaywright(metaclass=SingletonMeta):
    async def start(self):
        pass
    
    async def close(self):
        pass
    
    def __getattr__(self, __):
        raise RuntimeError(_("playwright.403"))


browser = BrowserManager() if cfg.playwright else DisabledPlaywright()

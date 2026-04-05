from asyncio import Semaphore
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from playwright.async_api import Browser, Page, async_playwright

from core.config import cfg
from core.i18n import _
from utils.misc import SingletonMeta

__all__ = ("browser", "BrowserManager")


class BrowserManager(metaclass=SingletonMeta):
    __slots__ = ("_semaphore", "playwright", "browser", "_args")

    def __init__(self):
        match cfg.memory_level:
            case "low":
                self._semaphore = Semaphore(1)
                self._args = (
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-accelerated-2d-canvas",
                    "--disable-software-rasterizer",
                )
            case "medium":
                self._semaphore = Semaphore(5)
                self._args = ("--no-sandbox", "--disable-setuid-sandbox")
            case "high":
                self._semaphore = Semaphore(64)
                self._args = ()
        self.playwright = None
        self.browser: Browser = None

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True, args=self._args)

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


browser_mgr = BrowserManager() if cfg.playwright else DisabledPlaywright()

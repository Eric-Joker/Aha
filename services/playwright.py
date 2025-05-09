# Copyright (C) 2025 github.com/Eric-Joker
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from asyncio import Semaphore
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from playwright.async_api import Browser, Page
from playwright.async_api import async_playwright

from config import cfg
from cores import SingletonMeta

LOW_MEM = cfg.get_config("low_memory", False, "aha", "声明服务器内存低。目前作用为 playwright 的浏览器参数进行内存优化。")


class BrowserManager(metaclass=SingletonMeta):
    def __init__(self):
        self._semaphore = Semaphore(1 if LOW_MEM else 1000)
        self.playwright = None
        self.browser: Browser = None

    async def start(self):
        self.playwright = await async_playwright().start()
        args = ["--no-sandbox", "--disable-setuid-sandbox"]
        if LOW_MEM:
            args += [
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-software-rasterizer",
            ]
        self.browser = await self.playwright.chromium.launch(headless=True, args=args)

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

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


browser = BrowserManager()

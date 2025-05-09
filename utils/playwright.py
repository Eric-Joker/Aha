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
from logging import getLogger

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from services.playwright import browser

logger = getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=10),
    retry=retry_if_exception_type((PlaywrightTimeoutError, TimeoutError)),
    reraise=True,
)
async def capture_element(url: str, selector: str, wait_until: str = "networkidle"):
    """执行元素截图操作

    Args:
        url: 目标网页URL
        selector: CSS选择器
        wait_until: 页面加载完成判定标准
    """
    async with browser.acquire_page() as page:
        try:
            await page.goto(url, timeout=60000, wait_until=wait_until)
            if not (element := await page.query_selector(selector)):
                return None
            if not await element.is_visible():
                return None
            return await element.screenshot(type="png", path=None, animations="disabled", scale="css", omit_background=True)
        except (PlaywrightTimeoutError, TimeoutError):
            raise
        except Exception:
            return None

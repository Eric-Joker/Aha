from datetime import timedelta
from logging import getLogger
from typing import Literal, overload

from anyio import Path
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from services.playwright import browser
from services.file_cache import cache_file_sessionmaker

logger = getLogger(__name__)


@overload
async def capture_element(
    url: str,
    selector: str,
    return_bytes: Literal[True],
    save=None,
    wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "load",
    **kwargs,
) -> bytes | None: ...


@overload
async def capture_element(
    url: str,
    selector: str,
    return_bytes: Literal[False] = False,
    save=None,
    wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] = "load",
    **kwargs,
) -> Path | None: ...


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=10),
    retry=retry_if_exception_type((PlaywrightTimeoutError, TimeoutError)),
    reraise=True,
)
async def capture_element(url, selector, return_bytes=False, save=None, wait_until="load", **kwargs):
    """执行元素截图操作

    Args:
        url: 目标网页URL。
        selector: CSS选择器。
        save: 文件存储路径，若未提供将向 `CacheFileManager` 注册；为 `False` 不保存至驱动器。
        wait_until: 页面加载完成判定标准。

    Returns:
        byte: 若 `return_bytes` 为 `True` 返回截图字节，否则返回保存路径。
    """
    if save is None:
        async with cache_file_sessionmaker(_level=3) as session:
            save = await session.register(timedelta(minutes=10))

    async with browser.acquire_page() as page:
        try:
            await page.goto(url, timeout=300000, wait_until=wait_until)
            if not (element := await page.query_selector(selector)):
                return None
            if not await element.is_visible():
                return None
            if return_bytes:
                return await element.screenshot(
                    type="jpeg", path=save or None, animations="disabled", scale="css", omit_background=True, **kwargs
                )
            await element.screenshot(
                type="jpeg", path=save or None, animations="disabled", scale="css", omit_background=True, **kwargs
            )
            return save
        except PlaywrightTimeoutError, TimeoutError:
            raise
        except Exception:
            return None

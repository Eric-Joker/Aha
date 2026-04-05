# [Playwright](https://github.com/microsoft/playwright-python)

本文档所述特性需将[配置文件](../统一配置系统.md)中的 `aha.playwright` 配置项设置为 `true` 才可用。

`services.playwright.browser_mgr` 是管理器实例，其 `playwright` 属性维护了 `Playright` 实例，`browser` 属性维护了一个 `Browser` 实例。

Playwright 非线程安全。

## services.playwright.browser_mgr.acquire_page

异步上下文管理器，用于获取一个页面实例。

```python
from services.playwright import browser_mgr

async with browser_mgr.acquire_page() as page:
    ...
```

## utils.playwright.capture_element

异步函数，为 URL 中的元素进行截图。

| 参数 | 类型 | 描述 |
| --- | --- | --- |
| url | str | 页面 URL。 |
| selector | str | CSS 元素选择器。 |
| return_bytes | bool | 为 `True` 返回字节，否则返回路径。默认为 `False`。 |
| save | StrPath \| Literal[False] | 文件保存路径，若未提供将由[文件缓存服务](./文件缓存.md)提供；为 `False` 时不保存至本地。 |
| wait_until | Literal["commit", "domcontentloaded", "load", "networkidle"] | 页面加载完成判定标准，默认为 `load`。 |

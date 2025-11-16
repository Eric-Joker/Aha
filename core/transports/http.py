import logging
from asyncio import create_task, sleep
from contextlib import suppress
from typing import Literal

from attrs import define
from httpx import AsyncClient, RequestError, TimeoutException
from orjson import JSONDecodeError, loads
from tenacity import before_sleep_log, retry, retry_if_exception_type, wait_exponential

from utils.network import local_srv

from .base import ClientTransport


class _HttpMixin(ClientTransport):
    """HTTP API调用"""

    """__slots__ = ("_http_client", "_http_config", "_logger")"""

    def __init__(self, logger=None):
        super().__init__(logger)
        self._logger = logger or logging.getLogger("API Connection (HTTP)")

    async def open(self, *, api_config: dict, **kwargs):
        await super().open(**kwargs)
        self._http_config = api_config
        with suppress(KeyError):
            self._http_config["base_url"] = str(self._http_config["base_url"])
        self._http_client = AsyncClient(**self._http_config)

    async def invoke(self, endpoint: str, method: Literal["POST", "GET"] = "POST", **kwargs):
        create_task(super().invoke(**kwargs))

        if not self._http_client:
            self._logger.error("Connection not established.")
            return
        if not self._http_client.base_url:
            self._logger.error("base_url is empty.")
            return

        response = await self._http_client.request(method.upper(), self._http_client.base_url.join(endpoint), **kwargs)
        response.raise_for_status()

        if "application/json" in (content_type := response.headers.get("content-type", "")):
            return loads(response.content)
        elif "text/" in content_type:
            return response.text
        return await response.content

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        await super().close()

    @property
    def local_srv(self):
        return local_srv(self._http_config["base_url"]) and super().local_srv


@define
class SseConfig:
    url: str
    heartbeat_interval: float
    retry_config: dict


class _SseMixin(ClientTransport):  # 该类纯纯瞎写未经测试
    """__slots__ = (
        "_sse_client",
        "_sse_config",
        "_sse_task",
        "_logger",
        "_active",
        "heartbeat_interval",
        "retry_config",
        "_current_event",
    )"""

    def __init__(self, logger=None):
        super().__init__(logger)
        self._logger = logger or logging.getLogger("API Connection (HTTP SSE)")

    async def open(self, *, sse_config: SseConfig, **kwargs):
        await super().open(**kwargs)
        self._sse_config = sse_config.__dict__
        self.heartbeat_interval = self._sse_config.pop("heartbeat_interval", 15)
        self.retry_config = {
                "wait": wait_exponential(multiplier=1, max=30),
                "retry": retry_if_exception_type((RequestError, TimeoutException, ConnectionError)),
                "before_sleep": before_sleep_log(self._logger, logging.WARNING),
                "reraise": True,
            }
        if custom_retry := self._sse_config.pop("retry_config", None):
            self.retry_config |= custom_retry
        self._sse_client = AsyncClient(**sse_config)
        self._active = True

    async def _listen_impl(self):
        create_task(super()._listen_impl())
        with suppress(RuntimeError):
            async for data in retry(**self.retry_config)(self._sse_event_loop)():
                yield data

    async def _sse_event_loop(self):
        async with self._sse_client.stream("GET", self._sse_config["url"], **self._sse_config) as response:
            response.raise_for_status()

            buffer = b""
            async for chunk in response.aiter_bytes():
                if not self._active:
                    return

                if not chunk:
                    if self.heartbeat_interval:
                        await sleep(self.heartbeat_interval)
                        continue
                    break

                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    async for data in self._process_sse_line(line.decode("utf-8")):
                        yield data

    _sse_event_loop.__qualname__ = "HTTPSse"

    async def _process_sse_line(self, line: str):
        if not (line := line.strip()) or line.startswith(":"):
            return

        if ":" in line:
            field, value = line.split(":", 1)
            field = field.strip()
            value = value.strip()
        else:
            field, value = line, ""

        match field:
            case "event":
                self._current_event = value
            case "data":
                try:
                    try:
                        (event_data := loads(value))["_sse_event"] = self._current_event
                        yield event_data
                    except JSONDecodeError:
                        yield {"data": value, "_sse_event": self._current_event}
                except Exception as e:
                    self._logger.exception(e)

    async def close(self):
        self._active = False
        if self._sse_client:
            await self._sse_client.aclose()
            self._sse_client = None

        await super().close()

    @property
    def local_srv(self):
        return local_srv(self._sse_config["base_url"]) and super().local_srv


class HttpSse(_HttpMixin, _SseMixin):
    __slots__ = (
        # _HttpMixin的slots
        "_http_client",
        "_http_config",
        # _SseMixin的slots
        "_sse_client",
        "_sse_config",
        "_sse_task",
        "_active",
        "heartbeat_interval",
        "retry_config",
        "_current_event",
        # abc
        "_logger",
    )

    async def open(self, *, api_config: dict, sse_config: SseConfig):
        await super().open(api_config=api_config, sse_config=sse_config)


class HttpFastAPI(_HttpMixin):
    async def open(self, api_config: dict):
        await super().open(api_config=api_config)

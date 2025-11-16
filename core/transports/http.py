import logging
from asyncio import Event, create_task
from contextlib import suppress

from httpx import AsyncClient, RequestError, StreamClosed, TimeoutException
from httpx_sse import aconnect_sse
from orjson import loads
from tenacity import before_sleep_log, retry, retry_if_exception_type, wait_exponential

from utils.network import local_srv

from ..i18n import _
from .base import ClientTransport


class _HttpMixin(ClientTransport):
    """HTTP API调用。瞎写的且未经测试，估计用不了。"""

    def __init__(self, logger=None):
        super().__init__(logger)
        self._logger = logger or logging.getLogger("API Connection (HTTP)")

    async def open(self, *, api_connect_config: dict, api_client_config: dict, **kwargs):
        await super().open(**kwargs)
        self._http_config = api_connect_config
        self._http_client = AsyncClient(**api_client_config)

    async def invoke(self, **kwargs):
        response = await self._http_client.request(**kwargs)
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


class _SseMixin(ClientTransport):
    """瞎写的且未经测试，估计用不了。"""
    def __init__(self, logger=None):
        super().__init__(logger)
        self._logger = logger or logging.getLogger("API Connection (HTTP SSE)")

    async def open(self, *, sse_connect_config: dict, sse_client_config: dict = {}, retry_config: dict = None, **kwargs):
        await super().open(**kwargs)
        self._sse_config = sse_connect_config
        self._retry_args = {
            "wait": wait_exponential(multiplier=1, max=30),
            "retry": retry_if_exception_type((RequestError, TimeoutException, ConnectionError)),
            "before_sleep": before_sleep_log(self._logger, logging.WARNING),
            "reraise": True,
        }
        if retry_config:
            self._retry_args |= retry_config
        self._sse_client = AsyncClient(**sse_client_config)
        self._closed_event = Event()

        await self._connect()

    async def _connect(self):
        if self._closed_event.is_set():
            return

        self.sse_connect = await aconnect_sse(self._sse_client, **self._sse_config).__aenter__()

    _connect.__qualname__ = "HTTPSse"

    async def _listen_impl(self):
        while True:
            try:
                async for sse_event in self.sse_connect.aiter_sse():
                    yield sse_event.data
            except StreamClosed:
                if self._closed_event.is_set():
                    break

                self._logger.warning(msg=_("api.transport.conn_close_retry"))
                try:
                    await self._disconnect_cb()
                    await retry(**self._retry_args)(self._connect)()
                    self._logger.info(_("api.transport.retry_success"))
                    create_task(self._reconnect_cb())
                    continue
                except Exception as e:
                    self._logger.error(_("api.transport.retry_failed") % e)
                    break
            except Exception as e:
                self._logger.exception(_("api.transport.unknown_error") % e)

    async def close(self):
        with suppress(AttributeError):
            self._closed_event.set()
        if self._sse_client:
            await self._sse_client.aclose()
        await super().close()

    @property
    def local_srv(self):
        if self._local_srv is None:
            self._local_srv = local_srv(self._sse_config["url"])
            return self._local_srv
        return self._local_srv


class HttpSse(_HttpMixin, _SseMixin):
    __slots__ = (
        # _HttpMixin的slots
        "_http_client",
        "_http_config",
        # _SseMixin的slots
        "_sse_client",
        "_sse_config",
        "sse_connect",
        "_closed_event",
        "_retry_args",
        # abc
        "_logger",
        "_local_srv",
        "_connect_args",
        "_disconnect_cb",
    )

    async def open(
        self,
        *,
        api_client_config: dict,
        api_connect_config: dict,
        sse_connect_config: dict,
        sse_client_config: dict = None,
        retry_config: dict = None,
        **kwargs,
    ):
        await super().open(
            api_client_config=api_client_config,
            api_connect_config=api_connect_config,
            sse_connect_config=sse_connect_config,
            sse_client_config=sse_client_config,
            retry_config=retry_config,
            **kwargs,
        )


class HttpFastAPI(_HttpMixin):
    async def open(self, api_config: dict):
        await super().open(api_config=api_config)

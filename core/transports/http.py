import logging
from asyncio import create_task
from contextlib import suppress

from httpx import AsyncClient, RequestError, StreamClosed, TimeoutException
from ssrjson import loads
from tenacity import before_sleep_log, retry, retry_if_exception_type, wait_exponential

from utils.func import get_arg_names
from utils.network import local_srv

from ..i18n import _
from .base import ClientTransport, FastAPITransport


class _HttpMixin(ClientTransport):
    """HTTP API调用。瞎写的且未经测试，估计用不了。"""

    def __init__(self, logger=None):
        super().__init__(logger)
        self._logger = logger or logging.getLogger("API Connection (HTTP)")
        self._local_srv = None

    async def open(self, *, api_connect_config: dict, api_client_config: dict, **kwargs):
        await super().open(**kwargs)
        args = set(get_arg_names(AsyncClient.request))
        self._http_config = {k: v for k, v in api_connect_config.items() if k in args}
        args = set(get_arg_names(AsyncClient.__init__))
        self._http_client = AsyncClient(**{k: v for k, v in api_client_config.items() if k in args})

    async def invoke(self, **kwargs):
        response = await self._http_client.request(**kwargs)
        response.raise_for_status()

        if "application/json" in (content_type := response.headers.get("content-type", "")):
            return loads(response.content)
        elif "text/" in content_type:
            return response.text
        return await response.content

    async def _close_impl(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    @property
    def local_srv(self):
        return local_srv(self._http_config["base_url"]) and super().local_srv


class _SseMixin(ClientTransport):
    """瞎写的且未经测试，估计用不了。"""

    def __init__(self, logger=None):
        super().__init__(logger)
        self._logger = logger or logging.getLogger("API Connection (HTTP SSE)")
        self._local_srv = None

    async def open(self, *, sse_connect_config: dict, sse_client_config: dict = {}, retry_config: dict = None, **kwargs):
        from httpx_sse import aconnect_sse

        await super().open(**kwargs)
        args = set(get_arg_names(aconnect_sse))
        self._sse_config = {k: v for k, v in sse_connect_config.items() if k in args}
        _retry_args = {
            "wait": wait_exponential(multiplier=1, max=30),
            "retry": retry_if_exception_type((RequestError, TimeoutException, ConnectionError)),
            "before_sleep": before_sleep_log(self._logger, logging.WARNING),
            "reraise": True,
        }
        if retry_config:
            _retry_args |= retry_config
        self._connect = retry(**_retry_args)(self._connect)
        args = set(get_arg_names(AsyncClient.__init__))
        self._sse_client = AsyncClient(**{k: v for k, v in sse_client_config.items() if k in args})
        self._closed = False

        await self._connect()

    async def _connect(self):
        if self._closed:
            return

        from httpx_sse import aconnect_sse

        self.sse_connect = await aconnect_sse(self._sse_client, **self._sse_config).__aenter__()
        return True

    _connect.__qualname__ = "HTTPSse"
    _connect.__module__ = None

    async def _listen_impl(self):
        while True:
            try:
                async for sse_event in self.sse_connect.aiter_sse():
                    yield sse_event.data
            except StreamClosed:
                if self._closed:
                    break

                self._logger.warning(msg=_("api.transport.conn_close_retry"))
                try:
                    await self._disconnect_cb()
                    if not await self._connect():
                        break
                    self._logger.info(_("api.transport.retry_success"))
                    create_task(self._connect_cb())
                    continue
                except Exception as e:
                    self._logger.error(_("api.transport.retry_failed") % e)
                    break
            except Exception as e:
                self._logger.exception(_("api.transport.unknown_error") % e)

    async def _close_impl(self):
        with suppress(AttributeError):
            self._closed = True
        if self._sse_client:
            await self._sse_client.aclose()

    @property
    def local_srv(self):
        if self._local_srv is None:
            self._local_srv = local_srv(self._sse_config["url"])
            return self._local_srv
        return self._local_srv


class HttpSse(_HttpMixin, _SseMixin):
    __slots__ = ("_local_srv", "_http_client", "_http_config", "_sse_client", "_sse_config", "sse_connect", "_closed")

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


class HttpFastAPI(FastAPITransport):
    async def open(self, api_config: dict):
        await super().open(api_config=api_config)

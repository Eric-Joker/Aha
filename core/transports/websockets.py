import logging
from asyncio import Event, create_task
from collections.abc import AsyncIterable, Buffer
from contextlib import suppress

from tenacity import before_sleep_log, retry, retry_if_exception_type, wait_exponential
from websockets import State, connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from utils.network import local_srv

from ..i18n import _
from .base import ClientTransport, Transport


class WebSocketClient(ClientTransport):
    __slots__ = ("websocket", "uri", "_logger", "_closed_event", "_connect_args", "_retry_args")

    async def open(
        self, uri: str, extra_headers=None, close_timeout=2, max_size=2**30, open_timeout=8, retry_config=None, **kwargs
    ):
        self._retry_args = {
            "wait": wait_exponential(1, 30),
            "retry": retry_if_exception_type((WebSocketException, ConnectionError, TimeoutError)),
            "before_sleep": before_sleep_log(self._logger, logging.WARNING),
            "reraise": True,
        }
        if retry_config:
            self._retry_args |= retry_config
        self._connect_args = {
            "additional_headers": extra_headers or {},
            "close_timeout": close_timeout,
            "max_size": max_size,
            "open_timeout": open_timeout,
            **kwargs,
        }
        self.uri = uri
        self._closed_event = Event()

        await self._connect()

    async def _connect(self):
        if self._closed_event.is_set():
            return

        self.websocket = await connect(self.uri, **self._connect_args)

    _connect.__qualname__ = "WebSocketClient"

    async def _listen_impl(self):
        while True:
            try:
                yield await self.websocket.recv(decode=False)
            except ConnectionClosed:
                if self._closed_event.is_set():
                    break

                self._logger.warning(_("api.transport.conn_close_retry"))
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

    async def invoke(self, data: Buffer | AsyncIterable[Buffer]):
        if self._closed_event.is_set():
            raise RuntimeError(_("api.transport.conn_close"))
        await self.websocket.send(data, text=True)

    async def close(self):
        with suppress(AttributeError):
            self._closed_event.set()
        if (w := getattr(self, "websocket", None)) and w.state is State.OPEN:
            await self.websocket.close()

    @property
    def local_srv(self):
        if self._local_srv is None:
            self._local_srv = local_srv(self.uri)
            return self._local_srv
        return self._local_srv


class WebSocketServer(Transport):
    """由FastAPI实现，由core.api_service劫持请求（暂未实现）。仅做标记"""


logging.getLogger("websockets.client").addFilter(
    lambda record: record.levelno != logging.DEBUG
    or not (msg := record.getMessage()).startswith("> GET /")
    and not msg.startswith("> Host: ")
)

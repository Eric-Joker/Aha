from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Callable, Coroutine
from logging import Logger, getLogger
from typing import TYPE_CHECKING, Any

from utils.aio import async_run_func


class Transport(ABC):
    __slots__ = ("_logger", "_disconnect_cb", "_reconnect_cb")
    
    def __init__(
        self,
        logger=None,
        disconnect_cb: Callable[[], Coroutine[Any, Any, Any]] = None,
        reconnect_cb: Callable[[], Coroutine[Any, Any, Any]] = None,
    ):
        """参数中两个回调不必须使用"""
        self._logger: Logger = logger or getLogger(self.__class__.__name__)
        self._disconnect_cb = disconnect_cb
        self._reconnect_cb = reconnect_cb

    @abstractmethod
    async def open(self, *args, **kwargs):
        pass

    @abstractmethod
    async def listen(self, callback: Callable[[Any], Any]):
        """正常情况下应一直阻塞，返回代表不再连接"""

    @abstractmethod
    async def close(self):
        """关闭连接"""


class ClientTransport(Transport):
    async def listen(self, callback: Callable[[Any], Any]):
        async for data in self._listen_impl():
            try:
                await async_run_func(callback, data)
            except Exception:
                self._logger.exception("")

    @abstractmethod
    async def _listen_impl(self) -> AsyncGenerator:
        pass

    @abstractmethod
    async def invoke(self, *args, **kwargs) -> Any | None:
        """向 API 发送请求，可直接返回值也可通过 listen 方法返回"""

    @property
    @abstractmethod
    def local_srv(self) -> bool:
        pass

    if TYPE_CHECKING:

        @abstractmethod
        async def open(self, *args, **kwargs):
            """建立连接，其中不得阻塞。需允许冗余关键字参数"""


class FastAPITransport(Transport):
    """TODO"""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Callable, Coroutine
from logging import Logger, getLogger
from typing import Any

from utils.aio import async_run_func


class Transport(ABC):
    def __init__(self, logger=None):
        self._logger: Logger = logger or getLogger(self.__class__.__name__)

    @abstractmethod
    async def open(self, *args, **kwargs):
        pass

    @abstractmethod
    async def listen(self, callback: Callable[[Any], Any]):
        """正常情况下应一直阻塞，返回代表不再连接"""

    @abstractmethod
    async def invoke(self, *args, **kwargs) -> Any | None:
        pass

    @abstractmethod
    async def close(self):
        pass

    @property
    def local_srv(self) -> bool:
        raise NotImplementedError


class ClientTransport(Transport):
    def __init__(
        self,
        logger=None,
        disconnect_cb: Callable[[], Coroutine[Any, Any, Any]] = None,
        reconnect_cb: Callable[[], Coroutine[Any, Any, Any]] = None,
    ):
        """实际实现不必须利用两个回调"""
        super().__init__(logger)
        self._local_srv: bool = None
        self._disconnect_cb = disconnect_cb
        self._reconnect_cb = reconnect_cb

    @abstractmethod
    async def open(self, *args, **kwargs):
        """建立连接，其中不得阻塞线程。需要允许冗余关键字参数"""
        pass

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
        """向 API 发送请求，可能直接返回值也可能只能通过listen返回"""
        pass

    @abstractmethod
    async def close(self):
        """关闭连接"""
        pass

    @property
    def local_srv(self) -> bool:
        raise NotImplementedError


class ServerTransport(Transport):
    @abstractmethod
    async def open(self, *args, **kwargs):
        """初始化服务，其中不得阻塞线程。需要允许冗余关键字参数"""
        pass

    @abstractmethod
    async def listen(self, _):
        """启动服务"""

    async def invoke(self):
        pass

    @abstractmethod
    async def close(self):
        """关闭连接"""
        pass

    @property
    def local_srv(self) -> bool:
        raise NotImplementedError

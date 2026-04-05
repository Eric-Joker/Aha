from abc import abstractmethod
from asyncio import Task, current_task, gather
from collections.abc import AsyncGenerator, Callable
from logging import Logger, getLogger
from types import CoroutineType
from typing import TYPE_CHECKING, Any
from weakref import ReferenceType, ref

from utils.aio import ThreadSafeAsyncMeta, async_run_func


class Transport(metaclass=ThreadSafeAsyncMeta):
    __slots__ = ("_logger", "_listen_tasks", "_disconnect_cb", "_connect_cb", "__weakref__")
    
    def __init__(
        self,
        logger=None,
        disconnect_cb: Callable[[], CoroutineType] = None,
        reconnect_cb: Callable[[], CoroutineType] = None,
    ):
        """参数中两个回调不必须使用"""
        self._logger: Logger = logger or getLogger(self.__class__.__name__)
        self._listen_tasks: list[ReferenceType[Task]] = []
        self._disconnect_cb = disconnect_cb
        self._connect_cb = reconnect_cb

    @abstractmethod
    async def open(self, *args, **kwargs):
        pass

    async def listen(self, callback: Callable):
        self._listen_tasks.append(ref(current_task()))
        await self._listen_impl(callback)
    
    @abstractmethod
    async def _listen_impl(self, callback: Callable):
        """正常情况下应一直阻塞，返回代表不再连接"""

    async def close(self):
        """关闭连接并清理资源"""
        await self._close_impl()
        tasks = []
        for t in self._listen_tasks:
            if (t := t()) is not None:
                t.cancel()
                tasks.append(t)
        await gather(*tasks, return_exceptions=True)
        
    @abstractmethod
    async def _close_impl(self):
        pass
        


class ClientTransport(Transport):
    async def listen(self, callback):
        self._listen_tasks.append(ref(current_task()))
        async for data in self._listen_impl():
            try:
                await async_run_func(callback, data)
            except Exception:
                self._logger.exception("")

    @abstractmethod
    async def invoke(self, *args, **kwargs) -> Any | None:
        """向 API 发送请求，可直接返回值也可通过 listen 方法返回"""

    @property
    @abstractmethod
    def local_srv(self) -> bool:
        pass

    if TYPE_CHECKING:
        @abstractmethod
        async def _listen_impl(self) -> AsyncGenerator: ...

        @abstractmethod
        async def open(self, *args, **kwargs):
            """建立连接，其中不得阻塞。需允许冗余关键字参数"""


class FastAPITransport(Transport):
    """TODO"""

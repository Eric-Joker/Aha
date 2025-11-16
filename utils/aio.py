import sys
from asyncio import Event as aioEvent
from asyncio import get_running_loop, run
from collections.abc import AsyncIterable
from contextlib import suppress
from inspect import iscoroutinefunction
from multiprocessing.connection import _ConnectionBase
from threading import Event, Thread

from aiologic import Queue
from wrapt import ObjectProxy


def run_with_uvloop(main, *, debug=None):
    if sys.platform == "win32":
        run(main, debug=debug)
    else:
        from uvloop import Loop

        run(main, debug=debug, loop_factory=Loop)


async def async_run_func(func, *args, **kwargs):
    return (await func(*args, **kwargs)) if iscoroutinefunction(func) else func(*args, **kwargs)


async def async_all(ait: AsyncIterable):
    async for item in ait:
        if not item:
            return False
    return True


async def async_any(ait: AsyncIterable):
    async for item in ait:
        if item:
            return True
    return False


def try_get_loop():
    with suppress(RuntimeError):
        return get_running_loop()


def run_in_executor_else_direct(func, *args):
    if loop := try_get_loop():
        loop.run_in_executor(None, func, *args)
    else:
        func(*args)


class AsyncCounter:
    """等待计数器归0"""

    def __init__(self):
        self._count = 0
        self._event = aioEvent()
        self._event.set()

    def __enter__(self):
        self._event.clear()
        self._count += 1

    def __exit__(self, *_):
        self._count -= 1
        if self._count == 0:
            self._event.set()

    async def wait_until_zero(self):
        await self._event.wait()


class AsyncConnection(ObjectProxy):
    """非线程安全"""

    __slots__ = ("_conn", "_closed", "_recv_queue", "_recv_thread", "_send_queue", "_send_thread")

    def __init__(self, connection: _ConnectionBase):
        self._conn = connection
        self._closed = Event()
        self._recv_queue = Queue()
        self._recv_thread = Thread(target=self._recv_worker, daemon=True)
        self._recv_thread.start()
        self._send_queue = Queue()
        self._send_thread = Thread(target=self._send_worker, daemon=True)
        self._send_thread.start()

    def _recv_worker(self):
        while not self._closed.is_set():
            try:
                self._recv_queue.green_put(self._conn.recv())
            except EOFError, OSError:
                break
        self._recv_queue.green_put(None)

    def _send_worker(self):
        while not self._closed.is_set():
            try:
                self._conn.send(self._send_queue.green_get())
            except EOFError, OSError:
                break

    async def send(self, obj):
        if self._closed.is_set():
            raise EOFError
        await self._send_queue.async_put(obj)

    async def recv(self):
        if self._closed.is_set():
            raise EOFError
        if (data := await self._recv_queue.async_get()) is None:
            self.close()
            raise EOFError
        return data

    def close(self):
        self._closed.set()
        self._conn.close()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.close()

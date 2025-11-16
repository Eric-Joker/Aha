import asyncio
import sys
import threading
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import suppress
from inspect import iscoroutinefunction
from multiprocessing.connection import _ConnectionBase

import aiologic
from wrapt import ObjectProxy


def run_with_uvloop(main, *, debug=None):
    if sys.platform == "win32":
        asyncio.run(main, debug=debug)
    else:
        from uvloop import Loop

        asyncio.run(main, debug=debug, loop_factory=Loop)


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
        return asyncio.get_running_loop()


def run_in_executor_else_direct(func, *args):
    if loop := try_get_loop():
        loop.run_in_executor(None, func, *args)
    else:
        func(*args)


class AsyncCounter:
    """等待计数器归0"""

    def __init__(self):
        self._count = 0
        self._event = asyncio.Event()
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


class AsyncTee[T]:
    __slots__ = ("ait", "buffer", "cond", "eof", "consumer_indices", "next_cid", "producer_task", "exc")

    def __init__(self, ait: AsyncIterator[T]):
        self.ait = ait
        self.buffer = []  # 已生成但尚未被所有消费者消费的数据
        self.cond = asyncio.Condition()
        self.eof = False
        self.consumer_indices = {}  # 消费者ID -> 下一个要读取的buffer索引
        self.next_cid = 0  # 下一个消费者ID
        self.producer_task = None
        self.exc = None

    async def _producer(self):
        try:
            async for item in self.ait:
                async with self.cond:
                    self.buffer.append(item)
                    self.cond.notify_all()
            async with self.cond:
                self.eof = True
                self.cond.notify_all()
        except Exception as e:
            async with self.cond:
                self.exc = e
                self.cond.notify_all()

    def new_consumer(self) -> AsyncIterator[T]:
        cid = self.next_cid
        self.next_cid += 1
        self.consumer_indices[cid] = 0
        if self.producer_task is None:
            self.producer_task = asyncio.create_task(self._producer())
        return self._Consumer(self, cid)

    async def close(self):
        if self.producer_task:
            self.producer_task.cancel()
            try:
                await self.producer_task
            except Exception:
                raise
            except BaseException:
                pass

    class _Consumer:
        __slots__ = ("tee", "cid")

        def __init__(self, tee: AsyncTee, cid):
            self.tee = tee
            self.cid = cid

        def __aiter__(self):
            return self

        async def __anext__(self):
            tee = self.tee
            cid = self.cid
            async with tee.cond:
                while True:
                    # 消费者已结束
                    if (idx := tee.consumer_indices.get(cid)) is None:
                        raise StopAsyncIteration

                    if idx < len(tee.buffer):
                        # 有数据可读
                        item = tee.buffer[idx]
                        tee.consumer_indices[cid] = idx + 1
                        # 清理无用头部
                        if tee.consumer_indices:
                            if (min_idx := min(tee.consumer_indices.values())) > 0:
                                del tee.buffer[:min_idx]
                                for k in tee.consumer_indices:
                                    tee.consumer_indices[k] -= min_idx
                        return item

                    # 数据源已结束且读完
                    if tee.eof:
                        tee.consumer_indices.pop(cid, None)
                        # 无活跃消费者
                        if not tee.consumer_indices and tee.producer_task:
                            tee.producer_task.cancel()
                        if tee.exc:
                            raise tee.exc
                        else:
                            raise StopAsyncIteration

                    await tee.cond.wait()

    @classmethod
    def gen[T](cls, agen: AsyncIterator[T], n: int = 2) -> tuple[AsyncIterator[T], ...]:
        tee = cls(agen)
        return tuple(tee.new_consumer() for _ in range(n))


class AsyncConnection(ObjectProxy):
    """非线程安全"""

    __slots__ = ("_conn", "_closed", "_recv_queue", "_recv_thread", "_send_queue", "_send_thread")

    def __init__(self, connection: _ConnectionBase):
        self._conn = connection
        self._closed = threading.Event()
        self._recv_queue = aiologic.Queue()
        self._recv_thread = threading.Thread(target=self._recv_worker, daemon=True)
        self._recv_thread.start()
        self._send_queue = aiologic.Queue()
        self._send_thread = threading.Thread(target=self._send_worker, daemon=True)
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

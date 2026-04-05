import asyncio
import sys
import threading
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator, Callable, MutableSequence, MutableSet
from concurrent.futures import Executor
from concurrent.futures.thread import BrokenThreadPool
from contextlib import suppress
from contextvars import copy_context
from copy import deepcopy
from dataclasses import dataclass, field
from functools import wraps
from inspect import isasyncgenfunction, iscoroutinefunction
from itertools import count
from multiprocessing.connection import _ConnectionBase
from os import process_cpu_count
from types import CoroutineType
from typing import TYPE_CHECKING, overload
from weakref import WeakSet, finalize, ref

import aiologic
from tenacity import _unset
from wrapt import decorator

from core.i18n import _

from .func import get_true_func
from .misc import SingletonMeta, slots_extend


def run_with_uvloop(main, *, debug=None):
    if sys.platform == "win32":
        asyncio.run(main, debug=debug)
    else:
        from uvloop import Loop

        asyncio.run(main, debug=debug, loop_factory=Loop)


async def async_run_func(func, *args, **kwargs):
    if asyncio.iscoroutine(result := func(*args, **kwargs)):
        result = await result
    return result


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


class ThreadSafeAsyncMeta(type):
    def __new__(mcs, name, bases, namespace):
        if slots := namespace.get("__slots__"):
            namespace["__slots__"] = slots_extend(slots, "_TS__loop", "_TS__queue")
        for attr_name, attr_value in namespace.items():
            if isinstance(attr_value, (staticmethod, classmethod)):
                continue

            if iscoroutinefunction(attr_value):
                # 协程函数
                @wraps(attr_value)
                async def wrapper(self, *args, __func=attr_value, **kwargs):
                    if ThreadSafeAsyncMeta.init_instance(self) or asyncio.get_running_loop() is self._TS__loop:
                        return await __func(self, *args, **kwargs)
                    return await asyncio.wrap_future(
                        asyncio.run_coroutine_threadsafe(__func(self, *args, **kwargs), self._TS__loop)
                    )

                namespace[attr_name] = wrapper

            elif isasyncgenfunction(attr_value):
                # 异步生成器函数
                @wraps(attr_value)
                def wrapper(self, *args, __func=attr_value, **kwargs):
                    if ThreadSafeAsyncMeta.init_instance(self) or asyncio.get_running_loop() is self._TS__loop:
                        return __func(self, *args, **kwargs)

                    queue, flag = aiologic.SimpleQueue(), aiologic.Flag()
                    self._TS__queue.put((queue, flag, __func, (self, *args), kwargs, copy_context()))
                    return ThreadSafeAsyncMeta._asyncgen_return(queue, flag)

                namespace[attr_name] = wrapper

        return super().__new__(mcs, name, bases, namespace)

    @classmethod
    def init_instance(cls, obj):
        if getattr(obj, "_TS__loop", None) is None:
            obj._TS__loop = asyncio.get_running_loop()
            obj._TS__queue = aiologic.SimpleQueue()
            task = asyncio.create_task(cls._task_handler(obj._TS__queue))
            finalize(obj, lambda t: t.cancel(), task)
            return True

    @staticmethod
    async def _asyncgen_return(queue: aiologic.SimpleQueue, flag: aiologic.Flag):
        try:
            while (item := await queue.async_get()) is not _unset:
                if isinstance(item, BaseException) and getattr(item, "_TS__", False):
                    raise item
                yield item
        finally:
            flag.get().cancel()

    if TYPE_CHECKING:

        @overload
        @staticmethod
        def decorator[T: Callable[..., CoroutineType | AsyncGenerator]](func: T) -> T: ...
        @overload
        @staticmethod
        def decorator[T: Callable[..., CoroutineType | AsyncGenerator]]() -> Callable[[T], T]: ...

    @staticmethod
    def decorator(func=None):
        if iscoroutinefunction(func):
            # 协程函数
            @wraps(func)
            async def func(*args, __func=func, **kwargs):
                if asyncio.get_running_loop() is ThreadSafeAsyncMeta._TS__loop:
                    return await __func(*args, **kwargs)
                return await asyncio.wrap_future(
                    asyncio.run_coroutine_threadsafe(__func(*args, **kwargs), ThreadSafeAsyncMeta._TS__loop)
                )

        elif isasyncgenfunction(func):
            # 异步生成器函数
            @wraps(func)
            def func(*args, __func=func, **kwargs):
                if asyncio.get_running_loop() is ThreadSafeAsyncMeta._TS__loop:
                    return __func(*args, **kwargs)

                queue, flag = aiologic.SimpleQueue(), aiologic.Flag()
                ThreadSafeAsyncMeta._TS__queue.put((queue, flag, __func, args, kwargs, copy_context()))
                return ThreadSafeAsyncMeta._asyncgen_return(queue, flag)

        return func or decorator

    @classmethod
    async def _task_handler(cls, queue: aiologic.SimpleQueue):
        while True:
            result_queue, task_flag, func, args, kwargs, context = await queue.async_get()
            task_flag.set(asyncio.create_task(cls._run_asyncgen(result_queue, func, args, kwargs), context=context))

    @staticmethod
    async def _run_asyncgen(result_queue: aiologic.SimpleQueue, func, self, args, kwargs):
        try:
            async for item in func(self, *args, **kwargs):
                result_queue.put(item)
        except Exception as e:
            e._TS__ = True
            result_queue.put(e)
        else:
            result_queue.put(_unset)


class SingletonThreadSafeAsyncMeta(ThreadSafeAsyncMeta, SingletonMeta): ...


class ThreadSafeMeta(type):
    """纯异步有异步锁，纯线程有线程锁，异步+线程有 aiologic，异步+线程+要求方法同步可用才用这个"""

    class Attribute:
        """描述符：维护线程本地缓存"""

        __slots__ = ("name", "private_name", "_main_thread", "_try_times")

        def __init__(self, name):
            self.name = name
            self.private_name = f"_TS__{name}"
            self._main_thread = threading.main_thread()
            self._try_times = process_cpu_count() ** 2

        def __get__(self, instance, owner):
            if instance is None:
                instance = owner

            if threading.current_thread() is self._main_thread:
                return object.__getattribute__(instance, self.private_name)

            # 非主线程：线程本地缓存
            if not (cacher := getattr(instance, "_TS____C", None)):
                object.__setattr__(instance, "_TS____C", cacher := threading.local())
            current_version = getattr(instance, "_TS____V", 0)
            if (data := getattr(cacher, "data", None)) is None:
                cacher.data = data = {}
            elif (value := data.get(self.name, _unset)) is not _unset and value[1] == current_version:
                return value[0]

            # 版本过期
            for __ in range(self._try_times):
                with suppress(Exception):
                    cached_value = deepcopy(object.__getattribute__(instance, self.private_name))
                    break
            else:
                raise RuntimeError(_("threadsafe_attr.cannot_copy") % self.name)
            data[self.name] = (cached_value, current_version)
            return cached_value

        def __set__(self, instance, value):
            if threading.current_thread() is not self._main_thread:
                raise RuntimeError(_("threadsafe_attr.cannot_set") % self.name)
            object.__setattr__(instance, self.private_name, value)

    @staticmethod
    def allow_non_main(func):
        """装饰器：方法允许在非主线程执行"""
        func._allow_non_main = True
        return func

    @staticmethod
    def version_increment(func):
        """装饰器：方法调用时会使版本计数器 +1"""
        func._version_increment = True
        return func

    def __new__(mcs, name, bases, namespace: dict):
        # 处理实例属性
        need_setattr = {}
        if safe_attrs := namespace.get("__thread_guarded_attrs__"):
            if slots := namespace.get("__slots__"):
                if slots.__class__ is str:
                    if slots in safe_attrs:
                        namespace["__slots__"] = (f"_TS__{slots}", "_TS____V", "_TS____C")
                elif isinstance(slots, MutableSet):
                    for i in safe_attrs:
                        slots.discard(i)
                        slots.add(f"_TS__{i}")
                    slots.add("_TS____V")
                    slots.add("_TS____C")
                elif isinstance(slots, MutableSequence):
                    for i in range(len(slots) - 1, -1, -1):
                        if slots[i] in safe_attrs:
                            del slots[i]
                    slots.extend(f"_TS__{s}" for s in safe_attrs)
                    slots.append("_TS____V")
                    slots.append("_TS____C")
                else:
                    namespace["__slots__"] = slots = [s for s in slots if s not in safe_attrs]
                    slots.extend(f"_TS__{s}" for s in safe_attrs)
                    slots.append("_TS____V")
                    slots.append("_TS____C")

            for attr in safe_attrs:
                if (orig_value := namespace.get(attr, _unset)) is _unset:
                    namespace[attr] = mcs.Attribute(attr)
                else:
                    need_setattr[attr] = orig_value

        # 处理方法
        for key, value in namespace.items():
            if callable(value) and not isinstance(value, (staticmethod, property)):
                value = get_true_func(value)
                allow, inc = getattr(value, "_allow_non_main", False), getattr(value, "_version_increment", False)
                if not allow or inc:
                    if iscoroutinefunction(value):

                        @wraps(value)
                        async def wrapper(
                            first,
                            *args,
                            __func=value,
                            __allow=allow,
                            __inc=inc,
                            __main_thread=threading.main_thread(),
                            **kwargs,
                        ):
                            if not __allow and threading.current_thread() is not __main_thread:
                                raise RuntimeError(_("threadsafe_attr.cannot_call") % __func.__name__)

                            if __inc:
                                result = await __func(first, *args, **kwargs)
                                if not hasattr(first, "_TS____V"):
                                    first._TS____V = 0
                                first._TS____V += 1
                                return result
                            return await __func(first, *args, **kwargs)

                    else:

                        @wraps(value)
                        def wrapper(
                            first,
                            *args,
                            __func=value,
                            __allow=allow,
                            __inc=inc,
                            __main_thread=threading.main_thread(),
                            **kwargs,
                        ):
                            if not __allow and threading.current_thread() is not __main_thread:
                                raise RuntimeError(_("threadsafe_attr.cannot_call") % __func.__name__)

                            if __inc:
                                result = __func(first, *args, **kwargs)
                                if not hasattr(first, "_TS____V"):
                                    first._TS____V = 0
                                first._TS____V += 1
                                return result
                            return __func(first, *args, **kwargs)

                    if isinstance(value, classmethod):
                        wrapper = classmethod(wrapper)
                    namespace[key] = wrapper

        cls = super().__new__(mcs, name, bases, namespace)

        # 处理类属性
        for attr, orig_value in need_setattr.items():
            (value := mcs.Attribute(attr)).__set__(cls, orig_value)
            setattr(cls, attr, value)

        return cls


class AsyncCounter:
    """等待计数器归0。非线程安全。"""

    def __init__(self):
        self._count = 0
        self._event = aiologic.REvent()
        self._event.set()

    def __enter__(self):
        self._event.clear()
        self._count += 1

    def __exit__(self, *_):
        self._count -= 1
        if self._count == 0:
            self._event.set()

    async def wait_until_zero(self):
        await self._event


class AsyncTee[T]:
    """非线程安全。"""

    __slots__ = (
        "ait",
        "buffer",
        "not_empty",
        "not_full",
        "eof",
        "consumer_indices",
        "next_cid",
        "producer_task",
        "exc",
        "maxsize",
    )

    def __init__(self, ait: AsyncIterator[T], maxsize):
        self.ait = ait
        self.buffer = []  # 已生成但尚未被所有消费者消费的数据
        self.not_empty = asyncio.Condition()
        self.eof = False
        self.consumer_indices = {}  # cid -> 下一个要读的buffer索引
        self.next_cid = 0
        self.producer_task = None
        self.exc = None
        self.maxsize = maxsize
        self.not_full = asyncio.Condition()

    async def _producer(self):
        try:
            async for item in self.ait:
                async with self.not_full:
                    while len(self.buffer) >= self.maxsize:
                        await self.not_full.wait()
                self.buffer.append(item)
                async with self.not_empty:
                    self.not_empty.notify_all()

            self.eof = True
            async with self.not_empty:
                self.not_empty.notify_all()
        except Exception as e:
            self.exc = e
            async with self.not_empty:
                self.not_empty.notify_all()

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
            async with tee.not_empty:
                while True:
                    # 消费者已结束
                    if (idx := tee.consumer_indices.get(cid)) is None:
                        raise StopAsyncIteration

                    # 有数据可读
                    if idx < len(tee.buffer):
                        item = tee.buffer[idx]
                        tee.consumer_indices[cid] = idx + 1
                        # 清理所有消费者都读过的头部
                        if tee.consumer_indices:
                            if (min_idx := min(tee.consumer_indices.values())) > 0:
                                del tee.buffer[:min_idx]
                                for k in tee.consumer_indices:
                                    tee.consumer_indices[k] -= min_idx
                                tee.not_full.notify()
                        return item

                    # 数据源已结束且读完
                    if tee.eof:
                        tee.consumer_indices.pop(cid, None)
                        # 无活跃消费者
                        if not tee.consumer_indices and tee.producer_task:
                            tee.producer_task.cancel()
                        if tee.exc:
                            raise tee.exc
                        raise StopAsyncIteration

                    await tee.not_empty.wait()

    @classmethod
    def gen[T](cls, agen: AsyncIterator[T], n=2, maxsize=2) -> tuple[AsyncIterator[T], ...]:
        tee = cls(agen, maxsize)
        return tuple(tee.new_consumer() for _ in range(n))


class AsyncResult:
    __slots__ = ("_event", "_flag")

    @dataclass(slots=True)
    class ExcWrapper:
        exc: BaseException

    def __init__(self):
        self._event = aiologic.Event()
        self._flag = aiologic.Flag()

    def __await__(self):
        yield from self._event.__await__()
        if isinstance(result := self._flag.get(), self.ExcWrapper):
            raise result.exc
        return result

    def set_result(self, value):
        ok = self._flag.set(value)
        self._event.set()
        return ok

    def set_exception(self, e):
        ok = self._flag.set(self.ExcWrapper(e))
        self._event.set()
        return ok

    def result(self):
        assert self._event.is_set()
        return self._flag.get()

    def is_set(self):
        return self._event.is_set()


class AsyncLoopExecutor(Executor):
    _counter = count().__next__
    BROKEN = BrokenThreadPool

    __slots__ = (
        "_max_workers",
        "_thread_name_prefix",
        "_initializer",
        "_initargs",
        "_global_queue",
        "_threads",
        "_broken",
        "_shutdown",
        "_finalizer",
    )

    @dataclass(slots=True)
    class _Thread:
        queue: aiologic.SimpleQueue = field(default_factory=aiologic.SimpleQueue)
        active_tasks: int = 1
        lock: aiologic.Lock = field(default_factory=aiologic.Lock)
        thread: threading.Thread = None

    def __init__(self, max_workers=None, thread_name_prefix="", initializer: Callable = None, initargs=()):
        if max_workers is None:
            max_workers = min(32, process_cpu_count())
        if max_workers <= 0:
            raise ValueError(_("async_loop_executor.422"))

        self._max_workers = max_workers
        self._thread_name_prefix = thread_name_prefix or f"AsyncLoopExecutor-{id(self)}"
        self._initializer = initializer
        self._initargs = initargs

        self._global_queue = aiologic.SimpleQueue()
        self._threads: list[AsyncLoopExecutor._Thread] = []
        self._broken = None
        self._shutdown = False
        self._finalizer = finalize(self, lambda: asyncio.create_task(self._clean_task(self._global_queue, self._threads)))

    async def submit(self, fn: Callable, *args, **kwargs):
        if self._broken:
            raise self.BROKEN(self._broken)
        if self._shutdown:
            raise RuntimeError(_("async_loop_executor.closed"))

        # 开找
        current_count = len(self._threads)
        best_info, min_tasks = None, float("inf")
        for meta in self._threads:
            if meta.active_tasks < min_tasks:
                min_tasks, best_info = meta.active_tasks, meta
                if min_tasks == 0:  # 空闲线程
                    break

        work_item = (result := AsyncResult(), fn, args, kwargs, copy_context())
        if best_info and min_tasks == 0:
            # 空闲线程
            async with best_info.lock:
                best_info.active_tasks += 1
            best_info.queue.put(work_item)
            return result

        if current_count < self._max_workers:
            # 新建线程
            meta = self._Thread()
            meta.thread = t = threading.Thread(
                name=f"{self._thread_name_prefix}_{self._counter()}",
                target=run_with_uvloop,
                args=(self._worker_main(meta, ref(self), self._global_queue, self._initializer, work_item),),
                daemon=True,
            )
            self._threads.append(meta)
            t.start()
            return result

        # 全局队列
        self._global_queue.put(work_item)
        return result

    @classmethod
    async def _worker_main(
        cls, meta: _Thread, executor: AsyncLoopExecutor, global_queue: aiologic.SimpleQueue, initializer, initial_work_item
    ):
        """工作线程的主协程。"""
        # 用户初始化函数
        if initializer:
            try:
                await async_run_func(initializer)
            except Exception as e:
                # 整个 executor 损坏
                if executor := executor():
                    executor._broken = e

                # 初始任务标记为异常
                if initial_work_item:
                    e._AL__ = True
                    initial_work_item[1].set(e)
                    initial_work_item[0].set()
                return
        meta.queue.put(initial_work_item)

        # 获取并创建任务
        tasks = WeakSet()
        while True:
            done, pending = await asyncio.wait(
                (asyncio.create_task(meta.queue.async_get()), global_task := asyncio.create_task(global_queue.async_get())),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

            for task in done:
                if (item := task.result()) is None:
                    # 清理全局队列后关闭
                    while True:
                        try:
                            item = await global_queue.async_get(blocking=False)
                        except aiologic.QueueEmpty:
                            break
                        async with meta.lock:
                            meta.active_tasks += 1
                        tasks.add(asyncio.create_task(cls._run_task(item, meta)))
                    return await asyncio.gather(*tasks, return_exceptions=True)
                else:
                    if task is global_task:
                        async with meta.lock:
                            meta.active_tasks += 1
                    tasks.add(asyncio.create_task(cls._run_task(item, meta)))

            await asyncio.sleep(0)

    @staticmethod
    async def _run_task(item, meta: _Thread):
        """执行用户函数并设置结果。"""
        result, fn, args, kwargs, context = item
        try:
            result.set_result(await asyncio.create_task(async_run_func(fn, *args, **kwargs), context=context))
        except Exception as e:
            result.set_exception(e)
        async with meta.lock:
            meta.active_tasks -= 1

    async def shutdown(self, cancel_futures=False):
        self._shutdown = True
        await self._clean_task(self._global_queue, self._threads, cancel_futures=cancel_futures)
        await asyncio.gather(*[asyncio.to_thread(t.thread.join) for t in self._threads])
        self._threads.clear()
        self._finalizer.detach()

    @staticmethod
    async def _clean_task(global_queue: aiologic.SimpleQueue, metas: list[_Thread], cancel_futures=False):
        """清空队列中所有任务并取消 future。"""
        if cancel_futures:
            (exc := asyncio.CancelledError())._AL__ = True
            while True:
                try:
                    item = await global_queue.async_get(blocking=False)
                    item[1] = exc
                    item[0].set()
                except aiologic.QueueEmpty:
                    break
        for meta in metas:
            if cancel_futures:
                while True:
                    try:
                        item = await meta.queue.async_get(blocking=False)
                        item[1] = exc
                        item[0].set()
                    except aiologic.QueueEmpty:
                        break
            meta.queue.put(None)


class AsyncConnection:
    """非线程安全"""

    __slots__ = ("_conn", "_closed", "_recv_queue", "_recv_thread", "_send_queue", "_send_thread")

    def __init__(self, connection: _ConnectionBase):
        self._conn = connection
        self._closed = threading.Event()
        self._recv_queue = aiologic.SimpleQueue()
        self._recv_thread = threading.Thread(target=self._recv_worker, daemon=True)
        self._recv_thread.start()
        self._send_queue = aiologic.SimpleQueue()
        self._send_thread = threading.Thread(target=self._send_worker, daemon=True)
        self._send_thread.start()

    def _recv_worker(self):
        while not self._closed.is_set():
            try:
                self._recv_queue.put(self._conn.recv())
            except EOFError, OSError:
                break
        self._recv_queue.put(None)

    def _send_worker(self):
        while not self._closed.is_set():
            try:
                self._conn.send(self._send_queue.green_get())
            except EOFError, OSError:
                break

    async def send(self, obj):
        if self._closed.is_set():
            raise EOFError
        self._send_queue.put(obj)

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

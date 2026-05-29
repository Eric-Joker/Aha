import os
import pickle
import re
import shlex
import sys
from asyncio import create_task
from base64 import b64encode
from collections import deque
from collections.abc import AsyncIterable, AsyncIterator, MutableSequence, MutableSet
from contextlib import suppress
from decimal import ROUND_HALF_UP, Decimal
from functools import wraps
from gc import collect
from logging import Logger
from multiprocessing import current_process
from time import monotonic
from weakref import WeakValueDictionary

from aiofiles import open
from aiologic import Queue
from ssrjson import JSONEncodeError
from ssrjson import dumps_to_bytes as json_dumps

from models.exc import ExactlyOneTruthyValueError


def round_decimal(num: Decimal, digits=2):
    return num.quantize(Decimal(f'0.{"0" * digits}'), rounding=ROUND_HALF_UP).normalize()


def decimal_to_str(d):
    if len(parts := (formatted := format(d, "f")).split(".")) == 2:
        # 去除右侧的零和小数点
        parts[1] = parts[1].rstrip("0")
        return f"{parts[0]}.{parts[1]}" if parts[1] else parts[0]
    return formatted


def check_single_true(raise_exc=True, *args, **kwargs):
    """要求参数中恰好有一个值的布尔值为True。

    Args:
        raise_exc: 如果为True，则在条件不满足时抛出异常；否则返回False。
    """
    all_values = args + tuple(kwargs.values())
    if sum(bool(v) for v in all_values) == 1:
        return True

    if raise_exc:
        if args:
            error_msg = f"Expected exactly one truthy value, but got the values: [{', '.join(repr(v) for v in all_values)}]"
        else:
            error_msg = f"Expected exactly one truthy value, but got the keyword arguments: {', '.join(f"{k}={v!r}" for k, v in kwargs.items())}"
        raise ExactlyOneTruthyValueError(error_msg)
    return False


def is_one_instance_of_other(a, b):
    """是否其中有一方是另一方的类或其子类的实例"""
    return isinstance(a, b.__class__) or isinstance(b, a.__class__)


def uninstall_module(module_name):
    modnames = [modname for modname in list(sys.modules) if modname.startswith(f"{module_name}.")]
    modnames.sort(key=lambda name: name.count("."), reverse=True)
    for modname in modnames:
        del sys.modules[modname]


def commented2basic(obj):
    from ruamel.yaml.comments import CommentedMap, CommentedSeq

    if isinstance(obj, CommentedMap):
        return {k: commented2basic(v) for k, v in obj.items()}
    elif isinstance(obj, CommentedSeq):
        return [commented2basic(item) for item in obj]
    else:
        return obj


def make_exc_picklable(exc: BaseException, logger: Logger = None):
    if is_pickleable(exc):
        return exc

    exc_type = exc.__class__
    try:
        new_exc = exc_type(*exc.args)
    except Exception:
        if logger:
            logger.exception(exc_info=exc)
        try:
            if not is_pickleable(new_exc := exc_type()):
                new_exc = Exception() if issubclass(exc_type, Exception) else BaseException()
        except Exception:
            new_exc = Exception() if issubclass(exc_type, Exception) else BaseException()

    # 复制所有可 pickle 的属性
    for attr_name in dir(exc):
        with suppress(AttributeError, TypeError):
            if attr_name.startswith("_") or not is_pickleable(attr_value := getattr(exc, attr_name)):
                continue
            setattr(new_exc, attr_name, attr_value)

    return new_exc


def is_pickleable(obj):
    try:
        pickle.dumps(obj)
        return True
    except pickle.PickleError, TypeError, AttributeError:
        return False


# region stream dumps json
def _try_dumps(obj):
    if obj is None:
        return b"null"
    elif isinstance(obj, bool):
        return b"true" if obj else b"false"
    try:
        return json_dumps(obj)
    except JSONEncodeError:
        return


async def stream_async_json(obj):
    if result := _try_dumps(obj):
        yield result
        return

    elif isinstance(obj, dict):
        if not obj:
            yield b"{}"
            return

        first, result, async_gen_items = True, bytearray(b"{"), []
        for key, value in obj.items():
            if json := _try_dumps(value):
                if not first:
                    result.append(44)  # ,
                first = False
                result.extend(json_dumps(key))
                result.append(58)  # :
                result.extend(json)
            else:
                async_gen_items.append((key, value))

        if async_gen_items:
            for key, value in async_gen_items:
                if not first:
                    result.append(44)  # ,
                result.extend(json_dumps(key))
                result.append(58)  # :
                yield result
                result = bytearray()

                async for chunk in stream_async_json(value):
                    yield chunk
                first = False
        else:
            yield result

        yield b"}"

    elif isinstance(obj, (list, tuple)):
        if not obj:
            yield b"[]"
            return

        first, result = True, bytearray(b"[")
        for value in obj:
            if json := _try_dumps(value):
                if not first:
                    result.append(44)  # ,
                result.extend(json)
            else:
                if first:
                    yield result
                    result = bytearray()
                elif result:
                    result.append(44)  # ,
                    yield result
                    result = bytearray()
                else:
                    yield b","
                async for chunk in stream_async_json(value):
                    yield chunk
            first = False
        if result:
            result.append(93)  # ]
            yield result
        else:
            yield b"]"

    elif isinstance(obj, AsyncIterable):
        yield b'"'
        async for chunk in obj:
            yield chunk
        yield b'"'

    else:
        yield json_dumps(obj)


# endregion
class AsyncBase64Encoder:
    __slots__ = (
        "_file",
        "_has_prefix",
        "_queue",
        "_max_chunk_size",
        "_running",
        "_gen_times",
        "_req_intervals",
        "_last_request_time",
        "_ewma_alpha",
        "_CAing",
        "_adjust_chunk_size",
        "_chunk_size",
        "_producer_task",
    )

    MSS = 1536
    DEFAULT_CHUNK = 65535

    def __init__(self, file: str, buffer=None, has_prefix=True):
        self._file = file
        self._has_prefix = has_prefix
        self._queue = Queue(maxsize=1)
        self._max_chunk_size = (buffer - 2) // 13 * 3 if buffer and buffer > 0 else None
        self._running = True

        # 用于调整chunk大小的状态变量
        self._gen_times = deque(maxlen=3)
        self._req_intervals = deque(maxlen=5)
        self._last_request_time = None
        self._ewma_alpha = 2 / (5 + 1)
        self._CAing = False

        # 预先计算的状态
        if self._max_chunk_size is not None:
            self._adjust_chunk_size = self._adjust_chunk_size_bounded
            self._chunk_size = min(self.DEFAULT_CHUNK, self._max_chunk_size)
        else:
            self._adjust_chunk_size = self._adjust_chunk_size_unbounded
            self._chunk_size = self.DEFAULT_CHUNK

        self._producer_task = create_task(self._producer())

    async def _producer(self):
        """读取文件、编码和调整chunk大小"""
        try:
            async with open(self._file, "rb") as f:
                if self._has_prefix:
                    await self._queue.async_put(b"base64://")

                while self._running:
                    start_time = monotonic()
                    if not (data := await f.read(self._chunk_size)):
                        break
                    gen_time = monotonic() - start_time
                    await self._queue.async_put(b64encode(data))

                    self._gen_times.append(gen_time)
                    if len(self._req_intervals) == 5:
                        self._adjust_chunk_size()
        finally:
            self._running = False
            await self._queue.async_put(None)  # 发送结束信号

    def _adjust_chunk_size_bounded(self):
        """有最大限制的chunk大小调整"""
        ewma_interval = self._req_intervals[0]
        for interval in list(self._req_intervals)[1:]:
            ewma_interval = self._ewma_alpha * interval + (1 - self._ewma_alpha) * ewma_interval

        if (r_i := sum(self._gen_times) / 3 / ewma_interval) >= 1.2:
            self._chunk_size = max(3, min(self._max_chunk_size, int(self._chunk_size / r_i) // 3 * 3))
            self._CAing = True
        elif r_i <= 0.8:
            self._chunk_size = max(
                3,
                min(
                    self._max_chunk_size,
                    (self._chunk_size + int(self.MSS * (1 + r_i)) if self._CAing else self._chunk_size * 2) // 3 * 3,
                ),
            )

    def _adjust_chunk_size_unbounded(self):
        """无最大限制的chunk大小调整"""
        ewma_interval = self._req_intervals[0]
        for interval in list(self._req_intervals)[1:]:
            ewma_interval = self._ewma_alpha * interval + (1 - self._ewma_alpha) * ewma_interval

        if (r_i := sum(self._gen_times) / 3 / ewma_interval) >= 1.2:
            self._chunk_size = max(3, int(self._chunk_size / r_i) // 3 * 3)
            self._CAing = True
        elif r_i <= 0.8:
            self._chunk_size = max(
                3, (self._chunk_size + int(self.MSS * (1 + r_i)) if self._CAing else self._chunk_size * 2) // 3 * 3
            )

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self

    async def __anext__(self) -> bytes:
        current_time = monotonic()

        # 更新请求间隔EWMA
        if self._last_request_time is not None:
            self._req_intervals.append(current_time - self._last_request_time)
        self._last_request_time = current_time

        # 获取数据
        if (data := await self._queue.async_get()) is None:
            self.close()
            raise StopAsyncIteration
        return data

    def close(self):
        self._running = False
        self._producer_task.cancel()


def slots_extend(slots, *items):
    if slots.__class__ is str:
        return (slots, *items)
    elif isinstance(slots, MutableSet):
        slots |= items
        return slots
    elif isinstance(slots, MutableSequence):
        slots.extend(i for i in items if i not in slots)
        return slots
    else:
        (slots := [s for s in slots if s not in items]).extend(items)
        return slots


class PerProcessSingletonMeta(type):
    """进程内单例元类"""

    _instances = WeakValueDictionary()

    def __new__(mcs, name, bases, namespace):
        if slots := namespace.get("__slots__"):
            namespace["__slots__"] = slots_extend(slots, "__weakref__")
        return super().__new__(mcs, name, bases, namespace)

    def __call__(cls, *args, **kwargs):
        collect()
        if cls in cls._instances:
            return cls._instances[cls]
        cls._instances[cls] = instance = super().__call__(*args, **kwargs)
        return instance

    def __getattr__(cls, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return getattr(cls._instances.get(cls), name)
        except AttributeError as e:
            from core.i18n import _

            raise RuntimeError(_("models.pre_proc_singleton_meta.getattr_error") % cls.__qualname__) from e


class SingletonMeta(PerProcessSingletonMeta):
    """仅主线程可创建单例的元类"""

    def __call__(cls, *args, **kwargs):
        if current_process().name != "MainProcess":
            from core.i18n import _

            raise ImportError(
                f"Refusing to create class '{cls.__qualname__}' in a subprocess, as this may violate the singleton pattern."
            )
        return super().__call__(*args, **kwargs)


# region fuck cmd
if os.name == "nt":
    import asyncio
    import asyncio.subprocess

    import _winapi

    _original_CreateProcess = _winapi.CreateProcess
    VON_PATTERN = re.compile(r"/v:(?:on|off)", re.IGNORECASE)

    @wraps(_winapi.CreateProcess)
    def CreateProcess(application_name, command_line: str, *args):
        splited = command_line.partition("cmd.exe")
        if splited[1] and not any(VON_PATTERN.fullmatch(a) for a in shlex.split(splited[2], posix=False)):
            return _original_CreateProcess(application_name, f"{splited[0]}{splited[1]} /v:on{splited[2]}", *args)
        return _original_CreateProcess(application_name, command_line, *args)

    _winapi.CreateProcess = CreateProcess

    _original_create_subprocess_shell = asyncio.subprocess.create_subprocess_shell
    SET_PATTERN = re.compile(r'(?:^|\s+)set\s+(?:/.\s+)*(("?)[^=]+)=.+?(?:("?)|&|\||\)|>|<|$)', re.IGNORECASE)

    @wraps(asyncio.subprocess.create_subprocess_shell)
    async def create_subprocess_shell(cmd: str, *args, **kwargs):
        if len(lines := cmd.splitlines()) > 1:
            declared_vars = set()
            for line in lines:
                if m := SET_PATTERN.search(line):
                    declared_vars.add(re.escape(m[1] if m[3] else m[1].lstrip(m[2])))
            replaced = re.sub(rf'%({"|".join(declared_vars)})%', r"!\1!", cmd)
            cmd = " & ".join(f"({x})" for x in replaced.splitlines())

        return await _original_create_subprocess_shell(cmd, *args, **kwargs)

    asyncio.subprocess.create_subprocess_shell = asyncio.create_subprocess_shell = create_subprocess_shell
# endregion

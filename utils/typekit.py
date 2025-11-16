from asyncio import Queue, create_task
from base64 import b64encode
from collections import deque
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import suppress
from logging import Logger
from pickle import PickleError
from pickle import dumps as pickle_dumps
from time import monotonic

from aiofiles import open
from orjson import dumps as json_dumps


def decimal_to_str(d):
    if len(parts := (formatted := format(d, "f")).split(".")) == 2:
        # 去除右侧的零和小数点
        parts[1] = parts[1].rstrip("0")
        return f"{parts[0]}.{parts[1]}" if parts[1] else parts[0]
    return formatted


def commented2basic(obj):
    from ruamel.yaml.comments import CommentedMap, CommentedSeq

    if isinstance(obj, CommentedMap):
        return dict(obj)
    elif isinstance(obj, CommentedSeq):
        return list(obj)
    else:
        return obj


# region stream dumps json
def _try_dumps(obj):
    if obj is None:
        return b"null"
    elif isinstance(obj, bool):
        return b"true" if obj else b"false"
    elif isinstance(obj, int):
        return str(obj).encode("utf-8")
    try:
        return json_dumps(obj)
    except TypeError:
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

    elif isinstance(obj, (list, tuple, set)):
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
                    await self._queue.put(b"base64://")

                while self._running:
                    start_time = monotonic()
                    if not (data := await f.read(self._chunk_size)):
                        break
                    gen_time = monotonic() - start_time
                    await self._queue.put(b64encode(data))

                    self._gen_times.append(gen_time)
                    if len(self._req_intervals) == 5:
                        self._adjust_chunk_size()
        finally:
            self._running = False
            await self._queue.put(None)  # 发送结束信号

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
        if (data := await self._queue.get()) is None:
            self.close()
            raise StopAsyncIteration
        return data

    def close(self):
        self._running = False
        self._producer_task.cancel()


def make_exc_picklable(exc: BaseException, logger: Logger = None):
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
            if attr_name.endswith("__") or not is_pickleable(attr_value := getattr(exc, attr_name)):
                continue
            setattr(new_exc, attr_name, attr_value)

    return new_exc


def is_pickleable(obj):
    try:
        pickle_dumps(obj)
        return True
    except PickleError, TypeError, AttributeError:
        return False

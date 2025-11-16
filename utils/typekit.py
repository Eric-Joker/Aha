
import re
from asyncio import Queue, create_task
from base64 import b64encode
from collections import defaultdict, deque, namedtuple
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import suppress
from numbers import Number
from pickle import PickleError
from pickle import dumps as pickle_dumps
from time import monotonic
from typing import Protocol, runtime_checkable

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


def sec2str(seconds):
    units = (("天", 86400), ("小时", 3600), ("分钟", 60), ("秒", 1))
    parts = []
    for unit, div in units:
        if value := seconds // div:
            parts.append(f"{value}{unit}")
        seconds %= div
    return "".join(parts) or "0秒"


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


EMPTY_DICT = b"{}"
EMPTY_LIST = b"[]"
QUOTE_MARK = b'"'
COMMA = b","
COLON = b":"
LEFT_BRACE = b"{"
RIGHT_BRACE = b"}"
LEFT_BRACKET = b"["
RIGHT_BRACKET = b"]"
COMMA_BYTE = 44  # ord(',')
COLON_BYTE = 58  # ord(':')
RIGHT_BRACKET_BYTE = 93  # ord(']')


async def stream_async_json(obj):
    if result := _try_dumps(obj):
        yield result
        return

    elif isinstance(obj, dict):
        if not obj:
            yield EMPTY_DICT
            return

        first, result, async_gen_items = True, bytearray(LEFT_BRACE), []
        for key, value in obj.items():
            if json := _try_dumps(value):
                if not first:
                    result.append(COMMA_BYTE)
                first = False
                result.extend(json_dumps(key))
                result.append(COLON_BYTE)
                result.extend(json)
            else:
                async_gen_items.append((key, value))

        if async_gen_items:
            for key, value in async_gen_items:
                if not first:
                    result.append(COMMA_BYTE)
                result.extend(json_dumps(key))
                result.append(COLON_BYTE)
                yield result
                result = bytearray()

                async for chunk in stream_async_json(value):
                    yield chunk
                first = False
        else:
            yield result

        yield RIGHT_BRACE

    elif isinstance(obj, (list, tuple, set)):
        if not obj:
            yield EMPTY_LIST
            return

        first, result = True, bytearray(LEFT_BRACKET)
        for value in obj:
            if json := _try_dumps(value):
                if not first:
                    result.append(COMMA_BYTE)
                result.extend(json)
            else:
                if first:
                    yield result
                    result = bytearray()
                elif result:
                    result.append(COMMA_BYTE)
                    yield result
                    result = bytearray()
                else:
                    yield COMMA_BYTE
                async for chunk in stream_async_json(value):
                    yield chunk
            first = False
        if result:
            result.append(RIGHT_BRACKET)
            yield result
        else:
            yield RIGHT_BRACKET

    elif isinstance(obj, AsyncIterable):
        yield QUOTE_MARK
        async for chunk in obj:
            yield chunk
        yield QUOTE_MARK

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


# region parse_size by humanfriendly
SizeUnit = namedtuple("SizeUnit", "divider, symbol, name")
CombinedUnit = namedtuple("CombinedUnit", "decimal, binary")
disk_size_units = (
    CombinedUnit(SizeUnit(1000**1, "KB", "kilobyte"), SizeUnit(1024**1, "KiB", "kibibyte")),
    CombinedUnit(SizeUnit(1000**2, "MB", "megabyte"), SizeUnit(1024**2, "MiB", "mebibyte")),
    CombinedUnit(SizeUnit(1000**3, "GB", "gigabyte"), SizeUnit(1024**3, "GiB", "gibibyte")),
    CombinedUnit(SizeUnit(1000**4, "TB", "terabyte"), SizeUnit(1024**4, "TiB", "tebibyte")),
    CombinedUnit(SizeUnit(1000**5, "PB", "petabyte"), SizeUnit(1024**5, "PiB", "pebibyte")),
    CombinedUnit(SizeUnit(1000**6, "EB", "exabyte"), SizeUnit(1024**6, "EiB", "exbibyte")),
    CombinedUnit(SizeUnit(1000**7, "ZB", "zettabyte"), SizeUnit(1024**7, "ZiB", "zebibyte")),
    CombinedUnit(SizeUnit(1000**8, "YB", "yottabyte"), SizeUnit(1024**8, "YiB", "yobibyte")),
)


def tokenize(text):
    tokenized_input = []
    for token in re.split(r"(\d+(?:\.\d+)?)", text):
        if re.match(r"\d+\.\d+", token := token.strip()):
            tokenized_input.append(float(token))
        elif token.isdigit():
            tokenized_input.append(int(token))
        elif token:
            tokenized_input.append(token)
    return tokenized_input


def parse_size(size, binary=False):
    if (tokens := tokenize(size)) and isinstance(tokens[0], Number):
        normalized_unit = tokens[1].lower() if len(tokens) == 2 and isinstance(tokens[1], str) else ""
        if len(tokens) == 1 or normalized_unit.startswith("b"):
            return int(tokens[0])
        if normalized_unit:
            normalized_unit = normalized_unit.rstrip("s")
            for unit in disk_size_units:
                if normalized_unit in (unit.binary.symbol.lower(), unit.binary.name.lower()):
                    return int(tokens[0] * unit.binary.divider)
                if normalized_unit in (unit.decimal.symbol.lower(), unit.decimal.name.lower()) or normalized_unit.startswith(
                    unit.decimal.symbol[0].lower()
                ):
                    return int(tokens[0] * (unit.binary.divider if binary else unit.decimal.divider))
    raise ValueError("Failed to parse size! (input %r was tokenized as %r)" % (size, tokens))


# endregion
@runtime_checkable
class Strable(Protocol):
    def __str__(self) -> str: ...


def make_exception_pickleable(exc: BaseException):
    exc_type = type(exc)
    try:
        new_exc = exc_type(*exc.args)
    except Exception:
        try:
            new_exc = exc_type()
        except Exception:
            new_exc = Exception()

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


# region str2sec
NUM_PATTERN = re.compile(
    r"(?:([\d\u4e00-\u9fa5a-zA-Z]*?)\s*)"
    r"(?:$|个?(小时|分钟|秒钟|[年个月周天日时分秒刻]|years?|y|mon(?:th)?s?|weeks?|w|days?|d|hours?|h|min(?:ute)?s?|m|sec(?:ond)?s?|s|qtr))",
    re.IGNORECASE,
)

# fmt: off
CHINESE_NUM = {
    '零':0, '一':1, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9, '十':10,
    '佰':100, '仟':1000, '萬':10000, '亿':100000000,
    '壹':1, '贰':2, '叁':3, '肆':4, '伍':5, '陆':6, '柒':7, '捌':8, '玖':9, '拾':10,
    '两':2, '百':100, '千':1000, '万':10000, '億':100000000, '〇':0,
    '兆':1000000, '桿':1000
} # '廿':20, '卅':30, '卌':40, '卄':20, '卋':30, '皕':200, 

UNIT_MAP = {
    '年':'year', '月':'month', '周':'week', '日':'day', '天':'day', '刻':'quarter',
    '小时':'hour', '时':'hour', '分钟':'minute', '分':'minute', '秒':'second',
    'year':'year', 'years':'year', 'y':'year', 'month':'month', 'months':'month', 'mons':'month', 'mon':'month', 'qtr':'quarter',
    'week':'week', 'weeks':'week', 'w':'week', 'day':'day', 'days':'day', 'd':'day', 'hour':'hour',
    'hours':'hour', 'h':'hour', 'minute':'minute', 'minutes':'minute', 'min':'minute', 'mins':'minute', 'm':'minute',
    'second':'second', 'seconds':'second', 's':'second', 'sec':'second', 'secs':'second'
}

UNIT_SECONDS = {
    'year': 31556952, 'month': 2629746, 'day': 86400, 'hour': 3600,
    'minute': 60, 'second': 1, 'quarter': 788400, 'week': 604800
}

UNIT_ORDER = [
    ['year', 'month', 'day', 'hour', 'minute', 'second'],
    ['month', 'day', 'hour', 'minute', 'second'],
    ['day', 'hour', 'minute', 'second'],
    ['hour', 'minute', 'second'],
    ['minute', 'second'],
    ['second']
]
# fmt: on

CHINESE_NUM_SET = frozenset(CHINESE_NUM)
TIME_STRS = set(CHINESE_NUM.keys()).union(UNIT_MAP.keys())


def _chinese_to_int(s: str):
    total = current = 0
    for char in s:
        val = CHINESE_NUM[char]
        if val >= 10:
            current = (current or 1) * val
            # 处理万/亿等大单位
            if val >= 10000:
                total, current = total + current, 0
        else:
            total += current
            current = val
    return total + current


def _parse_number(s: str):
    if not s:
        return 1
    if s.isdigit():
        return int(s)
    return _chinese_to_int(s) if all(c in CHINESE_NUM_SET for c in s) else None


def split_string(s):
    if (n := len(s)) == 0:
        return []

    best_count, best_sep, best_sep_len = 0, None, 0
    for sep_len in range(1, n):
        if (n - 1) // (sep_len + 1) < best_count:
            break

        sep_positions = defaultdict(list)
        for i in range(n - sep_len + 1):
            sep_positions[s[i : i + sep_len]].append(i)

        for sep, positions in sep_positions.items():
            if sep.isdigit() or sep in TIME_STRS:
                continue
            if not (valid := [i for i in positions if 0 < i < n - sep_len]):
                continue

            count, last_pos = 0, -sep_len
            for pos in sorted(valid):
                if pos >= last_pos + sep_len:
                    segment_start = last_pos + sep_len
                    if pos - segment_start > 0:
                        count += 1
                        last_pos = pos

            total_segments = count + 1 if n - last_pos + sep_len > 0 else count

            if (total_segments > best_count) or (total_segments == best_count and sep_len > best_sep_len):
                best_count = total_segments
                best_sep = sep
                best_sep_len = sep_len

    return [part for part in s.split(best_sep) if part] if best_sep is not None else []


def str2sec(time_str: str):
    total = prev_end = 0

    for match in NUM_PATTERN.finditer(time_str):
        if not match.group():
            continue

        start, end = match.start(), match.end()
        if start != prev_end:
            break
        prev_end = end

        num_part, unit_part = match.groups()
        num = _parse_number(num_part) if num_part else 1
        if num is None:
            return None

        unit = UNIT_MAP.get(unit_part.lower()) if unit_part else "second"
        if unit is None:
            return None

        if total:
            total += num * UNIT_SECONDS[unit]
        else:
            total = num * UNIT_SECONDS[unit]

    if not total and prev_end != len(time_str):
        parts = []
        for x in split_string(time_str):
            if (part := _parse_number(x)) is None:
                return None
            parts.append(part)
        if 0 < (length := len(parts)) <= 6:
            return sum(part * UNIT_SECONDS[unit] for part, unit in zip(parts, UNIT_ORDER[6 - length]))
        return None

    return total


# endregion

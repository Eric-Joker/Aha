import re
import unicodedata
from bisect import bisect_right
from collections.abc import Callable, Coroutine, Iterable, Iterator
from contextlib import suppress
from contextvars import ContextVar
from multiprocessing import current_process
from secrets import choice, randbelow
from typing import TYPE_CHECKING, Any, LiteralString, Self, SupportsIndex, overload

from core.i18n import _
from models.exc import CodePointConflictError, NotModified
from models.msg import Text

try:
    import numpy as np
except ImportError:
    np = None

if TYPE_CHECKING:
    from _typeshed import ReadableBuffer


if IS_MAINPROC := current_process().name == "MainProcess":
    from core.config import cfg


def fullwidth(char):
    if (code := ord(char)) == 0x20:  # 空格
        return chr(0x3000)
    return chr(code + 0xFEE0) if 0x21 <= code <= 0x7E else char


def halfwidth(char):
    if (code := ord(char)) == 0x3000:  # 空格
        return chr(0x20)
    return chr(code - 0xFEE0) if 0xFF01 <= code <= 0xFF5E else char


def is_version_newer(version_str: str, target_str: str):
    return tuple(map(int, version_str.split("."))) > tuple(map(int, target_str.split(".")))


# region re
def charclass_escape(s):
    """只转义正则字符集中有特殊含义的字符，需要传入方括号（不包括）之间的整个字符串"""
    s = s.replace("\\", "\\\\").replace("]", "\\]")
    if s.startswith("^"):
        s = "\\" + s
    if len(s) > 1 and "-" in s[1:-1]:
        s = "".join("\\-" if char == "-" and 0 < i < len(s) - 1 else char for i, char in enumerate(s))
    return s


# region re.asub by WFLing-seaer
async def asub(
    pattern: re.Pattern,
    repl: Callable[[re.Match], Coroutine[None, None, str]],
    text: str,
    count: int = 0,
    raise_on_not_modified: bool = False,
) -> str:
    results: list[str] = []
    last_end = 0
    n = 0

    matches: list[tuple[int, int, re.Match]] = []
    for mch in pattern.finditer(text):
        start, end = mch.span(0)
        matches.append((start, end, mch))

    if not matches and raise_on_not_modified:
        raise NotModified

    for start, end, mch in matches:
        if count > 0 and n >= count:
            break
        if start > last_end:
            results.append(text[last_end:start])

        try:
            replacement = await repl(mch)
        except Exception:
            raise

        results.append(replacement)
        last_end = end
        n += 1

    if last_end < len(text):
        results.append(text[last_end:])

    return "".join(results)


async def series_asub(
    patterns: Iterable[re.Pattern],
    repl: Iterable[Callable[[re.Match], Coroutine[None, None, str]]],
    text: str,
    count: int = 0,
    raise_on_not_modified: bool = False,
) -> str:
    modified = False
    for pattern, replacing in zip(patterns, repl):
        with suppress(NotModified):
            text = await asub(pattern, replacing, text, count, True)
            modified = True
    if not modified and raise_on_not_modified:
        raise NotModified
    return text


# endregion
# endregion
with suppress(ImportError):
    import unicodedata2

    if is_version_newer(unicodedata2.unicode_version, unicodedata.unicode_version):
        unicodedata = unicodedata2
    del unicodedata2


class InlineStr[T](str):
    cism: ContextVar[dict] = ContextVar("aha_inline_str_map", default=None)
    current_cp: ContextVar[set] = ContextVar("current_code_points", default=None)

    if IS_MAINPROC and cfg.memory_level == "high":

        def _init_intervals():
            _AREAS, _A_LEN, _A_PATTERN, _A_CPS, start, prev_cat = [], 0, [], [], None, None
            for code in range(0x110000):
                if (cur_cat := unicodedata.category(chr(code))) == "Cn" or cur_cat == "Co":
                    if start is None:
                        start, prev_cat = code, cur_cat
                    elif cur_cat != prev_cat:
                        # 类别变化
                        if (length := code - start) >= 1024:
                            _AREAS.append((start, code - 1))
                            _A_LEN += length
                            _A_PATTERN.append(rf"\U{start:08x}-\U{start:08x}")
                            for i in range(length):
                                _A_CPS.append((cp := start + i, chr(cp)))
                        start, prev_cat = code, cur_cat
                elif start is not None:
                    # 非 Cn/Co
                    if (length := code - start) >= 1024:
                        _AREAS.append((start, code - 1))
                        _A_LEN += length
                        _A_PATTERN.append(rf"\U{start:08x}-\U{start:08x}")
                        for i in range(length):
                            _A_CPS.append((cp := start + i, chr(cp)))
                    start = None

            if start is not None:  # 处理最后一个区间
                if (length := 0x110000 - start) >= 1024:
                    _AREAS.append((start, 0x10FFFF))
                    _A_LEN += length
                    _A_PATTERN.append(rf"\U{start:08x}-\U{start:08x}")
                    for i in range(length):
                        _A_CPS.append((cp := start + i, chr(cp)))

            return _AREAS, _A_LEN, _A_PATTERN, _A_CPS

        _AREAS, _A_LEN, _A_PATTERN, _A_CPS = _init_intervals()

        @classmethod
        def gen_char(cls):
            if (code_points := cls.current_cp.get()) is None:
                cls.current_cp.set({(t := choice(cls._A_CPS))[0]})
                return t[1]

            if len(code_points) >= cls._A_LEN * 0.95:
                raise OverflowError
            while (cp := (t := choice(cls._A_CPS))[0]) not in code_points:
                code_points.add(cp)
                return t[1]

    else:

        def _init_intervals():
            _AREAS, _A_LEN, _A_PATTERN, _A_CUM, _A_STARTS, start, prev_cat = [], 0, [], [], [], None, None
            for code in range(0x110000):
                if (cur_cat := unicodedata.category(chr(code))) == "Cn" or cur_cat == "Co":
                    if start is None:
                        start, prev_cat = code, cur_cat
                    elif cur_cat != prev_cat:
                        # 类别变化
                        if (length := code - start) >= 1024:
                            _AREAS.append((start, code - 1))
                            _A_LEN += length
                            _A_PATTERN.append(rf"\U{start:08x}-\U{start:08x}")
                            _A_CUM.append(_A_LEN)
                            _A_STARTS.append(start)
                        start, prev_cat = code, cur_cat
                elif start is not None:
                    # 非 Cn/Co
                    if (length := code - start) >= 1024:
                        _AREAS.append((start, code - 1))
                        _A_LEN += length
                        _A_PATTERN.append(rf"\U{start:08x}-\U{start:08x}")
                        _A_CUM.append(_A_LEN)
                        _A_STARTS.append(start)
                    start = None

            if start is not None:  # 处理最后一个区间
                if (length := 0x110000 - start) >= 1024:
                    _AREAS.append((start, 0x10FFFF))
                    _A_LEN += length
                    _A_PATTERN.append(rf"\U{start:08x}-\U{start:08x}")
                    _A_CUM.append(_A_LEN)
                    _A_STARTS.append(start)
            return _AREAS, _A_LEN, _A_PATTERN, _A_CUM, _A_STARTS

        _AREAS, _A_LEN, _A_PATTERN, _A_CUM, _A_STARTS = _init_intervals()

        @classmethod
        def _random_cp(cls):
            idx = bisect_right(cls._A_CUM, r := randbelow(cls._A_LEN))  # 找到所在区间的索引
            return cls._A_STARTS[idx] + (r if idx == 0 else r - cls._A_CUM[idx - 1])

        @classmethod
        def gen_char(cls):
            if (code_points := cls.current_cp.get()) is None:
                cls.current_cp.set({cp := cls._random_cp()})
                return chr(cp)

            # 已有已使用集合，需避免重复
            if len(code_points) >= cls._A_LEN * 0.95:
                raise OverflowError
            while (cp := cls._random_cp()) not in code_points:
                code_points.add(cp)
                return chr(cp)

    _A_PATTERN = re.compile("[" + "".join(_A_PATTERN) + "]")

    @classmethod
    def _extract_A_ord(cls, s: str) -> set[int]:
        if len(s) < 5:
            return {cp for ch in s if any(start <= (cp := ord(ch)) <= end for start, end in cls._AREAS)}

        elif len(s) < 300 or not np:
            return set(map(ord, cls._A_PATTERN.findall(s)))

        else:
            mask = np.zeros(len(arr := np.frombuffer(s.encode("utf-32-le"), dtype=np.uint32)), dtype=bool)
            for start, end in cls._AREAS:
                mask |= (arr >= start) & (arr <= end)
            return set(arr[mask])

    @classmethod
    def from_iterable[T](cls, obj: Iterable[T], mapping: dict = None) -> Self[T]:
        """
        Args:
            mapping: 将映射写入字典，键为字符串，值为被内联的对象。
        """
        result = []
        result_len = 0
        inline_indices = {}
        if (current_map := cls.cism.get()) is None:
            cls.cism.set(current_map := {})
        if (current_set := cls.current_cp.get()) is None:
            cls.current_cp.set(current_set := set())

        for seg in obj:
            if isinstance(seg, Text):
                if current_set.isdisjoint(extracted := cls._extract_A_ord(seg.text)):
                    current_set |= extracted
                else:
                    raise CodePointConflictError
            elif isinstance(seg, str):
                if current_set.isdisjoint(extracted := cls._extract_A_ord(seg)):
                    current_set |= extracted
                else:
                    raise CodePointConflictError

        if mapping is None:
            for seg in obj:
                if isinstance(seg, Text):
                    result.append(seg.text)
                    result_len += len(seg.text)
                elif isinstance(seg, str):
                    result.append(seg)
                    result_len += len(seg)
                else:
                    current_map.setdefault(char := cls.gen_char(), seg)
                    inline_indices[result_len] = seg
                    result.append(char)
                    result_len += 1
        else:
            for seg in obj:
                if isinstance(seg, Text):
                    result.append(seg.text)
                    result_len += len(seg.text)
                elif isinstance(seg, str):
                    result.append(seg)
                    result_len += len(seg)
                else:
                    current_map.setdefault(char := cls.gen_char(), seg)
                    mapping[char] = seg
                    inline_indices[result_len] = seg
                    result.append(char)
                    result_len += 1
        (result := cls().join(result)).inline_indices = inline_indices
        return result

    def to_list(self, mapping: dict = None) -> list[str | Any]:
        """
        Args:
            mapping: 映射表。若需要且未提供会自动从上下文中获取。
        """
        result: list[str | T] = []

        # 存在索引缓存
        if hasattr(self, "inline_indices"):
            last_end = 0

            for i, seg in self.inline_indices.items():
                if i > last_end:
                    result.append(self[last_end:i])
                result.append(seg)
                last_end = i + 1

            if last_end < len(self):
                result.append(self[last_end:])
            return result

        if not mapping and not (mapping := self.cism.get()):
            return [str(self)]

        if len(self) < 128:
            # 短的用传统逻辑
            start = 0  # 当前字符段的起始位置
            n = len(self)
            separator_chars = set(mapping)

            for i in range(n):
                if (char := self[i]) in separator_chars:
                    if i > start:
                        result.append(self[start:i])
                    result.append(mapping[char])
                    start = i + 1
            if start < n:
                result.append(self[start:])
        else:
            # 长的用正则
            last_end = 0
            for match in re.finditer(f"([{"".join(mapping)}])", self):
                if match.start() > last_end:
                    result.append(self[last_end : match.start()])
                result.append(mapping[match[0]])
                last_end = match.end()

            if last_end < len(self):
                result.append(self[last_end:])
        return result

    @classmethod
    def clear_map(cls):
        cls.cism.set(None)
        cls.current_cp.set(None)

    if TYPE_CHECKING:

        @overload
        def __new__(cls, object: object = "") -> Self: ...
        @overload
        def __new__(cls, object: ReadableBuffer, encoding: str = "utf-8", errors: str = "strict") -> Self: ...
    def __new__(cls, *args, **kwargs):
        if (current_set := cls.current_cp.get()) is None:
            cls.current_cp.set(cls._extract_A_ord(str(obj := super().__new__(cls, *args, **kwargs))))
        else:
            current_set |= cls._extract_A_ord(str(obj := super().__new__(cls, *args, **kwargs)))
        return obj

    if TYPE_CHECKING:

        @overload
        def capitalize(self: LiteralString) -> LiteralString: ...
        @overload
        def capitalize(self) -> Self: ...
    def capitalize(self):
        return self.__class__(super().capitalize())

    if TYPE_CHECKING:

        @overload
        def casefold(self: LiteralString) -> LiteralString: ...
        @overload
        def casefold(self) -> Self: ...
    def casefold(self):
        return self.__class__(super().casefold())

    if TYPE_CHECKING:

        @overload
        def center(self: LiteralString, width: SupportsIndex, fillchar: LiteralString = " ", /) -> LiteralString: ...
        @overload
        def center(self, width: SupportsIndex, fillchar: str = " ", /) -> Self: ...
    def center(self, width, fillchar=" ", /):
        # """
        if hasattr(self, "inline_indices"):
            if (length := len(self)) >= (width := width.__index__()):
                new_indices = self.inline_indices
            else:
                count = (marg := width - length) // 2 + (marg & width & 1)
                new_indices = {i + count: seg for i, seg in self.inline_indices.items()}
            (result := self.__class__(super().center(width, fillchar))).inline_indices = new_indices
            return result
        # """
        return self.__class__(super().center(width, fillchar))

    if TYPE_CHECKING:

        @overload
        def expandtabs(self: LiteralString, tabsize: SupportsIndex = 8) -> LiteralString: ...
        @overload
        def expandtabs(self, tabsize: SupportsIndex = 8) -> Self: ...
    def expandtabs(self, tabsize=8):
        return self.__class__(super().expandtabs(tabsize))

    if TYPE_CHECKING:

        @overload
        def format(self: LiteralString, *args: LiteralString, **kwargs: LiteralString) -> LiteralString: ...
        @overload
        def format(self, *args: object, **kwargs: object) -> Self: ...
    def format(self, *args, **kwargs):
        return self.__class__(super().format(*args, **kwargs))

    def format_map(self, mapping, /) -> Self:
        return self.__class__(super().format_map(mapping))

    if TYPE_CHECKING:

        @overload
        def join(self: LiteralString, iterable: Iterable[LiteralString], /) -> LiteralString: ...
        @overload
        def join(self, iterable: Iterable[str], /) -> Self: ...
    def join(self, iterable):
        return self.__class__(super().join(iterable))

    if TYPE_CHECKING:

        @overload
        def ljust(self: LiteralString, width: SupportsIndex, fillchar: LiteralString = " ", /) -> LiteralString: ...
        @overload
        def ljust(self, width: SupportsIndex, fillchar: str = " ", /) -> Self: ...
    def ljust(self, width, fillchar=" ", /):
        if hasattr(self, "inline_indices"):
            (result := self.__class__(super().ljust(width.__index__(), fillchar))).inline_indices = self.inline_indices
            return result
        return self.__class__(super().ljust(width, fillchar))

    if TYPE_CHECKING:

        @overload
        def lower(self: LiteralString) -> LiteralString: ...
        @overload
        def lower(self) -> Self: ...
    def lower(self):
        return self.__class__(super().lower())

    if TYPE_CHECKING:

        @overload
        def lstrip(self: LiteralString, chars: LiteralString | None = None, /) -> LiteralString: ...
        @overload
        def lstrip(self, chars: str | None = None, /) -> Self: ...
    def lstrip(self, chars=None, /):
        return self.__class__(super().lstrip(chars))

    if TYPE_CHECKING:

        @overload
        def partition(self: LiteralString, sep: LiteralString, /) -> tuple[LiteralString, LiteralString, LiteralString]: ...
        @overload
        def partition(self, sep: str, /) -> tuple[Self, Self, Self]: ...
    def partition(self, sep):
        return tuple(self.__class__(s) for s in super().partition(sep))

    if TYPE_CHECKING:

        @overload
        def replace(
            self: LiteralString, old: LiteralString, new: LiteralString, /, count: SupportsIndex = -1
        ) -> LiteralString: ...
        @overload
        def replace(self, old: str, new: str, /, count: SupportsIndex = -1) -> Self: ...
    def replace(self, old, new, count=-1):
        return self.__class__(super().replace(old, new, count))

    if TYPE_CHECKING:

        @overload
        def removeprefix(self: LiteralString, prefix: LiteralString, /) -> LiteralString: ...
        @overload
        def removeprefix(self, prefix: str, /) -> Self: ...
    def removeprefix(self, prefix):
        return self.__class__(super().removeprefix(prefix))

    if TYPE_CHECKING:

        @overload
        def removesuffix(self: LiteralString, suffix: LiteralString, /) -> LiteralString: ...
        @overload
        def removesuffix(self, suffix: str, /) -> Self: ...
    def removesuffix(self, suffix):
        return self.__class__(super().removesuffix(suffix))

    if TYPE_CHECKING:

        @overload
        def rjust(self: LiteralString, width: SupportsIndex, fillchar: LiteralString = " ", /) -> LiteralString: ...
        @overload
        def rjust(self, width: SupportsIndex, fillchar: str = " ", /) -> Self: ...
    def rjust(self, width, fillchar=" "):
        # """
        if hasattr(self, "inline_indices"):
            count = (width := width.__index__()) - len(self)
            result = self.__class__(super().rjust(width, fillchar))
            result.inline_indices = {i + count: seg for i, seg in self.inline_indices.items()}
            return result
        # """
        return self.__class__(super().rjust(width, fillchar))

    if TYPE_CHECKING:

        @overload
        def rpartition(self: LiteralString, sep: LiteralString, /) -> tuple[LiteralString, LiteralString, LiteralString]: ...
        @overload
        def rpartition(self, sep: str, /) -> tuple[Self, Self, Self]: ...
    def rpartition(self, sep):
        return tuple(self.__class__(s) for s in super().rpartition(sep))

    if TYPE_CHECKING:

        @overload
        def rsplit(
            self: LiteralString, sep: LiteralString | None = None, maxsplit: SupportsIndex = -1
        ) -> list[LiteralString]: ...
        @overload
        def rsplit(self, sep: str | None = None, maxsplit: SupportsIndex = -1) -> list[Self]: ...
    def rsplit(self, sep=None, maxsplit=-1):
        return [self.__class__(s) for s in super().rsplit(sep, maxsplit)]

    if TYPE_CHECKING:

        @overload
        def rstrip(self: LiteralString, chars: LiteralString | None = None, /) -> LiteralString: ...
        @overload
        def rstrip(self, chars: str | None = None, /) -> Self: ...
    def rstrip(self, chars=None):
        return self.__class__(super().rstrip(chars))

    if TYPE_CHECKING:

        @overload
        def split(
            self: LiteralString, sep: LiteralString | None = None, maxsplit: SupportsIndex = -1
        ) -> list[LiteralString]: ...
        @overload
        def split(self, sep: str | None = None, maxsplit: SupportsIndex = -1) -> list[Self]: ...
    def split(self, sep=None, maxsplit=-1):
        return [self.__class__(s) for s in super().split(sep, maxsplit)]

    if TYPE_CHECKING:

        @overload
        def splitlines(self: LiteralString, keepends: bool = False) -> list[LiteralString]: ...
        @overload
        def splitlines(self, keepends: bool = False) -> list[Self]: ...
    def splitlines(self, keepends=False):
        return [self.__class__(s) for s in super().splitlines(keepends)]

    if TYPE_CHECKING:

        @overload
        def strip(self: LiteralString, chars: LiteralString | None = None, /) -> LiteralString: ...
        @overload
        def strip(self, chars: str | None = None, /) -> Self: ...
    def strip(self, chars=None):
        return self.__class__(super().strip(chars))

    if TYPE_CHECKING:

        @overload
        def swapcase(self: LiteralString) -> LiteralString: ...
        @overload
        def swapcase(self) -> Self: ...
    def swapcase(self):
        return self.__class__(super().swapcase())

    if TYPE_CHECKING:

        @overload
        def title(self: LiteralString) -> LiteralString: ...
        @overload
        def title(self) -> Self: ...
    def title(self):
        return self.__class__(super().title())

    def translate(self, table, /) -> Self:
        return self.__class__(super().translate(table))

    if TYPE_CHECKING:

        @overload
        def upper(self: LiteralString) -> LiteralString: ...
        @overload
        def upper(self) -> Self: ...
    def upper(self):
        return self.__class__(super().upper())

    if TYPE_CHECKING:

        @overload
        def zfill(self: LiteralString, width: SupportsIndex, /) -> LiteralString: ...
        @overload
        def zfill(self, width: SupportsIndex, /) -> Self: ...
    def zfill(self, width):
        # """
        if hasattr(self, "inline_indices"):
            count = (width := width.__index__()) - len(self)
            result = self.__class__(super().zfill(width))
            result.inline_indices = {i + count: seg for i, seg in self.inline_indices.items()}
            return result
        # """
        return self.__class__(super().zfill(width))

    if TYPE_CHECKING:

        @overload
        def __add__(self: LiteralString, value: LiteralString, /) -> LiteralString: ...
        @overload
        def __add__(self, value: str, /) -> Self: ...
    def __add__(self, value):
        if hasattr(self, "inline_indices"):
            new_indices: dict = self.inline_indices
        else:
            new_indices: dict = value.inline_indices
        if hasattr(value, "inline_indices"):
            count = len(self)
            for i, seg in value.inline_indices.items():
                new_indices[i + count] = seg
        (result := self.__class__(super().__add__(value))).inline_indices = new_indices
        return result

    if TYPE_CHECKING:

        @overload
        def __getitem__(self: LiteralString, key: SupportsIndex | slice, /) -> LiteralString: ...
        @overload
        def __getitem__(self, key: SupportsIndex | slice, /) -> Self: ...
    def __getitem__(self, key):
        # """
        if not (indices := getattr(self, "inline_indices", None)):
            # """
            return self.__class__(super().__getitem__(key))
        new_indices = {}
        """
            if isinstance(key, slice):
                count = 0
                for k in range(*key.indices(len(self))):
                    if seg := indices.get(k):
                        new_indices[count] = seg
                    count += 1
            elif (index := getattr(key, "__index__", None)) is not None and (seg := indices.get(index())):
            """
        if (index := getattr(key, "__index__", None)) is not None and (seg := indices.get(index())):
            new_indices[0] = seg
        result = self.__class__(super().__getitem__(key))
        if new_indices:
            result.inline_indices = new_indices
        return result

    if TYPE_CHECKING:

        @overload
        def __iter__(self: LiteralString) -> Iterator[LiteralString]: ...
        @overload
        def __iter__(self) -> Iterator[Self]: ...
    def __iter__(self):
        if indices := getattr(self, "inline_indices", None):
            for i, char in enumerate(super().__iter__()):
                result = self.__class__(char)
                if seg := indices.get(i):
                    result.inline_indices = {0: seg}
                yield result
        else:
            for char in super().__iter__():
                yield self.__class__(char)

    if TYPE_CHECKING:

        @overload
        def __mod__(self: LiteralString, value: LiteralString | tuple[LiteralString, ...], /) -> LiteralString: ...
        @overload
        def __mod__(self, value, /) -> Self: ...
    def __mod__(self, value):
        return self.__class__(super().__mod__(value))

    if TYPE_CHECKING:

        @overload
        def __mul__(self: LiteralString, value: SupportsIndex, /) -> LiteralString: ...
        @overload
        def __mul__(self, value: SupportsIndex, /) -> Self: ...
    def __mul__(self, value):
        if hasattr(self, "inline_indices"):
            l = len(self)
            result = self.__class__(super().__mul__((value := value.__index__())))
            result.inline_indices = {i + j * l: seg for i, seg in self.inline_indices.items() for j in range(value)}
            return result
        return self.__class__(super().__mul__(value))

    if TYPE_CHECKING:

        @overload
        def __rmul__(self: LiteralString, value: SupportsIndex, /) -> LiteralString: ...
        @overload
        def __rmul__(self, value: SupportsIndex, /) -> Self: ...
    def __rmul__(self, value):
        if hasattr(self, "inline_indices"):
            l = len(self)
            result = self.__class__(super().__rmul__((value := value.__index__())))
            result.inline_indices = {i + j * l: seg for i, seg in self.inline_indices.items() for j in range(value)}
            return result
        return self.__class__(super().__rmul__(value))

    def __format__(self, format_spec: str, /) -> Self:
        return self.__class__(super().__format__(format_spec))

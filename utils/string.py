import re
from collections.abc import Iterable, Iterator
from contextvars import ContextVar
from multiprocessing import current_process
from random import getrandbits
from re import compile
from typing import Any, Literal, LiteralString, Self, SupportsIndex, overload

from core.i18n import _
from models.msg import Text

# import numpy as np


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


# region aha code
def escape_aha(text: str):
    """转义 Aha 码中的少数特殊字符为 HTML 实体"""
    return text.translate(str.maketrans({"&": "&amp;", "[": "&#91;", "]": "&#93;", ",": "&#44;"}))


def unescape_aha(text: str):
    """反转义 Aha 码"""
    return text.replace("&amp;", "&").replace("&#91;", "[").replace("&#93;", "]").replace("&#44;", ",")


AHA_CODE_PATTERN = compile(r"\[Aha:([^,\]]+)(?:,([^\]]+))?\]")


def aha_code2dict_list(string, pattern=AHA_CODE_PATTERN) -> list[dict[Literal["type", "data"], Any]]:
    """将 Aha 码字符串解析为字典列表"""
    result = []
    last_pos = 0
    # 遍历所有匹配的 Aha 码
    for match in pattern.finditer(string):
        # 处理 Aha 码之前的文本
        if text_before := string[last_pos : match.start()]:
            result.append(aha_code2dict_list(text_before, pattern))

        # 解析 Aha 码参数
        params = {}
        for param in (match[2] or "").split(","):
            if "=" in param:
                key, value = param.split("=", 1)
                params[key] = aha_code2dict_list(value, pattern)

        result.append({"type": match[1].lower(), "data": params})
        last_pos = match.end()

    # 处理最后一个 Aha 码之后的文本
    if text_after := string[last_pos:]:
        result.append(aha_code2dict_list(text_after, pattern))

    return result


def parse_aha_code(string):
    """将 Aha 码字符串解析为消息数组"""
    from models.msg import MessageChain

    chain = MessageChain()
    last_pos = 0
    # 遍历所有匹配的 Aha 码
    for match in AHA_CODE_PATTERN.finditer(string):
        # 处理 Aha 码之前的文本
        if text_before := string[last_pos : match.start()]:
            chain.append(unescape_aha(text_before))

        # 解析 Aha 码参数
        params = {}
        for param in (match[2] or "").split(","):
            if "=" in param:
                key, value = param.split("=", 1)
                params[key] = unescape_aha(value)

        chain.append(MessageChain.get_seg_class(match[1])(**params))
        last_pos = match.end()

    # 处理最后一个 Aha 码之后的文本
    if text_after := string[last_pos:]:
        chain.append(unescape_aha(text_after))

    return chain


def charclass_escape(s):
    """只转义正则字符集中有特殊含义的字符，需要传入方括号（不包括）之间的整个字符串。"""
    s = s.replace("\\", "\\\\").replace("]", "\\]")
    if s.startswith("^"):
        s = "\\" + s
    if len(s) > 1 and "-" in s[1:-1]:
        s = "".join("\\-" if char == "-" and 0 < i < len(s) - 1 else char for i, char in enumerate(s))
    return s


# endregion
"""
def contains_pua(s: str):
    if not s:
        return False
    if len(s) <= 100:
        for ch in s:
            if 0xE000 <= (cp := ord(ch)) <= 0xF8FF or 0xF0000 <= cp <= 0xFFFFD or 0x100000 <= cp <= 0x10FFFD:
                return True
    else:
        arr = np.frombuffer(s.encode("utf-32-le"), dtype=np.uint32)
        return bool(
            np.any(
                ((arr >= 0xE000) & (arr <= 0xF8FF))
                | ((arr >= 0xF0000) & (arr <= 0xFFFFD))
                | ((arr >= 0x100000) & (arr <= 0x10FFFD))
            )
        )
"""


class InlineStr[T](str):
    csim: ContextVar[dict] = ContextVar("aha_str_inline_map", default=None)
    csiK: ContextVar[list] = ContextVar("aha_str_inline_Ks", default=None)

    if IS_MAINPROC and cfg.memory_level == "high":
        _PUA_CHARS = [None] * 137468

        for i in range(65534):
            _PUA_CHARS[i] = chr(0xF0000 + i)
        for i in range(65534, 131068):
            _PUA_CHARS[i] = chr(0x100000 + (i - 65534))
        for i in range(131068, 131072):
            _PUA_CHARS[i] = chr(0xE100 + (i - 131068))

        @classmethod
        def get_pua_char(cls):
            return cls._PUA_CHARS[cls.permute() % 137468]

    else:

        @classmethod
        def get_pua_char(cls):
            if (num := cls.permute()) < 65534:
                return chr(0xF0000 + num)
            elif num < 131068:
                return chr(0x100000 + (num - 65534))
            else:
                return chr(0xE100 + (num - 131068))

    @classmethod
    def permute(cls) -> int:
        if Ks := cls.csiK.get():
            K0, K1 = Ks
        else:
            seed = getrandbits(30)
            cls.csiK.set((K0 := seed ^ 461845907, K1 := seed ^ 433494437))
        mixed = (len(cls.csim.get()) + 1) * 403  # 403: 16777619 & ((2^30-1) // 131072)

        L = mixed >> 9  # high 8 bits
        R = mixed & 0x1FF  # low 9 bits
        L, R = R, L ^ (((R ^ K0) * 1073741789) & 0xFF)  # R width 8 bits
        L, R = R, L ^ (((R ^ K1) * 1073741047) & 0x1FF)  # R width 9 bits
        L, R = R, L ^ (((R ^ K0) * 1073740781) & 0xFF)
        L, R = R, L ^ (((R ^ K1) * 1073741173) & 0x1FF)
        L, R = R, L ^ (((R ^ K0) * 1073741621) & 0xFF)
        L, R = R, L ^ (((R ^ K1) * 1073741287) & 0x1FF)
        L, R = R, L ^ (((R ^ K0) * 1073741783) & 0xFF)
        L, R = R, L ^ (((R ^ K1) * 1073741371) & 0x1FF)
        return (L << 9) | R

    @classmethod
    def from_iterable[T](cls, obj: Iterable[T], mapping: dict = None) -> Self[T]:
        """
        Args:
            mapping: 将映射写入字典，键为字符串，值为被内联的对象。
        """
        result = []
        result_len = 0
        inline_indices = {}
        if (current_map := cls.csim.get()) is None:
            cls.csim.set(current_map := {})
        if mapping is None:
            for seg in obj:
                if isinstance(seg, Text):
                    result.append(seg.text)
                    result_len += len(seg.text)
                elif isinstance(seg, str):
                    result.append(seg)
                    result_len += len(seg)
                else:
                    current_map.setdefault(char := cls.get_pua_char(), seg)
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
                    current_map.setdefault(char := cls.get_pua_char(), seg)
                    mapping.setdefault(char, seg)
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

        if not mapping and not (mapping := self.csim.get()):
            return [str(self)]

        if len(self) < 100:
            # 短的用传统逻辑
            start = 0  # 当前字符段的起始位置
            i = 0  # 当前扫描位置
            n = len(self)
            separator_chars = set(mapping)

            while i < n:
                if (char := self[i]) in separator_chars:
                    if i > start:
                        result.append(self[start:i])
                    result.append(mapping[char])
                    start = i + 1
                i += 1

            if start < n:
                result.append(self[start:])
        else:
            # 长的用正则
            pattern = re.compile(f"([{"".join(mapping)}])")
            last_end = 0
            for match in pattern.finditer(self):
                if match.start() > last_end:
                    result.append(self[last_end : match.start()])
                result.append(mapping[match[0]])
                last_end = match.end()

            if last_end < len(self):
                result.append(self[last_end:])
        return result

    @overload
    def capitalize(self: LiteralString) -> LiteralString: ...
    @overload
    def capitalize(self) -> Self: ...
    def capitalize(self):
        return self.__class__(super().capitalize())

    @overload
    def casefold(self: LiteralString) -> LiteralString: ...
    @overload
    def casefold(self) -> Self: ...
    def casefold(self):
        return self.__class__(super().casefold())

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

    @overload
    def expandtabs(self: LiteralString, tabsize: SupportsIndex = 8) -> LiteralString: ...
    @overload
    def expandtabs(self, tabsize: SupportsIndex = 8) -> Self: ...
    def expandtabs(self, tabsize=8):
        return self.__class__(super().expandtabs(tabsize))

    @overload
    def format(self: LiteralString, *args: LiteralString, **kwargs: LiteralString) -> LiteralString: ...
    @overload
    def format(self, *args: object, **kwargs: object) -> Self: ...
    def format(self, *args, **kwargs):
        return self.__class__(super().format(*args, **kwargs))

    def format_map(self, mapping: Any, /) -> Self:
        return self.__class__(super().format_map(mapping))

    @overload
    def join(self: LiteralString, iterable: Iterable[LiteralString], /) -> LiteralString: ...
    @overload
    def join(self, iterable: Iterable[str], /) -> Self: ...
    def join(self, iterable):
        return self.__class__(super().join(iterable))

    @overload
    def ljust(self: LiteralString, width: SupportsIndex, fillchar: LiteralString = " ", /) -> LiteralString: ...
    @overload
    def ljust(self, width: SupportsIndex, fillchar: str = " ", /) -> Self: ...
    def ljust(self, width, fillchar=" ", /):
        if hasattr(self, "inline_indices"):
            (result := self.__class__(super().ljust(width.__index__(), fillchar))).inline_indices = self.inline_indices
            return result
        return self.__class__(super().ljust(width, fillchar))

    @overload
    def lower(self: LiteralString) -> LiteralString: ...
    @overload
    def lower(self) -> Self: ...
    def lower(self):
        return self.__class__(super().lower())

    @overload
    def lstrip(self: LiteralString, chars: LiteralString | None = None, /) -> LiteralString: ...
    @overload
    def lstrip(self, chars: str | None = None, /) -> Self: ...
    def lstrip(self, chars=None, /):
        return self.__class__(super().lstrip(chars))

    @overload
    def partition(self: LiteralString, sep: LiteralString, /) -> tuple[LiteralString, LiteralString, LiteralString]: ...
    @overload
    def partition(self, sep: str, /) -> tuple[Self, Self, Self]: ...
    def partition(self, sep):
        return tuple(self.__class__(s) for s in super().partition(sep))

    @overload
    def replace(self: LiteralString, old: LiteralString, new: LiteralString, /, count: SupportsIndex = -1) -> LiteralString: ...
    @overload
    def replace(self, old: str, new: str, /, count: SupportsIndex = -1) -> Self: ...
    def replace(self, old, new, count=-1):
        return self.__class__(super().replace(old, new, count))

    @overload
    def removeprefix(self: LiteralString, prefix: LiteralString, /) -> LiteralString: ...
    @overload
    def removeprefix(self, prefix: str, /) -> Self: ...
    def removeprefix(self, prefix):
        return self.__class__(super().removeprefix(prefix))

    @overload
    def removesuffix(self: LiteralString, suffix: LiteralString, /) -> LiteralString: ...
    @overload
    def removesuffix(self, suffix: str, /) -> Self: ...
    def removesuffix(self, suffix):
        return self.__class__(super().removesuffix(suffix))

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

    @overload
    def rpartition(self: LiteralString, sep: LiteralString, /) -> tuple[LiteralString, LiteralString, LiteralString]: ...
    @overload
    def rpartition(self, sep: str, /) -> tuple[Self, Self, Self]: ...
    def rpartition(self, sep):
        return tuple(self.__class__(s) for s in super().rpartition(sep))

    @overload
    def rsplit(self: LiteralString, sep: LiteralString | None = None, maxsplit: SupportsIndex = -1) -> list[LiteralString]: ...
    @overload
    def rsplit(self, sep: str | None = None, maxsplit: SupportsIndex = -1) -> list[Self]: ...
    def rsplit(self, sep=None, maxsplit=-1):
        return [self.__class__(s) for s in super().rsplit(sep, maxsplit)]

    @overload
    def rstrip(self: LiteralString, chars: LiteralString | None = None, /) -> LiteralString: ...
    @overload
    def rstrip(self, chars: str | None = None, /) -> Self: ...
    def rstrip(self, chars=None):
        return self.__class__(super().rstrip(chars))

    @overload
    def split(self: LiteralString, sep: LiteralString | None = None, maxsplit: SupportsIndex = -1) -> list[LiteralString]: ...
    @overload
    def split(self, sep: str | None = None, maxsplit: SupportsIndex = -1) -> list[Self]: ...
    def split(self, sep=None, maxsplit=-1):
        return [self.__class__(s) for s in super().split(sep, maxsplit)]

    @overload
    def splitlines(self: LiteralString, keepends: bool = False) -> list[LiteralString]: ...
    @overload
    def splitlines(self, keepends: bool = False) -> list[Self]: ...
    def splitlines(self, keepends=False):
        return [self.__class__(s) for s in super().splitlines(keepends)]

    @overload
    def strip(self: LiteralString, chars: LiteralString | None = None, /) -> LiteralString: ...
    @overload
    def strip(self, chars: str | None = None, /) -> Self: ...
    def strip(self, chars=None):
        return self.__class__(super().strip(chars))

    @overload
    def swapcase(self: LiteralString) -> LiteralString: ...
    @overload
    def swapcase(self) -> Self: ...
    def swapcase(self):
        return self.__class__(super().swapcase())

    @overload
    def title(self: LiteralString) -> LiteralString: ...
    @overload
    def title(self) -> Self: ...
    def title(self):
        return self.__class__(super().title())

    def translate(self, table: Any, /) -> Self:
        return self.__class__(super().translate(table))

    @overload
    def upper(self: LiteralString) -> LiteralString: ...
    @overload
    def upper(self) -> Self: ...
    def upper(self):
        return self.__class__(super().upper())

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

    @overload
    def __getitem__(self: LiteralString, key: SupportsIndex | slice, /) -> LiteralString: ...
    @overload
    def __getitem__(self, key: SupportsIndex | slice, /) -> Self: ...
    def __getitem__(self, key):
        # """
        if indices := getattr(self, "inline_indices", None):
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
        # """
        return self.__class__(super().__getitem__(key))

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

    @overload
    def __mod__(self: LiteralString, value: LiteralString | tuple[LiteralString, ...], /) -> LiteralString: ...
    @overload
    def __mod__(self, value: Any, /) -> Self: ...
    def __mod__(self, value):
        return self.__class__(super().__mod__(value))

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

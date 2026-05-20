import sys
from array import array
from collections import defaultdict
from collections.abc import Callable, Generator, Iterable, Sequence
from typing import TYPE_CHECKING, Literal, Self, SupportsIndex, overload

if TYPE_CHECKING:
    from _typeshed import SupportsKeysAndGetItem


def find_first_instance(seq: Sequence, type_: type, start_index=0, end_index: int = None):
    n = len(seq)
    if start_index < 0:
        start_index = max(n + start_index, 0)
    if end_index is None:
        end_index = n
    elif end_index < 0:
        end_index = max(n + end_index, 0)
    else:
        end_index = min(end_index, n)
    if start_index >= end_index or start_index >= n:
        return (None, None)
    for i in range(start_index, end_index):
        if isinstance(item := seq[i], type_):
            return i, item
    return (None, None)


def is_subsequence(a: Sequence, b: Sequence):
    """判断a的所有元素是否按顺序包含在b中"""
    i, j = 0, 0
    len_a, len_b = len(a), len(b)
    while i < len_a and j < len_b:
        if a[i] == b[j]:
            i += 1
        j += 1
    return i == len_a


def is_prefix(a: Sequence, b: Sequence):
    return len(a) >= len(b) and a[: len(b)] == b


def is_suffix(a: Sequence, b: Sequence):
    return len(a) >= len(b) and a[-len(b) :] == b


def get_item_by_index[KT, VT](d: dict[KT, VT], index):
    for i, (k, v) in enumerate(d.items()):
        if i == index:
            return (k, v)
    raise IndexError("dictionary index out of range")


class SetSeqMixin[_T]:
    __mul__ = __rmul__ = __imul__ = __add__ = __iadd__ = __setitem__ = None

    def append(self, object: _T, /):
        if object not in self._set:
            super().append(object)
            self._set.add(object)

    def extend(self, iterable: Iterable[_T], /):
        for item in iterable:
            self.append(item)

    def insert(self, index: SupportsIndex, object: _T, /):
        if object not in self._set:
            super().insert(index, object)
            self._set.add(object)

    def __delitem__(self, key: SupportsIndex | slice, /):
        if isinstance(key, slice):
            for item in self[key]:
                self._set.remove(item)
        else:
            self._set.remove(self[key])
        super().__delitem__(key)

    def pop(self, index: SupportsIndex = -1, /) -> _T:
        self._set.remove(item := super().pop(index))
        return item

    def remove(self, value: _T, /):
        super().remove(value)
        self._set.remove(value)

    def __contains__(self, value: object, /):
        return value in self._set

    def isdisjoint(self, s: Iterable, /) -> bool:
        return self._set.isdisjoint(s)

    def issubset(self, s: Iterable, /) -> bool:
        return self._set.issubset(s)

    def issuperset(self, s: Iterable, /) -> bool:
        return self._set.issuperset(s)

    def count(self, value: _T, /):
        return 1 if value in self._set else 0

    def index(self, value: _T, start: SupportsIndex = 0, stop: SupportsIndex = sys.maxsize, /):
        if value not in self._set:
            raise ValueError(f"{value} not in sequence")
        return super().index(value, start, stop)


class SetArray[_T](SetSeqMixin[_T], array[_T]):
    """支持O(1)存在性检查的 array"""

    if TYPE_CHECKING:

        @overload
        def __new__(
            cls: type[SetArray[int]],
            typecode: Literal["b", "B", "h", "H", "i", "I", "l", "L", "q", "Q"],
            initializer: bytes | bytearray | Iterable[int] = b"",
            /,
        ) -> SetArray[int]: ...
        @overload
        def __new__(
            cls: type[SetArray[float]], typecode: Literal["f", "d"], initializer: bytes | bytearray | Iterable[float] = b"", /
        ) -> SetArray[float]: ...
        @overload
        def __new__(
            cls: type[SetArray[str]], typecode: Literal["w"], initializer: bytes | bytearray | Iterable[str] = b"", /
        ) -> SetArray[str]: ...
        @overload
        def __new__(cls, typecode: str, initializer: Iterable[_T], /) -> Self: ...
        @overload
        def __new__(cls, typecode: str, initializer: bytes | bytearray = b"", /) -> Self: ...
    def __new__(cls, typecode, initializer=b"", /):
        obj = super().__new__(cls, typecode, initializer := set(initializer))
        obj._set = initializer
        return obj

    __buffer__ = __release_buffer__ = itemsize = buffer_info = byteswap = frombytes = fromfile = fromlist = fromunicode = None

    def __copy__(self):
        return self.__class__(self.typecode, self)

    def __deepcopy__(self, unused, /):
        return self.__class__(self.typecode, super(array, self).__deepcopy__(unused))


class SetList[_T](SetSeqMixin[_T], list[_T]):
    """支持O(1)存在性检查的 list"""

    def __init__(self, iterable: Iterable[_T] = None, /):
        if iterable is None:
            self._set = set()
        else:
            self._set = iterable = set(iterable)
        super().__init__(iterable)

    def copy(self):
        return self.__class__(self)


class IndexedDictMixin[_KT, _VT]:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._keys: list[_KT] = list(self)

    def __setitem__(self, key: _KT, value: _VT):
        if key not in self:
            self._keys.append(key)
        super().__setitem__(key, value)

    def __delitem__(self, key: _KT):
        super().__delitem__(key)
        self._keys.remove(key)

    def clear(self):
        super().clear()
        self._keys.clear()

    if TYPE_CHECKING:

        @overload
        def pop(self, key: _KT, /) -> _VT: ...
        @overload
        def pop(self, key: _KT, default: _VT, /) -> _VT: ...
        @overload
        def pop[_T](self, key: _KT, default: _T, /) -> _VT | _T: ...
    def pop(self, key, default=None):
        if key in self:
            self._keys.remove(key)
        return super().pop(key, default)

    def popitem(self) -> _VT:
        self._keys.remove((result := super().popitem())[0])
        return result

    update = fromkeys = __or__ = __ror__ = __ior__ = None

    def key_at(self, index: SupportsIndex):
        return self._keys[index]

    def value_at(self, index: SupportsIndex) -> _VT:
        return self[self._keys[index]]

    def item_at(self, index: SupportsIndex) -> tuple[_KT, _VT]:
        return (k := self._keys[index]), self[k]

    def set_value_at(self, index: SupportsIndex, value: _VT):
        self[self._keys[index]] = value

    def pop_at(self, index: SupportsIndex) -> tuple[_KT, _VT]:
        return (key := self._keys.pop(index)), super().pop(key)

    def index(self, key: _KT, start: SupportsIndex = 0, stop: SupportsIndex = sys.maxsize, /):
        return self._keys.index(key, start, stop)

    def copy(self):
        return self.__class__(self)

    def safe_iter_keys(self):
        return iter(self._keys)

    def safe_iter_values(self) -> Generator[_VT, None, None]:
        return (self[key] for key in self._keys)

    def safe_iter_items(self) -> Generator[tuple[_KT, _VT], None, None]:
        return ((key, self[key]) for key in self._keys)


class IndexedDict[_KT, _VT](IndexedDictMixin[_KT, _VT], dict[_KT, _VT]):
    if TYPE_CHECKING:

        @overload
        def __init__(self) -> None: ...
        @overload
        def __init__(self: dict[str, _VT], **kwargs: _VT) -> None: ...
        @overload
        def __init__(self, map: SupportsKeysAndGetItem[_KT, _VT], /) -> None: ...
        @overload
        def __init__(self: dict[str, _VT], map: SupportsKeysAndGetItem[str, _VT], /, **kwargs: _VT) -> None: ...
        @overload
        def __init__(self, iterable: Iterable[tuple[_KT, _VT]], /) -> None: ...
        @overload
        def __init__(self: dict[str, _VT], iterable: Iterable[tuple[str, _VT]], /, **kwargs: _VT) -> None: ...
        @overload
        def __init__(self: dict[str, str], iterable: Iterable[list[str]], /) -> None: ...
        @overload
        def __init__(self: dict[bytes, bytes], iterable: Iterable[list[bytes]], /) -> None: ...


class DefaultIndexedDict[_KT, _VT](IndexedDictMixin[_KT, _VT], defaultdict[_KT, _VT]):
    if TYPE_CHECKING:

        @overload
        def __init__(self) -> None: ...
        @overload
        def __init__(self: defaultdict[str, _VT], **kwargs: _VT) -> None: ...
        @overload
        def __init__(self, default_factory: Callable[[], _VT] | None, /) -> None: ...
        @overload
        def __init__(self: defaultdict[str, _VT], default_factory: Callable[[], _VT] | None, /, **kwargs: _VT) -> None: ...
        @overload
        def __init__(self, default_factory: Callable[[], _VT] | None, map: SupportsKeysAndGetItem[_KT, _VT], /) -> None: ...
        @overload
        def __init__(
            self: defaultdict[str, _VT],
            default_factory: Callable[[], _VT] | None,
            map: SupportsKeysAndGetItem[str, _VT],
            /,
            **kwargs: _VT,
        ) -> None: ...
        @overload
        def __init__(self, default_factory: Callable[[], _VT] | None, iterable: Iterable[tuple[_KT, _VT]], /) -> None: ...
        @overload
        def __init__(
            self: defaultdict[str, _VT],
            default_factory: Callable[[], _VT] | None,
            iterable: Iterable[tuple[str, _VT]],
            /,
            **kwargs: _VT,
        ) -> None: ...

    def __missing__(self, key: _KT, /) -> _VT:
        self._keys.append(key)
        return super().__missing__(key)

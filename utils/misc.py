import re
import sys
from array import array
from collections.abc import Callable, Iterable, Sequence
from contextlib import suppress
from decimal import ROUND_HALF_UP, Decimal
from types import FunctionType
from typing import TYPE_CHECKING, Any, Literal, Self, SupportsIndex, overload

from models.exc import ExactlyOneTruthyValueError

if TYPE_CHECKING:
    from _typeshed import SupportsKeysAndGetItem

AHA_MODULE_PATTERN = re.compile(r"^[^.]*modules\.([^.]+)")
FULL_AHA_MODULE_PATTERN = re.compile(r"^([^.]*modules\.[^.]+)")


def caller_aha_module(level: int = 2, pattern=FULL_AHA_MODULE_PATTERN) -> str | None:
    return match[1] if (match := pattern.match(sys._getframe(level).f_globals.get("__name__", ""))) else None


def round_decimal(num: Decimal, digits=2):
    return num.quantize(Decimal(f'0.{"0" * digits}'), rounding=ROUND_HALF_UP).normalize()


def check_single_true(raise_exc=True, *args, **kwargs):
    """要求参数中恰好有一个值的布尔值为True。

    Args:
        raise_exc: 如果为True，则在条件不满足时抛出异常；否则返回False。
    """
    all_values = args + tuple(kwargs.values())
    if len(v for v in all_values if v) == 1:
        return True

    if raise_exc:
        if args:
            error_msg = f"Expected exactly one truthy value, but got the values: [{', '.join(repr(v) for v in all_values)}]"
        else:
            error_msg = f"Expected exactly one truthy value, but got the keyword arguments: {', '.join(f"{k}={v!r}" for k, v in kwargs.items())}"
        raise ExactlyOneTruthyValueError(error_msg)
    return False


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
    return len(b) >= len(a) and b[: len(a)] == a


def is_suffix(a: Sequence, b: Sequence):
    return len(a) >= len(b) and b[-len(a) :] == a


def is_instance_method(method):
    """检查方法对象是否是类方法或实例方法"""

    # 绑定方法
    if getattr(method, "__self__", None) is not None:
        return True

    # 类中定义
    with suppress(AttributeError, KeyError, IndexError):
        if (
            isinstance(method, FunctionType)
            and "." in method.__qualname__
            and not isinstance(method.__globals__[method.__qualname__.split(".")[-2]].__dict__[method.__name__], staticmethod)
        ):
            return True

    return False


def get_true_func(obj):
    return func if (func := getattr(obj := getattr(obj, "__func__", obj), "func", None)) else obj


def get_posarg_count(func: Callable[..., Any]):
    """获取函数的位置参数个数，不包含可变参数和self/cls"""
    return func.__code__.co_argcount - 1 if is_instance_method(func := get_true_func(func)) else func.__code__.co_argcount


def get_arg_names(func: Callable[..., Any]):
    """获取函数的所有参数名，不包含可变参数和self/cls"""
    code = get_true_func(func := get_true_func(func)).__code__
    names = list((all_arg_names := code.co_varnames)[: (arg_count := code.co_argcount)])
    names.extend(all_arg_names[arg_count : arg_count + code.co_kwonlyargcount])
    if is_instance_method(func):
        drops = {"self", "cls"}
        names = [n for n in names if n not in drops]
    return names


def get_item_by_index(d, index):
    for i, (k, v) in enumerate(d.items()):
        if i == index:
            return (k, v)
    raise IndexError("dictionary index out of range")


def uninstall_module(module_name):
    modnames = [modname for modname in list(sys.modules) if modname.startswith(f"{module_name}.")]
    modnames.sort(key=lambda name: name.count("."), reverse=True)
    for modname in modnames:
        del sys.modules[modname]


class SetArray[_T](array):
    """基于集合实现的array，支持O(1)存在性检查"""

    @overload
    def __new__(
        cls: type[SetArray[int]], typecode: Literal["b", "B", "h", "H", "i", "I", "l", "L", "q", "Q"], initializer: bytes | bytearray | Iterable[int] = b"", /
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
        if isinstance(initializer, SetArray):
            raise NotImplementedError
        obj = super().__new__(cls, typecode, seen := set(initializer))
        obj._set = seen
        return obj

    __mul__ = __rmul__ = __imul__ = __add__ = __iadd__ = __buffer__ = __release_buffer__ = itemsize = buffer_info = byteswap = (
        frombytes
    ) = fromfile = fromlist = fromunicode = __setitem__ = None

    def append(self, v: _T, /):
        if v not in self._set:
            super().append(v)
            self._set.add(v)

    def extend(self, bb: Iterable[_T], /):
        for item in bb:
            self.append(item)

    def insert(self, i: int, v: _T, /):
        if v not in self._set:
            super().insert(i, v)
            self._set.add(v)

    def __delitem__(self, key: SupportsIndex | slice, /):
        if isinstance(key, slice):
            for item in self[key]:
                self._set.remove(item)
        else:
            self._set.remove(self[key])
        super().__delitem__(key)

    def pop(self, i: int = -1, /) -> _T:
        self._set.remove(item := super().pop(i))
        return item

    def remove(self, v: _T, /):
        super().remove(v)
        self._set.remove(v)

    def __contains__(self, value: object, /):
        return value in self._set

    def isdisjoint(self, s: Iterable, /) -> bool:
        return self._set.isdisjoint(s)

    def issubset(self, s: Iterable, /) -> bool:
        return self._set.issubset(s)

    def issuperset(self, s: Iterable, /) -> bool:
        return self._set.issuperset(s)

    def count(self, v: _T, /):
        return 1 if v in self._set else 0

    def index(self, v: _T, start: int = 0, stop: int = sys.maxsize, /):
        if v not in self._set:
            raise ValueError(f"{v} not in array")
        return super().index(v, start, stop)

    def __copy__(self):
        return self.__class__(self.typecode, self)

    def __deepcopy__(self, unused, /):
        return self.__copy__()

    def __le__(self, value: array[_T], /) -> bool:
        if isinstance(value, SetArray):
            return self._set <= value._set
        return super().__le__(value)

    def __lt__(self, value: array[_T], /) -> bool:
        if isinstance(value, SetArray):
            return self._set < value._set
        return super().__lt__(value)

    def __ge__(self, value: array[_T], /) -> bool:
        if isinstance(value, SetArray):
            return self._set >= value._set
        return super().__ge__(value)

    def __gt__(self, value: SetArray[_T], /) -> bool:
        if isinstance(value, SetArray):
            return self._set > value._set
        return super().__gt__(value)


class IndexedDict[_KT, _VT](dict[_KT, _VT]):
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._keys = list(iter(self))

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

    def popitem(self):
        self._keys.remove((result := super().popitem())[0])
        return result

    update =  fromkeys = __or__ = __ror__ = __ior__ = None

    def key_at(self, index: SupportsIndex):
        return self._keys[index]

    def value_at(self, index: SupportsIndex):
        return self[self._keys[index]]

    def item_at(self, index: SupportsIndex):
        return (k := self._keys[index]), self[k]

    def set_value_at(self, index: SupportsIndex, value: _VT):
        self[self._keys[index]] = value

    def pop_at(self, index: SupportsIndex):
        return (key := self._keys.pop(index)), super().pop(key)

    def index(self, value: _KT, start: SupportsIndex = 0, stop: SupportsIndex = sys.maxsize, /):
        return self._keys.index(value, start, stop)

    def copy(self):
        return IndexedDict(self)

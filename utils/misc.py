import re
from collections.abc import Callable, Sequence
from contextlib import suppress
from decimal import ROUND_HALF_UP, Decimal
from sys import _getframe
import sys
from types import FunctionType
from typing import Any

from models.exc import ExactlyOneTruthyValueError


MODULE_PATTERN = re.compile(r"^[^.]*modules\.([^.]+)")
FULL_MODULE_PATTERN = re.compile(r"^([^.]*modules\.[^.]+)")


def caller_module(level: int = 2, pattern=FULL_MODULE_PATTERN) -> str | None:
    return match[1] if (match := pattern.match(_getframe(level).f_globals.get("__name__", ""))) else None


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


def get_arg_count(func: Callable[..., Any]):
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

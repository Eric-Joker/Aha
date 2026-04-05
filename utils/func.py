from collections.abc import Callable
from contextlib import suppress
from types import FunctionType


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


def get_true_func(obj) -> Callable:
    return func if (func := getattr(obj := getattr(obj, "__func__", obj), "func", None)) else obj


def get_posarg_count(func: Callable):
    """获取函数的位置参数个数，不包含可变参数和self/cls"""
    return func.__code__.co_argcount - 1 if is_instance_method(func := get_true_func(func)) else func.__code__.co_argcount


def get_arg_names(func: Callable):
    """获取函数的所有参数名，不包含可变参数和self/cls"""
    code = get_true_func(func := get_true_func(func)).__code__
    names = list((all_arg_names := code.co_varnames)[: (arg_count := code.co_argcount)])
    names.extend(all_arg_names[arg_count : arg_count + code.co_kwonlyargcount])
    if is_instance_method(func):
        first = {"self", "cls"}
        for i in range(len(names) - 1, -1, -1):
            if names[i] in first:
                del names[i]
    return names


def get_kwonlyarg_count(func: Callable):
    return get_true_func(func).__code__.co_kwonlyargcount


from collections.abc import Callable
from functools import partial
from logging import getLogger
from random import choice
from time import monotonic
from types import CoroutineType
from typing import Any, overload
from weakref import WeakSet

from cachetools import Cache
from cachetools import FIFOCache as OFIFOCache
from cachetools import LFUCache as OLFUCache
from cachetools import LRUCache as OLRUCache
from cachetools import RRCache as ORRCache
from cachetools import TLRUCache as OTLRUCache
from cachetools import TTLCache as OTTLCache
from cachetools.keys import hashkey
from pympler import asizeof
from wrapt import decorator

from utils.aio import async_run_func

__all__ = (
    "Cache",
    "FIFOCache",
    "LFUCache",
    "LRUCache",
    "RRCache",
    "TLRUCache",
    "TTLCache",
    "async_cached",
    "MemFIFOCache",
    "MemLFUCache",
    "MemLRUCache",
    "MemRRCache",
    "MemTLRUCache",
    "MemTTLCache",
    "CronFIFOCache",
    "CronLFUCache",
    "CronLRUCache",
    "CronRRCache",
    "CronTLRUCache",
    "CronTTLCache",
    "CronMemFIFOCache",
    "CronMemLFUCache",
    "CronMemLRUCache",
    "CronMemRRCache",
    "CronMemTLRUCache",
    "CronMemTTLCache",
    "hashkey",
)


cachers: WeakSet[Cache] = WeakSet()


def clear_all_cache():
    for c in tuple(cachers):
        c.clear()


# region 缓存器mixin
class AhaCacheMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cachers.add(self)

    def __hash__(self):
        return object.__hash__(self)
    
    def clear(self):
        super().clear()


class MemoryCacheMixin:
    def __init__(self, maxsize, *args, getsizeof=None, **kwargs):
        self._original_getsizeof = getsizeof or asizeof.asizeof
        super().__init__(maxsize, *args, getsizeof=self._get_item_size, **kwargs)
        self._total_memory = 0

    def _get_item_size(self, *args):
        return sum(self._original_getsizeof(i) for i in args)

    def __setitem__(self, key, value, **kwargs):
        # 移除旧项的内存占用
        if old := self._Cache__data.get(key):
            self._total_memory -= self._get_item_size({key: old})

        # 执行淘汰策略
        new_size = self._original_getsizeof({key: value})
        while self._total_memory + new_size > self.maxsize:
            self._total_memory -= self._get_item_size({(popped := self.popitem())[0]: popped[1]})  # 解包evicted元组

        super().__setitem__(key, value, **kwargs)
        self._total_memory += new_size


class CronCacheMixin:
    """需要在模块初始化时就实例化"""

    _logger = getLogger("AHA (Cron cache)")

    def __init__(self, *args, cron="0 0 * * *", **kwargs):
        super().__init__(*args, **kwargs)
        from apscheduler.triggers.cron import CronTrigger

        from core.router import on_start
        from services.apscheduler import scheduler

        on_start(partial(scheduler.add_schedule, self.clear, CronTrigger.from_crontab(cron)))


# endregion
@overload
def async_cached(
    cache: Cache, key: Callable = None, ignore: Callable[..., bool] = None
) -> Callable[[Callable[..., CoroutineType[Any, Any, Any]]], Callable[..., CoroutineType[Any, Any, Any]]]: ...


@overload
def async_cached(
    cache: Cache, key: Callable = None, ignore: Callable[..., bool] = None, func: Callable = None
) -> CoroutineType[Any, Any, Any]: ...


def async_cached(cache, key=None, ignore=None, func=None):
    """
    被装饰的函数增加了两个 kwargs：
        no_cache: 调用时临时禁用缓存。
        cache_key: 调用时临时更换哈希键回调。
    """

    @decorator
    async def wrapper(func, _, args, kwargs):
        no_cache = kwargs.pop("no_cache", False)
        cache_key = kwargs.pop("cache_key", None)

        if not no_cache:
            if not cache_key:
                cache_key = key
            cache_key = hashkey(*args, **kwargs) if cache_key is None else await async_run_func(cache_key, *args, **kwargs)
            if result := cache.get(cache_key):
                return result

        result = await func(*args, **kwargs)
        if not ignore or not await async_run_func(ignore, result, *args, **kwargs):
            cache[cache_key] = result
        return result

    return wrapper(func) if func else wrapper


# region 超级拼装
class FIFOCache(AhaCacheMixin, OFIFOCache):
    def __init__(self, maxsize: int, getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, getsizeof)


class LFUCache(AhaCacheMixin, OLFUCache):
    def __init__(self, maxsize: int, getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, getsizeof)


class LRUCache(AhaCacheMixin, OLRUCache):
    def __init__(self, maxsize: int, getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, getsizeof)


class RRCache(AhaCacheMixin, ORRCache):
    def __init__(self, maxsize: int, choice=choice, getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, choice, getsizeof)


class TTLCache(AhaCacheMixin, OTTLCache):
    def __init__(
        self, maxsize: int, ttl: float, timer: Callable[[], float] = monotonic, getsizeof: Callable[[Any], float] = None
    ):
        super().__init__(maxsize, ttl, timer, getsizeof)


class TLRUCache(AhaCacheMixin, OTLRUCache):
    def __init__(
        self, maxsize: int, ttu: float, timer: Callable[[], float] = monotonic, getsizeof: Callable[[Any], float] = None
    ):
        super().__init__(maxsize, ttu, timer, getsizeof)


class MemFIFOCache(MemoryCacheMixin, FIFOCache):
    """限制内存FIFO缓存"""

    def __init__(self, maxsize: int, getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, getsizeof=getsizeof)


class MemLFUCache(MemoryCacheMixin, LFUCache):
    """限制内存LFU缓存"""

    def __init__(self, maxsize: int, getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, getsizeof=getsizeof)


class MemLRUCache(MemoryCacheMixin, LRUCache):
    """限制内存LRU缓存"""

    def __init__(self, maxsize: int, getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, getsizeof=getsizeof)


class MemRRCache(MemoryCacheMixin, RRCache):
    """限制内存随机替换缓存"""

    def __init__(self, maxsize: int, choice=choice, getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, choice, getsizeof=getsizeof)


class MemTTLCache(MemoryCacheMixin, TTLCache):
    """限制内存TTL缓存"""

    def __init__(
        self, maxsize: int, ttl: float, timer: Callable[[], float] = monotonic, getsizeof: Callable[[Any], float] = None
    ):
        super().__init__(maxsize, ttl, timer, getsizeof=getsizeof)


class MemTLRUCache(MemoryCacheMixin, TLRUCache):
    """限制内存时间感知LRU缓存"""

    def __init__(
        self, maxsize: int, ttu: float, timer: Callable[[], float] = monotonic, getsizeof: Callable[[Any], float] = None
    ):
        super().__init__(maxsize, ttu, timer, getsizeof=getsizeof)


class CronFIFOCache(CronCacheMixin, FIFOCache):
    """定时清空FIFO缓存，需要在模块初始化时就实例化。"""

    def __init__(self, maxsize: int, cron="0 0 * * *", getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, getsizeof, cron=cron)


class CronLFUCache(CronCacheMixin, LFUCache):
    """定时清空LFU缓存，需要在模块初始化时就实例化。"""

    def __init__(self, maxsize: int, cron="0 0 * * *", getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, getsizeof, cron=cron)


class CronLRUCache(CronCacheMixin, LRUCache):
    """定时清空LRU缓存，需要在模块初始化时就实例化。"""

    def __init__(self, maxsize: int, cron="0 0 * * *", getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, getsizeof, cron=cron)


class CronRRCache(CronCacheMixin, RRCache):
    """定时清空随机替换缓存，需要在模块初始化时就实例化。"""

    def __init__(self, maxsize: int, choice=choice, cron="0 0 * * *", getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, choice, getsizeof, cron=cron)


class CronTTLCache(CronCacheMixin, TTLCache):
    """定时清空TTL缓存，需要在模块初始化时就实例化。"""

    def __init__(
        self,
        maxsize: int,
        ttl: float,
        timer: Callable[[], float] = monotonic,
        cron="0 0 * * *",
        getsizeof: Callable[[Any], float] = None,
    ):
        super().__init__(maxsize, ttl, timer, getsizeof, cron=cron)


class CronTLRUCache(CronCacheMixin, TLRUCache):
    """定时清空时间感知LRU缓存，需要在模块初始化时就实例化。"""

    def __init__(
        self,
        maxsize: int,
        ttu: float,
        timer: Callable[[], float] = monotonic,
        cron="0 0 * * *",
        getsizeof: Callable[[Any], float] = None,
    ):
        super().__init__(maxsize, ttu, timer, getsizeof, cron=cron)


class CronMemFIFOCache(CronCacheMixin, MemFIFOCache):
    """定时清空限制内存FIFO缓存，需要在模块初始化时就实例化。"""

    def __init__(self, maxsize: int, cron="0 0 * * *", getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, cron=cron, getsizeof=getsizeof)


class CronMemLFUCache(CronCacheMixin, MemLFUCache):
    """定时清空限制内存LFU缓存，需要在模块初始化时就实例化。"""

    def __init__(self, maxsize: int, cron="0 0 * * *", getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, cron=cron, getsizeof=getsizeof)


class CronMemLRUCache(CronCacheMixin, MemLRUCache):
    """定时清空限制内存LRU缓存，需要在模块初始化时就实例化。"""

    def __init__(self, maxsize: int, cron="0 0 * * *", getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, cron=cron, getsizeof=getsizeof)


class CronMemRRCache(CronCacheMixin, MemRRCache):
    """定时清空限制内存随机替换缓存，需要在模块初始化时就实例化。"""

    def __init__(self, maxsize: int, choice=choice, cron="0 0 * * *", getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, choice, cron=cron, getsizeof=getsizeof)


class CronMemTTLCache(CronCacheMixin, MemTTLCache):
    """定时清空限制内存TTL缓存，需要在模块初始化时就实例化。"""

    def __init__(
        self,
        maxsize: int,
        ttl: float,
        timer: Callable[[], float] = monotonic,
        cron="0 0 * * *",
        getsizeof: Callable[[Any], float] = None,
    ):
        super().__init__(maxsize, ttl, timer, cron=cron, getsizeof=getsizeof)


class CronMemTLRUCache(CronCacheMixin, MemTLRUCache):
    """定时清空限制内存时间感知LRU缓存，需要在模块初始化时就实例化。"""

    def __init__(
        self,
        maxsize: int,
        ttu: float,
        timer: Callable[[], float] = monotonic,
        cron="0 0 * * *",
        getsizeof: Callable[[Any], float] = None,
    ):
        super().__init__(maxsize, ttu, timer, cron=cron, getsizeof=getsizeof)


# endregion

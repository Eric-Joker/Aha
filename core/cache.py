from collections.abc import Callable, Hashable  # , MutableMapping
# from contextlib import suppress
from functools import partial
from logging import getLogger
from random import choice
from time import monotonic
from types import CoroutineType
from typing import TYPE_CHECKING, Any, ClassVar, overload
from weakref import WeakSet  # , WeakKeyDictionary, ref

import cachetools
from cachetools import Cache
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


class MemoryCacheMixin:
    INIT_MEM_SIZE: ClassVar[int]
    ADDITIONAL_PER_ITEM_MEM_SIZE: ClassVar[int]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, getsizeof=asizeof.asizeof, **kwargs)
        self._Cache__currsize = self.INIT_MEM_SIZE

    def __setitem(self, key, value):
        if (size := asizeof.asizeof(key, value) + self.ADDITIONAL_PER_ITEM_MEM_SIZE) > self._Cache__maxsize:
            raise ValueError("value too large")
        if key not in self._Cache__data or self._Cache__size[key] < size:
            while self._Cache__currsize + size > self._Cache__maxsize:
                self.popitem()
        diffsize = size - self._Cache__size[key] if key in self._Cache__data else size
        self._Cache__data[key] = value
        self._Cache__size[key] = size
        self._Cache__currsize += diffsize

    def __setitem__(self, key, value):
        super().__setitem__(key, value, MemoryCacheMixin.__setitem)


"""
class HybridKeyDictionary[KT, VT](MutableMapping[KT, VT]):
    __slots__ = ("_strong", "_weak", "_pending_cleanup")

    def __init__(self) -> None:
        self._strong: dict[KT, VT] = {}
        self._weak: WeakKeyDictionary[KT, VT] = WeakKeyDictionary()
        self._pending_cleanup = False

    def __contains__(self, key):
        return key in self._strong or key in self._weak

    def __getitem__(self, key):
        return self._strong[key] if key in self._strong else self._weak[key]

    def __setitem__(self, key, value):
        with suppress:
            del self._weak[key]
        self._strong[key] = value

    def __delitem__(self, key):
        self._weak[key] = self._strong.pop(key)

    def __len__(self):
        return len(self._strong) + len(self._weak)

    def __iter__(self):
        yield from self._strong.keys()
        for key in self._weak:
            if key not in self._strong:
                yield key


class WeakKeyCacheMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._Cache__data = HybridKeyDictionary()
        if self.getsizeof is not Cache.getsizeof:
            self._Cache__size = HybridKeyDictionary()
"""

class CronCacheMixin:
    """需要在模块初始化时就实例化"""

    _logger = getLogger("AHA (Cron cache)")

    def __init__(self, *args, cron="0 0 * * *", **kwargs):
        super().__init__(*args, **kwargs)
        from apscheduler.triggers.cron import CronTrigger

        from core.dispatcher import on_start
        from services.apscheduler import sched

        on_start(partial(sched.add_schedule, self.clear, CronTrigger.from_crontab(cron)))


# endregion
@overload
def async_cached(
    cache: Cache, key: Callable = None, ignore: Callable[..., bool] = None
) -> Callable[[Callable[..., CoroutineType[Any, Any, Any]]], Callable[..., CoroutineType[Any, Any, Any]]]: ...


@overload
def async_cached(
    cache: Cache, key: Callable = None, ignore: Callable[..., bool] = None, func: Callable = None
) -> CoroutineType[Any, Any, Any]: ...


def async_cached(
    cache, key: Callable[..., Hashable | CoroutineType[Any, Any, Hashable]] = None, ignore: Callable = None, func=None
):
    """
    被装饰的函数增加了两个 kwargs：
        no_cache: 调用时不查询缓存。
        cache_key: 调用时临时更换缓存键生成器。

    Args:
        cache: 缓存器。
        key: 缓存键生成器。
        ignore: 接受被装饰函数返回值、位置与关键字参数，返回值的 bool 为 True 时本次调用结果不写入缓存。
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
class FIFOCache(AhaCacheMixin, cachetools.FIFOCache):
    if TYPE_CHECKING:

        def __init__(self, maxsize: int, getsizeof: Callable[[Any], float] = None): ...


cachetools.FIFOCache = FIFOCache


class LFUCache(AhaCacheMixin, cachetools.LFUCache):
    if TYPE_CHECKING:

        def __init__(self, maxsize: int, getsizeof: Callable[[Any], float] = None): ...


cachetools.LFUCache = LFUCache


class LRUCache(AhaCacheMixin, cachetools.LRUCache):
    if TYPE_CHECKING:

        def __init__(self, maxsize: int, getsizeof: Callable[[Any], float] = None): ...


cachetools.LRUCache = LRUCache


class RRCache(AhaCacheMixin, cachetools.RRCache):
    if TYPE_CHECKING:

        def __init__(self, maxsize: int, choice=choice, getsizeof: Callable[[Any], float] = None): ...


cachetools.RRCache = RRCache


class TTLCache(AhaCacheMixin, cachetools.TTLCache):
    if TYPE_CHECKING:

        def __init__(
            self, maxsize: int, ttl: float, timer: Callable[[], float] = monotonic, getsizeof: Callable[[Any], float] = None
        ): ...


cachetools.TTLCache = TTLCache


class TLRUCache(AhaCacheMixin, cachetools.TLRUCache):
    if TYPE_CHECKING:

        def __init__(
            self, maxsize: int, ttu: float, timer: Callable[[], float] = monotonic, getsizeof: Callable[[Any], float] = None
        ): ...


cachetools.TLRUCache = TLRUCache


"""
class WeakKeyFIFOCache(WeakKeyCacheMixin, FIFOCache):
    \"""过期项转为弱引用的FIFO缓存\"""

    def __init__(self, maxsize: int, getsizeof: Callable[[Any], float] = None):


class WeakKeyLFUCache(WeakKeyCacheMixin, LFUCache):
    \"""过期项转为弱引用的LFU缓存\"""

    class _Link:
        __slots__ = ("count", "keys", "next", "prev")

        def __init__(self, count):
            self.count = count
            self.keys = WeakSet()

        def unlink(self):
            next = self.next
            prev = self.prev
            prev.next = next
            next.prev = prev

    def __init__(self, maxsize: int, getsizeof: Callable[[Any], float]=None):
        super().__init__(self, maxsize, getsizeof)
        self._LFUCache__root = root = WeakKeyLFUCache._Link(0)
        root.prev = root.next = root
        self._LFUCache__links = WeakKeyDictionary()



class WeakKeyLRUCache(WeakKeyCacheMixin, LRUCache):
    \"""过期项转为弱引用的LRU缓存\"""

    def __init__(self, maxsize: int, getsizeof: Callable[[Any], float] = None):


class WeakKeyRRCache(WeakKeyCacheMixin, RRCache):
    \"""过期项转为弱引用的随机替换缓存\"""

    def __init__(self, maxsize: int, choice=choice, getsizeof: Callable[[Any], float] = None):
"""

class MemFIFOCache(MemoryCacheMixin, FIFOCache):
    """限制内存FIFO缓存"""
    
    INIT_MEM_SIZE = 840
    ADDITIONAL_PER_ITEM_MEM_SIZE = 253

    def __init__(self, maxsize: int):
        super().__init__(maxsize)


class MemLFUCache(MemoryCacheMixin, LFUCache):
    """限制内存LFU缓存"""
    
    INIT_MEM_SIZE = 1112
    ADDITIONAL_PER_ITEM_MEM_SIZE = 223

    def __init__(self, maxsize: int):
        super().__init__(maxsize)


class MemLRUCache(MemoryCacheMixin, LRUCache):
    """限制内存LRU缓存"""

    INIT_MEM_SIZE = 840
    ADDITIONAL_PER_ITEM_MEM_SIZE = 253

    def __init__(self, maxsize: int):
        super().__init__(maxsize)


class MemRRCache(MemoryCacheMixin, RRCache):
    """限制内存随机替换缓存"""

    INIT_MEM_SIZE = 944
    ADDITIONAL_PER_ITEM_MEM_SIZE = 253

    def __init__(self, maxsize: int, choice=choice):
        super().__init__(maxsize, choice)


class MemTTLCache(MemoryCacheMixin, TTLCache):
    """限制内存TTL缓存"""

    INIT_MEM_SIZE = 1584
    ADDITIONAL_PER_ITEM_MEM_SIZE = 335

    def __init__(self, maxsize: int, ttl: float, timer: Callable[[], float] = monotonic):
        super().__init__(maxsize, ttl, timer)


class MemTLRUCache(MemoryCacheMixin, TLRUCache):
    """限制内存时间感知LRU缓存"""

    INIT_MEM_SIZE = 1528
    ADDITIONAL_PER_ITEM_MEM_SIZE = 328

    def __init__(self, maxsize: int, ttu: float, timer: Callable[[], float] = monotonic):
        super().__init__(maxsize, ttu, timer)

"""
class MemWeakKeyFIFOCache(MemoryCacheMixin, WeakKeyFIFOCache):
    \"""限制内存的过期项转为弱引用的FIFO缓存\"""

    def __init__(self, maxsize: int):
        super().__init__(maxsize)


class MemWeakKeyLFUCache(MemoryCacheMixin, WeakKeyLFUCache):
    \"""限制内存的过期项转为弱引用的LFU缓存\"""

    def __init__(self, maxsize: int):
        super().__init__(maxsize)


class MemWeakKeyLRUCache(MemoryCacheMixin, WeakKeyLRUCache):
    \"""限制内存的过期项转为弱引用的LRU缓存\"""

    def __init__(self, maxsize: int):
        super().__init__(maxsize)


class MemWeakKeyRRCache(MemoryCacheMixin, WeakKeyRRCache):
    \"""限制内存的过期项转为弱引用的随机替换缓存\"""

    def __init__(self, maxsize: int, choice=choice):
        super().__init__(maxsize, choice)
"""

class CronFIFOCache(CronCacheMixin, FIFOCache):
    """定时清空FIFO缓存，需要在模块初始化时就实例化"""

    def __init__(self, maxsize: int, cron="0 0 * * *", getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, getsizeof, cron=cron)


class CronLFUCache(CronCacheMixin, LFUCache):
    """定时清空LFU缓存，需要在模块初始化时就实例化"""

    def __init__(self, maxsize: int, cron="0 0 * * *", getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, getsizeof, cron=cron)


class CronLRUCache(CronCacheMixin, LRUCache):
    """定时清空LRU缓存，需要在模块初始化时就实例化"""

    def __init__(self, maxsize: int, cron="0 0 * * *", getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, getsizeof, cron=cron)


class CronRRCache(CronCacheMixin, RRCache):
    """定时清空随机替换缓存，需要在模块初始化时就实例化"""

    def __init__(self, maxsize: int, choice=choice, cron="0 0 * * *", getsizeof: Callable[[Any], float] = None):
        super().__init__(maxsize, choice, getsizeof, cron=cron)


class CronTTLCache(CronCacheMixin, TTLCache):
    """定时清空TTL缓存，需要在模块初始化时就实例化"""

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
    """定时清空时间感知LRU缓存，需要在模块初始化时就实例化"""

    def __init__(
        self,
        maxsize: int,
        ttu: float,
        timer: Callable[[], float] = monotonic,
        cron="0 0 * * *",
        getsizeof: Callable[[Any], float] = None,
    ):
        super().__init__(maxsize, ttu, timer, getsizeof, cron=cron)

"""
class CronWeakKeyFIFOCache(CronCacheMixin, WeakKeyFIFOCache):
    \"""过期转为弱引用的定期将全部项过期的FIFO缓存，需要在模块初始化时就实例化。\"""

    def __init__(self, maxsize: int, cron="0 0 * * *"):
        super().__init__(maxsize, cron=cron)


class CronWeakKeyLFUCache(CronCacheMixin, WeakKeyLFUCache):
    \"""过期转为弱引用的定期将全部项过期的LFU缓存，需要在模块初始化时就实例化。\"""

    def __init__(self, maxsize: int, cron="0 0 * * *"):
        super().__init__(maxsize, cron=cron)


class CronWeakKeyLRUCache(CronCacheMixin, WeakKeyLRUCache):
    \"""过期转为弱引用的定期将全部项过期的LRU缓存，需要在模块初始化时就实例化。\"""

    def __init__(self, maxsize: int, cron="0 0 * * *"):
        super().__init__(maxsize, cron=cron)


class CronWeakKeyRRCache(CronCacheMixin, WeakKeyRRCache):
    \"""过期转为弱引用的定期将全部项过期的随机替换缓存，需要在模块初始化时就实例化。\"""

    def __init__(self, maxsize: int, choice=choice, cron="0 0 * * *"):
        super().__init__(maxsize, choice, cron=cron)
"""

class CronMemFIFOCache(CronCacheMixin, MemFIFOCache):
    """定时清空限制内存FIFO缓存，需要在模块初始化时就实例化"""

    def __init__(self, maxsize: int, cron="0 0 * * *"):
        super().__init__(maxsize, cron=cron)


class CronMemLFUCache(CronCacheMixin, MemLFUCache):
    """定时清空限制内存LFU缓存，需要在模块初始化时就实例化"""

    def __init__(self, maxsize: int, cron="0 0 * * *"):
        super().__init__(maxsize, cron=cron)


class CronMemLRUCache(CronCacheMixin, MemLRUCache):
    """定时清空限制内存LRU缓存，需要在模块初始化时就实例化"""

    def __init__(self, maxsize: int, cron="0 0 * * *"):
        super().__init__(maxsize, cron=cron)


class CronMemRRCache(CronCacheMixin, MemRRCache):
    """定时清空限制内存随机替换缓存，需要在模块初始化时就实例化"""

    def __init__(self, maxsize: int, choice=choice, cron="0 0 * * *"):
        super().__init__(maxsize, choice, cron=cron)


class CronMemTTLCache(CronCacheMixin, MemTTLCache):
    """定时清空限制内存TTL缓存，需要在模块初始化时就实例化"""

    def __init__(self, maxsize: int, ttl: float, timer: Callable[[], float] = monotonic, cron="0 0 * * *"):
        super().__init__(maxsize, ttl, timer, cron=cron)


class CronMemTLRUCache(CronCacheMixin, MemTLRUCache):
    """定时清空限制内存时间感知LRU缓存，需要在模块初始化时就实例化"""

    def __init__(self, maxsize: int, ttu: float, timer: Callable[[], float] = monotonic, cron="0 0 * * *"):
        super().__init__(maxsize, ttu, timer, cron=cron)

"""
class CronMemWeakKeyFIFOCache(CronCacheMixin, MemWeakKeyFIFOCache):
    \"""过期转为弱引用的定期将全部项过期的限制内存的FIFO缓存，需要在模块初始化时就实例化。\"""

    def __init__(self, maxsize: int, cron="0 0 * * *"):
        super().__init__(maxsize, cron=cron)


class CronMemWeakKeyLFUCache(CronCacheMixin, MemWeakKeyLFUCache):
    \"""过期转为弱引用的定期将全部项过期的限制内存的LFU缓存，需要在模块初始化时就实例化。\"""

    def __init__(self, maxsize: int, cron="0 0 * * *"):
        super().__init__(maxsize, cron=cron)


class CronMemWeakKeyLRUCache(CronCacheMixin, MemWeakKeyLRUCache):
    \"""过期转为弱引用的定期将全部项过期的限制内存的LRU缓存，需要在模块初始化时就实例化。\"""

    def __init__(self, maxsize: int, cron="0 0 * * *"):
        super().__init__(maxsize, cron=cron)


class CronMemWeakKeyRRCache(CronCacheMixin, MemWeakKeyRRCache):
    \"""过期转为弱引用的定期将全部项过期的限制内存的随机替换缓存，需要在模块初始化时就实例化。\"""

    def __init__(self, maxsize: int, choice=choice, cron="0 0 * * *"):
        super().__init__(maxsize, choice, cron=cron)
"""

# endregion

# Copyright (C) 2025 github.com/Eric-Joker
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from functools import partial, wraps
from sys import _getframe
from typing import Callable

from apscheduler.triggers.cron import CronTrigger
from cachetools import Cache, LRUCache
from cachetools.keys import hashkey
from pympler import asizeof

from metas import RestrictiveMeta
from services.apscheduler import scheduler

from .misc import async_run_func

cachers: list[Cache] = []


def get_cache(obj, *args, **kwargs) -> Cache:
    cachers.append(cache := obj(*args, **kwargs))
    return cache


class MemoryCacheMixin(metaclass=RestrictiveMeta):
    def __init__(self, maxsize, getsizeof=None, **kwargs):
        self._original_getsizeof = getsizeof or asizeof.asizeof
        super().__init__(maxsize, getsizeof=self._get_item_size, **kwargs)
        self._total_memory = 0

    def _get_item_size(self, *args):
        return sum(self._original_getsizeof(i) for i in args)

    def __setitem__(self, key, value, **kwargs):
        # 移除旧项的内存占用
        if key in self:
            self._total_memory -= self._get_item_size({key: self._Cache__data.get(key)})

        # 执行LRU淘汰策略
        new_size = self._original_getsizeof({key: value})
        while self._total_memory + new_size > self.maxsize:
            self._total_memory -= self._get_item_size(*self.popitem())  # 解包evicted元组

        super().__setitem__(key, value, **kwargs)
        self._total_memory += new_size


class SchedulerCacheMixin(metaclass=RestrictiveMeta):
    def __init__(self, *args, clear_time=None, **kwargs):
        from config import cfg
        from .message_router import on_shutup, on_start

        super().__init__(*args, **kwargs)

        if not (qualname := _getframe(1).f_globals.get("__name__")):
            raise RuntimeError("Caller's module could not be determined")
        qualname = f"{qualname}.{self.__class__.__name__}"

        on_start(
            partial(
                scheduler.add_schedule,
                self.clear,
                CronTrigger.from_crontab(clear_time or cfg.cache_cron),
                id=qualname,
            )
        )
        on_shutup(partial(scheduler.remove_schedule, qualname))


class MemLRUCache(MemoryCacheMixin, LRUCache):
    pass


class SchMemLRUCache(SchedulerCacheMixin, MemLRUCache):
    pass


def async_cached(cache: Cache, key: Callable = None, ignore: Callable[..., bool] = None):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, no_cache=False, cache_key: Callable = None, **kwargs):
            if not no_cache:
                cache_key = (
                    hashkey(*args, **kwargs)
                    if (cache_key := cache_key or key) is None
                    else await async_run_func(cache_key, *args, **kwargs)
                )
                if cache_key in cache:
                    return cache[cache_key]

            result = await func(*args, **kwargs)
            if not ignore or not await async_run_func(ignore, result, *args, **kwargs):
                cache[cache_key] = result
            return result

        return wrapper

    return decorator

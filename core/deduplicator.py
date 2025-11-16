from abc import ABC, abstractmethod
from typing import Hashable

from cachetools import Cache

from models.api import BaseEvent
from utils.unit import parse_size

from .i18n import _


class Deduplicator(ABC):
    __slots__ = ("cache",)

    def __init__(self):
        from .cache import MemTTLCache
        from .config import cfg

        cache_cfg = cfg.event_cache
        self.cache: Cache[BaseEvent, _Bucket | set[int]] = MemTTLCache(parse_size(cache_cfg["size"]), cache_cfg["ttl"])
        super().__init__()

    @abstractmethod
    def is_duplicate(self, event: Hashable) -> bool:
        pass

    @abstractmethod
    def services_of(self, key: Hashable) -> list:
        """查询该键下已观测到的服务集合"""
        pass


class _Bucket:
    __slots__ = ("_counts", "services", "released")
    
    def __init__(self, bot_id):
        self._counts: dict[int, int] = {bot_id: 1}
        self.services: list[int] = [bot_id]
        self.released: int = 1

    def __len__(self):
        return len(self._counts)

    def is_duplicate(self, bot_id: int):
        if (count := self._counts.get(bot_id)) is None:
            self._counts[bot_id] = 1
            self.services.append(bot_id)
            return True
        else:
            self._counts[bot_id] = count + 1
        if self.released < max(self._counts.values()):
            self.released += 1
            return False
        return True

    def __contains__(self, item):
        return item in self._counts

    def __getitem__(self, index):
        return self.services[index]
    
    def __bool__(self):
        return bool(self._counts)


class NoneDeduplicator(Deduplicator):
    __slots__ = ()
    
    def __init__(self): ...
    
    def is_duplicate(self, _):
        return True

    def services_of(self, _):
        return ()


class FuzzyDeduplicator(Deduplicator):
    """适用于无唯一消息 ID 的平台"""

    def is_duplicate(self, event: BaseEvent):
        if (bucket := self.cache.get(event)) is None:
            self.cache[event] = _Bucket(event.bot_id)
            return False

        result = bucket.is_duplicate(event.bot_id)
        self.cache[event] = bucket  # 更新缓存计数
        return result

    def services_of(self, event):
        return b.services.copy() if (b := self.cache.get(event)) else []


class UniqueIdDeduplicator(Deduplicator):
    """适用于有唯一消息 ID 的平台"""

    def is_duplicate(self, event: BaseEvent):
        if (u := self.cache.get(event)) is None:
            self.cache[event] = {event.bot_id}
            return False

        u.add(event.bot_id)
        self.cache[event] = u  # 更新缓存计数
        return True

    def services_of(self, event):
        return list(u) if (u := self.cache.get(event)) else []

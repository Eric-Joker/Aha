
from abc import ABC, abstractmethod
from collections.abc import Iterable, KeysView
from typing import Hashable

from attrs import define

from models.api import BaseEvent
from utils.typekit import parse_size

from .i18n import _


class Deduplicator(ABC):
    __slots__ = ("cache",)

    def __init__(self):
        from .cache import TTLCache
        from .config import cfg

        cache_cfg = cfg.event_cache
        self.cache = TTLCache(parse_size(cache_cfg["size"]), cache_cfg["ttl"])
        super().__init__()

    @abstractmethod
    def is_duplicate(self, event: Hashable) -> bool:
        pass

    @abstractmethod
    def services_of(self, key: Hashable) -> Iterable:
        """查询该键下已观测到的服务集合"""
        pass


@define(slots=True)
class _Bucket:
    per_service_counts: dict[int, int]
    released: int

    def __len__(self):
        return len(self.per_service_counts)

    def __getitem__(self, index):
        return tuple(self.per_service_counts.keys())[index]

    def __iter__(self):
        return iter(self.per_service_counts.keys())


class NoneDeduplicator(Deduplicator):
    def is_duplicate(self, _):
        return True

    def services_of(self, _):
        return ()


class FuzzyDeduplicator(Deduplicator):
    """适用于无唯一消息 ID 的平台。"""

    def is_duplicate(self, event: BaseEvent):
        if (bucket := self.cache.get(hash(event))) is None:
            self.cache[hash(event)] = _Bucket(per_service_counts={event.bot_id: 1}, released=1)
            return False

        bucket.per_service_counts[event.bot_id] = bucket.per_service_counts.get(event.bot_id, 0) + 1
        if bucket.released < max(bucket.per_service_counts.values()):
            bucket.released += 1
            self.cache[hash(event)] = bucket  # 更新缓存计数
            return False

        self.cache[hash(event)] = bucket  # 更新缓存计数
        return True

    def services_of(self, event) -> tuple | KeysView:
        return () if (b := self.cache.get(hash(event))) is None else b.per_service_counts.keys()


class UniqueIdDeduplicator(Deduplicator):
    """适用于有唯一消息 ID 的平台。"""

    def is_duplicate(self, event: BaseEvent):
        if (u := self.cache.get(hash(event))) is None:
            self.cache[event] = {event.bot_id}
            return False

        u.add(event.bot_id)
        self.cache[hash(event)] = u  # 更新缓存计数
        return True

    def services_of(self, event) -> tuple | set:
        return () if (u := self.cache.get(hash(event))) is None else u

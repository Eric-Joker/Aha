
from asyncio import CancelledError, Event, Task, create_task, shield
from contextlib import suppress
from logging import getLogger
from weakref import WeakSet

from sqlalchemy import Column, PickleType, String, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import database_initialized, db_session_factory, dbBase
from core.i18n import _
from utils.misc import MODULE_PATTERN, caller_module
from utils.sqlalchemy import upsert

__all__ = "SimpleStore"

# 全局状态管理
_commit_task: Task = None
_commit_event = Event()
_instances: WeakSet[SimpleStore] = WeakSet()
_created_modules = set()

_logger = getLogger("simple data store")


async def initialize_all_stores():
    for instance in tuple(_instances):
        await instance.load_from_db()


async def clean_data_store():
    if _commit_task:
        _commit_task.cancel()
        await _commit_task
    _created_modules.clear()


async def _shield_commit():
    instances_to_commit = [instance for instance in tuple(_instances) if instance.has_changes]
    async with db_session_factory() as session:
        for instance in instances_to_commit:
            try:
                await instance.flush_to_db(session)
                await session.commit()
                instance._reset_changes()
            except Exception:
                _logger.exception(_("simple_data_store.commit_error") % instance._module)


async def commit_worker():
    with suppress(CancelledError):
        while True:
            await _commit_event.wait()
            _commit_event.clear()
            task = shield(create_task(_shield_commit()))
            try:
                await task
            except CancelledError:
                await task
                break


def get_commit_task():
    global _commit_task
    if _commit_task is None or _commit_task.done():
        _commit_task = create_task(commit_worker())
    return _commit_task


class SimpleStore[K: str, V]:
    """先写入内存，等待后台任务自动写入数据库。也就是说非正常退出程序可能会导致数据丢失。"""

    __slots__ = ("__weakref__", "table", "_cache", "_changed_keys", "_removed_keys", "_module")

    def __init__(self):
        if (module := caller_module(pattern=MODULE_PATTERN)) in _created_modules:
            raise RuntimeError(_("simple_data_store.duplicate"))
        _created_modules.add(module)

        if database_initialized:
            raise RuntimeError(_("simple_data_store.inited_error"))

        if (table_name := f"{module}___simple") in dbBase.metadata.tables:
            self.table = dbBase.metadata.tables[table_name]
        else:

            class Simple(dbBase):
                __tablename__ = table_name
                key = Column(String, primary_key=True)
                value = Column(PickleType)

            self.table = Simple
        self._cache: dict[K, V] = {}
        self._changed_keys: set[K] = set()
        self._removed_keys: set[K] = set()
        self._module = module

        _instances.add(self)
        get_commit_task()  # 确保提交任务运行

    @property
    def has_changes(self):
        return bool(self._changed_keys or self._removed_keys)

    def __getitem__(self, key: K):
        return self._cache[key]

    def __setitem__(self, key: K, value: V):

        if self._cache.get(key) != value:
            self._cache[key] = value
            self._changed_keys.add(key)
            self._removed_keys.discard(key)
            self._trigger_commit()

    def __delitem__(self, key: K):
        del self._cache[key]
        self._removed_keys.add(key)
        self._changed_keys.discard(key)
        self._trigger_commit()

    def __len__(self):
        return len(self._cache)

    def __iter__(self):
        """温馨提示：迭代时不可修改哦~"""
        return iter(self._cache)

    def __contains__(self, key: K):
        return key in self._cache

    def get(self, key: K, default: V | None = None):
        return self._cache.get(key, default)

    def keys(self):
        return self._cache.keys()

    def values(self):
        return self._cache.values()

    def items(self):
        return self._cache.items()

    def pop(self, key: K, default: V | None = None):
        if key in self._cache:
            result = self._cache.pop(key)
            self._removed_keys.add(key)
            self._changed_keys.discard(key)
            self._trigger_commit()
            return result
        return default

    def popitem(self):
        key, value = self._cache.popitem()
        self._removed_keys.add(key)
        self._changed_keys.discard(key)
        self._trigger_commit()
        return key, value

    def clear(self):
        if self._cache:
            # 将所有当前键标记为删除
            self._removed_keys.update(self._cache.keys())
            self._changed_keys.clear()
            self._cache.clear()
            self._trigger_commit()

    def update(self, other: dict[K, V] = None, **kwargs: V):
        changed = False

        if other:
            for key, value in other.items():
                if self._cache.get(key) != value:
                    self._cache[key] = value
                    self._changed_keys.add(key)
                    self._removed_keys.discard(key)
                    changed = True

        if kwargs:
            for key, value in kwargs.items():
                if self._cache.get(key) != value:
                    self._cache[key] = value
                    self._changed_keys.add(key)
                    self._removed_keys.discard(key)
                    changed = True

        if changed:
            self._trigger_commit()

    def setdefault(self, key: K, default: V):
        if key not in self._cache:
            self._cache[key] = default
            self._changed_keys.add(key)
            self._removed_keys.discard(key)
            self._trigger_commit()
            return default
        return self._cache[key]

    def copy(self):
        return self._cache.copy()

    def _trigger_commit(self):
        if self.has_changes:
            _commit_event.set()

    def _reset_changes(self):
        """重置更改状态"""
        self._changed_keys.clear()
        self._removed_keys.clear()

    async def flush_to_db(self, session: AsyncSession):
        """将变更数据刷新到数据库"""
        for key in self._changed_keys:
            if key in self._cache:  # 确保键没有被并发删除
                await session.execute(upsert(self.table, key=key, value=self._cache[key]))

        for key in self._removed_keys:
            await session.execute(delete(self.table).where(self.table.key == key))

    async def load_from_db(self):
        """从数据库加载所有数据到缓存"""
        async with db_session_factory() as session:
            self._cache.clear()
            self._reset_changes()

            for row in (await session.scalars(select(self.table))).all():
                self._cache[row.key] = row.value

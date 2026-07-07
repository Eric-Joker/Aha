from enum import Enum, auto
from functools import partial
from random import choice
from types import FunctionType
from typing import TYPE_CHECKING, Literal, _overload_dummy, _overload_registry, overload

from models.api import BaseEvent
from utils.func import get_arg_names, get_kwonlyarg_count

from ..api_service import bots, bots_lock, call_api, deduplicators, platform_bot_map
from ..config import cfg
from ..dispatcher import current_event
from ..i18n import _
from .account import AccountAPI
from .group import GroupAPI
from .message import MessageAPI
from .private import PrivateAPI
from .support import SupportAPI

if cfg.cache_conv:
    from ..api_service import friend_conv_lock, friends, group_conv_lock, groups

__all__ = ("API", "SS", "select_bot")


class APIMeta(type):
    @staticmethod
    def _warpper_with_overload(*args, _name, _args, **kwargs):
        if event := current_event.get():
            if "user_id" not in kwargs and "group_id" not in kwargs:
                if (value := getattr(event, "user_id", None)) is not None:
                    kwargs.setdefault("user_id", value)
                if (value := getattr(event, "group_id", None)) is not None:
                    kwargs.setdefault("group_id", value)
            kwargs.setdefault("bot", event.bot_id)
        for i, arg in enumerate(args):
            kwargs[_args[i + 2]] = arg
        return call_api(_name, **kwargs)

    @staticmethod
    def _warpper(*args, _name, **kwargs):
        if not kwargs.get("bot"):
            try:
                kwargs["bot"] = current_event.get().bot_id
            except AttributeError as e:
                raise RuntimeError(_("no_event_found_in_context")) from e
        return call_api(_name, *args, **kwargs)

    @classmethod
    def _warp_method(cls, new_class, attr_name, attr_value, method_src):
        if attr_value is _overload_dummy:
            for v in _overload_registry[method_src[0]][method_src[1]].values():
                if get_kwonlyarg_count(v) >= 3:
                    break

            setattr(
                new_class,
                attr_name,
                partial(cls._warpper_with_overload, _name=attr_name, _args=get_arg_names(v)),
            )
        else:

            setattr(new_class, attr_name, partial(cls._warpper, _name=attr_name))

    def __new__(mcs, name, bases, namespace, **kwargs):
        new_class = super().__new__(mcs, name, bases, namespace, **kwargs)

        methods_to_wrap = set()
        for attr_name, attr_value in namespace.items():
            if not attr_name.startswith("__") and attr_value.__class__ is FunctionType:
                methods_to_wrap.add(attr_name)
                mcs._warp_method(new_class, attr_name, attr_value, (base.__module__, f"{base.__qualname__}.{attr_name}"))

        # 父类
        for base in bases:
            for attr_name in dir(base):
                if (
                    not attr_name.startswith("__")
                    and (attr_value := getattr(base, attr_name)).__class__ is FunctionType
                    and attr_name not in methods_to_wrap
                ):
                    methods_to_wrap.add(attr_name)
                    mcs._warp_method(new_class, attr_name, attr_value, (base.__module__, f"{base.__qualname__}.{attr_name}"))

        return new_class

    def __getattr__(cls, name):
        setattr(cls, name, method := partial(cls._warpper, _name=name))
        return method


class API(AccountAPI, GroupAPI, MessageAPI, PrivateAPI, SupportAPI, metaclass=APIMeta):
    pass


# region API router
class SS(Enum):
    """API 实例选择策略，用于 `select_bot` 函数。详情见文档"""

    PREFS = auto()
    NTH = auto()
    UNORDERED_NTH = auto()
    RANDOM = auto()
    PLATFORM = auto()
    PLATFORM_NTH = auto()
    PLATFORM_RANDOM = auto()
    PREFS_ANY = auto()
    NTH_ANY = auto()
    RANDOM_ANY = auto()
    FRIEND = auto()
    FRIEND_NTH = auto()
    FRIEND_RANDOM = auto()
    GROUP = auto()
    GROUP_NTH = auto()
    GROUP_RANDOM = auto()


if TYPE_CHECKING:

    @overload
    async def select_bot(
        strategy: Literal[SS.NTH, SS.UNORDERED_NTH] = SS.PREFS, event: BaseEvent = None, *, index: int = 0
    ) -> int: ...

    @overload
    async def select_bot(strategy: Literal[SS.PLATFORM, SS.PLATFORM_RANDOM], event: BaseEvent = None, *, platform: str = None) -> int: ...

    @overload
    async def select_bot(
        strategy: Literal[SS.PLATFORM_NTH], event: BaseEvent = None, *, platform: str = None, index: int = 0
    ) -> int: ...

    @overload
    async def select_bot(
        strategy: Literal[SS.FRIEND_NTH, SS.GROUP_NTH],
        event: BaseEvent = None,
        *,
        platform: str = None,
        conv_id: str = None,
        index: int = 0,
    ) -> int: ...

    @overload
    async def select_bot(
        strategy: Literal[SS.FRIEND, SS.GROUP, SS.FRIEND_RANDOM, SS.GROUP_RANDOM],
        event: BaseEvent = None,
        *,
        platform: str = None,
        conv_id: str = None,
    ) -> int: ...

    @overload
    async def select_bot(strategy: Literal[SS.NTH_ANY], *, index: int = 0) -> int: ...

    @overload
    async def select_bot(strategy: Literal[SS.PREFS, SS.RANDOM, SS.PREFS_ANY, SS.RANDOM_ANY]) -> int: ...


async def select_bot(strategy=SS.PREFS, event=None, *, index=0, platform=None, conv_id=None):
    """依据策略选择 bot 实例

    Args:
        strategy: 默认为配置文件中选择的策略。
        event: 未传递所需参数时，从中提取所需值。为 `None` 时尝试从 ContextVar 获取。

    Raises:
        RuntimeError: 事件实例过期或未开启 `cache_conv` 配置项或精确指定的 bot 实例不再可用。
        KeyError: 未在 Aha 维护的缓存中找到指定的好友/群聊。
    """
    if not event:
        try:
            event = current_event.get()
        except AttributeError as e:
            raise RuntimeError(_("no_event_found_in_context")) from e

    match strategy:
        case SS.PREFS:
            if prefs := cfg.bot_prefs:
                data_set = set(deduplicators[event.platform].services_of(event))
                try:
                    async with bots_lock:
                        return [v for v in bots if v in data_set][min(prefs, len(data_set) - 1)]
                except IndexError:
                    raise RuntimeError(_("router.select_bot.event404"))
            try:
                return choice(deduplicators[event.platform].services_of(event))
            except IndexError:
                raise RuntimeError(_("router.select_bot.event404"))
        case SS.NTH:
            data_set = set(deduplicators[event.platform].services_of(event))
            async with bots_lock:
                try:
                    return [v for v in bots if v in data_set][index]
                except IndexError:
                    raise RuntimeError(_("router.select_bot.event404"))
        case SS.UNORDERED_NTH:
            try:
                return deduplicators[event.platform].services_of(event)[index]
            except IndexError:
                raise RuntimeError(_("router.select_bot.event404"))
        case SS.RANDOM:
            try:
                return choice(deduplicators[event.platform].services_of(event))
            except IndexError:
                raise RuntimeError(_("router.select_bot.event404"))
        case SS.PLATFORM:
            if prefs := cfg.bot_prefs:
                data_set = set(platform_bot_map[platform or event.platform])
                async with bots_lock:
                    return [v for v in bots if v in data_set][min(prefs, len(data_set) - 1)]
            return choice(platform_bot_map[platform or event.platform])
        case SS.PLATFORM_NTH:
            return platform_bot_map[platform or event.platform][index]
        case SS.PLATFORM_RANDOM:
            return choice(platform_bot_map[platform or event.platform])
        case SS.PREFS_ANY:
            if prefs := cfg.bot_prefs:
                result = bots.key_at(prefs - 1)
            else:
                async with bots_lock:
                    return choice(tuple(filter(None.__ne__, bots)))
        case SS.NTH_ANY:
            result = bots.key_at(index)
        case SS.RANDOM_ANY:
            async with bots_lock:
                container = tuple(filter(None.__ne__, bots))
            return choice(container)
        case SS.FRIEND:
            if not cfg.cache_conv:
                raise RuntimeError(_("router.select_bot.403"))
            if not conv_id:
                conv_id = getattr(event, "user_id", None)
            if not platform:
                platform = event.platform
            try:
                async with friend_conv_lock:
                    if prefs := cfg.bot_prefs:
                        data_set = set(friends[platform][conv_id])
                        async with bots_lock:
                            return [v for v in bots if v in data_set][min(prefs, len(data_set) - 1)]
                    return choice(friends[platform][conv_id])
            except KeyError as e:
                raise KeyError(_("router.select_bot.user404") % {"platform": platform, "conv_id": conv_id})
        case SS.FRIEND_NTH:
            if not cfg.cache_conv:
                raise RuntimeError(_("router.select_bot.403"))
            if not conv_id:
                conv_id = getattr(event, "user_id", None)
            if not platform:
                platform = event.platform
            try:
                async with friend_conv_lock:
                    return friends[platform][conv_id][index]
            except KeyError as e:
                raise KeyError(_("router.select_bot.user404") % {"platform": platform, "conv_id": conv_id})
        case SS.FRIEND_RANDOM:
            if cfg.cache_conv:
                if not conv_id:
                    conv_id = getattr(event, "user_id", None)
                if not platform:
                    platform = event.platform
                try:
                    async with friend_conv_lock:
                        return choice(friends[platform][conv_id])
                except KeyError as e:
                    raise KeyError(_("router.select_bot.user404") % {"platform": platform, "conv_id": conv_id})
            raise RuntimeError(_("router.select_bot.403"))
        case SS.GROUP:
            if not cfg.cache_conv:
                raise RuntimeError(_("router.select_bot.403"))
            if not conv_id:
                conv_id = getattr(event, "group_id", None)
            if not platform:
                platform = event.platform
            try:
                async with group_conv_lock:
                    if prefs := cfg.bot_prefs:
                        data_set = set(groups[platform][conv_id])
                        async with bots_lock:
                            return [v for v in bots if v in data_set][min(prefs, len(data_set) - 1)]
                    return choice(groups[platform][conv_id])
            except KeyError as e:
                raise KeyError(_("router.select_bot.group404") % {"platform": platform, "conv_id": conv_id})
        case SS.GROUP_NTH:
            if not cfg.cache_conv:
                raise RuntimeError(_("router.select_bot.403"))
            if not conv_id:
                conv_id = getattr(event, "group_id", None)
            if not platform:
                platform = event.platform
            try:
                async with group_conv_lock:
                    return groups[platform][conv_id][index]
            except KeyError as e:
                raise KeyError(_("router.select_bot.group404") % {"platform": platform, "conv_id": conv_id})
        case SS.GROUP_RANDOM:
            if cfg.cache_conv:
                if not conv_id:
                    conv_id = getattr(event, "group_id", None)
                if not platform:
                    platform = event.platform
                try:
                    async with group_conv_lock:
                        return groups[platform][conv_id][index]
                except KeyError as e:
                    raise KeyError(_("router.select_bot.group404") % {"platform": platform, "conv_id": conv_id})
            raise RuntimeError(_("router.select_bot.403"))

    if bots[result] is None:
        raise RuntimeError(_("router.api_closed"))
    return result

# endregion

from asyncio import create_task
from collections import defaultdict
from contextlib import suppress
from enum import Enum, auto
from functools import partial, wraps
from random import choice
from types import FunctionType
from typing import Literal, overload, _overload_dummy

from models.api import BaseEvent
from utils.misc import SetArray, get_arg_names

from ..api_service import call_api
from ..config import cfg
from ..i18n import _
from ..dispatcher import current_event
from .account import AccountAPI
from .group import GroupAPI
from .message import MessageAPI
from .private import PrivateAPI
from .support import SupportAPI

__all__ = ("API", "SS", "select_bot")


if cfg.cache_conv:
    groups: defaultdict[str, defaultdict[str, SetArray]] = defaultdict(partial(defaultdict, partial(SetArray, "i")))
    users: defaultdict[str, defaultdict[str, SetArray]] = defaultdict(partial(defaultdict, partial(SetArray, "i")))


class APIMeta(type):
    def __new__(cls, name, bases, namespace, **kwargs):
        new_class = super().__new__(cls, name, bases, namespace, **kwargs)

        methods_to_wrap = {}
        for attr_name, attr_value in namespace.items():
            if not attr_name.startswith("__") and attr_value.__class__ is FunctionType:
                methods_to_wrap[attr_name] = attr_value

        # 父类
        for base in bases:
            for attr_name in dir(base):
                if not attr_name.startswith("__"):
                    if (attr_value := getattr(base, attr_name)).__class__ is FunctionType and attr_name not in methods_to_wrap:
                        methods_to_wrap[attr_name] = attr_value

        # 处理
        for attr_name, attr_value in methods_to_wrap.items():
            if attr_value is _overload_dummy:

                @wraps(attr_value)
                def wrapper(*args, __name=attr_name, __args=get_arg_names(attr_value), **kwargs):
                    if event := current_event.get():
                        if (value := getattr(event, "user_id", None)) is not None:
                            kwargs.setdefault("user_id", value)
                        if (value := getattr(event, "group_id", None)) is not None:
                            kwargs.setdefault("group_id", value)
                        kwargs.setdefault("bot", event.bot_id)
                    for i, arg in enumerate(args):
                        kwargs[__args[i + 2]] = arg
                    return call_api(__name, **kwargs)

            else:

                @wraps(attr_value)
                def wrapper(*args, __name=attr_name, **kwargs):
                    if not kwargs.get("bot"):
                        try:
                            kwargs["bot"] = current_event.get().bot_id
                        except AttributeError as e:
                            raise RuntimeError(_("no_event_found_in_context")) from e
                    return call_api(__name, *args, **kwargs)

            setattr(new_class, attr_name, staticmethod(wrapper))

        return new_class


class API(AccountAPI, GroupAPI, MessageAPI, PrivateAPI, SupportAPI, metaclass=APIMeta):
    pass


# region API router
class SS(Enum):
    """API 实例选择策略，用于 `select_bot` 函数。

    Attributes:
        PREFS: 若配置项 `bot_prefs` 为 0 则随机选择接收到相同事件的实例；若指向的实例接收到该事件则采用，否则采用 `NTH`。
        NTH: 按配置文件顺序排序的收到该事件的实例中的第几个实例。
        UNORDERED_NTH: 接收到相同事件的第n个实例。
        RANDOM: 接收到相同事件的随机实例
        PLATFORM: 若配置项 `bot_prefs` 为 0 则随机选择相同平台的实例；若指向的实例为相同平台则采用，否则采用 `PLATFORM_NTH`。
        PLATFORM_NTH: 指定平台的第n个实例（基于配置文件顺序）。
        PLATFORM_RANDOM: 指定平台的随机实例。
        PREFS_ANY: 若配置项 `bot_prefs` 为 0 则选择随机实例，否则选择指向的实例。
        NTH_ANY: 第几个实例（基于配置文件顺序）。
        RANDOM_ANY: 随机实例。
        FRIEND: 若配置项 `bot_prefs` 为 0 则随机选择有指定好友的实例；若指向的实例有指定好友则采用，否则采用 `FRIEND_NTH`。
        FRIEND_NTH: 指定平台的有指定好友的第n个实例。
        FRIEND_RANDOM: 指定平台的有指定好友的随机实例。
        GROUP: 若配置项 `bot_prefs` 为 0 则随机选择有指定群的实例；若指向的实例有指定群则采用，否则采用 `GROUP_NTH`。
        GROUP_NTH: 指定平台的包含指定群聊的第n个实例
        GROUP_RANDOM: 指定平台的包含指定群聊的随机实例
    """

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


cfg.register(
    "bot_prefs",
    1,
    "脱离 Aha 事件上下文调用发送消息等 API 请求时偏好第几个 bot。支持负数（倒数），为 0 时随机选择。",
    module="aha",
)


async def init_conversations():
    from ..api_service import bots, call_api

    for i, v in bots.items():
        if v is None:
            continue

        g_task = create_task(call_api("get_group_list", bot=i))
        u_task = create_task(call_api("get_friends", bot=i))
        group_list = groups[v.platform]
        user_list = users[v.platform]

        with suppress(NotImplementedError):
            for u in await u_task:
                if (available_bots := user_list.get(u.user_id)) is None:
                    available_bots = user_list[u.user_id] = []
                available_bots.append(i)
        with suppress(NotImplementedError):
            for g in await g_task:
                if (available_bots := group_list.get(g.group_id)) is None:
                    available_bots = group_list[g.group_id] = []
                available_bots.append(i)

    return sum(len(i) for i in groups.values()), sum(len(i) for i in users.values())


@overload
def select_bot(strategy: Literal[SS.PREFS, SS.NTH, SS.UNORDERED_NTH], event: BaseEvent = None, *, index: int = 0) -> int: ...


@overload
def select_bot(strategy: Literal[SS.PLATFORM_RANDOM], event: BaseEvent = None, *, platform: str = None) -> int: ...


@overload
def select_bot(
    strategy: Literal[SS.PLATFORM, SS.PLATFORM_NTH], event: BaseEvent = None, *, platform: str = None, index: int = 0
) -> int: ...


@overload
def select_bot(
    strategy: Literal[SS.FRIEND, SS.GROUP, SS.FRIEND_NTH, SS.GROUP_NTH],
    event: BaseEvent = None,
    *,
    platform: str = None,
    conv_id: str = None,
    index: int = 0,
) -> int: ...


@overload
def select_bot(
    strategy: Literal[SS.FRIEND_RANDOM, SS.GROUP_RANDOM], event: BaseEvent = None, *, platform: str = None, conv_id: str = None
) -> int: ...


@overload
def select_bot(strategy: Literal[SS.NTH_ANY], *, index: int = 0) -> int: ...


@overload
def select_bot(strategy: Literal[SS.PREFS_ANY, SS.RANDOM, SS.RANDOM_ANY]) -> int: ...


def select_bot(strategy=SS.PREFS, event=None, *, index=0, platform=None, conv_id=None):
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

    from ..api_service import bots, deduplicators, platform_bot_map

    match strategy:
        case SS.PREFS:
            if not (prefs := cfg.bot_prefs):
                return choice(deduplicators[event.platform].services_of(event))
            if (result := bots.key_at(prefs if prefs < 0 else prefs - 1)) not in deduplicators[event.platform].cache[event]:
                result = deduplicators[event.platform].services_of(event)[index]
        case SS.NTH:
            try:
                lst = deduplicators[event.platform].services_of(event)
            except IndexError:
                raise RuntimeError(_("router.select_bot.event404"))
            lst.sort(key={value: idx for idx, value in enumerate(bots)}.get)
            result = lst[index]
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
            if not (prefs := cfg.bot_prefs):
                return choice(platform_bot_map[platform or event.platform])
            k, v = bots.item_at(prefs if prefs < 0 else prefs - 1)
            return (
                k if v and v.platform == (platform or event.platform) else platform_bot_map[platform or event.platform][index]
            )
        case SS.PLATFORM_NTH:
            return platform_bot_map[platform or event.platform][index]
        case SS.PLATFORM_RANDOM:
            return choice(platform_bot_map[platform or event.platform])
        case SS.PREFS_ANY:
            if not (prefs := cfg.bot_prefs):
                return choice(tuple(filter(None.__ne__, bots)))
            result = bots.key_at(prefs if prefs < 0 else prefs - 1)
        case SS.NTH_ANY:
            result = bots.key_at(index)
        case SS.RANDOM_ANY:
            return choice(tuple(filter(None.__ne__, bots)))
        case SS.FRIEND:
            if not cfg.cache_conv:
                raise RuntimeError(_("router.select_bot.403"))
            if not conv_id:
                conv_id = getattr(event, "user_id", None)
            if not platform:
                platform = event.platform
            try:
                if not (prefs := cfg.bot_prefs):
                    return choice(users[platform][conv_id])
                result = bots.key_at(prefs if prefs < 0 else prefs - 1)
                return result if result in users[platform][conv_id] else users[platform][conv_id][index]
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
                return users[platform][conv_id][index]
            except KeyError as e:
                raise KeyError(_("router.select_bot.user404") % {"platform": platform, "conv_id": conv_id})
        case SS.FRIEND_RANDOM:
            if cfg.cache_conv:
                if not conv_id:
                    conv_id = getattr(event, "user_id", None)
                if not platform:
                    platform = event.platform
                try:
                    return choice(users[platform][conv_id])
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
                if not (prefs := cfg.bot_prefs):
                    return choice(groups[platform][conv_id])
                result = bots.key_at(prefs if prefs < 0 else prefs - 1)
                return result if result in groups[platform][conv_id] else groups[platform][conv_id][index]
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
                    return groups[platform][conv_id][index]
                except KeyError as e:
                    raise KeyError(_("router.select_bot.group404") % {"platform": platform, "conv_id": conv_id})
            raise RuntimeError(_("router.select_bot.403"))

    if bots[result] is None:
        raise RuntimeError(_("router.api_closed"))
    return result


# endregion

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
from asyncio import as_completed, create_task
from time import time

from humanfriendly import parse_size

from config import cfg
from cores import Friend, GroupMemberInfo, Stranger
from ncatbot.core.message import GroupMessage, PrivateMessage
from services.apscheduler import scheduler
from services.ncatbot import bot

from . import SchMemLRUCache, TimeTrigger, async_cached, get_byte_length, get_cache, rm_schedules_by_meta


# region 正则表达式
def at(pattern: str = None):
    """@表达式，自带一个捕获组

    Args:
        pattern: 用于匹配 QQ 号的正则表达式，不传参则为任意数字。

    这是一个没有用途的函数。
    """

    return fr"\[CQ:at,qq=({pattern or r"\d+"})\]\s*?"


def at_or_int(pattern: str = None):
    """@表达式，也可以是纯QQ号，自带一个捕获组

    Args:
        pattern: 用于匹配 QQ 号的正则表达式，不传参则为任意数字。
    """

    return fr"(?:\[CQ:at,qq=)?({pattern or r"\d+"})(?:\])?\s*?"


def at_or_int_diff(pattern: str = None):
    """@表达式，也可以是纯QQ号，有两个捕获组
    - 可以通过判断第一个捕获组有没有值来检测是否是通过@返回的。
    - 第二个捕获组是 QQ 号。

    Args:
        pattern: 用于匹配 QQ 号的正则表达式，不传参则为任意数字。
    """

    return fr"(\[CQ:at,qq=)?({pattern or r"\d+"})(?:\])?\s*?"


# endregion


# region 从 msg 直接获取属性
def get_at(msg: GroupMessage | PrivateMessage, index=0):
    """获取消息中第 `index-1` 个被 @ 的人的 QQ 号

    这是一个没有用途的函数
    """

    count = 0
    for i, d in enumerate(msg.message):
        if i != 0 or d["data"].get("qq") != str(msg.self_id):
            if count == index:
                return d["qq"]
            count += 1
    return None


async def get_card_by_msg(msg: GroupMessage | PrivateMessage):
    """获取群成员名片，不存在时自动选择昵称"""
    return msg.sender.card or msg.sender.nickname


# endregion


# region API 工具
async def get_card(group_id, user_id, no_cache=False):
    """获取群成员名片，不存在时自动选择昵称"""
    return card if (card := (data := await get_group_member_info(group_id, user_id, no_cache)).card) else data.nickname


@async_cached(
    get_cache(
        SchMemLRUCache,
        maxsize=parse_size(cfg.get_config("nickname", "1MB", "cache", "从陌生人渠道获取昵称的缓存大小。该缓存定时清空。")),
    )
)
async def get_nickname(user_id):
    """获取陌生人昵称，不存在时返回QQ号"""
    return nickname if (nickname := (await get_stranger_info(user_id)).nickname.strip()) else str(user_id)


async def get_user_by_groups(user_id):
    """从所有群中查询群成员信息"""
    tasks = [create_task(get_group_member_list(g["group_id"], True)) for g in (await bot.api.get_group_list(True))["data"]]
    for task in as_completed(tasks):
        for member in await task:
            if member.user_id == user_id:
                for t in tasks:
                    t.cancel()
                return member


async def get_user_by_friend(user_id):
    """通过好友列表获取用户信息"""
    return next((i for i in await get_friend_list(True) if user_id == i.user_id), None)


@async_cached(
    get_cache(
        SchMemLRUCache,
        maxsize=parse_size(
            cfg.get_config("user_meta", "16MB", "cache", "从各种渠道获取用户元数据的缓存大小。该缓存定时清空。")
        ),
    ),
    ignore=lambda result, *_: not result or isinstance(result, Stranger) and result.nick is None,
)
async def get_user_by_search(user_id, group_id=None):
    """从陌生人、好友、所有群查询用户信息。

    Args:
        group_id: 指定群时优先从该群尝试获取信息。
    """
    if group_id:
        return next((i for i in await get_group_member_list(group_id, True) if user_id == i.user_id), None)
    if stranger_user := await get_stranger_info(user_id):
        return stranger_user
    if friend_user := await get_user_by_friend(user_id):
        return friend_user
    if user := await get_user_by_groups(user_id):
        return user


async def get_card_by_search(user_id, group_id=None, force_return_card=False):
    """获取群成员名片，不存在该成员时从陌生人、好友渠道获取昵称

    Args:
        force_return_card: 返回Tuple[群名片, 昵称]。
    """
    card = result.card if hasattr((result := await get_user_by_search(user_id, group_id)), "card") else None
    nickname = (result.nickname if hasattr(result, "nickname") else result.nick).strip() or user_id
    return (card, nickname) if force_return_card else card or nickname


async def get_level_by_search(user_id):
    """从陌生人、好友、群成员渠道获取用户等级"""
    if isinstance(result := await get_user_by_search(user_id), GroupMemberInfo):
        return result.qq_level
    return result.qqLevel if isinstance(result, Stranger) else result.level if isinstance(result, Friend) else None


async def is_admin(group_id, user_id):
    return any(m.user_id == user_id and m.role != "member" for m in (await get_group_member_list(group_id)))


# endregion


# region 封装 API，模拟正常客户端操作。
async def set_group_ban(group_id, user_id, seconds=0):
    """模拟正常客户端操作
    - 将禁言时长转为整分后通过定时任务解除禁言
    - 如果目标成员是管理则不禁言
    - 解禁时预先判断其是否被禁言
    """
    if (member := await get_group_member_info(group_id, user_id, True)).role == "member":
        if seconds:
            create_task(bot.api.set_group_ban(group_id, user_id, (seconds + 59) // 60 * 60))
            if seconds % 60 != 0:
                create_task(
                    scheduler.add_schedule(
                        bot.api.set_group_ban,
                        TimeTrigger(seconds),
                        args=(group_id, user_id, 0),
                        metadata={"user_id": user_id, "tag": "ban"},
                    )
                )
            return True
        elif member.shut_up_timestamp and member.shut_up_timestamp > time():
            create_task(bot.api.set_group_ban(group_id, user_id, 0))
            create_task(rm_schedules_by_meta({"tag": "ban", "user_id": user_id}, group_id))
            return True
    return False


async def set_group_add_request(flag: str, approve: bool, reason: str = None):
    if reason and get_byte_length(reason) > 60:
        raise ValueError("加群请求拒绝原因过长")
    else:
        return await bot.api.set_group_add_request(flag, approve, reason)


async def set_group_kick(group_id: int | str, user_id: int | str, is_ban=False):
    if user_id in {i.user_id for i in (await get_group_member_list(group_id, True)) if i.role == "member"}:
        return bool(await bot.api.set_group_kick(group_id, user_id, is_ban))
    return False


# endregion


# region 封装 API，返回数据类
async def get_group_member_info(group_id: int | str, user_id: int | str, no_cache=False):
    return GroupMemberInfo(**((await bot.api.get_group_member_info(group_id, user_id, no_cache))["data"] or {}))


async def get_group_member_list(group_id: int | str, no_cache=False):
    return [GroupMemberInfo(**d) for d in (await bot.api.get_group_member_list(group_id, no_cache))["data"]]


async def get_stranger_info(user_id: int | str):
    return Stranger(**((await bot.api.get_stranger_info(user_id))["data"] or {}))


async def get_friend_list(no_cache=False):
    return [Friend(**d) for d in (await bot.api.get_friend_list(no_cache))["data"]]


# endregion

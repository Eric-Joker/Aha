from asyncio import create_task
from typing import overload

from core.config import cfg
from core.router import SS, select_bot, current_event
from core.identity import aha_id2user
from models.api import Message
from models.msg import At


# region 正则表达式
def at_or_str(pattern: str = None):
    """返回一个可以匹配@或纯字符串的正则表达式，拥有一个捕获组

    Args:
        pattern: 用于匹配 user_id 的正则表达式，不传参则为任意字符。
    """

    return fr"(?:\[Aha:at,user_id=)?({pattern or r"\S+?"})(?:\])?\s*?"


# endregion
# region 从 msg 直接获取属性
def get_at(msg: Message, index=0):
    """获取消息中第 `index-1` 个被 @ 的 id

    这是一个没有用途的函数
    """

    count = 0
    for i, d in enumerate(msg.message):
        if i != 0 or isinstance(d, At) and d.user_id != str(msg.self_id):
            if count == index:
                return d.user_id
            count += 1
    return None


async def get_card_by_event(msg: Message):
    """获取群成员名片，不存在时自动选择昵称"""
    return msg.sender.card or msg.sender.nickname


# endregion
@overload
async def is_super(platform: str, user_id: str, /) -> bool: ...


@overload
async def is_super(user_id: int, /) -> bool:
    """
    Args:
        user_id (int): Aha ID.
    """


@overload
async def is_super() -> bool:
    """自动从上下文事件获取用户"""


async def is_super(arg1=None, arg2=None, /):
    if arg2:
        return any(arg2 == obj.user_id for obj in cfg.super if arg1 == obj.platform)
    if arg1:
        return any(u[1] == obj.user_id for obj in cfg.super for u in await aha_id2user(arg1) if u[0] == obj.platform)
    event = current_event.get()
    return any(event.user_id == obj.user_id for obj in cfg.super if event.platform == obj.platform)


async def post_msg_to_supers(msg: str):
    from core.api import API

    for s in cfg.super:
        create_task(API.send_private_msg(s.user_id, msg, bot=select_bot(SS.PLATFORM_NTH, platform=s.platform)))

from asyncio import create_task
from collections.abc import Sequence
from re import compile
from typing import Any, Literal

from models.api import Message
from models.msg import At, MsgSeg


# region re
def at_or_str(pattern: str = None):
    """返回一个可以匹配@或纯字符串的正则表达式，拥有一个捕获组

    Args:
        pattern: 用于匹配 user_id 的正则表达式，不传参则为任意字符。
    """

    return fr"(?:\[Aha:at,user_id=)?({pattern or r"\S+?"})(?:\])?\s*?"


# endregion
# region aha code
def escape_aha(text: str):
    """转义 Aha 码中的少数特殊字符为 HTML 实体"""
    return text.translate(str.maketrans({"&": "&amp;", "[": "&#91;", "]": "&#93;", ",": "&#44;"}))


def unescape_aha(text: str):
    """反转义 Aha 码"""
    return text.replace("&amp;", "&").replace("&#91;", "[").replace("&#93;", "]").replace("&#44;", ",")


AHA_CODE_PATTERN = compile(r"\[Aha:([^,\]]+)(?:,([^\]]+))?\]")


def aha_code2dict_list(string, pattern=AHA_CODE_PATTERN) -> list[dict[Literal["type", "data"], Any]]:
    """将 Aha 码字符串解析为字典列表"""
    result = []
    last_pos = 0
    # 遍历所有匹配的 Aha 码
    for match in pattern.finditer(string):
        # 处理 Aha 码之前的文本
        if text_before := string[last_pos : match.start()]:
            result.append(aha_code2dict_list(text_before, pattern))

        # 解析 Aha 码参数
        params = {}
        for param in (match[2] or "").split(","):
            if "=" in param:
                key, value = param.split("=", 1)
                params[key] = aha_code2dict_list(value, pattern)

        result.append({"type": match[1].lower(), "data": params})
        last_pos = match.end()

    # 处理最后一个 Aha 码之后的文本
    if text_after := string[last_pos:]:
        result.append(aha_code2dict_list(text_after, pattern))

    return result


def parse_aha_code(string):
    """将 Aha 码字符串解析为消息序列"""
    from models.msg import MessageChain

    chain = MessageChain()
    last_pos = 0
    # 遍历所有匹配的 Aha 码
    for match in AHA_CODE_PATTERN.finditer(string):
        # 处理 Aha 码之前的文本
        if text_before := string[last_pos : match.start()]:
            chain.append(unescape_aha(text_before))

        # 解析 Aha 码参数
        params = {}
        for param in (match[2] or "").split(","):
            if "=" in param:
                key, value = param.split("=", 1)
                params[key] = unescape_aha(value)

        chain.append(MessageChain.get_seg_class(match[1])(**params))
        last_pos = match.end()

    # 处理最后一个 Aha 码之后的文本
    if text_after := string[last_pos:]:
        chain.append(unescape_aha(text_after))

    return chain


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
async def post_msg_to_supers(msg: str | Sequence[MsgSeg | str] | MsgSeg | None = None):
    from core.api import API, SS, select_bot
    from core.config import cfg

    for s in cfg.super:
        create_task(API.send_private_msg(s.user_id, msg, bot=select_bot(SS.PLATFORM_NTH, platform=s.platform)))

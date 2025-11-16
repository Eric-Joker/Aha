from collections.abc import Sequence
from typing import TYPE_CHECKING, Any
from anyio import Path

from models.api import AudioFormat, Message, ReactionUser
from models.msg import Downloadable, File, Forward, MsgSeg

from .base import BaseAPI

if TYPE_CHECKING:
    from ..base import BaseBot


class BaseMessageAPI(BaseAPI):
    # region 消息发送
    async def send_msg(
        self: BaseBot,
        call_id,
        *,
        user_id: str | int = None,
        group_id: str | int = None,
        msg: str | Sequence[MsgSeg | str] | MsgSeg = None,
        at: str | int = None,
        reply: str | int = None,
        image: str | Path = None,
    ) -> str:
        """若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            msg: 不支持自动将 inline 格式字符串的转为消息数组。
            image: 接受路径或 URL。

        Returns:
            str: message_id
        """
        if group_id:
            return await self.send_group_msg(call_id, group_id, msg, at, reply, image)
        if user_id:
            return await self.send_private_msg(call_id, user_id, msg, at, reply, image)

    async def send_raw_msg(self: BaseBot, call_id, *, user_id: str | int = None, group_id: str | int = None, data: Any) -> str:
        """发送不经过 Aha 处理的原始消息。

        Returns:
            str: message_id
        """
        if group_id:
            return await self.send_group_raw_msg(call_id, group_id, data)
        if user_id:
            return await self.send_private_raw_msg(call_id, user_id, data)

    async def send_image(
        self: BaseBot, call_id, *, user_id: str | int = None, group_id: str | int = None, image: str | Path
    ) -> str:
        """发送图片消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            image: 接受路径或 URL。

        Returns:
            str: message_id
        """
        if group_id:
            return await self.send_group_image(call_id, group_id, image)
        if user_id:
            return await self.send_private_image(call_id, user_id, image)

    async def send_record(
        self: BaseBot, call_id, *, user_id: str | int = None, group_id: str | int = None, file: str | Path
    ) -> str:
        """发送语音消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            file: 接受路径或 URL。

        Returns:
            str: message_id
        """
        if group_id:
            return await self.send_group_record(call_id, group_id, file)
        if user_id:
            return await self.send_private_record(call_id, user_id, file)

    async def send_file(
        self: BaseBot, call_id, *, user_id: str | int = None, group_id: str | int = None, file: str | Path, name: str = None
    ) -> str:
        """发送文件消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            file: 接受路径或 URL。

        Returns:
            str: message_id
        """
        if group_id:
            return await self.send_group_file(call_id, group_id, file, name)
        if user_id:
            return await self.send_private_file(call_id, user_id, file, name)

    async def send_music(
        self: BaseBot,
        call_id,
        *,
        user_id: str | int = None,
        group_id: str | int = None,
        url: str,
        image: str | Path = None,
        audio: str = None,
        title: str = None,
        content: str = None,
    ) -> str:
        """发送音乐分享消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            url: 卡片跳转链接。
            audio: 媒体链接。
            image: 接受路径或 URL。

        Returns:
            str: message_id
        """
        if group_id:
            return await self.send_group_music(call_id, group_id, url, audio, title, content, image)
        if user_id:
            return await self.send_private_music(call_id, user_id, url, audio, title, content, image)

    async def send_forward_msg_by_id(
        self: BaseBot, call_id, *, user_id: str | int = None, group_id: str | int = None, messages: Sequence[str | int]
    ) -> str:
        """若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Returns:
            str: message_id
        """
        if group_id:
            return await self.send_group_forward_msg_by_id(call_id, group_id, messages)
        if user_id:
            return await self.send_private_forward_msg_by_id(call_id, user_id, messages)

    async def poke(self: BaseBot, call_id, *, user_id: str | int, group_id: str | int = None) -> None:
        """发送戳一戳消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息"""
        if group_id:
            return await self.group_poke(call_id, group_id, user_id)
        return await self.friend_poke(call_id, user_id)

    # endregion
    # region 消息获取

    async def get_msg(self, call_id, message_id: str | int) -> Message:
        raise NotImplementedError

    async def get_forward_msg(self, call_id, message_id: str | int) -> Forward:
        raise NotImplementedError

    async def get_file_src(self, call_id, msg_seg: Downloadable, record_format: AudioFormat = AudioFormat.MP3) -> str | bytes:
        """通过消息段获取文件的 URL，若无法获取 URL 则获取内容。

        Args:
            record_format (AudioFormat): 当 `msg_seg` 为 `Record` 类型时，可指定音频格式。
        """
        raise NotImplementedError

    async def get_file(self, call_id, file_id: str) -> File:
        """获取文件信息"""
        raise NotImplementedError

    # endregion
    async def get_reaction_users(self, call_id, message_id: str | int, emoji_id: str | int) -> list[ReactionUser]:
        """获取指定回应的详情"""
        raise NotImplementedError

    async def set_reaction(self, call_id, message_id: str | int, emoji_id: str | int, set: bool = True) -> None:
        """回应"""
        raise NotImplementedError

    async def delete_msg(self, call_id, message_id: str | int) -> None:
        """撤回消息"""
        raise NotImplementedError

    async def set_input_status(self, call_id, status: int) -> None:
        """设置输入状态

        Args:
            status (int): 状态码, 0 表示 "对方正在说话", 1 表示 "对方正在输入"
        """
        raise NotImplementedError

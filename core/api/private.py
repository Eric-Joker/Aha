from collections.abc import Sequence
from typing import Any
from anyio import Path

from models.api import MusicPlatform
from models.msg import MsgSeg


class PrivateAPI:
    # region 消息发送
    @staticmethod
    async def send_private_msg(
        user_id: str | int,
        msg: str | Sequence[MsgSeg] | MsgSeg = None,
        at: str | int = None,
        reply: str | int = None,
        image: str | Path = None,
        *,
        bot: int = None,
    ) -> str:
        """
        Args:
            image: 字符串类型可为路径、url、`base64://` 或 `data:image/` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_raw_msg(user_id: str | int, data: Any, *, bot: int = None) -> str:
        """发送不经过 Aha 处理的私聊原始消息。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_image(user_id: str | int, image: str | Path, *, bot: int = None) -> str:
        """发送私聊图片消息。

        Args:
            image: 字符串类型可为路径、url、`base64://` 或 `data:image/` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_record(user_id: str | int, file: str | Path, *, bot: int = None) -> str:
        """发送私聊语音消息。

        Args:
            file: 字符串类型可为路径、url、`base64://` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_dice(user_id: str | int, value: int = 1, *, bot: int = None) -> str:
        """发送私聊骰子消息。

        Args:
            value (int, optional): 骰子点数（暂不支持）. Defaults to 1.

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_rps(user_id: str | int, value: int = 1, *, bot: int = None) -> str:
        """发送私聊猜拳消息。

        Args:
            value (int, optional): 猜拳点数（暂不支持）. Defaults to 1.

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_file(user_id: str | int, file: str | Path, name: str = None, *, bot: int = None) -> str:
        """发送私聊文件消息。

        Args:
            file: 字符串类型可为路径、url、`base64://` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_music(user_id: str | int, platform: MusicPlatform, id: str | int, *, bot: int = None) -> str:
        """发送私聊平台音乐分享消息。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_custom_music(
        user_id: str | int,
        url: str,
        image: str | Path = None,
        audio: str = None,
        title: str = None,
        content: str = None,
        *,
        bot: int = None,
    ) -> str:
        """发送私聊非平台音乐分享消息。

        Args:
            url: 卡片跳转链接。
            audio: 媒体链接。
            image: 字符串类型可为路径、url、`base64://` 开头；字节类型只接受普通数据。


        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_forward_msg_by_id(user_id: str | int, messages: Sequence[str | int], *, bot: int = None) -> str:
        """
        Returns:
            str: message_id
        """

    @staticmethod
    async def friend_poke(user_id: str | int, *, bot: int = None):
        """私聊戳一戳"""

    # endregion

    @staticmethod
    async def upload_private_file(user_id: str | int, file: str, name: str, *, bot: int = None):
        pass

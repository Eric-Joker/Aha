from collections.abc import Sequence
from typing import Any, Literal
from anyio import Path

from models.api import Message
from models.msg import MsgSeg


class PrivateAPI:
    # region 消息发送
    @staticmethod
    async def send_private_msg(
        user_id: str | int,
        msg: str | Sequence[MsgSeg | str] | MsgSeg = None,
        at: str | int = None,
        reply: str | int = None,
        image: str | Path = None,
        *,
        bot: int = None,
    ) -> str:
        """
        Args:
            msg: 不支持自动将 inline 格式字符串的转为消息数组。
            image: 接受路径或 URL。

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
            image: 接受路径或 URL。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_record(user_id: str | int, file: str | Path, *, bot: int = None) -> str:
        """发送私聊语音消息。

        Args:
            file: 接受路径或 URL。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_dice(user_id: str | int, value: int = 1, *, bot: int = None) -> str:
        """发送私聊骰子消息。

        Args:
            value (int, optional): 骰子点数. Defaults to 1.

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_rps(user_id: str | int, value: int = 1, *, bot: int = None) -> str:
        """发送私聊猜拳消息。

        Args:
            value (int, optional): 猜拳点数. Defaults to 1.

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_file(user_id: str | int, file: str | Path, name: str = None, *, bot: int = None) -> str:
        """发送私聊文件消息。

        Args:
            file: 接受路径或 URL。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_platform_music(user_id: str | int, platform: Literal["qq", "163"], id: str | int, *, bot: int = None) -> str:
        """发送私聊平台音乐分享消息。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_private_music(
        user_id: str | int,
        url: str,
        audio: str = None,
        title: str = None,
        content: str = None,
        image: str | Path = None,
        *,
        bot: int = None,
    ) -> str:
        """发送私聊音乐分享消息。

        Args:
            url: 卡片跳转链接。
            audio: 媒体链接。
            image: 接受路径或 URL。


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
    async def get_private_msg_history(
        user_id: str | int, message_seq: str | int, number: int = 20, reverseOrder: bool = False, *, bot: int = None
    ) -> list[Message]:
        pass

    @staticmethod
    async def upload_private_file(user_id: str | int, file: str, name: str, *, bot: int = None):
        pass

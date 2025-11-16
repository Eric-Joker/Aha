from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal, overload

from anyio import Path

from models.api import AudioFormat, RetrievedMessage, ReactionUser
from models.msg import Downloadable, File, Forward, MsgSeg


class MessageAPI:
    # region 消息发送接口快捷签名

    @overload
    @staticmethod
    async def send_msg(
        msg: str | Sequence[MsgSeg | str] | MsgSeg = None, at: str | int = None, reply: str | int = None, image: str | Path = None
    ) -> str:
        """
        Args:
            msg: 不支持自动将 inline 格式字符串的转为消息数组。
            image: 接受路径与 URL。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_raw_msg(data: Any) -> str:
        """发送不经过 Aha 处理的原始消息。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_image(image: str | Path) -> str:
        """发送图片消息。

        Args:
            image: 接受路径或 URL。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_record(file: str | Path) -> str:
        """发送语音消息。

        Args:
            file: 接受路径或 URL。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_dice(value: int = 1) -> str:
        """发送骰子消息。

        Args:
            value (int, optional): 骰子点数. Defaults to 1.

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_rps(value: int = 1) -> str:
        """发送猜拳消息。

        Args:
            value (int, optional): 猜拳点数. Defaults to 1.

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_file(file: str | Path, name: str = None) -> str:
        """发送文件消息。

        Args:
            file: 接受路径或 URL。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_platform_music(platform: Literal["qq", "163"], id: str | int) -> str:
        """发送平台音乐分享消息。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_music(
        url: str, image: str | Path = None, audio: str = None, title: str = None, content: str = None
    ) -> str:
        """发送音乐分享消息。

        Args:
            url: 卡片跳转链接。
            audio: 媒体链接。
            image: 接受路径或 URL。


        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_forward_msg_by_id(messages: Sequence[str | int]) -> str:
        """
        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def poke():
        """发送戳一戳消息"""

    # endregion

    # region 消息发送接口完整签名
    @overload
    @staticmethod
    async def send_msg(
        *,
        user_id: str | int = None,
        group_id: str | int = None,
        msg: str | Sequence[MsgSeg | str] | MsgSeg = None,
        at: str | int = None,
        reply: str | int = None,
        image: str | Path = None,
        bot: int = None,
    ) -> str:
        """若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            msg: 不支持自动将 inline 格式字符串的转为消息数组。
            image: 接受路径与 URL。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_raw_msg(*, user_id: str | int = None, group_id: str | int = None, data: Any, bot: int = None) -> str:
        """发送不经过 Aha 处理的原始消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_image(*, user_id: str | int = None, group_id: str | int = None, image: str | Path, bot: int = None) -> str:
        """发送图片消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            image: 接受路径或 URL。
        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_record(*, user_id: str | int = None, group_id: str | int = None, file: str | Path, bot: int = None) -> str:
        """发送语音消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            file: 接受路径或 URL。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_dice(*, user_id: str | int = None, group_id: str | int = None, value: int = 1, bot: int = None) -> str:
        """发送骰子消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            value (int, optional): 骰子点数. Defaults to 1.

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_rps(*, user_id: str | int = None, group_id: str | int = None, value: int = 1, bot: int = None) -> str:
        """发送猜拳消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            value (int, optional): 猜拳点数. Defaults to 1.

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_file(
        *, user_id: str | int = None, group_id: str | int = None, file: str | Path, name: str = None, bot: int = None
    ) -> str:
        """发送文件消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            file: 接受路径或 URL。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_platform_music(
        *, user_id: str | int = None, group_id: str | int = None, platform: Literal["qq", "163"], id: str | int, bot: int = None
    ) -> str:
        """发送平台音乐分享消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_music(
        *,
        user_id: str | int = None,
        group_id: str | int = None,
        url: str,
        audio: str = None,
        title: str = None,
        content: str = None,
        image: str | Path = None,
        bot: int = None,
    ) -> str:
        """发送音乐分享消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            url: 卡片跳转链接。
            audio: 媒体链接。
            image: 接受路径或 URL。


        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_forward_msg_by_id(
        *, user_id: str | int = None, group_id: str | int = None, messages: Sequence[str | int], bot: int = None
    ) -> str:
        """若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def poke(*, user_id: str | int, group_id: str | int = None, bot: int = None):
        """发送戳一戳消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息"""

    # endregion
    # region 消息获取
    @staticmethod
    async def get_msg(message_id: str | int, *, bot: int = None) -> RetrievedMessage:
        pass

    @staticmethod
    async def get_forward_msg(message_id: str | int, *, bot: int = None) -> Forward:
        pass

    @staticmethod
    async def get_file_src(msg_seg: Downloadable, record_format: AudioFormat = AudioFormat.MP3, *, bot: int = None) -> str | bytes:
        """通过消息段获取文件的 URL，若无法获取 URL 则获取内容。

        Args:
            record_format (AudioFormat): 当 `msg_seg` 为 `Record` 类型时，可指定音频格式。
        """

    @staticmethod
    async def get_file(file_id: str, *, bot: int = None) -> File:
        """获取 `File` 消息段形式的文件信息"""
    # endregion

    @staticmethod
    async def get_reaction_users(self, call_id, message_id: str | int, emoji_id: str | int) -> list[ReactionUser]:
        """获取指定回应的详情"""

    @staticmethod
    async def set_reaction(self, call_id, message_id: str | int, emoji_id: str | int, set: bool = True):
        """回应"""

    @staticmethod
    async def delete_msg(message_id: str | int):
        """撤回消息"""

    @staticmethod
    async def set_input_status(status: int, *, bot: int = None):
        """设置输入状态

        Args:
            status (int): 状态码, 0 表示 "对方正在说话", 1 表示 "对方正在输入"
        """

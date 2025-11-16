from collections.abc import Sequence
from typing import Any, overload

from anyio import Path

from models.api import AudioFormat, EmojiLike, Message, MusicPlatform
from models.msg import Downloadable, File, Forward, MsgSeg


class MessageAPI:
    # region 消息发送接口快捷签名

    @overload
    @staticmethod
    async def send_msg(
        msg: str | Sequence[MsgSeg] | MsgSeg = None, at: str | int = None, reply: str | int = None, image: str | Path = None
    ) -> str:
        """
        Args:
            msg: 不支持自动将 inline 格式字符串的转为消息数组。
            image: 字符串类型可为路径、url、`base64://` 或 `data:image/` 开头；字节类型只接受普通数据。

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
            image: 字符串类型可为路径、url、`base64://` 或 `data:image/` 开头。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_record(file: str | Path) -> str:
        """发送语音消息。

        Args:
            file: 字符串类型可为路径、url、`base64://` 开头。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_dice(value: int = 1) -> str:
        """发送骰子消息。

        Args:
            value (int, optional): 骰子点数（暂不支持）. Defaults to 1.

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_rps(value: int = 1) -> str:
        """发送猜拳消息。

        Args:
            value (int, optional): 猜拳点数（暂不支持）. Defaults to 1.

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_file(file: str | Path, name: str = None) -> str:
        """发送文件消息。

        Args:
            file: 字符串类型可为路径、url、`base64://` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_music(platform: MusicPlatform, id: str | int) -> str:
        """发送平台音乐分享消息。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_custom_music(
        url: str, image: str | Path = None, audio: str = None, title: str = None, content: str = None
    ) -> str:
        """发送非平台音乐分享消息。

        Args:
            url: 卡片跳转链接。
            audio: 媒体链接。
            image: 字符串类型可为路径、url、`base64://` 开头；字节类型只接受普通数据。


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
        """发送戳一戳消息。"""

    # endregion

    # region 消息发送接口完整签名
    @overload
    @staticmethod
    async def send_msg(
        *,
        user_id: str | int = None,
        group_id: str | int = None,
        msg: str | Sequence[MsgSeg] | MsgSeg = None,
        at: str | int = None,
        reply: str | int = None,
        image: str | Path = None,
        bot: int = None,
    ) -> str:
        """若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            msg: 不支持自动将 inline 格式字符串的转为消息数组。
            image: 字符串类型可为路径、url、`base64://` 或 `data:image/` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_raw_data(*, user_id: str | int = None, group_id: str | int = None, data: Any, bot: int = None) -> str:
        """发送不经过 Aha 处理的原始消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_image(*, user_id: str | int = None, group_id: str | int = None, image: str | Path, bot: int = None) -> str:
        """发送图片消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            image: 字符串类型可为路径、url、`base64://` 或 `data:image/` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_record(*, user_id: str | int = None, group_id: str | int = None, file: str | Path, bot: int = None) -> str:
        """发送语音消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            file: 字符串类型可为路径、url、`base64://` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_dice(*, user_id: str | int = None, group_id: str | int = None, value: int = 1, bot: int = None) -> str:
        """发送骰子消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            value (int, optional): 骰子点数（暂不支持）. Defaults to 1.

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_rps(*, user_id: str | int = None, group_id: str | int = None, value: int = 1, bot: int = None) -> str:
        """发送猜拳消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            value (int, optional): 猜拳点数（暂不支持）. Defaults to 1.

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
            file: 字符串类型可为路径、url、`base64://` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_music(
        *, user_id: str | int = None, group_id: str | int = None, platform: MusicPlatform, id: str | int, bot: int = None
    ) -> str:
        """发送平台音乐分享消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Returns:
            str: message_id
        """

    @overload
    @staticmethod
    async def send_custom_music(
        *,
        user_id: str | int = None,
        group_id: str | int = None,
        url: str,
        image: str | Path = None,
        audio: str = None,
        title: str = None,
        content: str = None,
        bot: int = None,
    ) -> str:
        """发送非平台音乐分享消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            url: 卡片跳转链接。
            audio: 媒体链接。
            image: 字符串类型可为路径、url、`base64://` 开头；字节类型只接受普通数据。


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
        """发送戳一戳消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。"""

    # endregion

    # region 通用消息接口
    @staticmethod
    async def send_msg(*, user_id=None, group_id=None, msg=None, at=None, reply=None, image=None, bot=None) -> str:
        pass

    @staticmethod
    async def send_unescape_text(*, user_id=None, group_id=None, text, bot=None) -> str:
        pass

    @staticmethod
    async def send_image(*, user_id=None, group_id=None, image, bot=None) -> str:
        pass

    @staticmethod
    async def send_record(*, user_id=None, group_id=None, file, bot=None) -> str:
        pass

    @staticmethod
    async def send_dice(*, user_id=None, group_id=None, value=1, bot=None) -> str:
        pass

    @staticmethod
    async def send_rps(*, user_id=None, group_id=None, value=1, bot=None) -> str:
        pass

    @staticmethod
    async def send_file(*, user_id=None, group_id=None, file, name=None, bot=None) -> str:
        pass

    @staticmethod
    async def send_music(*, user_id=None, group_id=None, platform, id, bot=None) -> str:
        pass

    @staticmethod
    async def send_custom_music(
        *, user_id=None, group_id=None, url, image=None, audio=None, title=None, content=None, bot=None
    ) -> str:
        pass

    @staticmethod
    async def send_forward_msg_by_id(*, user_id=None, group_id=None, messages, bot=None) -> str:
        pass

    @staticmethod
    async def poke(*, user_id, group_id=None, bot=None):
        pass

    @staticmethod
    async def delete_msg(message_id: str | int, *, bot: int = None):
        """撤回消息、删除消息"""

    @staticmethod
    async def set_msg_emoji_like(message_id: str | int, emoji_id: str | int, set: bool = True, *, bot: int = None):
        """贴表情"""

    # endregion

    # region 消息获取
    @staticmethod
    async def get_group_msg_history(
        group_id: str | int, message_seq: str | int, number: int = 20, reverseOrder: bool = False, *, bot: int = None
    ) -> list[Message]:
        pass

    @staticmethod
    async def get_msg(message_id: str | int, *, bot: int = None) -> Message:
        pass

    @staticmethod
    async def get_forward_msg(message_id: str | int, *, bot: int = None) -> Forward:
        pass

    @staticmethod
    async def get_friend_msg_history(
        user_id: str | int, message_seq: str | int, number: int = 20, reverseOrder: bool = False, *, bot: int = None
    ) -> list[Message]:
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

    @staticmethod
    async def fetch_emoji_like(
        message_id: str | int, emoji_id: str | int, emoji_type: str | int, *, bot: int = None
    ) -> list[EmojiLike]:
        """获取贴表情详情"""

    # endregion

    @staticmethod
    async def set_input_status(status: int, *, bot: int = None):
        """设置输入状态

        Args:
            status (int): 状态码, 0 表示 "对方正在说话", 1 表示 "对方正在输入"
        """

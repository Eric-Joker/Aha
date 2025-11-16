
from anyio import Path

from models.api import AudioFormat, EmojiLike, Message, MusicPlatform
from models.msg import Forward, Image, Record

from .base import BaseAPI


class BaseMessageAPI(BaseAPI):
    # region 消息发送
    async def send_msg(
        self,
        call_id,
        *,
        user_id: str | int = None,
        group_id: str | int = None,
        msg: str | list | dict = None,
        at: str | int = None,
        reply: str | int = None,
        image: str | Path = None,
    ) -> str:
        """若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            image: 字符串类型可为路径、url、`base64://` 或 `data:image/` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_unescape_text(self, call_id, *, user_id: str | int = None, group_id: str | int = None, text: str) -> str:
        """发送不转义的文本消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_image(
        self, call_id, *, user_id: str | int = None, group_id: str | int = None, image: str | Path
    ) -> str:
        """发送图片消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            image: 字符串类型可为路径、url、`base64://` 或 `data:image/` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_record(
        self, call_id, *, user_id: str | int = None, group_id: str | int = None, file: str | Path
    ) -> str:
        """发送语音消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            file: 字符串类型可为路径、url、`base64://` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_dice(self, call_id, *, user_id: str | int = None, group_id: str | int = None, value: int = 1) -> str:
        """发送骰子消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            value (int, optional): 骰子点数（暂不支持）. Defaults to 1.

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_rps(self, call_id, *, user_id: str | int = None, group_id: str | int = None, value: int = 1) -> str:
        """发送猜拳消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            value (int, optional): 猜拳点数（暂不支持）. Defaults to 1.

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_file(
        self, call_id, *, user_id: str | int = None, group_id: str | int = None, file: str | Path, name: str = None
    ) -> str:
        """发送文件消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            file: 字符串类型可为路径、url、`base64://` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_music(
        self, call_id, *, user_id: str | int = None, group_id: str | int = None, platform: MusicPlatform, id: str | int
    ) -> str:
        """发送平台音乐分享消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_custom_music(
        self,
        *,
        user_id: str | int = None,
        group_id: str | int = None,
        url: str,
        image: str | Path = None,
        audio: str = None,
        title: str = None,
        content: str = None,
    ) -> str:
        """发送非平台音乐分享消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Args:
            url: 卡片跳转链接。
            audio: 媒体链接。
            image: 字符串类型可为路径、url、`base64://` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_forward_msg(
        self, call_id, *, user_id: str | int = None, group_id: str | int = None, forward: Forward
    ) -> str:
        """发送合并转发消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_forward_msg_by_id(
        self, call_id, *, user_id: str | int = None, group_id: str | int = None, messages: list[str | int]
    ) -> str:
        """若 `group_id` 有值则发送群聊消息，否则发送私聊消息。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def poke(self, call_id, *, user_id: str | int, group_id: str | int = None):
        """发送戳一戳消息。若 `group_id` 有值则发送群聊消息，否则发送私聊消息。"""
        raise NotImplementedError

    async def set_msg_emoji_like(self, call_id, message_id: str | int, emoji_id: str | int, set: bool = True):
        """贴表情"""
        raise NotImplementedError

    # endregion

    # region 消息获取
    async def get_group_msg_history(
        self, call_id, group_id: str | int, message_seq: str | int, number: int = 20, reverseOrder: bool = False
    ) -> list[Message]:
        raise NotImplementedError

    async def get_msg(self, call_id, message_id: str | int) -> Message:
        raise NotImplementedError

    async def get_forward_msg(self, call_id, message_id: str | int) -> Forward:
        raise NotImplementedError

    async def get_friend_msg_history(
        self, call_id, user_id: str | int, message_seq: str | int, number: int = 20, reverseOrder: bool = False
    ) -> list[Message]:
        raise NotImplementedError

    async def get_record(
        self, call_id, file: str = None, file_id: str = None, out_format: AudioFormat = AudioFormat.MP3
    ) -> Record:
        """获取语音文件"""
        raise NotImplementedError

    async def get_image(self, call_id, file: str = None, file_id: str = None) -> Image:
        """获取图片文件"""
        raise NotImplementedError

    async def fetch_emoji_like(
        self, call_id, message_id: str | int, emoji_id: str | int, emoji_type: str | int
    ) -> list[EmojiLike]:
        """获取贴表情详情"""
        raise NotImplementedError

    # endregion

    async def delete_msg(self, call_id, message_id: str | int):
        """撤回消息、删除消息"""
        raise NotImplementedError

    async def set_input_status(self, call_id, status: int):
        """设置输入状态

        Args:
            status (int): 状态码, 0 表示 "对方正在说话", 1 表示 "对方正在输入"
        """
        raise NotImplementedError

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal
from anyio import Path

from models.api import EssenceMessage, GroupFiles, GroupInfo, GroupMemberInfo, GroupMembers, Message
from models.msg import MsgSeg

if TYPE_CHECKING:
    from bots.napcat import GroupHonor, HonorType


class GroupAPI:
    # region 群聊消息发送
    @staticmethod
    async def send_group_msg(
        group_id: str | int,
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
    async def send_group_raw_msg(group_id: str | int, data: Any, *, bot: int = None) -> str:
        """发送不经过 Aha 处理的群聊原始消息。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_group_image(group_id: str | int, image: str | Path, *, bot: int = None) -> str:
        """发送群聊图片消息。

        Args:
            image: 接受路径或 URL。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_group_record(group_id: str | int, file: str | Path, *, bot: int = None) -> str:
        """发送群聊语音消息。

        Args:
            file: 接受路径或 URL。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_group_dice(group_id: str | int, value: int = 1, *, bot: int = None) -> str:
        """发送群聊骰子消息。

        Args:
            value (int, optional): 骰子点数. Defaults to 1.

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_group_rps(group_id: str | int, value: int = 1, *, bot: int = None) -> str:
        """发送群聊猜拳消息。

        Args:
            value (int, optional): 猜拳点数. Defaults to 1.

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_group_file(group_id: str | int, file: str | Path, name: str = None, *, bot: int = None) -> str:
        """发送群聊文件消息。

        Args:
            file: 接受路径或 URL。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_group_platform_music(group_id: str | int, platform: Literal["qq", "163"], id: str | int, *, bot: int = None) -> str:
        """发送群聊平台音乐分享消息。

        Returns:
            str: message_id
        """

    @staticmethod
    async def send_group_music(
        group_id: str | int,
        url: str,
        audio: str = None,
        title: str = None,
        content: str = None,
        image: str | Path = None,
        *,
        bot: int = None,
    ) -> str:
        """发送群聊音乐分享消息。

        Args:
            url: 卡片跳转链接。
            audio: 媒体链接。
            image: 接受路径或 URL。


        Returns:
            str: message_id
        """

    @staticmethod
    async def send_group_forward_msg_by_id(group_id: str | int, messages: Sequence[str | int], *, bot: int = None) -> str:
        """
        Returns:
            str: message_id
        """

    @staticmethod
    async def group_poke(group_id: str | int, user_id: str | int, *, bot: int = None):
        """群聊戳一戳"""

    # endregion
    # region 群成员管理
    @staticmethod
    async def group_kick_members(
        group_id: str | int, user_ids: Sequence[str | int], reject_add_request: bool = False, *, bot: int = None
    ):
        """批量踢群成员"""

    @staticmethod
    async def group_kick(group_id: str | int, user_id: str | int, reject_add_request: bool = False, *, bot: int = None):
        """群踢人"""

    @staticmethod
    async def group_ban(group_id: str | int, user_id: str | int, duration: int = 0, *, bot: int = None) -> bool:
        """群禁言

        Args:
            duration (int, optional): 禁言秒数. Defaults to 30*60.
        """

    @staticmethod
    async def set_group_whole_ban(group_id: str | int, enable: bool, *, bot: int = None):
        """设置群全员禁言"""

    @staticmethod
    async def set_group_admin(group_id: str | int, user_id: str | int, enable: bool, *, bot: int = None):
        """设置群管理员"""

    @staticmethod
    async def group_leave(group_id: str | int, is_dismiss: bool = False, *, bot: int = None):
        """退群"""

    @staticmethod
    async def set_group_special_title(group_id: str | int, user_id: str | int, special_title: str, *, bot: int = None):
        """设置群专属头衔"""

    @staticmethod
    async def process_group_join_request(flag: str, approve: bool, reason: str | None = None, *, bot: int = None):
        """处理加群请求"""

    @staticmethod
    async def set_group_card(group_id: str | int, user_id: str | int, card: str, *, bot: int = None):
        """改群友的群昵称"""

    @staticmethod
    async def get_card(group_id: str | int, user_id: str | int, *, bot: int = None):
        """获取群成员名片，不存在时自动选择昵称"""

    @staticmethod
    async def is_admin(group_id: str | int, user_id: str | int, *, bot: int = None):
        pass

    # endregion

    # region 群消息管理
    @staticmethod
    async def get_group_msg_history(
        group_id: str | int, message_seq: str | int, number: int = 20, reverseOrder: bool = False, *, bot: int = None
    ) -> list[Message]:
        pass

    @staticmethod
    async def set_essence_msg(message_id: str | int, *, bot: int = None):
        """设置精华消息"""

    @staticmethod
    async def delete_essence_msg(message_id: str | int, *, bot: int = None):
        """删除精华消息"""

    @staticmethod
    async def get_essence_msg_list(group_id: str | int, *, bot: int = None) -> list[EssenceMessage]:
        """获取群精华消息列表"""

    # endregion

    # region 群文件
    @staticmethod
    async def move_group_file(
        group_id: str | int, file_id: str, current_parent_directory: str, target_parent_directory: str, *, bot: int = None
    ):
        """移动群文件"""

    @staticmethod
    async def trans_group_file(group_id: str | int, file_id: str, *, bot: int = None):
        """转存为永久文件"""

    @staticmethod
    async def rename_group_file(group_id: str | int, file_id: str, new_name: str, *, bot: int = None):
        """重命名群文件"""

    @staticmethod
    async def upload_group_file(group_id: str | int, file: str, name: str, folder, *, bot: int = None):
        """上传群文件"""

    @staticmethod
    async def create_group_file_folder(group_id: str | int, folder_name: str, *, bot: int = None):
        """创建群文件文件夹"""

    @staticmethod
    async def group_file_folder_makedir(group_id: str | int, path: str, *, bot: int = None) -> str:
        """按路径创建群文件夹"""
        # 自定义函数, 按照路径创建群文件夹
        pass

    @staticmethod
    async def delete_group_file(group_id: str | int, file_id: str, *, bot: int = None):
        """删除群文件"""

    @staticmethod
    async def delete_group_folder(group_id: str | int, folder_id: str, *, bot: int = None):
        """删除群文件夹"""

    @staticmethod
    async def get_group_root_files(group_id: str | int, file_count: int = 50, *, bot: int = None) -> GroupFiles:
        """获取群根目录文件列表"""

    @staticmethod
    async def get_group_files_by_folder(
        group_id: str | int, folder_id: str, file_count: int = 50, *, bot: int = None
    ) -> GroupFiles:
        """获取文件夹内文件列表"""

    @staticmethod
    async def get_group_file_url(group_id: str | int, file_id: str, *, bot: int = None) -> str:
        """获取群文件URL"""

    # endregion

    # region 其它(用户功能)
    @staticmethod
    async def get_group_honor_info(group_id: str | int, type: HonorType = None, *, bot: int = None) -> GroupHonor:
        """获取群荣誉信息"""

    @staticmethod
    async def get_group_info(group_id: str | int, *, bot: int = None) -> GroupInfo:
        """获取群信息"""

    @staticmethod
    async def get_group_info_raw(group_id: str | int, *, bot: int = None) -> dict:
        """获取协议框架原始群信息数据"""

    @staticmethod
    async def get_group_member_info(group_id: str | int, user_id: str | int, *, bot: int = None) -> GroupMemberInfo:
        """获取群成员信息"""

    @staticmethod
    async def get_group_members(group_id: str | int, *, bot: int = None) -> GroupMembers:
        """获取群成员列表"""

    @staticmethod
    async def get_group_list(call_id, *, bot: int = None) -> list[GroupInfo]:
        """获取群列表"""

    @staticmethod
    async def get_user_by_groups(call_id, user_id: str | int, *, bot: int = None) -> GroupMemberInfo:
        """从所有群中查询群成员信息"""

    @staticmethod
    async def get_group_shut_list(group_id: str | int, *, bot: int = None) -> GroupMembers:
        """获取群禁言列表"""

    @staticmethod
    async def set_group_remark(group_id: str | int, remark: str, *, bot: int = None):
        """设置群备注"""

    @staticmethod
    async def set_group_sign(group_id: str | int, *, bot: int = None):
        """群签到"""

    # endregion

    # region 其它(管理员功能)
    @staticmethod
    async def set_group_avatar(group_id: str | int, file: str, *, bot: int = None):
        """设置群头像
        Args:
            file (str): 文件路径（只支持 url）
        """
        # TODO: 支持本地文件
        pass

    @staticmethod
    async def set_group_name(group_id: str | int, name: str, *, bot: int = None):
        """设置群名"""

    # endregion

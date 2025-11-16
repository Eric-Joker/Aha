
from anyio import Path

from models.api import (
    EssenceMessage,
    GroupChatActivity,
    GroupFiles,
    GroupInfo,
    GroupMemberInfo,
    GroupMemberList,
    HonorType,
    MusicPlatform,
)
from models.msg import Forward

from .base import BaseAPI


class BaseGroupAPI(BaseAPI):
    # region 消息发送
    async def send_group_msg(
        self,
        call_id,
        group_id: str | int,
        msg: str | list | dict = None,
        at: str | int = None,
        reply: str | int = None,
        image: str | Path = None,
    ) -> str:
        """
        Args:
            image: 字符串类型可为路径、url、`base64://` 或 `data:image/` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_unescape_text(self, call_id, group_id: str | int, text: str) -> str:
        """发送不转义的群聊文本消息。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_image(self, call_id, group_id: str | int, image: str | Path) -> str:
        """发送群聊图片消息。

        Args:
            image: 字符串类型可为路径、url、`base64://` 或 `data:image/` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_record(self, call_id, group_id: str | int, file: str | Path) -> str:
        """发送群聊语音消息。

        Args:
            file: 字符串类型可为路径、url、`base64://` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_dice(self, call_id, group_id: str | int, value: int = 1) -> str:
        """发送群聊骰子消息。

        Args:
            value (int, optional): 骰子点数（暂不支持）. Defaults to 1.

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_rps(self, call_id, group_id: str | int, value: int = 1) -> str:
        """发送群聊猜拳消息。

        Args:
            value (int, optional): 猜拳点数（暂不支持）. Defaults to 1.

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_file(self, call_id, group_id: str | int, file: str | Path, name: str = None) -> str:
        """发送群聊文件消息。

        Args:
            file: 字符串类型可为路径、url、`base64://` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_music(self, call_id, group_id: str | int, platform: MusicPlatform, id: str | int) -> str:
        """发送群聊平台音乐分享消息。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_custom_music(
        self, group_id: str | int, url: str, image: str | Path = None, audio: str = None, title: str = None, content: str = None
    ) -> str:
        """发送群聊非平台音乐分享消息。

        Args:
            url: 卡片跳转链接。
            audio: 媒体链接。
            image: 字符串类型可为路径、url、`base64://` 开头；字节类型只接受普通数据。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_forward_msg(self, call_id, group_id: str | int, forward: Forward) -> str:
        """发送群聊合并转发消息。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_forward_msg_by_id(self, call_id, group_id: str | int, messages: list[str | int]) -> str:
        """
        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def group_poke(self, call_id, group_id: str | int, user_id: str | int):
        """群聊戳一戳"""
        raise NotImplementedError

    # endregion

    # region 群成员管理
    async def set_group_kick_members(self, call_id, group_id: str | int, user_id: str | int, reject_add_request: bool = False):
        """设置群成员踢人"""
        raise NotImplementedError

    async def set_group_kick(self, call_id, group_id: str | int, user_id: str | int, reject_add_request: bool = False):
        """设置群踢人"""
        raise NotImplementedError

    async def set_group_ban(self, call_id, group_id: str | int, user_id: str | int, duration: int = 0) -> bool:
        """设置群禁言

        Args:
            duration (int, optional): 禁言秒数. Defaults to 30*60.
        """
        raise NotImplementedError

    async def set_group_whole_ban(self, call_id, group_id: str | int, enable: bool):
        """设置群全员禁言"""
        raise NotImplementedError

    async def set_group_admin(self, call_id, group_id: str | int, user_id: str | int, enable: bool):
        """设置群管理员"""
        raise NotImplementedError

    async def set_group_leave(self, call_id, group_id: str | int, is_dismiss: bool = False):
        """退出群聊"""
        raise NotImplementedError

    async def set_group_special_title(self, call_id, group_id: str | int, user_id: str | int, special_title: str = ""):
        """设置群特殊头衔"""
        raise NotImplementedError

    async def set_group_add_request(self, call_id, flag: str, approve: bool, reason: str | None = None):
        """处理加群请求"""
        raise NotImplementedError

    async def set_group_card(self, call_id, group_id: str | int, user_id: str | int, card: str = ""):
        """改群友的群昵称"""
        raise NotImplementedError

    async def get_card(self, call_id, group_id: str | int, user_id: str | int):
        """获取群成员名片，不存在时自动选择昵称"""
        raise NotImplementedError

    async def is_admin(self, call_id, group_id: str | int, user_id: str | int):
        raise NotImplementedError

    # endregion

    # region 群消息管理
    async def set_essence_msg(self, call_id, message_id: str | int):
        """设置精华消息"""
        raise NotImplementedError

    async def delete_essence_msg(self, call_id, message_id: str | int):
        """删除精华消息"""
        raise NotImplementedError

    async def get_essence_msg_list(self, call_id, group_id: str | int) -> list[EssenceMessage]:
        """获取群精华消息列表"""
        raise NotImplementedError

    # endregion

    # region 群文件
    async def move_group_file(
        self, group_id: str | int, file_id: str, current_parent_directory: str, target_parent_directory: str
    ):
        """移动群文件"""
        raise NotImplementedError

    async def trans_group_file(self, call_id, group_id: str | int, file_id: str):
        """转存为永久文件"""
        raise NotImplementedError

    async def rename_group_file(self, call_id, group_id: str | int, file_id: str, new_name: str):
        """重命名群文件"""
        raise NotImplementedError

    async def get_file(self, call_id, file_id: str, file: str):
        """获取文件信息"""
        raise NotImplementedError

    async def upload_group_file(self, call_id, group_id: str | int, file: str, name: str, folder):
        """上传群文件"""
        raise NotImplementedError

    async def create_group_file_folder(self, call_id, group_id: str | int, folder_name: str):
        """创建群文件文件夹"""
        raise NotImplementedError

    async def group_file_folder_makedir(self, call_id, group_id: str | int, path: str) -> str:
        """按路径创建群文件夹"""
        # 自定义函数, 按照路径创建群文件夹
        raise NotImplementedError

    async def delete_group_file(self, call_id, group_id: str | int, file_id: str):
        """删除群文件"""
        raise NotImplementedError

    async def delete_group_folder(self, call_id, group_id: str | int, folder_id: str):
        """删除群文件夹"""
        raise NotImplementedError

    async def get_group_root_files(self, call_id, group_id: str | int, file_count: int = 50) -> GroupFiles:
        """获取群根目录文件列表"""
        raise NotImplementedError

    async def get_group_files_by_folder(self, call_id, group_id: str | int, folder_id: str, file_count: int = 50) -> GroupFiles:
        """获取文件夹内文件列表"""
        raise NotImplementedError

    async def get_group_file_url(self, call_id, group_id: str | int, file_id: str) -> str:
        """获取群文件URL"""
        raise NotImplementedError

    # endregion

    # region 其它(用户功能)
    async def get_group_honor_info(self, call_id, group_id: str | int, type: HonorType) -> GroupChatActivity:
        """获取群荣誉信息"""
        raise NotImplementedError

    async def get_group_info(self, call_id, group_id: str | int) -> GroupInfo:
        """获取群信息"""
        raise NotImplementedError

    async def get_group_info_ex(self, call_id, group_id: str | int) -> dict:
        """获取群扩展信息"""
        raise NotImplementedError

    async def get_group_member_info(self, call_id, group_id: str | int, user_id: str | int) -> GroupMemberInfo:
        """获取群成员信息"""
        raise NotImplementedError

    async def get_group_member_list(self, call_id, group_id: str | int) -> GroupMemberList:
        """获取群成员列表"""
        raise NotImplementedError

    async def get_group_list(self, call_id) -> list[GroupInfo]:
        """获取群列表"""
        raise NotImplementedError

    async def get_user_by_groups(self, call_id, user_id: str | int) -> GroupMemberInfo:
        """从所有群中查询群成员信息"""
        raise NotImplementedError

    async def get_group_shut_list(self, call_id, group_id: str | int) -> GroupMemberList:
        """获取群禁言列表"""
        raise NotImplementedError

    async def set_group_remark(self, call_id, group_id: str | int, remark: str):
        """设置群备注"""
        raise NotImplementedError

    async def set_group_sign(self, call_id, group_id: str | int):
        """群签到"""
        raise NotImplementedError

    async def send_group_sign(self, call_id, group_id: str | int):
        """发送群签到"""
        raise NotImplementedError

    # endregion

    # region 其它(管理员功能)
    async def set_group_avatar(self, call_id, group_id: str | int, file: str):
        """设置群头像
        Args:
            file (str): 文件路径（只支持 url）
        """
        # TODO: 支持本地文件
        raise NotImplementedError

    async def set_group_name(self, call_id, group_id: str | int, name: str):
        """设置群名"""
        raise NotImplementedError

    async def _send_group_notice(
        self,
        call_id,
        group_id: str | int,
        content: str,
        confirm_required: bool = False,
        image: str | None = None,
        is_show_edit_card: bool = False,
        pinned: bool = False,
    ):
        """发送群公告"""
        # TODO: 测试
        raise NotImplementedError

    # endregion

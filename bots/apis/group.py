from asyncio import as_completed, create_task
from collections.abc import Sequence
from typing import Any
from anyio import Path

from models.api import EssenceMessage, GroupFiles, GroupInfo, GroupMemberInfo, GroupMembers, Message
from models.msg import MsgSeg

from .base import BaseAPI


class BaseGroupAPI(BaseAPI):
    # region 消息发送
    async def send_group_msg(
        self,
        call_id,
        group_id: str | int,
        msg: str | Sequence[MsgSeg | str] | MsgSeg = None,
        at: str | int = None,
        reply: str | int = None,
        image: str | Path = None,
    ) -> str:
        """
        Args:
            msg: 不支持自动将 inline 格式字符串的转为消息数组。
            image: 接受路径或 URL。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_raw_msg(self, call_id, group_id: str | int, data: Any) -> str:
        """发送不经过 Aha 处理的群聊原始消息。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_image(self, call_id, group_id: str | int, image: str | Path) -> str:
        """发送群聊图片消息。

        Args:
            image: 接受路径或 URL。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_record(self, call_id, group_id: str | int, file: str | Path) -> str:
        """发送群聊语音消息。

        Args:
            file: 接受路径或 URL。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_file(self, call_id, group_id: str | int, file: str | Path, name: str = None) -> str:
        """发送群聊文件消息。

        Args:
            file: 接受路径或 URL。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_music(
        self, call_id, group_id: str | int, url: str, audio: str = None, title: str = None, content: str = None, image: str | Path = None
    ) -> str:
        """发送群聊音乐分享消息。

        Args:
            url: 卡片跳转链接。
            audio: 媒体链接。
            image: 接受路径或 URL。

        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def send_group_forward_msg_by_id(self, call_id, group_id: str | int, messages: Sequence[str | int]) -> str:
        """
        Returns:
            str: message_id
        """
        raise NotImplementedError

    async def group_poke(self, call_id, group_id: str | int, user_id: str | int) -> None:
        """群聊戳一戳"""
        raise NotImplementedError

    # endregion

    # region 群成员管理
    async def group_kick_members(
        self, call_id, group_id: str | int, user_ids: Sequence[str | int], reject_add_request: bool = False
    ) -> None:
        """批量踢群成员"""
        raise NotImplementedError

    async def group_kick(self, call_id, group_id: str | int, user_id: str | int, reject_add_request: bool = False) -> None:
        """群踢人"""
        raise NotImplementedError

    async def group_ban(self, call_id, group_id: str | int, user_id: str | int, duration: int = 0) -> bool:
        """群禁言

        Args:
            duration (int, optional): 禁言秒数. Defaults to 30*60.
        """
        raise NotImplementedError

    async def set_group_whole_ban(self, call_id, group_id: str | int, enable: bool) -> None:
        """设置群全员禁言"""
        raise NotImplementedError

    async def set_group_admin(self, call_id, group_id: str | int, user_id: str | int, enable: bool) -> None:
        """设置群管理员"""
        raise NotImplementedError

    async def group_leave(self, call_id, group_id: str | int, is_dismiss: bool = False) -> None:
        """退出群聊"""
        raise NotImplementedError

    async def set_group_special_title(self, call_id, group_id: str | int, user_id: str | int, special_title: str) -> None:
        """设置群专属头衔"""
        raise NotImplementedError

    async def process_group_join_request(self, call_id, flag: str, approve: bool, reason: str | None = None) -> None:
        """处理加群请求"""
        raise NotImplementedError

    async def set_group_card(self, call_id, group_id: str | int, user_id: str | int, card: str) -> None:
        """改群友的群昵称"""
        raise NotImplementedError

    async def get_card(self, call_id, group_id: str | int, user_id: str | int) -> None:
        """获取群成员名片，不存在时自动选择昵称"""
        raise NotImplementedError

    async def is_admin(self, call_id, group_id: str | int, user_id: str | int) -> None:
        raise NotImplementedError

    # endregion

    # region 群消息管理
    async def get_group_msg_history(
        self, call_id, group_id: str | int, message_seq: str | int, number: int = 20, reverseOrder: bool = False
    ) -> list[Message]:
        raise NotImplementedError

    async def set_essence_msg(self, call_id, message_id: str | int) -> None:
        """设置精华消息"""
        raise NotImplementedError

    async def delete_essence_msg(self, call_id, message_id: str | int) -> None:
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

    async def trans_group_file(self, call_id, group_id: str | int, file_id: str) -> None:
        """转存为永久文件"""
        raise NotImplementedError

    async def rename_group_file(self, call_id, group_id: str | int, file_id: str, new_name: str) -> None:
        """重命名群文件"""
        raise NotImplementedError

    async def upload_group_file(self, call_id, group_id: str | int, file: str, name: str, folder) -> None:
        """上传群文件"""
        raise NotImplementedError

    async def create_group_file_folder(self, call_id, group_id: str | int, folder_name: str) -> None:
        """创建群文件文件夹"""
        raise NotImplementedError

    async def group_file_folder_makedir(self, call_id, group_id: str | int, path: str) -> str:
        """按路径创建群文件夹"""
        # TODO: 自定义函数, 按照路径创建群文件夹
        raise NotImplementedError

    async def delete_group_file(self, call_id, group_id: str | int, file_id: str) -> None:
        """删除群文件"""
        raise NotImplementedError

    async def delete_group_folder(self, call_id, group_id: str | int, folder_id: str) -> None:
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
    async def get_group_info(self, call_id, group_id: str | int) -> GroupInfo:
        """获取群信息"""
        raise NotImplementedError

    async def get_group_info_raw(self, call_id, group_id: str | int) -> dict:
        """获取协议框架原始群信息数据"""
        raise NotImplementedError

    async def get_group_member_info(self, call_id, group_id: str | int, user_id: str | int) -> GroupMemberInfo:
        """获取群成员信息"""
        raise NotImplementedError

    async def get_group_members(self, call_id, group_id: str | int) -> GroupMembers:
        """获取群成员列表"""
        raise NotImplementedError

    async def get_group_list(self, call_id) -> list[GroupInfo]:
        """获取群列表"""
        raise NotImplementedError

    async def get_user_by_groups(self, call_id, user_id: str | int) -> GroupMemberInfo:
        """从所有群中查询群成员信息"""
        tasks = [create_task(self.get_group_members(self.gen_id(), g["group_id"])) for g in (await self.get_group_list())]
        for task in as_completed(tasks):
            for member in await task:
                if member.user_id == user_id:
                    for t in tasks:
                        t.cancel()
                    return member

    async def get_group_shut_list(self, call_id, group_id: str | int) -> GroupMembers:
        """获取群禁言列表"""
        raise NotImplementedError

    async def set_group_remark(self, call_id, group_id: str | int, remark: str) -> None:
        """设置群备注"""
        raise NotImplementedError

    async def set_group_sign(self, call_id, group_id: str | int) -> None:
        """群签到"""
        raise NotImplementedError

    # endregion

    # region 其它(管理员功能)
    async def set_group_avatar(self, call_id, group_id: str | int, file: str) -> None:
        """设置群头像
        Args:
            file (str): 文件路径（只支持 url）
        """
        # TODO: 支持本地文件
        raise NotImplementedError

    async def set_group_name(self, call_id, group_id: str | int, name: str) -> None:
        """设置群名"""
        raise NotImplementedError

    # endregion

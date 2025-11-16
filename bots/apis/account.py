from typing import Any

from models.api import (
    AccountStatus,
    CustomFaceList,
    Friend,
    FriendCategory,
    LoginInfo,
    RecentContact,
    Sex,
    Stranger,
    UserAccount,
)
from models.msg import File, Image

from .base import BaseAPI


class BaseAccountAPI(BaseAPI):
    # region 账号相关
    async def set_profile(self, call_id, nickname: str, personal_note: str, sex: Sex):
        raise NotImplementedError

    async def set_online_status(self, call_id, status: int, ext_status: int, battary_status: int):
        raise NotImplementedError

    async def set_avatar(self, call_id, file: str | File | Image):
        raise NotImplementedError

    async def set_self_longnick(self, call_id, long_nick: str):
        raise NotImplementedError

    async def get_login_info(self, call_id) -> LoginInfo:
        raise NotImplementedError

    async def get_status(self, call_id) -> AccountStatus:
        raise NotImplementedError

    # endregion

    # region 好友
    async def get_friends_with_category(self, call_id) -> list[FriendCategory]:
        raise NotImplementedError

    async def send_like(self, call_id, user_id: str | int, times: int = 1) -> dict[str, Any]:
        raise NotImplementedError

    async def set_friend_add_request(self, call_id, flag: str, approve: bool, remark: str | None = None):
        """设置通过好友请求

        Args:
            flag (str): 请求 flag
            approve (bool): 是否同意
            remark (str, optional): 通过后好友备注. Defaults to None.
        """
        raise NotImplementedError

    async def get_friend_list(self, call_id) -> list[Friend]:
        raise NotImplementedError

    async def get_user_by_friend(self, call_id, user_id: str | int) -> Friend:
        """通过好友列表获取用户信息"""
        raise NotImplementedError

    async def delete_friend(self, call_id, user_id: str | int, block: bool = True, both: bool = True):
        """删除好友
        Args:
            user_id (Union[str, int]): 目标用户 QQ 号
            block (bool, optional): 是否拉黑. Defaults to True.
            both (bool, optional): 是否双向删除. Defaults to True.
        """
        raise NotImplementedError

    async def set_friend_remark(self, call_id, user_id: str | int, remark: str):
        raise NotImplementedError

    # endregion

    # region 消息
    async def mark_group_msg_as_read(self, call_id, group_id: str | int):
        raise NotImplementedError

    async def mark_private_msg_as_read(self, call_id, user_id: str | int):
        raise NotImplementedError

    async def create_collection(self, call_id, raw_data: str, brief: str):
        raise NotImplementedError

    async def get_recent_contact(self, call_id) -> list[RecentContact]:
        raise NotImplementedError

    async def mark_all_as_read(self, call_id):
        raise NotImplementedError

    # endregion

    # region 群
    async def ask_share_group(self, call_id, group_id: str | int):
        raise NotImplementedError

    # endregion

    # region 其它
    async def get_stranger_info(self, call_id, user_id: str | int) -> Stranger:
        raise NotImplementedError

    async def get_card_by_search(
        self, call_id, user_id: str | int, group_id: str | int = None, force_return_card=False
    ) -> tuple[str | None, str] | str | None:
        """获取群成员名片，不存在该成员时从陌生人、好友渠道获取昵称

        Args:
            force_return_card: 返回Tuple[群名片, 昵称]。
        """
        raise NotImplementedError

    async def get_level_by_search(self, call_id, user_id) -> int | None:
        """从陌生人、好友、群成员渠道获取用户等级"""
        raise NotImplementedError

    async def get_nickname(self, call_id, user_id: str | int) -> str:
        """获取陌生人昵称，不存在时返回 uid。"""
        raise NotImplementedError

    async def fetch_custom_face(self, call_id, count: int = 48) -> CustomFaceList:
        raise NotImplementedError

    async def get_user_status(self, call_id, user_id: str | int) -> UserAccount:
        raise NotImplementedError

    # endregion

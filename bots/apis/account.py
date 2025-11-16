from typing import Any, TYPE_CHECKING

from models.api import Friend, FriendCategory, LoginInfo, Sex, Stranger, UserStatus
from models.api.account import LastestMsgs
from models.api.group import GroupMemberInfo
from models.msg import File, Image, Sticker

from .base import BaseAPI

if TYPE_CHECKING:
    from ..base import BaseBot


class BaseAccountAPI(BaseAPI):
    # region 账号相关
    async def set_profile(self, call_id, nickname: str, personal_note: str, sex: Sex) -> None:
        raise NotImplementedError

    async def set_online_status(self, call_id, status: int, ext_status: Any) -> None:
        raise NotImplementedError

    async def set_avatar(self, call_id, file: str | File | Image) -> None:
        raise NotImplementedError

    async def set_bio(self, call_id, content: str) -> None:
        raise NotImplementedError

    async def get_login_info(self, call_id) -> LoginInfo:
        raise NotImplementedError

    # endregion
    # region 好友
    async def get_friends_with_category(self, call_id) -> list[FriendCategory]:
        raise NotImplementedError

    async def send_like(self, call_id, user_id: str | int, times: int = 1) -> dict[str, Any]:
        raise NotImplementedError

    async def process_friend_add_request(self, call_id, flag: str, approve: bool, remark: str | None = None) -> None:
        """处理加好友请求

        Args:
            flag (str): 请求 flag
            approve (bool): 是否同意
            remark (str, optional): 通过后好友备注. Defaults to None.
        """
        raise NotImplementedError

    async def get_friends(self, call_id) -> frozenset[Friend]:
        raise NotImplementedError

    async def get_user_by_friend(self, call_id, user_id: str | int) -> Friend:
        """通过好友列表获取用户信息"""
        raise NotImplementedError

    async def delete_friend(self, call_id, user_id: str | int, block: bool = False, both: bool = True) -> None:
        """删除好友
        Args:
            user_id (Union[str, int]): 目标用户 QQ 号
            block (bool, optional): 是否拉黑
            both (bool, optional): 是否双向删除
        """
        raise NotImplementedError

    async def set_friend_remark(self, call_id, user_id: str | int, remark: str) -> None:
        raise NotImplementedError

    # endregion
    # region 消息
    async def get_last_msg_per_conv(self, call_id) -> list[LastestMsgs]:
        raise NotImplementedError

    async def mark_group_msg_as_read(self, call_id, group_id: str | int) -> None:
        raise NotImplementedError

    async def mark_private_msg_as_read(self, call_id, user_id: str | int) -> None:
        raise NotImplementedError

    async def mark_all_as_read(self, call_id) -> None:
        raise NotImplementedError

    # endregion
    # region 其它
    async def get_stranger_info(self, call_id, user_id: str | int) -> Stranger:
        raise NotImplementedError

    async def _get_user_by_search(self: BaseBot, _, user_id, group_id=None) -> Stranger | Friend | GroupMemberInfo | None:
        if group_id:
            return next(
                (i for i in await self.get_group_members(self.gen_id(), group_id) if user_id == i.user_id),
                None,
            )
        if stranger_user := await self.get_stranger_info(self.gen_id(), user_id):
            return stranger_user
        if friend_user := await self.get_user_by_friend(self.gen_id(), user_id):
            return friend_user
        if user := await self.get_user_by_groups(None, user_id):
            return user

    async def get_card_by_search(
        self: BaseBot, call_id, user_id: str | int, group_id: str | int = None, force_return_card=False
    ) -> tuple[str | None, str] | str | None:
        """获取群成员名片，不存在该成员时从陌生人、好友渠道获取昵称

        Args:
            force_return_card: 返回Tuple[群名片, 昵称]。
        """
        if (result := await self._get_user_by_search(None, user_id, group_id)) is None:
            return None
        card = getattr(result, "card", None)
        nickname = result.nickname.strip() or user_id
        return (card, nickname) if force_return_card else (card or nickname)

    async def get_nickname(self, call_id, user_id: str | int) -> str:
        """获取陌生人昵称，不存在时返回 uid"""
        raise NotImplementedError

    async def fetch_collected_stickers(self, call_id, count: int = 48) -> list[Sticker]:
        raise NotImplementedError

    async def get_user_status(self, call_id, user_id: str | int) -> UserStatus:
        raise NotImplementedError

    # endregion

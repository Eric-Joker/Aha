from typing import Any
from models.api import Friend, FriendCategory, LoginInfo, Sex, Stranger, UserStatus
from models.api.account import LastestMsgs
from models.msg import File, Image, Sticker


class AccountAPI:
    # region 账号相关
    @staticmethod
    async def set_profile(nickname: str, personal_note: str, sex: Sex, *, bot: int = None):
        pass

    @staticmethod
    async def set_online_status(status: int | str, ext_status: Any, *, bot: int = None):
        pass

    @staticmethod
    async def set_avatar(file: str | File | Image, *, bot: int = None):
        pass

    @staticmethod
    async def set_bio(content: str, *, bot: int = None):
        pass

    @staticmethod
    async def get_login_info(*, bot: int = None) -> LoginInfo:
        pass

    # endregion
    # region 好友
    @staticmethod
    async def get_friends_with_category(*, bot: int = None) -> list[FriendCategory]:
        pass

    @staticmethod
    async def process_friend_add_request(flag: str, approve: bool, remark: str | None = None, *, bot: int = None):
        """处理加好友请求

        Args:
            flag (str): 请求 flag
            approve (bool): 是否同意
            remark (str, optional): 通过后好友备注. Defaults to None.
        """

    @staticmethod
    async def get_friends(*, bot: int = None) -> frozenset[Friend]:
        pass

    @staticmethod
    async def get_user_by_friend(user_id: str | int, *, bot: int = None) -> Friend:
        """通过好友列表获取用户信息"""

    @staticmethod
    async def delete_friend(user_id: str | int, block: bool = True, both: bool = False, *, bot: int = None):
        """删除好友
        Args:
            user_id (Union[str, int]): 目标用户 QQ 号
            block (bool): 是否拉黑
            both (bool): 是否双向删除
        """

    @staticmethod
    async def set_friend_remark(user_id: str | int, remark: str, *, bot: int = None):
        pass

    # endregion
    # region 消息
    @staticmethod
    async def get_last_msg_per_conv(*, bot: int = None) -> list[LastestMsgs]:
        pass

    @staticmethod
    async def mark_group_msg_as_read(group_id: str | int, *, bot: int = None):
        pass

    @staticmethod
    async def mark_private_msg_as_read(user_id: str | int, *, bot: int = None):
        pass

    @staticmethod
    async def create_collection(raw_data: str, brief: str, *, bot: int = None):
        pass

    @staticmethod
    async def mark_all_as_read(*, bot: int = None):
        pass

    # endregion
    # region 其它
    @staticmethod
    async def get_stranger_info(user_id: str | int, *, bot: int = None) -> Stranger:
        pass

    @staticmethod
    async def get_card_by_search(
        user_id: str | int, group_id: str | int = None, force_return_card=False, *, bot: int = None
    ) -> tuple[str | None, str] | str | None:
        """获取群成员名片，不存在该成员时从陌生人、好友渠道获取昵称

        Args:
            force_return_card: 返回Tuple[群名片, 昵称]。
        """

    @staticmethod
    async def get_level_by_search(user_id, *, bot: int = None) -> int | None:
        """从陌生人、好友渠道获取用户等级"""

    @staticmethod
    async def get_nickname(user_id: str | int, *, bot: int = None) -> str:
        """获取陌生人昵称，不存在时返回 uid"""

    @staticmethod
    async def fetch_collected_stickers(count: int = 48, *, bot: int = None) -> list[Sticker]:
        pass

    @staticmethod
    async def get_user_status(user_id: str | int, *, bot: int = None) -> UserStatus:
        pass

    # endregion

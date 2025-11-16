from typing import TYPE_CHECKING

from models.api import (
    AccountStatus,
    CustomFaceList,
    Friend,
    FriendCategory,
    GroupMemberInfo,
    LoginInfo,
    RecentContact,
    Sex,
    Stranger,
    UserAccount,
)

from ...apis import BaseAccountAPI
from ..utils import Utils

if TYPE_CHECKING:
    from .. import NapCat


class AccountAPI(Utils, BaseAccountAPI):
    SEX_MAPPING = {Sex.MALE: 1, Sex.FEMALE: 2}

    # region 账号相关
    async def set_profile(self, call_id, nickname, personal_note, sex: Sex):
        return await self._call_api(
            call_id,
            "set_qq_profile",
            {"nickname": nickname, "personal_note": personal_note, "sex": self.SEX_MAPPING.get(sex, 3)},
        )

    async def set_online_status(self, call_id, status, ext_status, battary_status):
        return await self._call_api(
            call_id, "set_online_status", {"status": status, "ext_status": ext_status, "battary_status": battary_status}
        )

    async def set_avatar(self, call_id, file):
        return await self._call_api(
            call_id,
            "set_avatar",
            {"file": await self.prepare_upload(file if isinstance(file, str) else file.file, self.transport.local_srv)},
        )

    async def set_self_longnick(self, call_id, long_nick):
        return await self._call_api(call_id, "set_self_longnick", {"longNick": long_nick})

    async def get_login_info(self, call_id):
        return LoginInfo.model_validate(await self._call_api(call_id, "get_login_info"))

    async def get_status(self, call_id):
        return AccountStatus.model_validate(await self._call_api(call_id, "get_status"))

    # endregion

    # region 好友
    async def get_friends_with_category(self, call_id):
        return [FriendCategory.model_validate(cat) for cat in await self._call_api(call_id, "get_friends_with_category")]

    async def send_like(self, call_id, user_id, times=1):
        return await self._call_api(call_id, "send_like", {"user_id": user_id, "times": times})

    async def set_friend_add_request(self, call_id, flag, approve, remark=None):
        return await self._call_api(call_id, "set_friend_add_request", {"flag": flag, "approve": approve, "remark": remark})

    async def get_friend_list(self, call_id):
        return [Friend.model_validate(friend) for friend in await self._call_api(call_id, "get_friend_list")]

    async def get_user_by_friend(self, call_id, user_id):
        return next((i for i in await self.get_friend_list(call_id) if user_id == i.user_id), None)

    async def delete_friend(self, call_id, user_id, block=True, both=True):
        return await self._call_api(call_id, "delete_friend", {"user_id": user_id, "block": block, "both": both})

    async def set_friend_remark(self, call_id, user_id, remark):
        return await self._call_api(call_id, "set_friend_remark", {"user_id": user_id, "remark": remark})

    # endregion

    # region 消息
    async def mark_group_msg_as_read(self, call_id, group_id):
        return await self._call_api(call_id, "mark_group_msg_as_read", {"group_id": group_id})

    async def mark_private_msg_as_read(self, call_id, user_id):
        return await self._call_api(call_id, "mark_private_msg_as_read", {"group_id": user_id})

    async def create_collection(self, call_id, raw_data, brief):
        return await self._call_api(call_id, "create_collection", {"rawData": raw_data, "brief": brief})

    async def get_recent_contact(self, call_id):
        return [RecentContact.model_validate(contact) for contact in await self._call_api(call_id, "get_recent_contact")]

    async def mark_all_as_read(self, call_id):
        return await self._call_api(call_id, "_mark_all_as_read")

    # endregion

    # region 群
    async def ask_share_group(self, call_id, group_id):
        return await self._call_api(call_id, "AskShareGroup", {"group_id": group_id})

    # endregion

    # region 其它
    async def get_stranger_info(self, call_id, user_id):
        data["level"] = (data := await self._call_api(call_id, "get_stranger_info", {"user_id": user_id})).pop("qqLevel", None)
        return Stranger.model_validate(data)

    async def _get_user_by_search(self: NapCat, _, user_id, group_id=None) -> Stranger | Friend | GroupMemberInfo | None:
        if group_id:
            return next(
                (i for i in await self.get_group_member_list(self.gen_id(), group_id) if user_id == i.user_id),
                None,
            )
        if stranger_user := await self.get_stranger_info(self.gen_id(), user_id):
            return stranger_user
        if friend_user := await self.get_user_by_friend(self.gen_id(), user_id):
            return friend_user
        if user := await self.get_user_by_groups(None, user_id):
            return user

    async def get_card_by_search(self, _, user_id, group_id=None, force_return_card=False):
        if (result := await self._get_user_by_search(None, user_id, group_id)) is None:
            return None
        card = getattr(result, "card", None)
        nickname = result.nickname.strip() or user_id
        return (card, nickname) if force_return_card else (card or nickname)

    async def get_level_by_search(self, _, user_id):
        if stranger_user := await self.get_stranger_info(self.gen_id(), user_id):
            return stranger_user.level
        if friend_user := await self.get_user_by_friend(self.gen_id(), user_id):
            return friend_user.level

    async def get_nickname(self, call_id, user_id):
        return nickname if (nickname := (await self.get_stranger_info(call_id, user_id)).nickname.strip()) else str(user_id)

    async def fetch_custom_face(self, call_id, count=48):
        return CustomFaceList(await self._call_api(call_id, "fetch_custom_face", {"count": count}))

    async def get_user_status(self, call_id, user_id):
        return UserAccount.model_validate(await self._call_api(call_id, "nc_get_user_status", {"user_id": user_id}))

    # endregion

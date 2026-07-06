from models.api import Friend, FriendCategory, LoginInfo, LastestMsgs, Sex, Stranger, UserStatus
from models.msg import Sticker

from ...apis import BaseAccountAPI
from ..utils import StickerType, Utils


class AccountAPI(Utils, BaseAccountAPI):
    SEX_MAPPING = {Sex.MALE: 1, Sex.FEMALE: 2}

    # region 账号相关
    def set_profile(self, call_id, nickname, personal_note, sex: Sex):
        return self._call_api(
            call_id,
            "set_qq_profile",
            {"nickname": nickname, "personal_note": personal_note, "sex": self.SEX_MAPPING.get(sex, 3)},
        )

    def set_online_status(self, call_id, status, ext_status):
        return self._call_api(
            call_id,
            "set_online_status",
            (
                {"status": 10, "ext_status": 1000, "battary_status": ext_status}
                if status == 10
                else {"status": status, "ext_status": ext_status, "battary_status": 0}
            ),
        )

    async def set_avatar(self, call_id, file):
        return await self._call_api(
            call_id,
            "set_avatar",
            {"file": await self.prepare_upload(file if isinstance(file, str) else file.file, self.transport.local_srv)},
        )

    def set_bio(self, call_id, content):
        return self._call_api(call_id, "set_self_longnick", {"longNick": content})

    async def get_login_info(self, call_id):
        return LoginInfo.model_validate(await self._call_api(call_id, "get_login_info"))

    # endregion

    # region 好友
    async def get_friends_with_category(self, call_id):
        result = []
        for cat in await self._call_api(call_id, "get_friends_with_category"):
            cat["friends"] = cat.pop("buddyList")
            result.append(FriendCategory.model_validate(cat))
        return result

    def send_like(self, call_id, user_id, times=1):
        return self._call_api(call_id, "send_like", {"user_id": user_id, "times": times})

    def process_friend_add_request(self, call_id, flag, approve, remark=None):
        return self._call_api(call_id, "set_friend_add_request", {"flag": flag, "approve": approve, "remark": remark})

    async def get_friends(self, call_id):
        return [Friend.model_validate(friend) for friend in await self._call_api(call_id, "get_friend_list")]

    async def get_user_by_friend(self, call_id, user_id):
        return next((i for i in await self.get_friends(call_id) if user_id == i.user_id), None)

    def delete_friend(self, call_id, user_id, block=False, both=True):
        return self._call_api(call_id, "delete_friend", {"user_id": user_id, "block": block, "both": both})

    def set_friend_remark(self, call_id, user_id, remark):
        return self._call_api(call_id, "set_friend_remark", {"user_id": user_id, "remark": remark})

    # endregion

    # region 消息
    def mark_group_msg_as_read(self, call_id, group_id):
        return self._call_api(call_id, "mark_group_msg_as_read", {"group_id": group_id})

    def mark_private_msg_as_read(self, call_id, user_id):
        return self._call_api(call_id, "mark_private_msg_as_read", {"group_id": user_id})

    def create_collection(self, call_id, raw_data, brief):
        return self._call_api(call_id, "create_collection", {"rawData": raw_data, "brief": brief})

    async def get_last_msg_per_conv(self, call_id):
        return [LastestMsgs.model_validate(contact) for contact in await self._call_api(call_id, "get_recent_contact")]

    def mark_all_as_read(self, call_id):
        return self._call_api(call_id, "_mark_all_as_read")

    # endregion

    # region 群
    def ask_share_group(self, call_id, group_id):
        return self._call_api(call_id, "AskShareGroup", {"group_id": group_id})

    # endregion

    # region 其它
    async def get_stranger_info(self, call_id, user_id):
        data["level"] = (data := await self._call_api(call_id, "get_stranger_info", {"user_id": user_id})).pop("qqLevel", None)
        data["bio"] = data.pop("long_nick", None)
        return Stranger.model_validate(data)

    async def get_level_by_search(self, _, user_id):
        if stranger_user := await self.get_stranger_info(self.gen_id(), user_id):
            return stranger_user.level
        if friend_user := await self.get_user_by_friend(self.gen_id(), user_id):
            return friend_user.level

    async def get_nickname(self, call_id, user_id):
        return nickname if (nickname := (await self.get_stranger_info(call_id, user_id)).nickname.strip()) else str(user_id)

    async def fetch_collected_stickers(self, call_id, count=48):
        return [
            Sticker(file=i)
            for i in await self._call_api(call_id, "fetch_custom_face", {"count": count})
        ]

    async def get_user_status(self, call_id, user_id):
        return UserStatus.model_validate(await self._call_api(call_id, "nc_get_user_status", {"user_id": user_id}))

    # endregion

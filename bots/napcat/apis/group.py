from collections.abc import Sequence
from time import time
from asyncio import create_task
from typing import TYPE_CHECKING, Literal

from models.api import EssenceMessage, GroupFiles, RetrievedMessage, Role
from models.core import AddScheduleArgs, APSTriggerType
from models.msg import Forward, MsgSeq

from ...apis import BaseGroupAPI
from ..utils import GroupInfo, GroupMemberInfo, GroupMembers, Utils

if TYPE_CHECKING:
    from .. import GroupHonor, HonorType, NapCat


class GroupAPI(Utils, BaseGroupAPI):
    # region 消息发送
    async def send_group_msg(self, call_id, group_id, msg=None, at=None, reply=None, image=None):
        # TODO: 检查消息合法性
        if (
            not isinstance(msg, str)
            and isinstance(msg, Sequence)
            and isinstance(forward := msg[0], Forward)
            or isinstance(forward := msg, Forward)
        ):
            return await self.send_group_forward_msg(call_id, group_id, forward)

        msg = await self.serialize_msg(msg)
        if reply is not None:
            msg.insert(0, {"type": "reply", "data": {"id": reply}})
        if at is not None:
            msg.insert(0, {"type": "at", "data": {"qq": at}})
        if image is not None:
            msg.append({"type": "image", "data": {"file": await self.prepare_upload(image, self.transport.local_srv)}})

        if forward := (await self.shorter_or_forward(msg)):
            return await self.send_group_forward_msg(call_id, group_id, forward)
        return (await self._call_api(call_id, "send_group_msg", {"group_id": group_id, "message": msg}))["message_id"]

    async def send_group_raw_msg(self, call_id, group_id, data):
        return (await self._call_api(call_id, "send_group_msg", {"group_id": group_id, "message": data}))["message_id"]

    async def send_group_image(self, call_id, group_id, image):
        return (
            await self._call_api(
                call_id,
                "send_group_msg",
                {
                    "group_id": group_id,
                    "message": {
                        "type": "image",
                        "data": {"file": await self.prepare_upload(image, self.transport.local_srv), "summary": "[图片]"},
                    },
                },
            )
        )["message_id"]

    async def send_group_record(self, call_id, group_id, file):
        return (
            await self._call_api(
                call_id,
                "send_group_msg",
                {
                    "group_id": group_id,
                    "message": {"type": "record", "data": {"file": await self.prepare_upload(file, self.transport.local_srv)}},
                },
            )
        )["message_id"]

    async def send_group_dice(self, call_id, group_id, value=1):
        return (
            await self._call_api(
                call_id, "send_group_msg", {"group_id": group_id, "message": {"type": "dice", "data": {"value": value}}}
            )
        )["message_id"]

    async def send_group_rps(self, call_id, group_id, value=1):
        return (
            await self._call_api(
                call_id, "send_group_msg", {"group_id": group_id, "message": {"type": "rps", "data": {"value": value}}}
            )
        )["message_id"]

    async def send_group_file(self, call_id, group_id, file, name=None):
        return (
            await self._call_api(
                call_id,
                "send_group_msg",
                {
                    "group_id": group_id,
                    "message": {
                        "type": "file",
                        "data": {"file": await self.prepare_upload(file, self.transport.local_srv), "name": name},
                    },
                },
            )
        )["message_id"]

    async def send_group_platform_music(self, call_id, group_id, platform: Literal["qq", "163"], id):
        return (
            await self._call_api(
                call_id,
                "send_group_msg",
                {"group_id": group_id, "message": {"type": "music", "data": {"type": platform.value, "id": id}}},
            )
        )["message_id"]

    async def send_group_music(self, call_id, group_id, url, audio=None, title=None, content=None, image=None):
        return (
            await self._call_api(
                call_id,
                "send_group_msg",
                {
                    "group_id": group_id,
                    "message": {
                        "type": "custom_music",
                        "data": {
                            "url": url,
                            "image": await self.prepare_upload(image, self.transport.local_srv),
                            "audio": audio,
                            "title": title,
                            "content": content,
                        },
                    },
                },
            )
        )["message_id"]

    async def send_group_forward_msg(self, call_id, group_id, forward: Forward):
        (d := await self.forward2dict(forward))["group_id"] = group_id
        return (await self._call_api(call_id, "send_group_forward_msg", d))["message_id"]

    async def send_group_forward_msg_by_id(self: NapCat, call_id, group_id, messages):
        d = self.content2send_raw(
            self.raw2forward_data(
                [await self._call_api(self.gen_id(), "get_msg", {"message_id": msg_id}) for msg_id in messages]
            )
        )
        d["group_id"] = group_id
        return (await self._call_api(call_id, "send_group_forward_msg", d))["message_id"]

    async def group_poke(self, call_id, group_id, user_id):
        return await self._call_api(call_id, "group_poke", {"group_id": group_id, "user_id": user_id})

    # endregion
    # region 群成员管理
    async def group_kick_members(self, call_id, group_id, user_ids, reject_add_request=False):
        return await self._call_api(
            call_id,
            "set_group_kick_members",
            {"group_id": group_id, "user_id": user_ids, "reject_add_request": reject_add_request},
        )

    async def group_kick(self, call_id, group_id, user_id, reject_add_request=False):
        if user_id in {i.user_id for i in (await self.get_group_members(self.gen_id(), group_id)) if i.role == "member"}:
            return bool(
                await self._call_api(
                    call_id,
                    "set_group_kick",
                    {"group_id": group_id, "user_id": user_id, "reject_add_request": reject_add_request},
                )
            )
        return False

    async def group_ban(self, _, group_id, user_id, duration=0):
        if (member := await self.get_group_member_info(self.gen_id(), group_id, user_id)).role != Role.MEMBER:
            return False

        if duration > 0:
            if duration > 2591940:
                create_task(
                    self._call_api(
                        self.gen_id(), "set_group_ban", {"group_id": group_id, "user_id": user_id, "duration": 2591940}
                    )
                )

                # 计算剩余时长并设置续期任务
                schedule_args = AddScheduleArgs(
                    "set_group_ban",
                    {"group_id": group_id, "user_id": user_id, "duration": duration - 2591940 + 60},  # 提前一分钟续期
                    APSTriggerType.TIME_TRIGGER,
                    {"seconds": 2591940 - 60},
                    {"metadata": {"platform": "QQ", "group_id": group_id, "user_id": user_id, "tag": "ban"}},
                )
                create_task(self.add_schedule(schedule_args))
                return True

            # 转为整分钟
            create_task(
                self._call_api(
                    self.gen_id(),
                    "set_group_ban",
                    {"group_id": group_id, "user_id": user_id, "duration": (duration + 59) // 60 * 60},
                )
            )

            if duration % 60 != 0:
                schedule_args = AddScheduleArgs(
                    "set_group_ban",
                    {"group_id": group_id, "user_id": user_id, "duration": 0},
                    APSTriggerType.TIME_TRIGGER,
                    {"seconds": duration},
                    {"metadata": {"platform": "QQ", "group_id": group_id, "user_id": user_id, "tag": "ban"}},
                )
                create_task(self.add_schedule(schedule_args))
            return True

        # 解禁
        if member.shut_up_time.timestamp() > time():
            create_task(
                self._call_api(self.gen_id(), "set_group_ban", {"group_id": group_id, "user_id": user_id, "duration": 0})
            )
            create_task(self.rm_schedule_by_meta({"platform": "QQ", "group_id": group_id, "user_id": user_id, "tag": "ban"}))
            return True

        return False

    async def set_group_whole_ban(self, call_id, group_id, enable):
        return await self._call_api(call_id, "set_group_whole_ban", {"group_id": group_id, "enable": enable})

    async def set_group_admin(self, call_id, group_id, user_id, enable):
        return await self._call_api(call_id, "set_group_admin", {"group_id": group_id, "user_id": user_id, "enable": enable})

    async def group_leave(self, call_id, group_id, is_dismiss=False):
        return await self._call_api(call_id, "set_group_leave", {"group_id": group_id, "is_dismiss": is_dismiss})

    async def set_group_special_title(self, call_id, group_id, user_id, special_title=""):
        return await self._call_api(
            call_id, "set_group_special_title", {"group_id": group_id, "user_id": user_id, "special_title": special_title}
        )

    async def process_group_join_request(self, call_id, flag, approve, reason=None):
        if reason and len(reason.encode("gbk")) > 60:
            raise ValueError("加群请求拒绝原因过长")
        else:
            return await self._call_api(call_id, "set_group_add_request", {"flag": flag, "approve": approve, "reason": reason})

    async def set_group_card(self, call_id, group_id, user_id, card=""):
        return await self._call_api(call_id, "set_group_card", {"group_id": group_id, "user_id": user_id, "card": card})

    async def get_card(self, call_id, group_id, user_id):
        return card if (card := (data := await self.get_group_member_info(call_id, group_id, user_id)).card) else data.nickname

    async def is_admin(self, call_id, group_id, user_id):
        return (await self.get_group_members(call_id, group_id)).is_admin(user_id)

    # endregion

    # region 群消息管理
    async def get_group_msg_history(self: NapCat, call_id, group_id, message_seq, number=20, reverseOrder=False):
        return [
            RetrievedMessage.model_validate(await self._msg_event_processor(data["message"]))
            for data in await self._call_api(
                call_id,
                "get_group_msg_history",
                {"group_id": group_id, "message_seq": message_seq, "number": number, "reverseOrder": reverseOrder},
            )
        ]

    async def set_essence_msg(self, call_id, message_id):
        return await self._call_api(call_id, "set_essence_msg", {"message_id": message_id})

    async def delete_essence_msg(self, call_id, message_id):
        return await self._call_api(call_id, "delete_essence_msg", {"message_id": message_id})

    async def get_essence_msg_list(self: NapCat, call_id, group_id):
        result = []
        for msg in await self._call_api(call_id, "get_essence_msg_list", {"group_id": group_id}):
            msg["content"] = MsgSeq([await self.build_msg_seg(item, gid=group_id) for item in msg["content"]])
            result.append(EssenceMessage.model_validate(msg))
        return result

    # endregion

    # region 群文件
    async def move_group_file(self, call_id, group_id, file_id, current_parent_directory, target_parent_directory):
        return await self._call_api(
            call_id,
            "move_group_file",
            {
                "group_id": group_id,
                "file_id": file_id,
                "current_parent_directory": current_parent_directory,
                "target_parent_directory": target_parent_directory,
            },
        )

    async def trans_group_file(self, call_id, group_id, file_id):
        return await self._call_api(call_id, "trans_group_file", {"group_id": group_id, "file_id": file_id})

    async def rename_group_file(self, call_id, group_id, file_id, new_name):
        return await self._call_api(
            call_id, "rename_group_file", {"group_id": group_id, "file_id": file_id, "new_name": new_name}
        )

    async def upload_group_file(self, call_id, group_id, file, name, folder):
        return await self._call_api(
            call_id, "upload_group_file", {"group_id": group_id, "file": file, "name": name, "folder": folder}
        )

    async def create_group_file_folder(self, call_id, group_id, folder_name):
        return await self._call_api(call_id, "create_group_file_folder", {"group_id": group_id, "folder_name": folder_name})

    async def group_file_folder_makedir(self, call_id, group_id, path):
        await super().group_file_folder_makedir(call_id, group_id, path)

    async def delete_group_file(self, call_id, group_id, file_id):
        return await self._call_api(call_id, "delete_group_file", {"group_id": group_id, "file_id": file_id})

    async def delete_group_folder(self, call_id, group_id, folder_id):
        return await self._call_api(call_id, "delete_group_folder", {"group_id": group_id, "folder_id": folder_id})

    async def get_group_root_files(self, call_id, group_id, file_count=50):
        return GroupFiles.model_validate(
            await self._call_api(call_id, "get_group_root_files", {"group_id": group_id, "file_count": file_count})
        )

    async def get_group_files_by_folder(self, call_id, group_id, folder_id, file_count=50):
        return GroupFiles.model_validate(
            await self._call_api(
                call_id, "get_group_files_by_folder", {"group_id": group_id, "folder_id": folder_id, "file_count": file_count}
            )
        )

    async def get_group_file_url(self, call_id, group_id, file_id):
        return (await self._call_api(call_id, "get_group_file_url", {"group_id": group_id, "file_id": file_id}))["url"]

    # endregion

    # region 其它(用户功能)
    async def get_group_honor_info(self, call_id, group_id, honor_type: HonorType):
        return GroupHonor.model_validate(
            await self._call_api(call_id, "get_group_honor_info", {"group_id": group_id, "type": honor_type.value})
        )

    async def get_group_info(self, call_id, group_id):
        return GroupInfo.model_validate(await self._call_api(call_id, "get_group_info", {"group_id": group_id}))

    async def get_group_info_raw(self, call_id, group_id):
        return await self._call_api(call_id, "get_group_info_ex", {"group_id": group_id})["extInfo"]

    async def get_group_member_info(self, call_id, group_id, user_id):
        data: dict = await self._call_api(call_id, "get_group_member_info", {"group_id": group_id, "user_id": user_id})
        if level := data.pop("level", None):
            data["activity_level"] = level
        data["shut_up_time"] = shut_up if (shut_up := data["shut_up_timestamp"]) else 0
        if aa := data.pop("qage", None):
            data["account_age"] = aa
        return GroupMemberInfo.model_validate(data)

    async def get_group_members(self, call_id, group_id):
        for i in (data := await self._call_api(call_id, "get_group_member_list", {"group_id": group_id})):
            if level := i.pop("level", None):
                i["activity_level"] = level
            i["shut_up_time"] = shut_up if (shut_up := i["shut_up_timestamp"]) else 0
            if aa := i.pop("qage", None):
                i["account_age"] = aa
        return GroupMembers(data)

    async def get_group_list(self, call_id):
        return [GroupInfo.model_validate(g) for g in await self._call_api(call_id, "get_group_list")]

    async def get_group_shut_list(self, call_id, group_id):
        for i in (data := await self._call_api(call_id, "get_group_shut_list", {"group_id": group_id})):
            if level := i.pop("memberRealLevel", None):
                i["activity_level"] = level
        return GroupMembers(data)

    async def set_group_remark(self, call_id, group_id, remark):
        return await self._call_api(call_id, "set_group_remark", {"group_id": group_id, "remark": remark})

    async def set_group_sign(self, call_id, group_id):
        return await self._call_api(call_id, "set_group_sign", {"group_id": group_id})

    async def send_group_sign(self, call_id, group_id):
        return await self._call_api(call_id, "send_group_sign", {"group_id": group_id})

    # endregion

    # region 其它(管理员功能)
    async def set_group_avatar(self, call_id, group_id, file):
        if self.transport.local_srv:
            return await self._call_api(call_id, "set_group_portrait", {"group_id": group_id, "file": file})
        raise NotImplementedError("远端 NapCat 暂不支持 set_group_avatar API。")

    async def set_group_name(self, call_id, group_id, name):
        return await self._call_api(call_id, "set_group_name", {"group_id": group_id, "group_name": name})

    async def _send_group_notice(
        self, call_id, group_id, content, confirm_required=False, image=None, is_show_edit_card=False, pinned=False
    ):
        # TODO: 测试
        return await self._call_api(
            call_id,
            "send_group_notice",
            {
                "group_id": group_id,
                "content": content,
                "confirm_required": 1 if confirm_required else 0,
                "image": image,
                "is_show_edit_card": 1 if is_show_edit_card else 0,
                "pinned": 1 if pinned else 0,
                "tip_window_type": 0,
                "type": 0,
            },
        )

    # endregion

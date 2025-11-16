from collections.abc import Sequence
from typing import TYPE_CHECKING, Literal

from models.api.message import RetrievedMessage
from models.msg import Forward

from ...apis import BasePrivateAPI
from ..utils import Utils

if TYPE_CHECKING:
    from .. import NapCat


class PrivateAPI(Utils, BasePrivateAPI):
    # region 消息发送
    async def send_private_msg(self, call_id, user_id, msg=None, at=None, reply=None, image=None):
        # TODO: 检查消息合法性
        if (
            not isinstance(msg, str)
            and isinstance(msg, Sequence)
            and isinstance(forward := msg[0], Forward)
            or isinstance(forward := msg, Forward)
        ):
            return await self.send_private_forward_msg(call_id, user_id, forward)

        msg = await self.serialize_msg(msg)
        if reply is not None:
            msg.insert(0, {"type": "reply", "data": {"id": reply}})
        if at is not None:
            msg.insert(0, {"type": "at", "data": {"qq": at}})
        if image is not None:
            msg.append({"type": "image", "data": {"file": await self.prepare_upload(image, self.transport.local_srv)}})

        if forward := (await self.shorter_or_forward(msg)):
            return await self.send_private_forward_msg(call_id, user_id, forward)
        return (await self._call_api(call_id, "send_private_msg", {"user_id": user_id, "message": msg}))["message_id"]

    async def send_private_raw_msg(self, call_id, user_id, data):
        return (await self._call_api(call_id, "send_private_msg", {"user_id": user_id, "message": data}))["message_id"]

    async def send_private_image(self, call_id, user_id, image):
        return (
            await self._call_api(
                call_id,
                "send_private_msg",
                {
                    "user_id": user_id,
                    "message": {
                        "type": "image",
                        "data": {"file": await self.prepare_upload(image, self.transport.local_srv), "summary": "[图片]"},
                    },
                },
            )
        )["message_id"]

    async def send_private_record(self, call_id, user_id, file):
        return (
            await self._call_api(
                call_id,
                "send_private_msg",
                {
                    "user_id": user_id,
                    "message": {"type": "record", "data": {"file": await self.prepare_upload(file, self.transport.local_srv)}},
                },
            )
        )["message_id"]

    async def send_private_dice(self, call_id, user_id, value=1):
        return (
            await self._call_api(
                call_id, "send_private_msg", {"user_id": user_id, "message": {"type": "dice", "data": {"value": value}}}
            )
        )["message_id"]

    async def send_private_rps(self, call_id, user_id, value=1):
        return (
            await self._call_api(
                call_id, "send_private_msg", {"user_id": user_id, "message": {"type": "rps", "data": {"value": value}}}
            )
        )["message_id"]

    async def send_private_file(self, call_id, user_id, file, name=None):
        return (
            await self._call_api(
                call_id,
                "send_private_msg",
                {
                    "user_id": user_id,
                    "message": {"file": await self.prepare_upload(file, self.transport.local_srv), "name": name},
                },
            )
        )["message_id"]

    async def send_private_platform_music(self, call_id, user_id, platform: Literal["qq", "163"], id):
        return (
            await self._call_api(
                call_id,
                "send_private_msg",
                {"user_id": user_id, "message": {"type": "music", "data": {"type": platform.value, "id": id}}},
            )
        )["message_id"]

    async def send_private_music(self, call_id, user_id, url, audio=None, title=None, content=None, image=None):
        return (
            await self._call_api(
                call_id,
                "send_private_msg",
                {
                    "user_id": user_id,
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

    async def send_private_forward_msg(self, call_id, user_id, forward: Forward):
        (d := await self.forward2dict(forward))["user_id"] = user_id
        return (await self._call_api(call_id, "send_private_forward_msg", d))["message_id"]

    async def send_private_forward_msg_by_id(self: NapCat, call_id, user_id, messages):
        d = self.content2send_raw(
            self.raw2forward_data(
                [await self._call_api(self.gen_id(), "get_msg", {"message_id": msg_id}) for msg_id in messages]
            )
        )
        d["user_id"] = user_id
        return (await self._call_api(call_id, "send_private_forward_msg", d))["message_id"]

    async def friend_poke(self, call_id, user_id):
        return await self._call_api(call_id, "friend_poke", {"user_id": user_id})

    # endregion
    async def get_private_msg_history(self, call_id, user_id, message_seq, number=20, reverseOrder=False):
        return [
            RetrievedMessage.model_validate(data)
            for data in await self._call_api(
                call_id,
                "get_friend_msg_history",
                {"user_id": user_id, "message_seq": message_seq, "number": number, "reverseOrder": reverseOrder},
            )
        ]

    async def upload_private_file(self, call_id, user_id, file, name):
        return await self._call_api(call_id, "upload_private_file", {"user_id": user_id, "file": file, "name": name})

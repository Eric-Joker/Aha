
from models.api import LoginInfo, MusicPlatform
from models.msg import CustomMusic, File, Forward, Image, Music, Record, Text

from ...apis import BasePrivateAPI


class PrivateAPI(BasePrivateAPI):
    # region 消息发送
    async def send_private_msg(self, call_id, user_id, msg=None, at=None, reply=None, image=None):
        msg = self.build_message_chain(msg)
        if reply is not None:
            msg.prepand_reply(reply)
        if at is not None:
            msg.prepand_at(at)
        if image is not None:
            msg.prepand_image(await self.prepare_file(image, self.transport.local_srv))
        # TODO: 检查消息合法性
        if forward := (await self.long_or_forword(msg)):
            return await self.send_private_forward_msg(call_id, user_id, forward)
        return (await self._call_api(call_id, "send_private_msg", {"user_id": user_id, "message": await msg.serialize()}))[
            "message_id"
        ]

    async def send_private_unescape_text(self, call_id, user_id, text):
        return (
            await self._call_api(
                call_id, "send_private_msg", {"user_id": user_id, "message": await Text(text=text).serialize()}
            )
        )["message_id"]

    async def send_private_image(self, call_id, user_id, image):
        return (
            await self._call_api(
                call_id,
                "send_private_msg",
                {
                    "user_id": user_id,
                    "message": await Image(
                        summary="[图片]", file=await self.prepare_file(image, self.transport.local_srv)
                    ).serialize(),
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
                    "message": await Record(file=await self.prepare_file(file, self.transport.local_srv)).serialize(),
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
                    "message": await File(
                        file=await self.prepare_file(file, self.transport.local_srv), file_name=name
                    ).serialize(),
                },
            )
        )["message_id"]

    async def send_private_music(self, call_id, user_id, platform: MusicPlatform, id):
        return (
            await self._call_api(
                call_id,
                "send_private_msg",
                {"user_id": user_id, "message": await Music(type=platform.value, id=id).serialize()},
            )
        )["message_id"]

    async def send_private_custom_music(self, call_id, user_id, url, image=None, audio=None, title=None, content=None):
        return (
            await self._call_api(
                call_id,
                "send_private_msg",
                {
                    "user_id": user_id,
                    "message": [
                        await CustomMusic(
                            url=url,
                            title=title,
                            audio=audio,
                            content=content,
                            image=await self.prepare_file(image, self.transport.local_srv),
                        ).serialize()
                    ],
                },
            )
        )["message_id"]

    async def send_private_forward_msg(self, call_id, user_id, forward: Forward):
        (d := await self.to_forward_dict(forward))["user_id"] = user_id
        return (await self._call_api(call_id, "send_private_forward_msg", d))["message_id"]

    async def send_private_forward_msg_by_id(self, call_id, user_id, messages):
        info: LoginInfo = await self.get_login_info(self.gen_id())
        forward = Forward()
        for message_id in messages:
            forward.append((await self.get_msg(self.gen_id(), message_id)).message, info.user_id, info.nickname)
        return await self.send_private_forward_msg(call_id, user_id, forward)

    async def friend_poke(self, call_id, user_id):
        return await self._call_api(call_id, "friend_poke", {"user_id": user_id})

    # endregion
    async def upload_private_file(self, call_id, user_id, file, name):
        return await self._call_api(call_id, "upload_private_file", {"user_id": user_id, "file": file, "name": name})

    async def get_private_file_url(self, call_id, file_id):
        return (await self._call_api(call_id, "get_private_file_url", {"file_id": file_id}))["url"]

from collections.abc import Sequence
from random import getrandbits
from time import time
from typing import Annotated

from anyio import Path
from pydantic import BeforeValidator, Field, PrivateAttr, field_validator
from xxhash import xxh3_64

from ..base import BaseModel, PureNameEnum
from ..core import Group, User
from ..msg import MessageChain, MsgSeg
from .utils import Role  # , Sex


class BaseEvent(BaseModel):
    bot_id: int = Field(default=None, exclude=True, repr=False)
    platform: str = Field(default=None, exclude=True, repr=False)
    adapter: str = Field(default=None, exclude=True, repr=False)
    _user_obj: User = PrivateAttr(None)
    _group_obj: Group = PrivateAttr(None)

    time: int = Field(default_factory=time)
    self_id: Annotated[str, BeforeValidator(str)] | None = None

    event_type: EventType
    sub_type: EventSubType | None = None

    async def user_aha_id(self):
        if user_id := getattr(self, "user_id"):
            from core.identity import user2aha_id

            return await user2aha_id(self.platform, user_id)

    async def group_aha_id(self):
        if group_id := getattr(self, "group_id"):
            from core.identity import group2aha_id

            return await group2aha_id(self.platform, group_id)

    @property
    def user(self):
        """可用于表达式 PM.group"""
        if self._user_obj:
            return self._user_obj
        if user_id := getattr(self, "user_id"):
            self._user_obj = User(self.platform, user_id)
            return self._user_obj

    @property
    def group(self):
        """可用于表达式 PM.user"""
        if self._group_obj:
            return self._group_obj
        if group_id := getattr(self, "group_id"):
            self._group_obj = Group(self.platform, group_id)
            return self._group_obj

    def __hash__(self):
        raise NotImplementedError

    def __eq__(self, other):
        return isinstance(other, BaseEvent) and self.__hash__() == other.__hash__()

    def _recursion_hash(self, obj, hasher: xxh3_64):
        if isinstance(obj, dict):
            for k, v in obj.items():
                hasher.update(k)
                self._recursion_hash(v, hasher)
        elif isinstance(obj, list):
            for i in obj:
                self._recursion_hash(i, hasher)
        else:
            hasher.update(str(obj))


class EventType(str, PureNameEnum):
    def __repr__(self):
        return self.name


class EventSubType(str, PureNameEnum):
    def __repr__(self):
        return self.name


# region message
class MessageEventType(EventType):
    GROUP = "group"
    PRIVATE = "private"


class MessageSubType(EventSubType):
    # 群聊消息
    NORMAL = "normal"
    ANONYMOUS = "anonymous"
    NOTICE = "notice"
    # 私聊消息
    TEMPORARY = "temporary"
    FRIEND = "friend"


class MessageSender(BaseModel):
    nickname: str

    card: str | None = None  # 群名片
    # sex: Sex | None = None
    # age: int | None = None
    # area: str | None = None
    level: int | None = None
    role: Role | None = None
    title: str | None = None


class AnonymousInfo(BaseModel):
    id: str
    name: str
    flag: str


class Message[T: MsgSeg](BaseEvent):
    """
    Attributes:
        message_str: 会自动生成。把 `message` 中非 Text 类型的消息依照 `f"[Aha:{type.__name__.lower()},{attr}={value},{attr}={value}]"` 的格式进行处理并合并，其中 `value` 会经过 `utils.aha.escape_aha`。
    """

    event_type: MessageEventType = Field(validation_alias="message_type")
    sub_type: MessageSubType
    self_id: Annotated[str, BeforeValidator(str)]
    message_id: Annotated[str, BeforeValidator(str)] | None = None
    user_id: Annotated[str, BeforeValidator(str)]
    message: MessageChain[T]
    sender: MessageSender
    # anonymous: AnonymousInfo | None = None
    group_id: Annotated[str, BeforeValidator(str)] | None = None

    @property
    def msg(self):
        return self.message

    msg_chain = msg

    @property
    def message_str(self):
        return str(self.message)

    msg_str = message_str

    def get_msg_inline(self):
        """
        建议减少调用该方法的次数。

        Returns:
            InlineStr: 跨事件上下文不一致，具有易被恶意碰撞的风险，不可直接用于调用 API 发送消息。
        """
        from utils.string import InlineStr

        return InlineStr.from_iterable(self.message)

    @property
    def is_group_msg(self):
        return self.event_type is MessageEventType.GROUP

    async def delete(self) -> None:
        from core.api_service import call_api

        return await call_api("delete_msg", self.message_id, bot=self.bot_id)

    async def kick(self) -> None:
        if self.is_group_msg:
            from core.api_service import call_api

            return await call_api("group_kick", self.group_id, self.user_id, bot=self.bot_id)

    async def ban(self, duration: int = 0) -> None:
        if self.is_group_msg:
            from core.api_service import call_api

            return await call_api("group_ban", self.group_id, self.user_id, duration, bot=self.bot_id)

    async def reply(self, msg: str | Sequence[MsgSeg | str] | MsgSeg = None, at=False, image: str | Path = None) -> str:
        from core.api_service import call_api

        return await call_api(
            "send_msg",
            user_id=self.user_id,
            group_id=self.group_id,
            msg=msg,
            at=self.user_id if at else None,
            reply=self.message_id,
            image=image,
            bot=self.bot_id,
        )

    async def send(self, msg: str | Sequence[MsgSeg | str] | MsgSeg = None, at=False, image: str | Path = None) -> str:
        from core.api_service import call_api

        return await call_api(
            "send_msg",
            user_id=self.user_id,
            group_id=self.group_id,
            msg=msg,
            at=self.user_id if at else None,
            image=image,
            bot=self.bot_id,
        )

    async def poke(self) -> None:
        from core.api_service import call_api

        return await call_api("poke", user_id=self.user_id, group_id=self.group_id, bot=self.bot_id)

    def __hash__(self):
        hasher = xxh3_64()
        hasher.update(self.event_type.value)
        hasher.update(self.sub_type.value)
        hasher.update(self.user_id)
        hasher.update(self.group_id or "None")
        hasher.update(str(self.time))
        hasher.update(self.message_str)
        self._recursion_hash(self.extra, hasher)
        return hasher.intdigest()


# endregion
# region notice
class NoticeEventType(EventType):
    GROUP_ADMIN = "group_admin"
    GROUP_DECREASE = "group_decrease"
    GROUP_INCREASE = "group_increase"
    GROUP_BAN = "group_ban"
    FRIEND_ADD = "friend_add"
    GROUP_RECALL = "group_recall"
    FRIEND_RECALL = "friend_recall"
    NOTIFY = "notify"
    REACTION = "reaction"
    ESSENCE = "essence"
    GROUP_CARD = "group_card"


class NoticeSubType(EventSubType):
    SET = "set"  # group_admin
    UNSET = "unset"  # group_admin
    LEAVE = "leave"  # group_decrease
    KICK = "kick"  # group_decrease
    KICK_ME = "kick_me"  # group_decrease
    DISBAND = "disband"  # group_decrease
    APPROVE = "approve"  # group_increase
    INVITE = "invite"  # group_increase
    BAN = "ban"  # group_ban
    LIFT_BAN = "lift_ban"  # group_ban
    POKE = "poke"  # notify
    GROUP_NAME = "group_name"  # notify
    TITLE = "title"  # notify
    ADD = "add"  # essence
    DELETE = "delete"  # essence


class Notice(BaseEvent):
    event_type: NoticeEventType | str = Field(validation_alias="notice_type")
    sub_type: NoticeSubType | str | None = None
    group_id: Annotated[str, BeforeValidator(str)] | None = None
    user_id: Annotated[str, BeforeValidator(str)] | None = None
    operator_id: Annotated[str, BeforeValidator(str)] | None = None  # group_decrease, group_increase, group_ban, group_recall
    duration: int | None = None  # group_ban
    message_id: Annotated[str, BeforeValidator(str)] | None = None  # group_recall, friend_recall
    target_id: Annotated[str, BeforeValidator(str)] | None = None  # notify.poke, notify.lucky_king

    @field_validator("event_type", mode="plain")
    @classmethod
    def event_type_or_str(cls, v):
        if isinstance(v, str):
            try:
                return NoticeEventType(v)
            except ValueError:
                return v
        raise ValueError("Input should be a string or valid enum value.")

    @field_validator("sub_type", mode="plain")
    @classmethod
    def sub_type_or_str(cls, v):
        if isinstance(v, str):
            try:
                return NoticeSubType(v)
            except ValueError:
                return v
        raise ValueError("Input should be a string or valid enum value.")

    def __hash__(self):
        hasher = xxh3_64()
        hasher.update(self.event_type.value if isinstance(self.event_type, NoticeEventType) else self.event_type)
        hasher.update(self.sub_type.value if isinstance(self.sub_type, NoticeSubType) else self.sub_type or "None")
        hasher.update(self.user_id or "None")
        hasher.update(self.group_id or "None")
        hasher.update(str(self.time))
        hasher.update(self.operator_id or "None")
        hasher.update(str(self.duration))
        hasher.update(self.message_id or "None")
        hasher.update(self.target_id or "None")
        self._recursion_hash(self.extra, hasher)
        return hasher.intdigest()


# endregion
# region request
class RequestEventType(EventType):
    FRIEND = "friend"
    GROUP = "group"


class RequestSubType(EventSubType):
    ADD = "add"
    INVITE = "invite"


class Request(BaseEvent):
    event_type: RequestEventType = Field(validation_alias="request_type")
    sub_type: RequestSubType | None = None
    user_id: Annotated[str, BeforeValidator(str)]
    group_id: Annotated[str, BeforeValidator(str)] | None = None
    comment: str | None = None
    flag: str = None

    async def process(self, approve: bool = True, *, remark: str = None, reason: str = None):
        from core.api_service import call_api

        if self.event_type is RequestEventType.FRIEND:
            return await call_api("process_friend_add_request", self.flag, approve, remark)
        elif self.event_type is RequestEventType.GROUP:
            return await call_api("process_group_join_request", self.flag, approve, reason)

    def __hash__(self):
        hasher = xxh3_64()
        hasher.update(self.event_type.value)
        hasher.update(self.sub_type.value if self.sub_type else "None")
        hasher.update(self.flag or "None")
        self._recursion_hash(self.extra, hasher)
        return hasher.intdigest()


# endregion
# region meta
class MetaEventType(EventType):
    HEARTBEAT = "heartbeat"
    LIFECYCLE = "lifecycle"


class LifecycleSubType(EventSubType):
    CONNECT = "connect"
    DISCONNECT = "disconnect"


class HeartbeatStatusStatistics(BaseModel):
    packet_received: int | None = None
    packet_sent: int | None = None
    packet_lost: int | None = None
    message_received: int | None = None
    message_sent: int | None = None
    disconnect_times: int | None = None
    lost_times: int | None = None
    last_message_time: int | None = None


class HeartbeatStatus(BaseModel):
    online: bool | None = None
    stat: HeartbeatStatusStatistics | None = None


class MetaEvent(BaseEvent):
    event_type: MetaEventType = Field(validation_alias="meta_event_type")
    sub_type: LifecycleSubType | None = None  # lifecycle
    interval: int | None = None  # heartbeat
    status: HeartbeatStatus | None = None  # heartbeat

    def __hash__(self):
        return getrandbits(28)


# endregion
class MessageSent(Message):
    """该类型不会被路由"""

    target_id: Annotated[str, BeforeValidator(str)] | None = None


Events = Message | Notice | Request | MetaEvent | MessageSent
MessageEvent = Message | MessageSent

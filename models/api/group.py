from collections.abc import Container, Iterable
from datetime import datetime
from time import time
from typing import Annotated, Self, overload

from pydantic import AliasChoices, BeforeValidator, Field, field_validator

from ..base import FrozenBaseModel
from ..msg import MessageChain
from .utils import Role, Sex


class GroupInfo(FrozenBaseModel):
    group_all_shut: Annotated[bool, BeforeValidator(bool)]
    group_remark: str
    group_id: Annotated[str, BeforeValidator(str)]
    group_name: str
    member_count: int | None = None


class GroupMemberInfo(FrozenBaseModel):
    group_id: Annotated[str, BeforeValidator(str)]
    user_id: Annotated[str, BeforeValidator(str)] = Field(validation_alias="uin")
    nickname: str | None = Field(None, validation_alias="nick")
    card: str | None = Field(None, validation_alias=AliasChoices("cardName", "nick"))
    sex: Sex = Sex.UNKNOWN
    age: int | None = None
    area: str | None = None
    join_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)] | None = Field(None, validation_alias="joinTime")
    last_sent_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)] | None = Field(
        None, validation_alias="lastSpeakTime"
    )
    unfriendly: bool = False
    is_robot: bool = Field(False, validation_alias="isRobot")
    shut_up_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)] | None = Field(
        None, validation_alias="shutUpTime"
    )
    role: Role = Role.MEMBER
    title: str | None = Field(None, validation_alias="memberSpecialTitle")

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, v):
        if isinstance(v, Sex):
            return v
        elif v in Sex.__members__.values():
            return Sex(v)
        match v:
            case 1:
                return Sex.MALE
            case 2:
                return Sex.FEMALE
            case _:
                return Sex.UNKNOWN

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if isinstance(v, Role):
            return v
        match v:
            case 2:
                return Role.ADMIN
            case 3:
                return Role.OWNER
            case _:
                return Role.MEMBER

    def __hash__(self):
        return hash(self.user_id)

    def __eq__(self, other):
        return isinstance(other, GroupMemberInfo) and self.user_id == other.user_id or self.user_id == other


class GroupMembers[T: GroupMemberInfo, _T_co, _S](frozenset[T]):
    @overload
    def __new__(cls) -> Self: ...

    @overload
    def __new__(cls, *elements: dict | T, element_cls: type[T] = GroupMemberInfo) -> Self: ...

    @overload
    def __new__(cls, iterable: Iterable[dict | T], /, *, element_cls: type[T] = GroupMemberInfo) -> Self: ...

    def __new__(cls, *args, element_cls=GroupMemberInfo):
        if not args:
            return super().__new__(cls, ())
        elif len(args) == 1:
            if isinstance(arg := args[0], dict):
                return super().__new__(cls, (element_cls.model_validate(arg),))
            elif isinstance(arg, GroupMemberInfo):
                return super().__new__(cls, (arg,))
            else:
                return super().__new__(
                    cls, (element_cls.model_validate(item) if isinstance(item, dict) else item for item in arg)
                )
        else:
            return super().__new__(cls, (element_cls.model_validate(item) if isinstance(item, dict) else item for item in args))

    def is_admin(self, user_id: str):
        return any(m.user_id == user_id and m.role is not Role.MEMBER for m in self)

    def is_manager_of(self, manager: str, subordinate: str):
        manager_role = None
        subordinate_role = None
        for m in self:
            if m.user_id == manager:
                manager_role = m.role
            if m.user_id == subordinate:
                subordinate_role = m.role
            if manager_role and subordinate_role:
                return (
                    manager_role is Role.OWNER
                    or manager_role is Role.ADMIN
                    and (subordinate_role is Role.MEMBER or manager == subordinate)
                )

    def filter_by_last_sent_time_upto_now(self, seconds: int):
        return self.__class__(member for member in self if member.last_sent_time.timestamp() > time() - seconds)

    def filter_by_role(self, role: Role):
        return self.__class__(member for member in self if member.role == role)

    def filter_by_role_not_in(self, roles: Container[Role]):
        return self.__class__(member for member in self if member.role not in roles)

    def filter_by_have_title(self):
        return self.__class__(member for member in self if member.title)

    def copy(self) -> Self:
        return self.__class__(super().copy())

    def difference(self, *s: Iterable[object]) -> Self:
        return self.__class__(super().difference(*s))

    def intersection(self, *s: Iterable[object]) -> Self:
        return self.__class__(super().intersection(*s))

    def symmetric_difference(self, s: Iterable[_T_co], /) -> Self:
        return self.__class__(super().symmetric_difference(s))

    def union(self, *s: Iterable[_S]) -> Self:
        return self.__class__(super().union(*s))

    def __and__(self, value: set[_T_co], /) -> Self:
        return self.__class__(super().__and__(value))

    def __or__(self, value: set[_S], /) -> Self:
        return self.__class__(super().__or__(value))

    def __sub__(self, value: set[_T_co], /) -> Self:
        return self.__class__(super().__sub__(value))

    def __xor__(self, value: set[_S], /) -> Self:
        return self.__class__(super().__xor__(value))


class EssenceMessage(FrozenBaseModel):
    sender_id: Annotated[str, BeforeValidator(str)]
    sender_nick: str
    operator_id: Annotated[str, BeforeValidator(str)] | None
    operator_nick: str | None
    message_id: Annotated[str, BeforeValidator(str)]
    operator_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)]
    message: MessageChain = Field(validation_alias="content")

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


class GroupFile(FrozenBaseModel):
    group_id: Annotated[str, BeforeValidator(str)]
    file_id: str
    file_name: str
    busid: int
    file_size: int = Field(validation_alias="size")
    upload_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)]
    dead_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)]
    modify_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)]
    download_times: int
    uploader: Annotated[str, BeforeValidator(str)]
    uploader_name: str


class GroupFolder(FrozenBaseModel):
    group_id: Annotated[str, BeforeValidator(str)]
    folder_id: str
    folder: str
    folder_name: str
    create_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)]
    creator: Annotated[str, BeforeValidator(str)]
    creator_name: str
    total_file_count: int


class GroupFiles(FrozenBaseModel):
    files: Annotated[tuple[GroupFile], BeforeValidator(tuple)]
    folders: Annotated[tuple[GroupFolder], BeforeValidator(tuple)]

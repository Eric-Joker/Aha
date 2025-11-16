
from collections.abc import Iterable
from datetime import datetime
from time import time
from typing import Annotated, overload

from pydantic import AliasChoices, BeforeValidator, Field, field_validator

from ..base import BaseModelConfig
from ..msg import MsgSeq
from .utils import Role, Sex


class UserInfo(BaseModelConfig):
    user_id: Annotated[str, BeforeValidator(str)]
    nickname: str
    avatar: str
    description: str | None = None


class GroupChatActivity(BaseModelConfig):
    group_id: Annotated[str, BeforeValidator(str)]
    current_talkative: UserInfo
    talkative_list: list[UserInfo]
    performer_list: list[UserInfo] = []
    legend_list: list[UserInfo] = []
    emotion_list: list[UserInfo] = []


class GroupInfo(BaseModelConfig):
    group_all_shut: Annotated[bool, BeforeValidator(bool)]
    group_remark: str
    group_id: Annotated[str, BeforeValidator(str)]
    group_name: str
    member_count: int | None = None  
    max_member_count: int | None = None


class GroupMemberInfo(BaseModelConfig):
    group_id: Annotated[str, BeforeValidator(str)]
    user_id: Annotated[str, BeforeValidator(str)] = Field(validation_alias="uin")
    nickname: str | None = Field(None, validation_alias="nick")
    card: str | None = Field(None, validation_alias=AliasChoices("cardName", "nick"))
    sex: Sex = Sex.UNKNOWN
    age: int | None = None
    area: str = ""
    activity_level: str | None = None
    join_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)] | None = Field(None, validation_alias="joinTime")
    last_sent_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)] | None = Field(None, validation_alias="lastSpeakTime")
    title_expire_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)] | None = Field(None, validation_alias="specialTitleExpireTime")
    unfriendly: bool | None = None
    card_changeable: bool | None = None
    is_robot: bool = Field(False, validation_alias="isRobot")
    shut_up_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)] | None = Field(None, validation_alias="shutUpTime")
    role: Role = Role.MEMBER
    title: str | None = Field(None, validation_alias="memberSpecialTitle")
    account_age: int | None = None

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


class GroupMemberList(list[GroupMemberInfo]):
    @overload
    def __init__(self) -> None: ...

    @overload
    def __init__(self, *elements: dict | GroupMemberInfo) -> None: ...

    @overload
    def __init__(self, iterable: Iterable[dict | GroupMemberInfo], /) -> None: ...

    def __init__(self, *args):
        if not args:
            super().__init__()
        elif len(args) == 1:
            if isinstance(arg := args[0], dict):
                super().__init__((GroupMemberInfo.model_validate(arg),))
            elif isinstance(arg, GroupMemberInfo):
                super().__init__(args)
            else:
                super().__init__(GroupMemberInfo.model_validate(item) if isinstance(item, dict) else item for item in arg)
        else:
            super().__init__(GroupMemberInfo.model_validate(item) if isinstance(item, dict) else item for item in args)

    def filter_by_another_list_not_in(self, another_list: GroupMemberList):
        return GroupMemberList(member for member in self if member not in another_list)

    def filter_by_level_ge(self, level: int):
        return GroupMemberList(member for member in self if int(member.level) >= level)

    def filter_by_level_le(self, level: int):
        return GroupMemberList(member for member in self if int(member.level) <= level)

    def filter_by_last_sent_time_upto_now(self, seconds: int):
        return GroupMemberList(member for member in self if member.last_sent_time.timestamp() > time() - seconds)

    def filter_by_role(self, role: Role):
        return GroupMemberList(member for member in self if member.role == role)

    def filter_by_role_not_in(self, roles: list[Role]):
        return GroupMemberList(member for member in self if member.role not in roles)

    def filter_by_have_title(self):
        return GroupMemberList(member for member in self if member.title)


class EssenceMessage(BaseModelConfig):
    sender_id: Annotated[str, BeforeValidator(str)]
    sender_nick: str
    operator_id: Annotated[str, BeforeValidator(str)]
    operator_nick: str
    message_id: Annotated[str, BeforeValidator(str)]
    operator_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)]
    content: MsgSeq


class GroupFile(BaseModelConfig):
    group_id: Annotated[str, BeforeValidator(str)]
    file_id: str
    file_name: str
    busid: int
    size: int
    file_size: int
    upload_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)]
    dead_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)]
    modify_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)]
    download_times: int
    uploader: Annotated[str, BeforeValidator(str)]
    uploader_name: str


class GroupFolder(BaseModelConfig):
    group_id: Annotated[str, BeforeValidator(str)]
    folder_id: str
    folder: str
    folder_name: str
    create_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)]
    creator: Annotated[str, BeforeValidator(str)]
    creator_name: str
    total_file_count: int


class GroupFiles(BaseModelConfig):
    files: list[GroupFile]
    folders: list[GroupFolder]

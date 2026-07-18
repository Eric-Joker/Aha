from datetime import datetime
from typing import Annotated

from pydantic import BeforeValidator, Field

from models.api import EssenceMessage as AhaEssenceMessage
from models.api import GroupInfo as AhaGroupInfo
from models.api import GroupMemberInfo as AhaGroupMemberInfo
from models.api import GroupMembers as AhaGroupMembers
from models.base import FrozenBaseModel, PureNameEnum


class GroupInfo(AhaGroupInfo):
    max_member_count: int | None = None


class GroupMemberInfo(AhaGroupMemberInfo):
    activity_level: str
    card_changeable: bool
    qq_level: int = Field(validation_alias="qqLevel")


class GroupMembers(AhaGroupMembers[GroupMemberInfo]):
    def __new__(cls, *args):
        return super().__new__(cls, *args, element_cls=GroupMemberInfo)

    def filter_by_level_ge(self, level: int):
        """过滤活跃等级大于等于指定值的成员"""
        return GroupMembers(member for member in self if int(member.activity_level) >= level)

    def filter_by_level_le(self, level: int):
        """过滤活跃等级小于等于指定值的成员"""
        return GroupMembers(member for member in self if int(member.activity_level) <= level)


class HonorType(str, PureNameEnum):
    TALKATIVE = "talkative"
    PERFORMER = "performer"
    EMOTION = "emotion"


class GroupHonorUser(FrozenBaseModel):
    user_id: Annotated[str, BeforeValidator(str)]
    nickname: str
    avatar: str
    description: str | None = None


class GroupHonor(FrozenBaseModel):
    group_id: Annotated[str, BeforeValidator(str)]
    current_talkative: GroupHonorUser
    talkative_list: list[GroupHonorUser]
    performer_list: list[GroupHonorUser] = []
    legend_list: list[GroupHonorUser] = []
    emotion_list: list[GroupHonorUser] = []


class EssenceMessage(AhaEssenceMessage):
    msg_seq: int = Field(validation_alias="msgSeq")
    msg_random: int = Field(validation_alias="msgRandom")

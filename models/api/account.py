import contextlib
from collections.abc import Iterable
from datetime import date, datetime
from typing import Annotated, overload

from pydantic import BeforeValidator, Field, model_validator

from ..base import BaseModelConfig
from .events import Message


class LoginInfo(BaseModelConfig):
    nickname: str
    user_id: Annotated[str, BeforeValidator(str)]


class CustomFaceList(list[str]):
    @overload
    def __init__(self) -> None: ...

    @overload
    def __init__(self, *elements: dict | str) -> None: ...

    @overload
    def __init__(self, iterable: Iterable[dict | str], /) -> None: ...

    def __init__(self, *args):
        if not args:
            super().__init__()
        elif len(args) == 1:
            if isinstance(arg := args[0], str):
                super().__init__((arg,))
            elif isinstance(arg, dict):
                super().__init__((arg["url"],))
            else:
                super().__init__(item["url"] if isinstance(item, dict) else item for item in arg)
        else:
            super().__init__(item["url"] if item.__class__ is dict else item for item in args)

    __setitem__ = extend = append = insert = __add__ = __iadd__ = __radd__ = __mul__ = __rmul__ = __imul__ = None


class AccountStatistics(BaseModelConfig):
    pass


class AccountStatus(BaseModelConfig):
    online: bool
    good: bool
    stat: AccountStatistics


class Friend(BaseModelConfig):
    user_id: Annotated[str, BeforeValidator(str)]
    nickname: str
    remark: str | None = None
    sex: str | None = None
    level: int | None = None
    age: int | None = None
    birthday: date | None = None
    phone_num: str | None = None
    email: str | None = None
    category_id: int | None = None

    @model_validator(mode="before")
    @classmethod
    def combine_birthday_fields(cls, data):
        if isinstance(data, dict):
            year = data.get("birthday_year")
            month = data.get("birthday_month")
            day = data.get("birthday_day")
            if all(isinstance(x, int) for x in (year, month, day)):
                with contextlib.suppress(ValueError):
                    data["birthday"] = date(year, month, day)
            # 移除原始的三个生日字段
            data.pop("birthday_year", None)
            data.pop("birthday_month", None)
            data.pop("birthday_day", None)

        return data


class FriendCategory(BaseModelConfig):
    category_id: int = Field(validation_alias="categoryId")
    category_name: str = Field(validation_alias="categoryName")
    category_mb_count: int = Field(validation_alias="categoryMbCount")
    online_count: int = Field(validation_alias="onlineCount")
    buddy_list: list[Friend] = Field(validation_alias="buddyList")


class RecentContact(BaseModelConfig):
    peer_uin: Annotated[str, BeforeValidator(str)] = Field(validation_alias="peerUin")
    remark: str
    msg_time: Annotated[datetime, BeforeValidator(lambda t: datetime.fromtimestamp(int(t)))] = Field(validation_alias="msgTime")
    chat_type: int = Field(validation_alias="chatType")
    msg_id: Annotated[str, BeforeValidator(str)] = Field(validation_alias="msgId")
    send_nickname: str = Field(validation_alias="sendNickName")
    send_member_name: str = Field(validation_alias="sendMemberName")
    peer_name: str = Field(validation_alias="peerName")
    latest_msg: Message | None = Field(None, validation_alias="lastestMsg")


class Stranger(BaseModelConfig):
    user_id: Annotated[str, BeforeValidator(str)]
    nickname: str
    sex: str
    age: int | None = None
    level: int | None = None
    long_nick: str | None = None
    reg_time: Annotated[datetime, BeforeValidator(datetime.fromtimestamp)] | None = None
    is_vip: bool | None = None
    remark: str | None = None


class UserAccount(BaseModelConfig):
    status: int

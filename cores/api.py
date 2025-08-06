# Copyright (C) 2025 github.com/Eric-Joker
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from typing import Any, Literal, Optional

from .misc import RobustBaseModel


class GroupMemberInfo(RobustBaseModel):
    group_id: Optional[int] = None
    user_id: Optional[int] = None
    nickname: Optional[str] = None
    card: Optional[str] = None
    sex: Optional[Literal["male", "female", "unknown"]] = None
    age: Optional[int] = None
    area: Optional[str] = None
    join_time: Optional[int] = None
    last_sent_time: Optional[int] = None
    level: Optional[str] = None
    qq_level: Optional[int] = None
    role: Optional[Literal["owner", "admin", "member"]] = None
    unfriendly: Optional[bool] = None
    title: Optional[str] = None
    title_expire_time: Optional[int] = None
    card_changeable: Optional[bool] = None
    shut_up_timestamp: Optional[int] = None
    is_robot: Optional[bool] = None


class Stranger(RobustBaseModel):
    uid: Optional[str] = None
    uin: Optional[str] = None
    nick: Optional[str] = None
    remark: Optional[str] = None
    constellation: Optional[int] = None
    shengXiao: Optional[int] = None
    kBloodType: Optional[int] = None
    homeTown: Optional[str] = None
    makeFriendCareer: Optional[int] = None
    pos: Optional[str] = None
    college: Optional[str] = None
    country: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    postCode: Optional[str] = None
    address: Optional[str] = None
    regTime: Optional[int] = None
    interest: Optional[str] = None
    labels: Optional[list[str]] = None
    qqLevel: Optional[int] = None
    qid: Optional[str] = None
    longNick: Optional[str] = None
    birthday_year: Optional[int] = None
    birthday_month: Optional[int] = None
    birthday_day: Optional[int] = None
    age: Optional[int] = None
    sex: Optional[Literal["male", "female", "unknown"]] = None
    eMail: Optional[str] = None
    phoneNum: Optional[str] = None
    categoryId: Optional[int] = None
    richTime: Optional[int] = None
    richBuffer: Optional[dict[str, int]] = None
    status: Optional[int] = None
    extStatus: Optional[int] = None
    batteryStatus: Optional[int] = None
    termType: Optional[int] = None
    netType: Optional[int] = None
    iconType: Optional[int] = None
    customStatus: Optional[Any] = None
    setTime: Optional[str] = None
    specialFlag: Optional[int] = None
    abiFlag: Optional[int] = None
    eNetworkType: Optional[int] = None
    showName: Optional[str] = None
    termDesc: Optional[str] = None
    musicInfo: Optional[dict[str, Any]] = None
    extOnlineBusinessInfo: Optional[dict[str, Any]] = None
    extBuffer: Optional[dict[str, Any]] = None
    user_id: Optional[int] = None
    nickname: Optional[str] = None
    long_nick: Optional[str] = None
    reg_time: Optional[int] = None
    is_vip: Optional[bool] = None
    is_years_vip: Optional[bool] = None
    vip_level: Optional[int] = None
    login_days: Optional[int] = None


class Friend(RobustBaseModel):
    birthday_year: Optional[int] = None
    birthday_month: Optional[int] = None
    user_id: Optional[int] = None
    age: Optional[int] = None
    phone_num: Optional[str] = None
    email: Optional[str] = None
    category_id: Optional[int] = None
    nickname: Optional[str] = None
    remark: Optional[str] = None
    sex: Optional[Literal["male", "female", "unknown"]] = None
    level: Optional[int] = None

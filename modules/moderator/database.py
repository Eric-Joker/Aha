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
from sqlalchemy import Boolean, Column, DateTime, Integer

from services.database import dbBase


class BlackList(dbBase):
    __tablename__ = "blacklist"
    user_id = Column(Integer, primary_key=True)


class Verify(dbBase):
    __tablename__ = "verify"
    user_id = Column(Integer, primary_key=True)
    code = Column(Integer)
    times = Column(Integer, default=0)
    is_validated = Column(Boolean, default=False)


class HubIncrease(dbBase):
    __tablename__ = "hub_increase"
    user_id = Column(Integer, primary_key=True)
    time = Column(DateTime, index=True)


class Shutup(dbBase):
    __tablename__ = "shutup"
    user_id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime)
    remain = Column(Integer, default=0)

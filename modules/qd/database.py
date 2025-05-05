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
from sqlalchemy import Column, DateTime, Integer

from services.database import dbBase


class UserSign(dbBase):
    __tablename__ = "sign"
    user_id = Column(Integer, primary_key=True)
    last_sign = Column(DateTime)
    continuous_days = Column(Integer, default=0)
    streak_stage = Column(Integer, default=0)
    last_bonus_date = Column(DateTime)

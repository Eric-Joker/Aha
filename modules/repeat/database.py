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
from sqlalchemy import Column, Integer

from services.database import dbBase


class Repeat(dbBase):
    __tablename__ = "repeat"
    user_id = Column(Integer, primary_key=True)
    group_id = Column(Integer, primary_key=True)
    enable_time = Column(Integer, index=True)
    count = Column(Integer, default=0)
    last_time = Column(Integer)

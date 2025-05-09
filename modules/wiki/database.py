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

from cores import Iterable, YarlURL
from services.database import dbBase


class WikiSearch(dbBase):
    __tablename__ = "wiki_search"
    user_id = Column(Integer, primary_key=True)
    base_url = Column(YarlURL)
    results = Column(Iterable)
    timestamp = Column(Integer)

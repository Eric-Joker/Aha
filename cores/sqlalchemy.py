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
from sqlalchemy import TypeDecorator, VARCHAR, JSON
from yarl import URL


class Iterable(TypeDecorator):
    impl = JSON
    cache_ok = True  # 避免警告

    def process_bind_param(self, value, _):
        return list(value) if value else None

    def process_result_value(self, value, _):
        return tuple(value) if value else None

class YarlURL(TypeDecorator):
    impl = VARCHAR(2048)  # 假设 URL 最大长度 2048
    cache_ok = True  # 避免警告

    def process_bind_param(self, value: URL | None, _):
        return str(value)

    def process_result_value(self, value: str | None, _):
        return URL(value)

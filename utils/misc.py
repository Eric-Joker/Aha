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
from decimal import ROUND_HALF_UP, Decimal
from inspect import iscoroutinefunction


def round_decimal(num: Decimal, digits=2):
    return num.quantize(Decimal(f'0.{"0" * digits}'), rounding=ROUND_HALF_UP).normalize()


def get_byte_length(s: str, encoding="gbk"):
    return len(s.encode(encoding))


async def async_run_func(func, *args, **kwargs):
    return (await func(*args, **kwargs)) if iscoroutinefunction(func) else func(*args, **kwargs)


class Wrapper:
    def __init__(self, wrapped_obj, method_names, action, *args, **kwargs):
        self.wrapped_obj = wrapped_obj
        self._wrapped_methods = {}
        for name in method_names:
            if method := getattr(wrapped_obj, name, None):
                self._wrapped_methods[name] = action(*args, **kwargs)(method)

    @property
    def __class__(self):
        return self.wrapped_obj.__class__

    def __getattr__(self, name):
        return self._wrapped_methods.get(name) or getattr(self.wrapped_obj, name)

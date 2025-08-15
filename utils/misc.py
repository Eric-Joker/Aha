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
    __slots__ = ("wrapped_obj", "_wrapped_methods")

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


def convert_char(char):
    # 处理半角字符
    if (code := ord(char)) == 0x20:  # 空格
        return chr(0x3000)
    elif 0x21 <= code <= 0x7E:
        return chr(code + 0xFEE0)
    # 处理全角字符
    elif code == 0x3000:  # 空格
        return chr(0x20)
    elif 0xFF01 <= code <= 0xFF5E:
        return chr(code - 0xFEE0)
    return char


def convert_text(text):
    return "".join(convert_char(c) for c in text)

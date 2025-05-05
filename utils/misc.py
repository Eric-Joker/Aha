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
import sys
from asyncio import get_running_loop, set_event_loop_policy
from decimal import ROUND_HALF_UP, Decimal
from inspect import iscoroutinefunction
from logging import getLogger

from pydantic import BaseModel, ConfigDict


def install_uvloop():
    if sys.platform != "win32":
        import uvloop

        if sys.version_info >= (3, 11):
            set_event_loop_policy(uvloop.EventLoopPolicy())
        else:
            uvloop.install()


def round_decimal(num: Decimal, digits=2):
    return num.quantize(Decimal(f'0.{"0" * digits}'), rounding=ROUND_HALF_UP).normalize()


class RobustBaseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_default=False, populate_by_name=True)
    _validated_classes = set()

    def model_post_init(self, __context) -> None:
        super().model_post_init(__context)
        class_id = f"{self.__class__.__module__}.{self.__class__.__qualname__}"
        if class_id not in self._validated_classes:
            self._validated_classes.add(class_id)
            get_running_loop().create_task(self._async_check())

    @classmethod
    def _field_metadata(cls) -> tuple[set[str], dict[str, str]]:
        required = set()
        alias_map = {}
        for name, info in cls.model_fields.items():
            if info.is_required():
                required.add(name)

            # 优先处理validation_alias
            aliases = []
            if info.validation_alias:
                if isinstance(info.validation_alias, str):
                    aliases.append(str(info.validation_alias))
                else:
                    aliases.extend([str(a) for a in info.validation_alias])
            if info.serialization_alias:
                aliases.append(str(info.serialization_alias))
            if ag := cls.model_config.get("alias_generator"):
                aliases.append(ag(name))

            # 去重并保留唯一别名映射
            for alias in filter(None, set(aliases)):
                if alias not in alias_map:
                    alias_map[alias] = name

        return required, alias_map

    async def _async_check(self):
        data = self.model_dump(mode="json")
        required, alias_map = self._field_metadata()

        if missing := required - set(data.keys()):
            getLogger(self.__qualname__).warning(f"Missing fields in {self.__class__.__name__}: {missing}")
        if extra := set(data.keys()) - set(alias_map) - set(self.__class__.model_fields.keys()):
            getLogger(self.__qualname__).warning(f"Extra fields in {self.__class__.__name__}: {extra}")


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

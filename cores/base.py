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
from asyncio import get_running_loop
from logging import getLogger

from pydantic import BaseModel, ConfigDict


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

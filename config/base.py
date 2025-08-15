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
from collections.abc import Iterable
from logging import getLogger
from os import getenv
from pathlib import Path
from sys import exit

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from cores import MODULE_PATTERN, SingletonMeta, caller_module

logger = getLogger(__name__)


class Config(metaclass=SingletonMeta):
    __slots__ = (
        "_yaml",
        "_data",
        "_old_data",
        "_env",
        "_config_file",
        "_loaded",
        "_default_types",
        "_default_used",
        "_modified",
    )

    def __init__(self):
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._data = CommentedMap()
        self._env = getenv("BOT_ENV", "dev")
        self._config_file = Path(f"config.{self._env}.yml")
        self._loaded = False
        self._default_types = {}
        self._default_used = False
        self._modified = set()

    def _ensure_loaded(self):
        if not self._loaded:
            if self._config_file.exists():
                with open(self._config_file, "r", encoding="utf-8") as f:
                    self._old_data = self._yaml.load(f)
                    if self._old_data:
                        self._data.update(self._old_data)
            self._loaded = True

    def __getattr__(self, key: str):
        if key[0] == "_" and key[:2] != "__":
            logger.warning(f"Attempting to access a private attribute: {key}")
        return self.get_config(key, module=caller_module())

    def __setattr__(self, key: str, value):
        if key.startswith("_"):
            super().__setattr__(key, value)
        else:
            self.set_config(key, value, module=caller_module())

    def _convert_type(self, value, target_type):
        if isinstance(value, dict):
            return value
        if target_type is tuple:
            if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
                return tuple(value)
            else:
                return (value,)
        elif target_type is frozenset:
            if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
                return frozenset(value)
            else:
                return frozenset((value,))
        return value

    def _check_permission(self, module: str, caller: str):
        if module and caller and MODULE_PATTERN.match(caller):
            raise PermissionError(f"Permission denied for module: {caller}")

    def get_config(self, key: str, default=None, module: str = None, comment: str = None):
        self._ensure_loaded()
        caller = caller_module()
        storage_module = module or caller

        # 查找配置项
        for mod in ("aha", storage_module):
            if mod in self._data and key in self._data[mod]:
                # 优先使用default参数的类型，其次查找记录的默认类型
                if default is None:
                    target_type = self._default_types.get(mod, {}).get(key)
                else:
                    target_type = self._default_types.setdefault(mod, {}).setdefault(key, type(default))
                return self._data[mod][key] if target_type is None else self._convert_type(self._data[mod][key], target_type)
        if (expr_extractors := self._data.get("expr_extractors")) is not None:
            if (key_dict := expr_extractors.get(key)) is not None and (mod_name := storage_module[8:]) in key_dict:
                return key_dict[mod_name]

        # 设置默认值
        if default is None:
            return None
        self._check_permission(module, caller)
        if storage_module not in self._data:
            self._data[storage_module] = CommentedMap()
            self._data.yaml_set_comment_before_after_key(storage_module, before="\n")

        if isinstance(default, Iterable) and not isinstance(default, (tuple, frozenset, dict, str, bytes)):
            logger.error(f"Iterable default must be tuple or frozenset. Module: {caller}")

        # 记录默认类型并存储值
        self._default_types.setdefault(storage_module, {})[key] = type(default)
        stored_value = list(default) if isinstance(default, (tuple, frozenset)) else default

        self._data[storage_module][key] = stored_value
        self._modified.add((storage_module, key))
        if comment:
            self._data[storage_module].yaml_set_comment_before_after_key(key, comment, 2)

        self._default_used = True
        return default

    def set_config(self, key: str, value, module: str = None):
        self._check_permission(module, (caller := caller_module()))
        module = module or caller
        self._modified.add((module, key))

        if isinstance(value, Iterable) and not isinstance(value, (tuple, frozenset, dict, str, bytes)):
            logger.error(f"Iterable value must be tuple or frozenset. Module: {caller}")

        self._data.setdefault(module or caller, CommentedMap())[key] = (
            list(value) if isinstance(value, (tuple, frozenset)) else value
        )

    def save(self):
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        current_data = CommentedMap()
        if self._config_file.exists():
            with open(self._config_file, "r", encoding="utf-8") as f:
                current_data = self._yaml.load(f) or CommentedMap()

        # 将程序修改的项合并到当前配置
        for module, key in self._modified:
            if (module_data := self._data.get(module)) and key in module_data:
                if module not in current_data:
                    current_data[module] = CommentedMap()
                current_data[module][key] = module_data[key]

        with open(self._config_file, "w", encoding="utf-8") as f:
            self._yaml.dump(current_data, f)

        self._data = current_data
        self._modified.clear()

    def _has_new_keys(self, new_data, old_data):
        if not isinstance(new_data, dict):
            return False
        if not isinstance(old_data, dict):
            return True

        for key in new_data:
            if key not in old_data:
                return True
            if self._has_new_keys(new_data[key], old_data[key]):
                return True
        return False

    def finalize_initialization(self):
        if not self._default_used:
            for module, key in self._modified:
                if self._has_new_keys(self._data[module][key], self._old_data.get(module, {}).get(key, None)):
                    self._default_used = True
                    break

        self._old_data = None

        if self._default_used:
            self.save()
            logger.warning("检测到新的配置，已写入至配置文件，请修改后重启。")
            exit(1)

    # region 公共属性
    @property
    def super(self) -> tuple[int, ...]:
        return self.get_config("super", (114514,), "aha", "超级用户ID。")

    @property
    def action_groups(self) -> frozenset[int]:
        return self.get_config("action_groups", frozenset({1, 2}), "aha", "默认启用群组。")

    @property
    def message_prefix(self) -> str:
        return self.get_config("message_prefix", "\\", "aha", "匹配词条的消息前缀。")

    @property
    def limit(self) -> str:
        return self.get_config("limit", 3, "aha", "1分钟内机器人最多处理1个用户的多少条指令。")

    @property
    def database(self) -> str:
        return self.get_config("database", "sqlite+aiosqlite:///data.db", "aha", "用于 sqlalchemy 异步引擎的数据库 url.")

    @property
    def cache_cron(self) -> str:
        return self.get_config("cache_cron", "0 0 * * *", "aha", "清理部分缓存的 crontab。")

    @property
    def fastapi_port(self) -> int:
        return self.get_config("fastapi_port", 6550, "aha", "FastAPI 的监听端口，小于1024时禁用 FastAPI。")

    @property
    def enable_fastapi(self) -> bool:
        return self.fastapi_port > 1023

    @property
    def alembic(self) -> str:
        return self.get_config(
            "alembic", "sqlite:///data.db", "aha", "用于 alembic 的数据库 url。由于其无法使用异步所以与 `database` 字段区分。"
        )

    # endregion


cfg = Config()

# 保证配置文件键值顺序
cfg.super
cfg.action_groups
cfg.message_prefix
cfg.database
cfg.alembic
cfg.limit
cfg.cache_cron
cfg.fastapi_port

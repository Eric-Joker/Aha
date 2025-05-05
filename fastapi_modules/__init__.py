import importlib
import sys
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
from pkgutil import iter_modules

__all__ = []

for _, module_name, _ in iter_modules(__path__):
    module = importlib.import_module(f".{module_name}", __name__)
    globals()[module_name] = module
    __all__.append(module_name)


def reload_fastapi_modules():
    modules = []
    # 收集当前包及其所有子模块
    for modname in list(sys.modules):
        if modname.startswith(__name__ + ".") and modname != f"{__name__}.reload" and not ".database" in modname:
            modules.append(sys.modules[modname])

    # 按模块层级深度降序排序（确保先加载子模块）
    modules.sort(key=lambda m: m.__name__.count("."), reverse=True)

    for module in modules:
        importlib.reload(module)

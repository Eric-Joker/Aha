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
import threading
from abc import ABCMeta
import sys
from multiprocessing import current_process
from logging import getLogger


IS_WINDOWS = sys.platform == "win32"


class RestrictiveMeta(ABCMeta):
    def __call__(cls, *args, **kwargs):
        if sys._getframe(1).f_globals.get("__name__") != cls.__module__:
            raise RuntimeError(f"Cannot instantiate {cls.__name__} outside of module {cls.__module__}")
        return super().__call__(*args, **kwargs)


class SingletonMeta(type):
    """
    线程安全的进程内单例元类
    """

    _instances = {}
    _thread_lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        if current_process().name != "MainProcess":
            getLogger(cls.__qualname__).warning(
                f"Creating {cls.__name__} instance in child process. "
                "Note: This will create a separate instance per process, not a true singleton."
            )

        if cls not in cls._instances:
            with cls._thread_lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

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
import multiprocessing
import threading
from abc import ABCMeta
import sys


IS_WINDOWS = sys.platform == "win32"


class RestrictiveMeta(ABCMeta):
    def __call__(cls, *args, **kwargs):
        if sys._getframe(1).f_globals.get("__name__") != cls.__module__:
            raise RuntimeError(f"Cannot instantiate {cls.__name__} outside of module {cls.__module__}")
        return super().__call__(*args, **kwargs)


class BaseSingletonMeta(type):
    """
    线程安全的进程内单例元类
    """

    _instances = {}
    _thread_lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._thread_lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class ProcessSafeSingletonMeta(BaseSingletonMeta):
    """
    跨进程安全的单例元类
    """

    _process_lock = None

    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        if IS_WINDOWS:
            # Windows使用spawn上下文
            cls._mp_ctx = multiprocessing.get_context("spawn")
            cls._process_lock = cls._mp_ctx.Lock()
        else:
            cls._process_lock = multiprocessing.Lock()

    def __call__(cls, *args, **kwargs):
        if not hasattr(cls, "_shared_instance"):
            with cls._process_lock:
                if not hasattr(cls, "_shared_instance"):
                    # 主进程创建实例并共享
                    if multiprocessing.parent_process() is None:
                        cls._shared_instance = super().__call__(*args, **kwargs)
                    else:
                        # 子进程等待主进程初始化完成
                        while not hasattr(cls, "_shared_instance"):
                            threading.Event().wait(0.1)
        return cls._shared_instance


if IS_WINDOWS:
    SingletonMeta = ProcessSafeSingletonMeta
else:
    SingletonMeta = BaseSingletonMeta

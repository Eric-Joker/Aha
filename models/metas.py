import threading
from multiprocessing import current_process


class PerProcessSingletonMeta(type):
    """线程安全的进程内单例元类"""

    _instances = {}
    _thread_lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._thread_lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

    def __getattr__(cls, name: str):
        if name.startswith("_"):
            return super().__getattr__(name)
        
        try:
            return getattr(cls._instances.get(cls), name)
        except AttributeError as e:
            from core.i18n import _

            raise RuntimeError(_("models.pre_proc_singleton_meta.getattr_error") % cls.__qualname__) from e


class SingletonMeta(PerProcessSingletonMeta):
    """线程安全的进程内单例元类"""

    def __call__(cls, *args, **kwargs):
        if current_process().name != "MainProcess":
            from core.i18n import _

            raise ImportError(f"Refusing to create class '{cls.__qualname__}' in a subprocess, as this may violate the singleton pattern.")
        return super().__call__(*args, **kwargs)

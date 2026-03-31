from gc import collect
from multiprocessing import current_process
from threading import Lock
from weakref import WeakValueDictionary


class PerProcessSingletonMeta(type):
    """线程安全的进程内单例元类"""

    _instances = WeakValueDictionary()
    _thread_lock = Lock()
    
    def __new__(cls, name, bases, namespace):
        if slots := namespace.get("__slots__"):
            namespace['__slots__'] = (*slots, "__weakref__")
        return super().__new__(cls, name, bases, namespace)

    def __call__(cls, *args, **kwargs):
        collect()
        if cls in cls._instances:
            return cls._instances[cls]
        with cls._thread_lock:
            if cls not in cls._instances:
                cls._instances[cls] = instance = super().__call__(*args, **kwargs)
        return instance

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

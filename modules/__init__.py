import importlib
import os
import sys
from logging import getLogger
from pkgutil import iter_modules

__all__ = []

SYSTEM_MODULES = {"reload", "cache_manager", "id_mapper"}
_logger = getLogger("AHA (module)")


async def init_load_mod():
    from yaspin import yaspin
    from yaspin.spinners import Spinners

    from core.i18n import load_locales, _

    _checked_paths = set()
    modules = []

    for __, module_name, is_pkg in iter_modules(__path__):
        if module_name.startswith("DISABLED"):
            continue
        if (module_path := os.path.join(__path__[0], module_name if is_pkg else f"{module_name}.py")) in _checked_paths:
            continue

        _checked_paths.add(module_path)
        modules.append(f"{__name__}.{module_name}")

    await load_locales(*modules)

    with yaspin(Spinners, text="Loading aha modules", color="cyan", timer=True) as spinner:
        for mod in modules:
            spinner.text = f"Loading aha module {mod} ({len(__all__)} modules loaded)"
            try:
                globals()[mod] = importlib.import_module(mod)
                __all__.append(mod)
            except ImportError as e:
                _logger.warning(_("module.import.error") % {"mod": mod, "err": e})
                spinner.color = "red"

        spinner.text = _("module.import.done") % len(__all__)
        spinner.ok("✅")


async def reload_modules():
    from core.cache import clear_all_cache
    from core.config import cfg
    from core.expr import extractor_registrations, redirect_extractors
    from core.i18n import load_locales
    from core.router import clear_handlers, process_clean, process_start
    from services.apscheduler import scheduler
    from services.data_store import clean_data_store

    clear_handlers()
    await process_clean()
    await scheduler.reset_temp_sched()
    await clean_data_store()
    extractor_registrations.clear()
    clear_all_cache()
    cfg.reload_and_save()

    # 重载 Python 模块
    current_module_prefix = f"{__name__}."
    modules = []
    root_module_names = set()
    for modname, mod in sys.modules.items():
        if not modname.startswith(current_module_prefix) or ".database" in modname:
            continue
        modules.append(mod)
        root_module_names.add(modname if (pos := modname.find('.', modname.find('.') + 1)) == -1 else modname[:pos])
    
    await load_locales(*root_module_names)
    modules.sort(key=lambda m: m.__name__.count("."), reverse=True)  # 按模块层级深度降序排序（确保先加载子模块）
    for module in modules:
        importlib.reload(module)

    redirect_extractors()
    await process_start()

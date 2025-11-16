import importlib
import os
import sys
from asyncio import create_task, gather
from contextlib import suppress
from logging import getLogger
from pkgutil import iter_modules

from anyio import Path
from tqdm import tqdm

SYSTEM_MODULES = {"reload", "cache_manager", "id_mapper"}
persist_blacklist = set()
persist_whitelist = set()
_logger = getLogger("AHA")


async def disable_modules(*mods: str):
    tasks = []
    for root in __path__:
        root = Path(root)
        for mod in mods:
            with suppress(OSError):
                tasks.append(create_task((root / mod).rename(root / f"DISABLED{mod}")))
            with suppress(OSError):
                tasks.append(create_task((root / f"{mod}.py").rename(root / f"DISABLED{mod}.py")))
    await gather(*tasks)


async def enable_modules(*mods: str):
    tasks = []
    for root in __path__:
        root = Path(root)
        for mod in mods:
            with suppress(OSError):
                tasks.append(create_task((root / f"DISABLED{mod}").rename(root / mod)))
            with suppress(OSError):
                tasks.append(create_task((root / f"DISABLED{mod}.py").rename(root / f"{mod}.py")))
    await gather(*tasks)


async def init_load_mod(exclude: set = None):
    """
    Args:
        exclude: 与 `__name__` 的相对模块名。
    """
    from core.i18n import _, load_locales

    _checked_paths = set()
    modules = {}

    if exclude:
        exclude.update(persist_blacklist)
    else:
        exclude = persist_blacklist

    for finder, module_name, is_pkg in iter_modules(__path__):
        if (
            module_name.startswith("DISABLED")
            or module_name in exclude
            or persist_whitelist
            and module_name not in persist_whitelist
            or module_name in globals()
        ):
            continue
        if (module_path := os.path.join(finder.path, module_name if is_pkg else f"{module_name}.py")) in _checked_paths:
            continue

        _checked_paths.add(module_path)
        modules[(f"{__name__}.{module_name}")] = module_name

    await load_locales(*modules)

    loaded = 0
    with tqdm(
        modules.items(), desc="Loading aha modules", bar_format="{desc}: |{bar}| {n_fmt}/{total_fmt} {elapsed}", leave=False
    ) as bar:
        for mod, shorter in bar:
            bar.set_description(f"Loading aha module {shorter} ({loaded} loaded)")
            try:
                globals()[mod] = importlib.import_module(mod)
                loaded += 1
            except Exception:
                _logger.warning(_("module.import.error") % shorter, exc_info=True)
                bar.colour = "yellow"

    _logger.info(_("module.import.done") % loaded)


async def reload_modules(disable: set[str] = None):
    from core.cache import clear_all_cache
    from core.config import cfg
    from core.expr import extractor_registrations, redirect_extractors
    from core.i18n import _, load_locales
    from core.dispatcher import clear_handlers, process_clean, process_start
    from services.apscheduler import sched
    from services.data_store import clean_data_store
    from utils.misc import uninstall_module

    clear_handlers()
    await process_clean()
    await sched.reset_temp_sched()
    await clean_data_store()
    extractor_registrations.clear()
    clear_all_cache()
    await cfg.reload_and_save()

    # 重载 Python 模块
    current_module_prefix = f"{__name__}."
    modules = []
    root_module_names = set()
    root_module_shorter_names = set()
    exclueded = set()
    for modname in tuple(sys.modules):
        if not modname.startswith(current_module_prefix) or ".database" in modname:
            continue

        aha_mod = modname if (pos := modname.find(".", modname.find(".") + 1)) == -1 else modname[:pos]
        shorter_mod = aha_mod[8:]

        # 排除模块
        if disable and shorter_mod in disable:
            if shorter_mod not in exclueded:
                # 重命名文件
                mod_path = Path(sys.modules[aha_mod].__file__.replace(f"{os.sep}__init__.py", ""))
                try:
                    await mod_path.rename(mod_path.parent / f"DISABLED{mod_path.name}")
                except OSError:
                    _logger.error(_("module.disable.error") % shorter_mod, exc_info=True)

                exclueded.add(shorter_mod)
                uninstall_module(aha_mod)
                globals()[aha_mod] = None
            continue

        modules.append(sys.modules[modname])
        root_module_names.add(aha_mod)
        root_module_shorter_names.add(shorter_mod)

    await load_locales(*root_module_names)

    modules.sort(key=lambda m: m.__name__.count("."), reverse=True)  # 按模块层级深度降序排序（确保先加载子模块）
    with tqdm(modules, desc="Reloading aha modules", bar_format="{l_bar}{bar}| {elapsed}", leave=False) as bar:
        for module in bar:
            try:
                bar.set_description(f"Reloading module {module.__name__}")
                importlib.reload(module)
            except Exception:
                _logger.error(_("module.import.error") % module.__name__, exc_info=True)
                bar.colour = "red"
        bar.set_description(_("main.run_start_callback"))
        redirect_extractors()
        await process_start()

    _logger.info(_("module.reload.done") % len(root_module_names))
    await init_load_mod(exclude=root_module_shorter_names)


async def load_modules(*modules: str):
    """自动启用模块"""
    from core.i18n import _, load_locales

    await load_locales(*(full_names := [f"{__name__}.{mod}" for mod in modules]))
    loaded = []
    for i, mod in enumerate(full_names):
        for root in __path__:
            with suppress(OSError):
                await ((root := Path(root)) / f"DISABLED{modules[i]}").rename(root / modules[i])
            with suppress(OSError):
                await (root / f"DISABLED{modules[i]}.py").rename(root / f"{modules[i]}.py")
        try:
            globals()[mod] = importlib.import_module(mod)
            loaded.append(modules[i])
        except Exception:
            _logger.warning(_("module.import.error") % mod, exc_info=True)
    _logger.info(_("module.import.done.with_names") % " ".join(loaded))
    return loaded

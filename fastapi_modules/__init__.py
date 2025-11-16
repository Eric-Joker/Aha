import os
import importlib
from logging import getLogger
from pkgutil import iter_modules

from tqdm import tqdm

_logger = getLogger("AHA")


async def init_load_mod():
    from core.i18n import load_locales, _

    _checked_paths = set()
    modules = {}

    for finder, module_name, is_pkg in iter_modules(__path__):
        if module_name.startswith("DISABLED"):
            continue
        if (module_path := os.path.join(finder.path, module_name if is_pkg else f"{module_name}.py")) in _checked_paths:
            continue

        _checked_paths.add(module_path)
        modules[(f"{__name__}.{module_name}")] = module_name

    await load_locales(*modules)

    loaded = 0
    with tqdm(
        modules.items(), desc="Loading fastapi modules", bar_format="{desc}: |{bar}| {n_fmt}/{total_fmt} {elapsed}", leave=False
    ) as bar:
        for mod, shorter in bar:
            bar.set_description(f"Loading fastapi module {shorter} ({loaded} loaded)")
            try:
                globals()[mod] = importlib.import_module(mod)
                loaded += 1
            except Exception:
                _logger.warning(_("fastapi_module.import.error", "bots.fastapi") % mod, exc_info=True)
                bar.colour = "yellow"
    _logger.info(_("fastapi_module.import.done", "bots.fastapi") % loaded)

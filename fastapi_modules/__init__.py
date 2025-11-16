import os
import importlib
from logging import getLogger
from pkgutil import iter_modules

from yaspin import yaspin
from yaspin.spinners import Spinners

from core.i18n import load_locales, _

__all__ = []

_logger = getLogger("AHA (fastapi module)")


async def init_load_mod():
    _checked_paths = set()
    modules = []

    for __, module_name, is_pkg in iter_modules(__path__):
        if (module_path := os.path.join(__path__[0], module_name if is_pkg else f"{module_name}.py")) in _checked_paths:
            continue
        if module_name.startswith("DISABLED"):
            continue

        _checked_paths.add(module_path)
        modules.append(f"{__name__}.{module_name}")

    await load_locales(*modules)

    with yaspin(Spinners, text=_("fastapi_module.import.short"), color="cyan", timer=True) as spinner:
        for mod in modules:
            spinner.text = _("fastapi_module.import.long") % {"count": len(__all__), "mod": mod}
            try:
                globals()[mod] = importlib.import_module(mod)
                __all__.append(mod)
            except ImportError as e:
                _logger.warning(_("fastapi_module.import.error") % {"mod": mod, "err": e})
                spinner.color = "red"

        spinner.text = _("fastapi_module.import.done") % len(__all__)
        spinner.ok("✅")

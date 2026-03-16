import os
import sys
from asyncio import create_task, gather
from collections import defaultdict
from collections.abc import Callable
from functools import partial
from logging import getLogger
from multiprocessing import current_process
from re import Pattern, compile

from aiofiles import open
from anyio import Path
from ruamel.yaml import YAML

import core.status
from utils.misc import caller_aha_module

__all__ = ("create_translator", "gettext", "_")

# fmt: off
LANGUAGE_FALLBACKS = {
    "zh": ("zh_CN", "zh_TW", "zh_HK", "zh_SG", "zh_MO"),
    "en": ("en_US", "en_GB", "en_CA", "en_AU", "en_NZ", "en_IN", "en_IE", "en_ZA", "en_PH", "en_SG"),
    "es": ("es_ES", "es_MX", "es_AR", "es_CO", "es_CL", "es_PE", "es_VE", "es_EC", "es_GT", "es_CU", "es_DO",
           "es_BO", "es_PY", "es_UY", "es_CR", "es_SV", "es_HN", "es_NI", "es_PA", "es_PR"),
    "fr": ("fr_FR", "fr_CA", "fr_BE", "fr_CH", "fr_LU", "fr_MC", "fr_SN", "fr_CI",
           "fr_CD", "fr_CM", "fr_ML", "fr_BF", "fr_NE", "fr_TD", "fr_GA", "fr_BJ", "fr_TG", "fr_MG"),
    "de": ("de_DE", "de_AT", "de_CH", "de_LI", "de_LU"),
    "pt": ("pt_BR", "pt_PT", "pt_AO", "pt_MZ", "pt_GW", "pt_CV"),
    "ru": ("ru_RU", "ru_UA", "ru_KZ", "ru_BY", "ru_KG", "ru_MD"),
    "ar": ("ar_SA", "ar_EG", "ar_AE", "ar_MA", "ar_DZ", "ar_IQ", "ar_SD", "ar_JO", "ar_LB", "ar_PS",
           "ar_TN", "ar_LY", "ar_YE", "ar_KW", "ar_QA", "ar_BH", "ar_OM"),
    "it": ("it_IT", "it_CH", "it_SM"),
    "nl": ("nl_NL", "nl_BE", "nl_SR", "nl_AW", "nl_CW"),
    "sv": ("sv_SE", "sv_FI"),
    "no": ("nb_NO", "nn_NO"),
    "ms": ("ms_MY", "ms_BN", "ms_SG"),
    "bn": ("bn_BD", "bn_IN"),
    "ta": ("ta_IN", "ta_LK", "ta_SG", "ta_MY"),
    "ur": ("ur_PK", "ur_IN"),
    "fa": ("fa_IR", "fa_AF"),
    "sw": ("sw_TZ", "sw_KE", "sw_UG", "sw_RW", "sw_BI"),
    "el": ("el_GR", "el_CY"),
    "tr": ("tr_TR", "tr_CY"),
    "ro": ("ro_RO", "ro_MD"),
    "sr": ("sr_RS", "sr_ME", "sr_BA"),
    "hr": ("hr_HR", "hr_BA"),
    "sq": ("sq_AL", "sq_XK", "sq_MK"),
    "az": ("az_AZ", "az_IR"),
    "kk": ("kk_KZ", "kk_CN"),
    "uz": ("uz_UZ", "uz_AF"),
    "eu": ("eu_ES", "eu_FR"),
    "ca": ("ca_ES", "ca_AD", "ca_FR", "ca_IT"),
    "ti": ("ti_ER", "ti_ET"),
    "so": ("so_SO", "so_ET", "so_KE"),
    "yo": ("yo_NG", "yo_BJ"),
    "ha": ("ha_NG", "ha_NE", "ha_GH"),
    "af": ("af_ZA", "af_NA"),
    "ne": ("ne_NP", "ne_IN"),
    "mn": ("mn_MN", "mn_CN"),
    "bo": ("bo_CN", "bo_IN"),
    "ky": ("ky_KG", "ky_CN"),
    "tg": ("tg_TJ", "tg_AF"),
    "ps": ("ps_AF", "ps_PK"),
    "ku": ("ku_TR", "ku_IQ", "ku_IR", "ku_SY"),
    "hy": ("hy_AM", "hy_LB"),
    "pa": ("pa_IN", "pa_PK"),
    "sd": ("sd_IN", "sd_PK"),
    "oc": ("oc_FR", "oc_ES", "oc_IT"),
    "fy": ("fy_NL", "fy_DE"),
    "ff": ("ff_NG", "ff_SN", "ff_CM", "ff_GN"),
}
# fmt: on
DEFAULT_LANGUAGE = None
loaded_i10n: defaultdict[str, dict[str, dict[str, str]]] = defaultdict(dict)  # dict[module, dict[lang, dict[key, value]]]
_created_translator = defaultdict(dict)  # dict[module, dict[lang, Callable]]
_logger = getLogger("AHA (i18n)")


class LocalizedString(str):
    """用于表达式评估"""

    def __new__(cls, key: str, module: str = None):
        obj = super().__new__(cls, get_translation(key, module))
        obj._key = key
        obj._module = module
        obj.translations = get_all_translations(obj._key, obj._module)
        obj._patterns = None
        return obj

    @property
    def patterns(self) -> dict[str, Pattern]:
        """编译所有已存在语言的翻译为正则表达式"""
        if self._patterns is not None:
            return self._patterns

        self._patterns = {k: compile(v) for k, v in self.translations.items()}
        self.translations: dict = None
        self._key = None
        self._module = None

        return self._patterns


def get_translation(key: str, module: str = None, lang_code: str = None):
    """获取翻译"""
    for lang in _get_fallback_chain(lang_code):
        if ((i18ns := loaded_i10n[module].get(lang)) or (i18ns := loaded_i10n[None].get(lang))) and key in i18ns:
            return i18ns[key]
    return key


def get_all_translations(key: str, module: str | None):
    return {lang: d[key] for lang, d in loaded_i10n[module].items() if key in d}


L18NABLE_MODULE_PATTERN = compile(r"^((?:[^.]*modules|bots)\.[^.]+)")


def gettext(key: str, module: str = None):
    return LocalizedString(key, module or caller_aha_module(pattern=L18NABLE_MODULE_PATTERN))


_ = gettext


def create_translator(module: str = None, lang_code: str = None) -> Callable[[str], str]:
    if (obj := _created_translator[module].get(lang_code)) is None:
        obj = _created_translator[module][lang_code] = partial(get_translation, module=module, lang_code=lang_code)
    return obj


def _get_fallback_chain(lang_code: str | None):
    global DEFAULT_LANGUAGE
    chain = []
    seen = set()

    def add(lang: str):
        if lang in seen:
            return False
        chain.append(lang)
        seen.add(lang)
        return True

    if DEFAULT_LANGUAGE is None:
        if current_process().name == "MainProcess":
            from .config import cfg

            DEFAULT_LANGUAGE = cfg.lang
        else:
            if (DEFAULT_LANGUAGE := core.status.def_lang) is None:
                raise RuntimeError(
                    "Unable to retrieve the default language configuration item. Please do not use localization features in child processes."
                )

    for lang in (lang_code, DEFAULT_LANGUAGE):
        if (
            lang
            and add(lang)
            and (base_lang := lang.split("_")[0]) != lang
            and add(base_lang)
            and base_lang in LANGUAGE_FALLBACKS
        ):
            for dialect in LANGUAGE_FALLBACKS[base_lang]:
                add(dialect)

    for lang in ("en", "zh"):
        if add(lang) and lang in LANGUAGE_FALLBACKS:
            for dialect in LANGUAGE_FALLBACKS[lang]:
                add(dialect)

    return chain


_yaml = YAML(typ="safe")


async def load_locales(*module: str):
    cwd = Path(sys.modules["__main__"].__file__).parent

    if module:
        tasks = []
        for mod in module:
            loaded_i10n[mod].clear()
            module_path = cwd / mod.replace(".", os.sep)
            if (await module_path.is_dir()) and await (locales_path := module_path / "locales").exists():
                tasks.append(create_task(_process_locales_directory(mod, locales_path)))

        if tasks:
            await gather(*tasks)
    else:
        loaded_i10n[None].clear()
        await _process_locales_directory(None, cwd / "locales")


YAML_EXT = {".yml", ".yaml"}


async def _process_locales_directory(module: str | None, locales_path: Path):
    tasks = []
    async for entry in locales_path.iterdir():
        if not await entry.is_file() or entry.suffix.lower() not in YAML_EXT:
            continue
        tasks.append(create_task(_process_locale_file(module, entry)))

    if tasks:
        await gather(*tasks)


async def _process_locale_file(module: str | None, file_path: Path):
    try:
        async with open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()

        if (lang_code := file_path.stem) not in loaded_i10n[module]:
            loaded_i10n[module][lang_code] = {}
        loaded_i10n[module][lang_code].update(_yaml.load(content))
    except Exception as e:
        _logger.error(f"Can't processing {file_path}: {e}")

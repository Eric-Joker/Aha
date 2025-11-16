from core.log import setup_logging, shutdown_logging  # isort: skip
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("--load-only", "-l", metavar="MODULE", nargs="+", help="Load only these modules.")
    parser.add_argument("--exclude", metavar="MODULE", nargs="+", help="Do not load these modules.")
    module_group = parser.add_argument_group("Module Control")
    module_group.add_argument("--disable", "-d", metavar="MODULE", nargs="+", help="Disable these modules.")
    module_group.add_argument("--enable", "-e", metavar="MODULE", nargs="+", help="Enable these modules.")
    parser = parser.parse_args()

    import signal
    import sys
    from asyncio import CancelledError, create_task, gather, get_running_loop, sleep
    from contextlib import suppress
    from logging import getLogger

    from core.config import cfg, init_base_cfgs
    from core.i18n import _, load_locales, loaded_i10n
    from modules import disable_modules, enable_modules, init_load_mod, persist_blacklist, persist_whitelist
    from utils.aio import run_with_uvloop
    from utils.misc import uninstall_module

    setup_logging()
    logger = getLogger("AHA")

    async def main_workflow():
        await load_locales()

        if parser.disable:
            await disable_modules(*parser.disable)
        if parser.enable:
            await enable_modules(*parser.enable)
        if parser.disable or parser.enable:
            exit()
        if parser.load_only:
            persist_whitelist.update(parser.load_only)
        if parser.exclude:
            persist_blacklist.update(parser.exclude)

        init_base_cfgs()

        # isort: skip_file
        from core.database import db_init
        from services.apscheduler import scheduler
        from services.playwright import browser
        from services.file_cache import cfm
        from services.data_store import initialize_all_stores
        from core.expr import redirect_extractors
        from core.router import init_conversations, process_start
        from core.api_service import start_bots

        # import core.identity 由 core.expr 引用

        await init_load_mod()

        redirect_extractors()
        await cfg.finalize_initialization()
        db_init()

        try:
            logger.info(_("main.load_simple_data_store"))
            await initialize_all_stores()
            logger.info(_("main.start_api_services"))
            await start_bots()
            logger.info(_("main.start_extra_services"))
            await scheduler.start()
            await gather(browser.start(), cfm.start_service())
            if cfg.cache_conv:
                logger.info(_("main.start_get_conv"))
                g, u = await init_conversations()
                logger.info(_("main.got_conv") % {"group": g, "user": u})
            logger.info(_("main.run_start_callback"))
            await process_start()
            logger.info(_("main.started"))
            await get_running_loop().create_future()
        except CancelledError:
            pass
        finally:
            await cleanup()

    async def cleanup():
        from core.api_service import clean_bots
        from core.cache import clear_all_cache
        from core.database import db_engine
        from core.expr import extractor_registrations
        from core.router import clear_handlers, process_clean
        from services.apscheduler import scheduler
        from services.data_store import clean_data_store
        from services.playwright import browser
        from utils.network import _httpx_client

        logger.info(_("main.run_cleanup_callback"))
        await process_clean()
        clear_handlers()
        logger.info(_("main.unload_mods"))
        uninstall_module("modules")
        logger.info(_("main.release_res"))
        persist_blacklist.clear()
        persist_whitelist.clear()
        extractor_registrations.clear()
        with suppress(Exception):
            await scheduler.stop()
        with suppress(Exception):
            await _httpx_client.aclose()
        clear_all_cache()
        await clean_data_store()
        await gather(browser.close(), db_engine.dispose(), cfg.reload_and_save(), clean_bots())
        await sleep(0.001)  # 让日志打印出来
        cfg.clean()
        loaded_i10n.clear()
        shutdown_logging()

    async def restart():
        await cleanup()
        (args := [sys.executable]).extend(sys.argv)
        os.execv(sys.executable, args)

    async def main():
        loop = get_running_loop()
        main_task = create_task(main_workflow())
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError, ValueError):
                loop.add_signal_handler(sig, lambda *_: main_task.cancel())
        await main_task

    with suppress(KeyboardInterrupt):
        run_with_uvloop(main())

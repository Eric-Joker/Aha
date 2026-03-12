from core.log import setup_logging, shutdown_logging  # isort: skip
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    import signal
    import subprocess
    import sys
    from asyncio import create_task, gather, get_running_loop, sleep
    from contextlib import suppress
    from logging import getLogger

    import core.status
    from core.arg_parser import parser
    from core.config import cfg, init_base_cfgs
    from core.i18n import _, load_locales
    from modules import disable_modules, enable_modules, init_load_mod, persist_blacklist, persist_whitelist
    from utils.aio import run_with_uvloop

    setup_logging()
    logger = getLogger("AHA")

    async def main_workflow():
        await load_locales()

        if parser.disable:
            await disable_modules(*parser.disable)
        if parser.enable:
            await enable_modules(*parser.enable)
        if parser.disable or parser.enable:
            sys.exit(0)
        if parser.load_only:
            persist_whitelist.update(parser.load_only)
        if parser.exclude:
            persist_blacklist.update(parser.exclude)

        init_base_cfgs()

        # isort: skip_file
        import core.status
        from core.database import db_engine, db_init
        from core.api import init_conversations
        from services.apscheduler import sched
        from services.playwright import browser
        from services.file_cache import start_file_cache_service
        from services.data_store import clean_data_store, initialize_all_stores
        from core.expr import redirect_extractors
        from core.dispatcher import clear_handlers, process_clean, process_start
        from core.api_service import clean_bots, start_bots
        from utils.network import _httpx_client

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
            await sched.start()
            if cfg.cache_conv:
                logger.info(_("main.start_get_conv"))
                conv_counts = (await gather(browser.start(), start_file_cache_service(), init_conversations()))[2]
                logger.info(_("main.got_conv") % {"group": conv_counts[0], "user": conv_counts[1]})
            else:
                await gather(browser.start(), start_file_cache_service())
            logger.info(_("main.run_start_callback"))
            await process_start()
            logger.info(_("main.started"))
            await get_running_loop().create_future()
        except Exception:
            raise
        except BaseException:
            pass
        finally:
            logger.info(_("main.run_cleanup_callback"))
            await process_clean()
            clear_handlers()
            # logger.info(_("main.unload_mods"))
            # uninstall_module("modules")
            logger.info(_("main.release_res"))
            # persist_blacklist.clear()
            # persist_whitelist.clear()
            # extractor_registrations.clear()
            with suppress(Exception):
                await sched.stop()
            with suppress(Exception):
                await _httpx_client.aclose()
            # clear_all_cache()
            await clean_data_store()
            await gather(browser.close(), db_engine.dispose(), cfg.reload_and_save(), clean_bots())
            await sleep(0.001)  # 让日志打印出来
            # cfg.clean()
            # loaded_i10n.clear()
            shutdown_logging()
            if core.status.need_reboot:
                subprocess.Popen((sys.executable, *sys.argv), creationflags=subprocess.CREATE_NEW_CONSOLE)

    async def main():
        loop = get_running_loop()
        core.status.main_task = create_task(main_workflow())
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError, ValueError):
                loop.add_signal_handler(sig, lambda *_: core.status.main_task.cancel())
        await core.status.main_task

    with suppress(KeyboardInterrupt):
        run_with_uvloop(main())

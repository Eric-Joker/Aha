from core.log import setup_logging, shutdown_logging  # isort: skip

import signal
import sys
from asyncio import CancelledError, create_task, gather, get_running_loop, run, sleep, to_thread
from contextlib import suppress
from logging import getLogger

from core.i18n import load_locales, loaded_i10n, _
from utils.aio import install_uvloop

if __name__ == "__main__":
    from core.config import cfg, init_base_cfgs

    setup_logging()

    logger = getLogger("AHA")

    async def main_workflow():
        global cfg, init_base_cfgs, loaded_i10n

        await load_locales()
        init_base_cfgs()

        # isort: skip_file
        from core.database import db_engine, db_init
        from services.apscheduler import scheduler
        from services.playwright import browser
        from core.cache import clear_all_cache
        from services.file_cache import cfm
        from services.data_store import initialize_all_stores, clean_data_store
        from core.api_service import clean_bots, start_bots
        from core.expr import redirect_extractors, extractor_registrations
        from core.router import clear_handlers, init_conversations, process_start, process_clean
        from modules import init_load_mod

        # import core.identity 由 core.expr 引用

        await init_load_mod()

        redirect_extractors()
        cfg.finalize_initialization()
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
            logger.info(_("main.run_cleanup_callback"))
            await process_clean()
            logger.info(_("main.release_res"))
            clear_handlers()
            await scheduler.stop()
            clear_all_cache()
            await clean_data_store()
            await gather(browser.close(), db_engine.dispose(), to_thread(cfg.reload_and_save), clean_bots())
            await sleep(0.001)  # 让日志打印出来
            cfg.clear()
            scheduler = cfm = cfg = None
            logger.info(_("main.unload_mods"))
            modnames = [modname for modname in list(sys.modules) if modname.startswith("modules.")]
            modnames.sort(key=lambda name: name.count("."), reverse=True)
            for modname in modnames:
                del sys.modules[modname]
            loaded_i10n.clear()
            shutdown_logging()

    async def main():
        loop = get_running_loop()
        main_task = create_task(main_workflow())
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError, ValueError):
                loop.add_signal_handler(sig, lambda *_: main_task.cancel())
        await main_task

    install_uvloop()
    with suppress(KeyboardInterrupt):
        run(main())

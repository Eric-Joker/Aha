from core.log import setup_logging, shutdown_logging  # isort: skip
import os
import utils.misc

os.chdir(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    import signal
    import subprocess
    import sys
    from asyncio import create_task, gather, get_running_loop, sleep
    from contextlib import suppress
    from logging import getLogger

    import core.status
    from core.arg_parser import process_args
    from core.config import cfg, init_base_cfgs
    from core.i18n import _, load_locales
    from modules import init_load_mod
    from utils.aio import run_with_uvloop

    setup_logging()
    logger = getLogger("AHA")

    async def main_workflow():
        await load_locales()
        await process_args()
        init_base_cfgs()

        # isort: skip_file
        import core.api
        import core.status
        from core.database import db_engine, db_init
        from services.apscheduler import aps_log_warn, sched
        from services.playwright import browser_mgr
        from services.file_cache import start_file_cache_service
        from services.data_store import clean_data_store, initialize_all_stores
        from core.expr import custom_fields, redirect_extractors
        from core.dispatcher import clear_handlers, process_clean, process_start
        from core.api_service import close_bots, start_bots
        from utils.aio import AsyncLoopExecutor, ThreadSafeAsyncMeta
        from utils.network import _httpx_client

        # import core.identity 由 core.expr 引用

        await init_load_mod()
        redirect_extractors()
        await cfg.finalize_initialization()
        db_init()

        feats = []
        if cfg._default_group_list:
            if cfg._default_group_list_mode == "blacklist":
                feats.append(_("default_feat.group_blacklist") % len(cfg._default_group_list))
            else:
                feats.append(_("default_feat.group_whitelist") % len(cfg._default_group_list))
        if cfg._default_user_list:
            if cfg._default_user_list_mode == "blacklist":
                feats.append(_("default_feat.user_blacklist") % len(cfg._default_user_list))
            else:
                feats.append(_("default_feat.user_whitelist") % len(cfg._default_user_list))
        feats.append(_("default_feat.private_enabled") if cfg.private else _("default_feat.private_disabled"))
        if cfg.limit:
            feats.append(_("default_feat.rate_limit") % cfg.limit)
        if cfg.global_msg_prefix == "":
            feats.append(_("default_feat.prefix_at_only"))
        elif cfg.global_msg_prefix:
            feats.append(_("default_feat.prefix_custom") % cfg.global_msg_prefix)
        if cfg.get("validated", module="expr_extractors"):
            feats.append(_("default_feat.validation_enabled"))
        if custom_fields:
            feats.append(_("default_feat.custom_fields") % " ".join(custom_fields))
        logger.info(_("default_feat.header") % " ".join(feats))

        try:
            logger.info(_("main.start_api_services"))
            ThreadSafeAsyncMeta.init_instance(ThreadSafeAsyncMeta)
            core.status.async_loop_executor = AsyncLoopExecutor()
            await start_bots()
            logger.info(_("main.start_extra_services"))
            await initialize_all_stores()
            await browser_mgr.start()
            await sched.start()
            with aps_log_warn():
                await start_file_cache_service()
            core.status.all_ready.set()
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
            await gather(
                browser_mgr.close(),
                db_engine.dispose(),
                cfg.reload_and_save(),
                close_bots(),
                core.status.async_loop_executor.shutdown(),
            )
            await sleep(0)  # 让日志打印出来
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

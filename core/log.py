import logging
import os
import sys
from dataclasses import dataclass
from logging.handlers import BaseRotatingHandler
from multiprocessing import Process
from multiprocessing import Queue as PQueue
from pathlib import Path
from queue import Empty
from queue import Queue as TQueue
from re import compile
from threading import Thread
from time import localtime, mktime, strftime, strptime, time
from traceback import print_exception, print_stack
from typing import TYPE_CHECKING

from colorama import Back, Fore, Style, init

from utils.misc import AHA_MODULE_PATTERN, caller_aha_module, is_subsequence
from utils.unit import parse_size

if TYPE_CHECKING:
    from multiprocessing.queues import Queue as PQueue

AHA_DEBUG = 15

init()

LEVEL_COLOR = {
    "DEBUG": Fore.CYAN,
    "AHA_DEBUG": Fore.CYAN,
    "INFO": Fore.GREEN,
    "WARNING": Fore.YELLOW,
    "ERROR": Fore.RED,
    "CRITICAL": f"{Back.RED}{Fore.WHITE}",
}
FILE_FORMAT = {  # 来源 ncatbot
    logging.DEBUG: "[%(asctime)s.%(msecs)03d] %(levelname)-8s [%(threadName)s|%(processName)s] %(name)s (%(filename)s:%(funcName)s:%(lineno)d) | %(message)s",
    AHA_DEBUG: "[%(asctime)s.%(msecs)03d] %(levelname)-8s [%(threadName)s|%(processName)s] %(name)s (%(filename)s:%(funcName)s:%(lineno)d) | %(message)s",
    logging.INFO: "[%(asctime)s.%(msecs)03d] %(levelname)-8s %(name)s ➜ %(message)s",
    logging.WARNING: "[%(asctime)s.%(msecs)03d] %(levelname)-8s %(name)s ➜ %(message)s",
    logging.ERROR: "[%(asctime)s.%(msecs)03d] %(levelname)-8s [%(filename)s]%(name)s:%(lineno)d ➜ %(message)s",
    logging.CRITICAL: "[%(asctime)s.%(msecs)03d] %(levelname)-8s {%(module)s}[%(filename)s]%(name)s:%(lineno)d ➜ %(message)s",
}
CONSOLE_FORMAT = {  # 来源 ncatbot
    logging.DEBUG: f"{Fore.CYAN}[%(asctime)s.%(msecs)03d]{Fore.RESET} "
    f"%(levelname)-8s "
    f"{Fore.LIGHTBLACK_EX}[%(threadName)s|%(processName)s]{Fore.RESET} "
    f"{Fore.MAGENTA}%(name)s{Fore.RESET} "
    f"{Fore.YELLOW}%(filename)s:%(funcName)s:%(lineno)d{Fore.RESET} "
    "| %(message)s",
    AHA_DEBUG: f"{Fore.CYAN}[%(asctime)s.%(msecs)03d]{Fore.RESET} "
    f"%(levelname)-8s "
    f"{Fore.LIGHTBLACK_EX}[%(threadName)s|%(processName)s]{Fore.RESET} "
    f"{Fore.MAGENTA}%(name)s{Fore.RESET} "
    f"{Fore.YELLOW}%(filename)s:%(funcName)s:%(lineno)d{Fore.RESET} "
    "| %(message)s",
    logging.INFO: f"{Fore.CYAN}[%(asctime)s.%(msecs)03d]{Fore.RESET} "
    f"%(levelname)-8s "
    f"{Fore.MAGENTA}%(name)s{Fore.RESET} ➜ "
    f"{Fore.WHITE}%(message)s{Fore.RESET}",
    logging.WARNING: f"{Fore.CYAN}[%(asctime)s.%(msecs)03d]{Fore.RESET} "
    f"%(levelname)-8s "
    f"{Fore.MAGENTA}%(name)s{Fore.RESET} "
    f"{Fore.RED}➜{Fore.RESET} "
    f"{Fore.YELLOW}%(message)s{Fore.RESET}",
    logging.ERROR: f"{Fore.CYAN}[%(asctime)s.%(msecs)03d]{Fore.RESET} "
    f"%(levelname)-8s "
    f"{Fore.LIGHTBLACK_EX}[%(filename)s]{Fore.RESET}"
    f"{Fore.MAGENTA}%(name)s:%(lineno)d{Fore.RESET} "
    f"{Fore.RED}➜{Fore.RESET} "
    f"{Fore.RED}%(message)s{Fore.RESET}",
    logging.CRITICAL: f"{Fore.CYAN}[%(asctime)s.%(msecs)03d]{Fore.RESET} "
    f"%(levelname)-8s "
    f"{Fore.LIGHTBLACK_EX}{{%(module)s}}{Fore.RESET}"
    f"{Fore.MAGENTA}[%(filename)s]{Fore.RESET}"
    f"{Fore.MAGENTA}%(name)s:%(lineno)d{Fore.RESET} "
    f"{Back.RED}➜{Back.RESET} "
    f"{Style.BRIGHT}%(message)s{Style.RESET_ALL}",
}
REDIRECT_LOGGER = {"uvicorn.error": "Uvicorn", "uvicorn.access": "Uvicorn", "apscheduler._schedulers.async_": "APScheduler"}


@dataclass
class HandlerConfig:
    queue: TQueue | PQueue
    file_level: int
    console_level: int


class AhaHandlerMixin:
    def emit(self, msg):
        try:
            self.stream.write(msg + self.terminator)
            self.flush()
        except RecursionError:
            raise
        except Exception:
            self.handleError(msg)

    def emits(self, msgs: list[str]):
        self.emit("\n".join(msgs) + "\n")

    @staticmethod
    def handleError(msg: str):
        if not logging.raiseExceptions or not sys.stderr:
            return
        t, v, tb = sys.exc_info()
        try:
            sys.stderr.write("--- Logging error ---\n")
            print_exception(t, v, tb, None, sys.stderr)
            sys.stderr.write("Call stack:\n")
            while (frame := tb.tb_frame) and os.path.dirname(frame.f_code.co_filename) == __path__[0]:
                frame = frame.f_back
            if frame:
                print_stack(frame, file=sys.stderr)
            try:
                sys.stderr.write(f"Message: {msg}\n")
            except RecursionError:
                raise
            except Exception:
                sys.stderr.write(
                    "Unable to print the message and arguments - possible formatting error.\nUse the traceback above to help find the error.\n"
                )
        except OSError:
            pass
        finally:
            del t, v, tb


class TimeRangeRotatingFileHandler(AhaHandlerMixin, BaseRotatingHandler):
    FILE_PATTERN = compile(r"(\d{8}_\d{6})(?:_to_\d{8}_\d{6})?\.log$")

    def __init__(self, backupCount=5, maxBytes=16 * 1024 * 1024, encoding="utf-8", delay=False, errors=None):
        self.backupCount = backupCount
        self.maxBytes = maxBytes
        self.start_time = time()
        self.end_time = None
        self.log_dir = Path(os.getenv("LOG_FILE_PATH", os.path.join(os.getcwd(), "logs")))
        self.log_dir.mkdir(parents=True, exist_ok=True)

        if backupCount > 0:
            # 分析目录
            log_files: list[tuple[Path, float]] = []
            for file in self.log_dir.iterdir():
                if match := self.FILE_PATTERN.match(file.name):
                    try:
                        log_files.append((file, mktime(strptime(match[1], "%Y%m%d_%H%M%S"))))
                    except ValueError, OSError:
                        # 跳过格式不正确的文件
                        continue
            log_files.sort(key=lambda x: x[1])

            # 超过数量限制
            self.backupFiles = [f[0] for f in log_files]
            while len(self.backupFiles) >= self.backupCount:
                self.backupFiles.pop(0).unlink(True)

        BaseRotatingHandler.__init__(self, self.log_dir / self.rotation_filename(self.start_time), "a", encoding, delay, errors)

    def rotation_filename(self, start_time, end_time=None):
        start_str = strftime("%Y%m%d_%H%M%S", localtime(start_time))
        return (
            self.log_dir / f"{start_str}_to_{strftime("%Y%m%d_%H%M%S", localtime(end_time))}.log"
            if end_time
            else f"{start_str}.log"
        )

    def doRollover(self):
        """轮转文件"""
        self.end_time = time()
        if self.stream:
            self.stream.close()
            new_path = Path(self.baseFilename).rename(self.rotation_filename(self.start_time, self.end_time))
            if self.backupCount > 0:
                self.backupFiles.append(new_path)
                while len(self.backupFiles) > self.backupCount:
                    self.backupFiles.pop(0).unlink(True)

        # 轮转至新文件
        self.start_time = time()
        self.baseFilename = str((self.log_dir / self.rotation_filename(self.start_time)).absolute())
        self.stream = None if self.delay else self._open()

    def shouldRollover(self, msg):
        if self.stream is None:  # delay was set...
            self.stream = self._open()
        return pos + len(msg) >= self.maxBytes if self.maxBytes > 0 and (pos := self.stream.tell()) else False

    def emit(self, data):
        try:
            if self.shouldRollover(data):
                self.doRollover()
            super().emit(data)
        except Exception:
            self.handleError(data)


class ConsoleHandler(AhaHandlerMixin, logging.StreamHandler): ...


class QueueHandler(logging.Handler):
    """将日志发送到统一日志进程的处理器"""

    def __init__(self, queue: TQueue | PQueue, file_formatter, file_level, console_formatter, console_level):
        super().__init__()
        self.queue = queue
        self._file_formatter: logging.Formatter = file_formatter
        self._file_level = file_level
        self._console_formatter: logging.Formatter = console_formatter
        self._console_level = console_level

    def emit(self, record):
        record.name = REDIRECT_LOGGER.get(record.name, record.name)
        try:
            self.queue.put(
                (
                    self._file_formatter.format(record) if record.levelno >= self._file_level else None,
                    self._console_formatter.format(record) if record.levelno >= self._console_level else None,
                )
            )
        except Exception:
            self.handleError(record)


class LevelNameColoredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord):
        try:
            record.levelname = f"{LEVEL_COLOR.get(record.levelname, Style.RESET_ALL)}" f"{record.levelname}{Style.RESET_ALL}"
            return super().format(record)
        except Exception as e:
            return f"[FORMAT ERROR] {record.getMessage()}"


class AhaLogger(logging.Logger):
    def aha_debug(self, msg, *args, stacklevel=1, **kwargs):
        if self.isEnabledFor(AHA_DEBUG):
            self._log(AHA_DEBUG, msg, args, stacklevel=stacklevel + 1, **kwargs)


def _logger_worker(queue: TQueue | PQueue, file, file_kwargs, console, console_kwargs):
    log_buffer = []
    file: AhaHandlerMixin | logging.Handler = file(**file_kwargs)
    console: AhaHandlerMixin | logging.Handler = console(**console_kwargs)

    running = True
    while running:
        try:
            if (record := queue.get()) is None:
                running = False
                continue

            if (msg := record[1]) is not None:
                console.emit(msg)
            if record[0] is not None:
                log_buffer.append(record[0])

            while len(log_buffer) < 64:
                try:
                    if (record := queue.get(timeout=0.1)) is None:
                        running = False
                        break
                    if msg := record[1]:
                        console.emit(msg)
                    if record[0] is not None:
                        log_buffer.append(record[0])
                except Empty:
                    break

        except KeyboardInterrupt:
            pass
        finally:
            file.emits(log_buffer)
            log_buffer = []

    file.emits(log_buffer)
    file.close()
    console.close()


log_config = None
_log_queue = None
_log_handler = None
_log_instance = None
_IS_PROCESS_MODE = None


def setup_logging(handler: HandlerConfig = None):
    global log_config, _log_queue, _log_handler, _log_instance, _IS_PROCESS_MODE
    if not handler:
        from core.config import cfg

        # 创建统一文件日志线/进程
        if _IS_PROCESS_MODE := cfg.execution_mode == "process":
            _log_instance = Process(
                target=_logger_worker,
                args=(
                    (_log_queue := PQueue()),
                    TimeRangeRotatingFileHandler,
                    {"backupCount": cfg.max_log_files, "maxBytes": parse_size(cfg.log_file_max_size)},
                    ConsoleHandler,
                    {},
                ),
                daemon=True,
            )
        else:
            _log_instance = Thread(
                target=_logger_worker,
                args=(
                    (_log_queue := TQueue()),
                    TimeRangeRotatingFileHandler,
                    {"backupCount": cfg.max_log_files, "maxBytes": parse_size(cfg.log_file_max_size)},
                    ConsoleHandler,
                    {},
                ),
                daemon=True,
            )
        _log_instance.start()

        handler = log_config = HandlerConfig(
            _log_queue,
            (level_map := logging._nameToLevel)[os.getenv("LOG_LEVEL", cfg.file_log_level)],
            level_map[os.getenv("LOG_LEVEL", cfg.console_log_level)],
        )

    # 配置根 Logger
    (logger := getLogger()).addHandler(
        _log_handler := QueueHandler(
            _log_queue or handler.queue,
            logging.Formatter(
                os.getenv("LOG_FILE_FORMAT", FILE_FORMAT.get(handler.file_level, logging.INFO)), datefmt="%H:%M:%S"
            ),
            handler.file_level,
            LevelNameColoredFormatter(
                os.getenv("LOG_FORMAT", CONSOLE_FORMAT.get(handler.console_level, logging.INFO)), datefmt="%H:%M:%S"
            ),
            handler.console_level,
        )
    )
    logger.setLevel(logging.DEBUG)


def shutdown_logging():
    global _log_queue, _log_instance
    if _log_queue and _log_instance:
        _log_queue.put(None)
        _log_instance.join()
        if _IS_PROCESS_MODE:
            _log_instance.close()
    # _log_queue = _log_instance = None
    getLogger().removeHandler(_log_handler)


logging.addLevelName(AHA_DEBUG, "AHA_DEBUG")
logging.setLoggerClass(AhaLogger)

_original_getLogger = logging.getLogger


def getLogger(name: str = None):
    if not (module := caller_aha_module(pattern=AHA_MODULE_PATTERN)):
        return _original_getLogger(name)
    return _original_getLogger(module if not name or is_subsequence(name.lower(), module.lower()) else f"{module}({name})")


logging.getLogger = getLogger

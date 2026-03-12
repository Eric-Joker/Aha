from argparse import ArgumentParser
from sys import exit

from modules import disable_modules, enable_modules, persist_blacklist, persist_whitelist

parser = ArgumentParser()
parser.add_argument("--load-only", "-l", metavar="MODULE", nargs="+", help="Load only these modules.")
parser.add_argument("--exclude", metavar="MODULE", nargs="+", help="Do not load these modules.")
parser.add_argument("--no-db-backup", action="store_true", help="Skip database backup")
module_group = parser.add_argument_group("Module Control")
module_group.add_argument("--disable", "-d", metavar="MODULE", nargs="+", help="Disable these modules.")
module_group.add_argument("--enable", "-e", metavar="MODULE", nargs="+", help="Enable these modules.")
parser = parser.parse_args()


async def process_args():
    if parser.disable:
        await disable_modules(*parser.disable)
    if parser.enable:
        await enable_modules(*parser.enable)
    if parser.disable or parser.enable:
        exit(0)
    if parser.load_only:
        persist_whitelist.update(parser.load_only)
    if parser.exclude:
        persist_blacklist.update(parser.exclude)

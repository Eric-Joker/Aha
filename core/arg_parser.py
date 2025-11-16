from argparse import ArgumentParser

parser = ArgumentParser()
parser.add_argument("--load-only", "-l", metavar="MODULE", nargs="+", help="Load only these modules.")
parser.add_argument("--exclude", metavar="MODULE", nargs="+", help="Do not load these modules.")
parser.add_argument("--no-db-backup", action="store_true", help="Skip database backup")
module_group = parser.add_argument_group("Module Control")
module_group.add_argument("--disable", "-d", metavar="MODULE", nargs="+", help="Disable these modules.")
module_group.add_argument("--enable", "-e", metavar="MODULE", nargs="+", help="Enable these modules.")
parser = parser.parse_args()

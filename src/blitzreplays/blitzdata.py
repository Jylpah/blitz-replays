#!/usr/bin/env python3

from os.path import isfile, isdir, dirname, realpath, expanduser, join as join_path
from pathlib import Path
from typing import Optional, Any
from configparser import ConfigParser
from asyncio import set_event_loop_policy, run, create_task, get_event_loop_policy, Task

import sys, argparse, logging
import logging

sys.path.insert(0, dirname(dirname(realpath(__file__))))

from pyutils import MultilevelFormatter
from blitzreplays import tankopedia
from blitzreplays import maps

# logging.getLogger("asyncio").setLevel(logging.DEBUG)
logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

FILE_CONFIG = "blitzstats.ini"


## main() -------------------------------------------------------------
async def main() -> None:
    global logger, error, debug, verbose, message
    # set the directory for the script
    # os.chdir(os.path.dirname(sys.argv[0]))

    ## Read config
    _PKG_NAME = "blitzreplays"
    CONFIG = _PKG_NAME + ".ini"
    LOG = _PKG_NAME + ".log"
    config: Optional[ConfigParser] = None
    CONFIG_FILE: Optional[str] = None

    CONFIG = "blitzstats.ini"
    CONFIG_FILES: list[str] = [
        "./" + CONFIG,
        dirname(realpath(__file__)) + "/" + CONFIG,
        "~/." + CONFIG,
        "~/.config/" + CONFIG,
        f"~/.config/{_PKG_NAME}/config",
        "~/.config/blitzstats.ini",
        "~/.config/blitzstats/config",
    ]
    for fn in [expanduser(f) for f in CONFIG_FILES]:
        if isfile(fn):
            CONFIG_FILE = fn
            verbose(f"config file: {CONFIG_FILE}")
            break

    parser = argparse.ArgumentParser(
        description="Read/update Blitz metadata", add_help=False
    )
    arggroup_verbosity = parser.add_mutually_exclusive_group()
    arggroup_verbosity.add_argument(
        "--debug",
        "-d",
        dest="LOG_LEVEL",
        action="store_const",
        const=logging.DEBUG,
        help="Debug mode",
    )
    arggroup_verbosity.add_argument(
        "--verbose",
        "-v",
        dest="LOG_LEVEL",
        action="store_const",
        const=logging.INFO,
        help="Verbose mode",
    )
    arggroup_verbosity.add_argument(
        "--silent",
        "-s",
        dest="LOG_LEVEL",
        action="store_const",
        const=logging.CRITICAL,
        help="Silent mode",
    )
    parser.add_argument(
        "--log",
        type=str,
        nargs="?",
        default=None,
        const=f"{LOG}",
        help="Enable file logging",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=CONFIG_FILE,
        metavar="CONFIG",
        help="Read config from CONFIG",
    )
    parser.set_defaults(LOG_LEVEL=logging.WARNING)

    args, argv = parser.parse_known_args()

    # setup logging
    logger.setLevel(args.LOG_LEVEL)
    logger_conf: dict[int, str] = {
        logging.INFO: "%(message)s",
        logging.WARNING: "%(message)s",
        # logging.ERROR: 		'%(levelname)s: %(message)s'
    }
    MultilevelFormatter.setLevels(
        logger,
        fmts=logger_conf,
        fmt="%(levelname)s: %(funcName)s(): %(message)s",
        log_file=args.log,
    )
    error = logger.error
    message = logger.warning
    verbose = logger.info
    debug = logger.debug

    if args.config is not None and isfile(args.config):
        debug("Reading config from %s", args.config)
        config = ConfigParser()
        config.read(args.config)
    else:
        debug("No config file found")
    # Parse command args
    parser.add_argument("-h", "--help", action="store_true", help="Show help")

    cmd_parsers = parser.add_subparsers(
        dest="main_cmd",
        title="main commands",
        description="valid subcommands",
        metavar="tankopedia | maps",
    )
    cmd_parsers.required = True

    tankopedia_parser = cmd_parsers.add_parser(
        "tankopedia", aliases=["tp"], help="tankopedia help"
    )
    maps_parser = cmd_parsers.add_parser("maps", aliases=["map"], help="maps help")

    if not tankopedia.add_args(tankopedia_parser, config):
        raise Exception("Failed to define argument parser for: tankopedia")

    if not maps.add_args(maps_parser, config):
        raise Exception("Failed to define argument parser for: maps")

    debug("parsing full args")
    args = parser.parse_args(args=argv)
    if args.help:
        parser.print_help()
    debug("arguments given:")
    debug(str(args))

    if args.main_cmd == "tankopedia":
        if not await tankopedia.cmd(args):
            sys.exit(1)
    elif args.main_cmd in ["maps", "map"]:
        if not await maps.cmd(args):
            sys.exit(1)


# ### main()
# if __name__ == "__main__":
#     # To avoid 'Event loop is closed' RuntimeError due to compatibility issue with aiohttp
#     if sys.platform.startswith("win") and sys.version_info >= (3, 8):
#         try:
#             from asyncio import WindowsSelectorEventLoopPolicy
#         except ImportError:
#             pass
#         else:
#             if not isinstance(get_event_loop_policy(), WindowsSelectorEventLoopPolicy):
#                 set_event_loop_policy(WindowsSelectorEventLoopPolicy())
#     run(main())


########################################################
#
# main() entry
#
########################################################


def cli_main():
    run(main())


if __name__ == "__main__":
    # asyncio.run(main(sys.argv[1:]), debug=True)
    cli_main()

#!/usr/bin/env python3

import click
from sys import path
from pathlib import Path
from typing import Optional, Any
from configparser import ConfigParser
import configparser

import sys, logging
import logging

from pyutils import MultilevelFormatter
from pyutils.utils import set_config
from blitzutils import get_config_file

path.insert(0, str(Path(__file__).parent.parent.resolve()))

from metadata import tankopedia, maps

# logging.getLogger("asyncio").setLevel(logging.DEBUG)
logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

CONFIG_FILE: Path | None = get_config_file()


MAPS: str = "maps.json"


## main() -------------------------------------------------------------
@click.group(help="CLI tool extrac WoT Blitz Tankopedia and Maps from ")
@click.option(
    "--normal",
    "LOG_LEVEL",
    flag_value=logging.WARNING,
    default=True,
    help="default verbosity",
)
@click.option("--verbose", "LOG_LEVEL", flag_value=logging.INFO, help="verbose logging")
@click.option("--debug", "LOG_LEVEL", flag_value=logging.DEBUG, help="debug logging")
@click.option(
    "--config",
    "config_file",
    type=click.Path(),
    default=CONFIG_FILE,
    help=f"read config from file (default: {CONFIG_FILE})",
)
@click.option(
    "--log", type=click.Path(path_type=Path), default=None, help="log to FILE"
)
@click.pass_context
def cli(
    ctx: click.Context,
    LOG_LEVEL: int = logging.WARNING,
    config_file: Path | None = CONFIG_FILE,
    log: Path | None = None,
) -> None:
    """CLI app to extract WoT Blitz tankopedia and maps for other tools"""
    global logger, error, debug, verbose, message

    MultilevelFormatter.setDefaults(logger, log_file=log)
    logger.setLevel(LOG_LEVEL)
    ctx.ensure_object(dict)

    config: ConfigParser = ConfigParser(allow_no_value=True)
    if config_file is not None:
        try:
            config.read(config_file)
        except configparser.Error as err:
            error(f"could not read config file {config_file}: {err}")
            exit(1)
    ctx.obj["config"] = config


# Add sub commands
cli.add_command(tankopedia.tankopedia)  # type: ignore
cli.add_command(maps.maps)  # type: ignore


# cmd_parsers = parser.add_subparsers(
#     dest="main_cmd",
#     title="main commands",
#     description="valid subcommands",
#     metavar="tankopedia | maps",
# )
# cmd_parsers.required = True

# tankopedia_parser = cmd_parsers.add_parser(
#     "tankopedia", aliases=["tp"], help="tankopedia help"
# )
# maps_parser = cmd_parsers.add_parser("maps", aliases=["map"], help="maps help")

# if not tankopedia.add_args(tankopedia_parser, config):
#     raise Exception("Failed to define argument parser for: tankopedia")

# if not maps.add_args(maps_parser, config):
#     raise Exception("Failed to define argument parser for: maps")

# debug("parsing full args")
# args = parser.parse_args(args=argv)
# if args.help:
#     parser.print_help()
# debug("arguments given:")
# debug(str(args))

# if args.main_cmd == "tankopedia":
#     if not await tankopedia.cmd(args):
#         sys.exit(1)
# elif args.main_cmd in ["maps", "map"]:
#     if not await maps.cmd(args):
#         sys.exit(1)


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
    cli(obj={})


if __name__ == "__main__":
    # asyncio.run(main(sys.argv[1:]), debug=True)
    cli_main()

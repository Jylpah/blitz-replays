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

from .metadata import tankopedia, maps

# logging.getLogger("asyncio").setLevel(logging.DEBUG)
logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

CONFIG_FILE: Path | None = get_config_file()


MAPS: str = "maps.json"


## main() -------------------------------------------------------------
@click.group(help="CLI tool extract WoT Blitz metadata for other tools")
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

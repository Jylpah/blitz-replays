#!/usr/bin/env python3

import click
from asyncio import run
import logging
from pathlib import Path
from configparser import ConfigParser
import configparser
from sys import path, exit
from os.path import dirname, realpath

from pyutils import MultilevelFormatter
from pyutils.utils import set_config
from blitzutils import get_config_file

path.insert(0, dirname(dirname(realpath(__file__))))

from blitzreplays import replays_upload

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

##############################################
#
## Constants
#
##############################################


_PKG_NAME = "blitz-replays"
LOG = _PKG_NAME + ".log"
CONFIG_FILE: Path | None = get_config_file()
WI_RATE_LIMIT: float = 20 / 3600
WI_AUTH_TOKEN: str | None = None
WI_WORKERS: int = 3
TANKOPEDIA: str = "tanks.json"
MAPS: str = "maps.json"

##############################################
#
## cli_xxx()
#
##############################################


@click.group(help="CLI tool upload WoT Blitz Replays to WoTinspector.com")
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
@click.option(
    "--wi-rate-limit",
    type=float,
    default=None,
    help="rate-limit for WoTinspector.com",
)
@click.option(
    "--wi-auth_token",
    type=str,
    default=None,
    help="authentication token for WoTinsepctor.com",
)
@click.option(
    "--tankopedia",
    type=str,
    default=None,
    help="tankopedia JSON file",
)
@click.option(
    "--maps",
    type=str,
    default=None,
    help="maps JSON file",
)
@click.pass_context
def cli(
    ctx: click.Context,
    LOG_LEVEL: int = logging.WARNING,
    config_file: Path | None = CONFIG_FILE,
    log: Path | None = None,
    wi_rate_limit: float | None = None,
    wi_auth_token: str | None = None,
    tankopedia: str | None = None,
    maps: str | None = None,
):
    """CLI app to upload WoT Blitz replays"""
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

    set_config(config, "WOTINSPECTOR", "rate_limit", wi_rate_limit, WI_RATE_LIMIT)
    set_config(config, "WOTINSPECTOR", "auth_token", wi_auth_token, WI_AUTH_TOKEN)

    set_config(config, "METADATA", "tankopedia_json", tankopedia, TANKOPEDIA)
    set_config(config, "METADATA", "maps_json", maps, MAPS)

    ctx.obj["config"] = config


# Add sub commands
cli.add_command(replays_upload.upload)  # type: ignore

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

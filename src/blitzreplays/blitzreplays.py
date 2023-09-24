import click
from asyncio import run
import logging
from pathlib import Path
from configparser import ConfigParser
import configparser
from typing import Optional, Callable
import sys

from pyutils import MultilevelFormatter, FileQueue
from blitzutils import WoTinspector, get_config_file

from . import replays_upload

# sys.path.insert(0, dirname(dirname(realpath(__file__))))


def async_click(callable_: Callable):
    def wrapper(*args, **kwargs):
        run(callable_(*args, **kwargs))

    return wrapper


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

##############################################
#
## cli_xxx()
#
##############################################


@click.group(help="CLI tool upload WoT Blitz Replays to WoTinspector.com")
# @click.option("--normal", "LOG_LEVEL", flag_value=logging.WARNING, default=True, help="default verbosity")
@click.option("--verbose", "LOG_LEVEL", flag_value=logging.INFO, help="verbose logging")
@click.option("--debug", "LOG_LEVEL", flag_value=logging.DEBUG, help="debug logging")
@click.option(
    "--config",
    "config_file",
    type=str,
    default=CONFIG_FILE,
    help=f"read config from file (default: {CONFIG_FILE})",
)
@click.option("--log", type=click.Path(), default=None, help="log to FILE")
@click.option(
    "--wi-rate-limit",
    type=float,
    default=WI_RATE_LIMIT,
    help="rate-limit for WoTinspector.com",
)
@click.option(
    "--wi-auth_token",
    type=str,
    default=WI_AUTH_TOKEN,
    help="authentication token for WoTinsepctor.com",
)
@click.option(
    "--wi-workers",
    type=int,
    default=WI_WORKERS,
    help="number for WoTinspector.com workers",
)
@click.pass_context
def cli(
    ctx: click.Context,
    LOG_LEVEL: int = logging.WARNING,
    config_file: str | None = None,
    log: Path | None = None,
    wi_rate_limit: float = WI_RATE_LIMIT,
    wi_auth_token: str | None = WI_AUTH_TOKEN,
    wi_workers: int = WI_WORKERS,
):
    """CLI app to upload WoT Blitz replays"""
    global logger, error, debug, verbose, message

    logger.setLevel(LOG_LEVEL)
    MultilevelFormatter.setDefaults(logger, log_file=log)
    ctx.ensure_object(dict)

    config: ConfigParser | None = None
    if config_file is not None:
        try:
            config = ConfigParser()
            config.read(config_file)
            if config.has_section("WOTINSPECTOR"):
                configWI = config["WOTINSPECTOR"]
                wi_rate_limit = configWI.getfloat("rate_limit", wi_rate_limit)
                wi_auth_token = configWI.get("auth_token", wi_auth_token)
                wi_workers = configWI.getint("workers", wi_workers)
        except configparser.Error as err:
            error(f"could not read config file {config_file}")
            error(f"{type(err)}: {err}")
    else:
        verbose("no config file defined")

    ctx.obj["WI"] = WoTinspector(rate_limit=wi_rate_limit, auth_token=wi_auth_token)
    ctx.obj["wi_workers"] = wi_workers
    ctx.obj["config"] = config


# Add sub commands
cli.add_command(replays_upload.cli)  # type: ignore

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

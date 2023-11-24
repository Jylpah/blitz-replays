#!/usr/bin/env python3

# import click
import typer

# from sys import path
from pathlib import Path
from typing import Optional, Any
from typing_extensions import Annotated
from configparser import ConfigParser
import sys
from os.path import dirname, realpath

sys.path.insert(0, dirname(dirname(realpath(__file__))))
import configparser
import logging


from pyutils import MultilevelFormatter
from pyutils.utils import set_config
from blitzutils import get_config_file

from blitzreplays.metadata import tankopedia

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

CONFIG_FILE: Path | None = get_config_file()

MAPS: str = "maps.json"

app = typer.Typer()
app.add_typer(tankopedia.typer_app, name="tankopedia")


## main() -------------------------------------------------------------
# @click.group(help="CLI tool extract WoT Blitz metadata for other tools")
# @click.option(
#     "--normal",
#     "LOG_LEVEL",
#     flag_value=logging.WARNING,
#     default=True,
#     help="default verbosity",
# )
# @click.option("--verbose", "LOG_LEVEL", flag_value=logging.INFO, help="verbose logging")
# @click.option("--debug", "LOG_LEVEL", flag_value=logging.DEBUG, help="debug logging")
# @click.option(
#     "--config",
#     "config_file",
#     type=click.Path(),
#     default=CONFIG_FILE,
#     help=f"read config from file (default: {CONFIG_FILE})",
# )
# @click.option(
#     "--log", type=click.Path(path_type=Path), default=None, help="log to FILE"
# )
# @click.pass_context


@app.callback()
def cli(
    ctx: typer.Context,
    print_verbose: Annotated[
        int,
        typer.Option(
            "--verbose",
            "-v",
            is_flag=True,
            flag_value=logging.INFO,
            show_default=False,
            metavar="",
            help="verbose logging",
        ),
    ] = logging.WARNING,
    print_debug: Annotated[
        int,
        typer.Option(
            "--debug",
            is_flag=True,
            flag_value=logging.DEBUG,
            show_default=False,
            metavar="",
            help="debug logging",
        ),
    ] = logging.WARNING,
    config_file: Annotated[
        Optional[Path],
        typer.Option("--config", help=f"read config from FILE", metavar="FILE"),
    ] = CONFIG_FILE,
    log: Annotated[
        Optional[Path], typer.Option(help="log to FILE", metavar="FILE")
    ] = None,
) -> None:
    """CLI app to extract WoT Blitz tankopedia and maps for other tools"""
    global logger, error, debug, verbose, message

    LOG_LEVEL: int = min([print_debug, print_verbose])
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


########################################################
#
# main() entry
#
########################################################


# def cli_main():
#     cli(obj={})


if __name__ == "__main__":
    app()

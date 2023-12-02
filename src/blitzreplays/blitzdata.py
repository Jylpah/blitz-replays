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
from icecream import ic  # type: ignore

from pyutils import MultilevelFormatter
from pyutils.utils import set_config
from blitzutils import get_config_file

from blitzreplays.metadata import tankopedia, maps

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

CONFIG_FILE: Path | None = get_config_file()

MAPS: str = "maps.json"

app = typer.Typer()
app.add_typer(tankopedia.typer_app, name="tankopedia")
app.add_typer(maps.typer_app, name="maps")


@app.callback()
def cli(
    ctx: typer.Context,
    print_verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            show_default=False,
            metavar="",
            help="verbose logging",
        ),
    ] = False,
    print_debug: Annotated[
        bool,
        typer.Option(
            "--debug",
            show_default=False,
            metavar="",
            help="debug logging",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(show_default=False, help="Overwrite instead of updating data"),
    ] = False,
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

    LOG_LEVEL: int = logging.WARNING
    if print_verbose:
        LOG_LEVEL = logging.INFO
    elif print_debug:
        LOG_LEVEL = logging.DEBUG
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
    ctx.obj["force"] = force


########################################################
#
# main() entry
#
########################################################


# def cli_main():
#     cli(obj={})


if __name__ == "__main__":
    app()

#!/usr/bin/env python3

import typer
from pathlib import Path
from typing import Optional, Annotated
from configparser import ConfigParser
import configparser
import logging

from multilevellogger import getMultiLevelLogger, MultiLevelLogger, MESSAGE, VERBOSE
from blitzmodels import get_config_file

from .metadata import tankopedia, maps

logger: MultiLevelLogger = getMultiLevelLogger(__name__)
error = logger.error
message = logger.message
verbose = logger.verbose
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
        typer.Option("--config", help="read config from FILE", metavar="FILE"),
    ] = CONFIG_FILE,
    log: Annotated[
        Optional[Path], typer.Option(help="log to FILE", metavar="FILE")
    ] = None,
) -> None:
    """CLI app to extract WoT Blitz tankopedia and maps for other tools"""
    global logger, error, debug, verbose, message

    if log is not None:
        logger.addLogFile(log_file=log)
    LOG_LEVEL: int = MESSAGE
    if print_verbose:
        LOG_LEVEL = VERBOSE
    elif print_debug:
        LOG_LEVEL = logging.DEBUG

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

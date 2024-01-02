#!/usr/bin/env python3

import typer

from asyncio import run
from typing import Annotated, Optional
import logging
from pathlib import Path
from configparser import ConfigParser
import configparser
from sys import path

from pyutils import MultilevelFormatter, AsyncTyper
from pyutils.utils import set_config
from blitzmodels import get_config_file, WGApiWoTBlitzTankopedia, Maps

path.insert(0, str(Path(__file__).parent.parent.resolve()))

from blitzreplays.replays import upload

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

##############################################
#
## Typer CLI arg parsing
#
##############################################

app = AsyncTyper()
app.async_command(
    name="upload",
)(upload.upload)


##############################################
#
## Constants
#
##############################################

CONFIG_FILE: Path | None = get_config_file()
WI_WORKERS: int = 1
TANKOPEDIA: str = "tanks.json"
MAPS: str = "maps.json"


##############################################
#
## cli()
#
##############################################


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
    tankopedia_fn: Annotated[
        Optional[Path],
        typer.Option("--tankopedia", help="tankopedia JSON file", metavar="FILE"),
    ] = None,
    maps_fn: Annotated[
        Optional[Path],
        typer.Option("--maps", help="maps JSON file", metavar="FILE"),
    ] = None,
) -> None:
    """
    CLI app to upload WoT Blitz replays
    """
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
            debug("reading config from: %s", str(config_file))
            config.read(config_file)
        except configparser.Error as err:
            error(f"could not read config file {config_file}: {err}")
            raise typer.Exit(code=1)

    tankopedia: WGApiWoTBlitzTankopedia | None
    try:
        tankopedia_fn = Path(
            set_config(
                config,
                TANKOPEDIA,
                "METADATA",
                "tankopedia_json",
                str(tankopedia_fn) if tankopedia_fn else None,
            )
        )
        debug("tankopedia file: %s", str(tankopedia_fn))

        if (
            tankopedia := run(
                WGApiWoTBlitzTankopedia.open_json(tankopedia_fn, exceptions=True)
            )
        ) is None:
            error(f"could not parse tankopedia from {tankopedia_fn}")
            raise typer.Exit(code=2)
        ctx.obj["tankopedia"] = tankopedia
    except Exception as err:
        error(f"error reading Tankopedia from {tankopedia_fn}: {err}")
        raise typer.Exit(code=3)

    maps: Maps | None
    try:
        maps_fn = Path(
            set_config(
                config,
                MAPS,
                "METADATA",
                "maps_json",
                str(maps_fn) if maps_fn else None,
            )
        )
        debug("maps file: %s", str(maps_fn))
        if (maps := run(Maps.open_json(maps_fn, exceptions=True))) is None:
            error(f"could not parse maps from {maps_fn}")
            raise typer.Exit(code=4)
        ctx.obj["maps"] = maps
    except Exception as err:
        error(f"error reading maps from {maps_fn}: {err}")
        raise typer.Exit(code=5)

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

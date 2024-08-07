#!/usr/bin/env python3

import typer
from typing import Annotated, Optional
import logging
from pathlib import Path
from importlib.resources.abc import Traversable
from importlib.resources import as_file
import importlib
from configparser import ConfigParser
import configparser

from pyutils import MultilevelFormatter, AsyncTyper
from pyutils.utils import set_config
from blitzmodels import get_config_file, WGApiWoTBlitzTankopedia, Maps

from .replays import upload, analyze

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
app.add_typer(analyze.app, name="analyze")
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

TANKOPEDIA: Path
packaged_tankopedia: Traversable = importlib.resources.files("blitzreplays").joinpath(
    "files", "tanks.json"
)  # REFACTOR in Python 3.12
with as_file(packaged_tankopedia) as tankopedia_fn:
    TANKOPEDIA = tankopedia_fn

MAPS: Path
packaged_maps: Traversable = importlib.resources.files("blitzreplays").joinpath(
    "files", "maps.json"
)  # REFACTOR in Python 3.12
with as_file(packaged_maps) as maps_fn:
    MAPS = maps_fn


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
    # force: Annotated[
    #     bool,
    #     typer.Option(show_default=False, help="Overwrite instead of updating data"),
    # ] = False,
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

    tankopedia: WGApiWoTBlitzTankopedia | None = None
    try:
        tankopedia_fn = Path(
            set_config(
                config,
                str(TANKOPEDIA.resolve()),
                "METADATA",
                "tankopedia_json",
                str(tankopedia_fn) if tankopedia_fn else None,
            )
        )
        debug("tankopedia file: %s", str(tankopedia_fn))

        with open(tankopedia_fn, "r", encoding="utf-8") as file:
            if (tankopedia := WGApiWoTBlitzTankopedia.parse_str(file.read())) is None:
                error(f"could not parse tankopedia from {tankopedia_fn}")
                raise typer.Exit(code=2)
        debug("read %d tanks from %s", len(tankopedia), str(tankopedia_fn))
        ctx.obj["tankopedia"] = tankopedia
    except Exception as err:
        error(f"error reading Tankopedia from {tankopedia_fn}: {err}")
        raise typer.Exit(code=3)

    maps: Maps | None
    try:
        maps_fn = Path(
            set_config(
                config,
                str(MAPS.resolve()),
                "METADATA",
                "maps_json",
                str(maps_fn) if maps_fn else None,
            )
        )
        debug("maps file: %s", str(maps_fn))
        with open(maps_fn, mode="r", encoding="utf-8") as file:
            if (maps := Maps.parse_str(file.read())) is None:
                error(f"could not parse maps from {maps_fn}")
                raise typer.Exit(code=4)
        debug("read %d maps from %s", len(maps), str(maps_fn))
        ctx.obj["maps"] = maps
    except Exception as err:
        error(f"error reading maps from {maps_fn}: {err}")
        raise typer.Exit(code=5)

    ctx.obj["config"] = config
    # ctx.obj["force"] = force


########################################################
#
# main() entry
#
########################################################


# def cli_main():
#     cli(obj={})


if __name__ == "__main__":
    app()

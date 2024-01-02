from typing import Optional, Annotated

# from typing_extensions import Annotated
from pathlib import Path
from os import unlink
from re import Pattern, Match, compile

import yaml
import logging
import typer
import configparser

from pyutils.utils import get_temp_filename, set_config
from pyutils import AsyncTyper
from blitzmodels import Map, Maps, Region, MapModeStr
from dvplc import decode_dvpl_file

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

BLITZAPP_STRINGS: str = "Data/Strings/en.yaml"
MAPS: str = "maps.json"
WG_APP_ID: str = "d6d03acb6bee0e9f361b6e02e1780b56"
WG_REGION: Region = Region.eu

typer_app = AsyncTyper()


###########################################
#
# maps
#
###########################################


@typer_app.callback()
def maps(
    ctx: typer.Context,
    # force: bool = False,
    outfile: Annotated[
        Optional[str],
        typer.Option(help="Write maps to FILE", metavar="FILE"),
    ] = None,
) -> None:
    """extract maps data into a JSON file"""
    debug("starting")
    try:
        config: configparser.ConfigParser = ctx.obj["config"]
        set_config(
            config,
            MAPS,
            "METADATA",
            "maps_json",
            outfile,
        )
    except Exception as err:
        error(f"{type(err)}: {err}")
        typer.Exit(code=1)


########################################################
#
# maps app
#
########################################################


@typer_app.async_command()
async def app(
    ctx: typer.Context,
    blitz_app_dir: Annotated[
        Optional[Path],
        typer.Argument(
            show_default=False,
            file_okay=False,
            help="Blitz game files directory",
        ),
    ] = None,
):
    """
    Read maps data from game files
    """
    debug("starting")
    force: bool = False
    outfile: Path = Path("__ERROR_NOT_EXISTING__")
    try:
        config: configparser.ConfigParser = ctx.obj["config"]
        # wg_app_id = set_config(config, WG_APP_ID, "WG", "app_id", wg_app_id)
        ## region: Region
        # if wg_region is None:
        ##     region = Region(
        #         set_config(config, WG_REGION.value, "WG", "default_region", None)
        #     )
        # else:
        ##     region = wg_region
        outfile = Path(config.get("METADATA", "maps_json"))
        force = ctx.obj["force"]
        if blitz_app_dir is None:
            blitz_app_dir = Path(config.get("METADATA", "blitz_app_dir"))
    except configparser.Error as err:
        error(f"could not read config file: {type(err)}: {err}")
        typer.Exit(code=1)
    except Exception as err:
        error(f"{type(err)}: {err}")
        typer.Exit(code=1)
    assert isinstance(force, bool), f"error: 'force' is not bool: {type(force)}"
    assert (
        blitz_app_dir is not None
    ), "Set --blitz-app-dir or define it in config file ('blitz_app_dir' in 'METADATA' section)"
    assert (
        blitz_app_dir.is_dir()
    ), f"--blitz-app-dir has to be a directory: {blitz_app_dir}"

    filename: Path = blitz_app_dir / BLITZAPP_STRINGS
    is_dvpl: bool = False
    maps = Maps()
    user_strs: dict[str, str] = dict()
    try:
        if (blitz_app_dir / "assets").is_dir():
            # WG has changed the location of Data directory - at least in steam client
            blitz_app_dir = blitz_app_dir / "assets"
        debug("base dir for game files: %s", str(blitz_app_dir))

        if filename.is_file():
            pass
        elif (filename := filename.parent / (filename.name + ".dvpl")).is_file():
            is_dvpl = True
            debug("decoding DVPL file: %s", filename.resolve())
            temp_fn: Path = get_temp_filename("blitz-data.")
            debug("using temporary file: %s", str(temp_fn))
            if not await decode_dvpl_file(filename, temp_fn):
                raise IOError(f"could not decode DVPL file: {filename}")
            filename = temp_fn

        debug("Opening file: %s for reading map strings", str(filename))
        with open(filename, "r", encoding="utf8") as strings_file:
            user_strs = yaml.safe_load(strings_file)
    except:
        raise
    finally:
        if is_dvpl:
            debug("deleting temp file: %s", str(filename))
            unlink(filename)
    try:
        re_map: Pattern = compile(r"^#maps:(\w+?):.+?$")
        match: Match | None
        for key, value in user_strs.items():
            # some Halloween map variants have the same short name
            if (match := re_map.match(key)) and key not in maps:
                maps.add(Map(name=value, key=match.group(1)))
        await update_maps(outfile=outfile, maps=maps, force=force)
    except Exception as err:
        error(f"unable to read maps from {filename.resolve()}: {err}")
    return None


########################################################
#
# maps file
#
########################################################


@typer_app.async_command()
async def file(
    ctx: typer.Context,
    infile: Annotated[
        Path,
        typer.Argument(show_default=False, dir_okay=False, help="read maps from file"),
    ],
):
    """
    Read maps data from a JSON file
    """
    debug("starting")
    force: bool = False
    outfile: Path = Path("__ERROR_NOT_EXISTING__")
    try:
        config: configparser.ConfigParser = ctx.obj["config"]
        outfile = Path(config.get("METADATA", "maps_json"))
        force = ctx.obj["force"]
    except configparser.Error as err:
        error(f"could not read config file: {type(err)}: {err}")
        typer.Exit(code=1)
    except Exception as err:
        error(f"{type(err)}: {err}")
        typer.Exit(code=1)
    if (maps := await Maps.open_json(infile)) is not None:
        await update_maps(outfile=outfile, maps=maps, force=force)
    else:
        error(f"could not read Maps from {infile}")


########################################################
#
# maps list
#
########################################################


@typer_app.async_command()
async def list(
    ctx: typer.Context,
    file: Annotated[
        Optional[Path],
        typer.Argument(show_default=False, dir_okay=False, help="list maps from file"),
    ] = None,
    # TODO:
    # -[ ] Add support for MapMode
    # -[ ] might need a StrEnum() type of Enum instead of IntEnum()
    map_mode: Annotated[
        Optional[MapModeStr], typer.Option(help="list maps for of mode")
    ] = MapModeStr.normal,
    all: Annotated[bool, typer.Option(help="list all maps of all modes")] = False,
):
    """
    list maps from a JSON file
    """
    debug("starting")
    try:
        config: configparser.ConfigParser = ctx.obj["config"]
        if file is None:
            file = Path(config.get("METADATA", "maps_json"))
    except configparser.Error as err:
        error(f"could not read config file: {type(err)}: {err}")
        typer.Exit(code=1)
    except Exception as err:
        error(f"{type(err)}: {err}")
        typer.Exit(code=1)
    assert isinstance(file, Path), f"file is not type of Path(): {type(file)}"
    if (maps := await Maps.open_json(file)) is not None:
        count: int = 0
        for mode in MapModeStr:
            if all or map_mode == mode:
                print(f"map mode: {mode} =======================================")
                for map in maps:
                    if map.mode == mode.toMapMode:
                        print(f"{map.key:<18}: {map.name}")
                        count += 1
        print(f"{count} maps in total (map mode = {'any' if all else map_mode})")
    else:
        error(f"could not read Maps from {file}")


###########################################
#
# update_maps
#
###########################################


async def update_maps(outfile: Path, maps: Maps, force: bool = False):
    try:
        debug("starting")
        maps_old: Maps | None = None

        if not force and outfile.is_file():
            if (maps_old := await Maps.open_json(outfile)) is None:
                error(f"could not parse old Maps file: {outfile}")
                return None
        else:
            maps_old = Maps()

        new: set[str] = {map.key for map in maps}
        old: set[str] = {map.key for map in maps_old}
        added: set[str] = new - old
        updated: set[str] = new & old
        updated = {key for key in updated if maps[key] != maps_old[key]}

        if not force:
            maps_old.update(maps)
            maps = maps_old

        if await maps.save_json(outfile) > 0:
            if logger.level < logging.WARNING:
                for key in added:
                    verbose(f"added:   {maps[key].name}")

            if logger.level < logging.WARNING:
                for key in updated:
                    verbose(f"updated: {maps[key].name}")

            message(f"added {len(added)} and updated {len(updated)} maps to map list")
            message(f"saved {len(maps)} maps to map list ({outfile})")
        else:
            error(f"writing map list failed: {outfile}")

    except Exception as err:
        error(f"{type(err)}: {err}")
    return None


if __name__ == "__main__":
    typer_app()

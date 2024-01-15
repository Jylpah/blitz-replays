from typing import Optional, Annotated

# from typing_extensions import Annotated
from pathlib import Path
from os import unlink
from aiofiles import open
from result import is_ok, Err

import yaml
import logging
import typer
import configparser

from pyutils.utils import get_temp_filename, set_config, add_suffix
from pyutils import AsyncTyper
from pydantic_exportables import Idx
from blitzmodels import Maps, Region, MapModeStr

from dvplc import decode_dvpl, open_dvpl_or_file

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

BLITZAPP_STRINGS: str = "Data/Strings/en.yaml"
BLITZAPP_MAPS: str = "Data/maps.yaml"
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
        outfile = Path(config.get("METADATA", "maps_json"))
        force = ctx.obj["force"]
        if blitz_app_dir is None:
            blitz_app_dir = Path(config.get("METADATA", "blitz_app_dir"))
    except configparser.Error as err:
        error(f"could not read config file: {type(err)}: {err}")
        typer.Exit(code=2)
    except Exception as err:
        error(f"{type(err)}: {err}")
        typer.Exit(code=3)
    assert isinstance(force, bool), f"error: 'force' is not bool: {type(force)}"
    assert (
        blitz_app_dir is not None
    ), "Set --blitz-app-dir or define it in config file ('blitz_app_dir' in 'METADATA' section)"
    assert (
        blitz_app_dir.is_dir()
    ), f"--blitz-app-dir has to be a directory: {blitz_app_dir}"

    localization_strs: dict[str, str] = dict()
    maps: Maps | None = None
    try:
        if (blitz_app_dir / "assets").is_dir():
            # WG has changed the location of Data directory - at least in steam client
            blitz_app_dir = blitz_app_dir / "assets"
        debug("base dir for game files: %s", str(blitz_app_dir))

        maps_fn: Path = blitz_app_dir / BLITZAPP_MAPS
        strings_fn: Path = blitz_app_dir / BLITZAPP_STRINGS

        if isinstance(res := await open_dvpl_or_file(maps_fn), Err):
            raise ValueError(f"could not open: {maps_fn}")
        if (maps := Maps.load_yaml(res.ok_value.decode(encoding="utf-8"))) is None:
            raise ValueError(f"could not read maps for game files: {maps_fn}")

        debug(f"{len(maps)}maps read from {maps_fn}")

        if isinstance(res := await open_dvpl_or_file(strings_fn), Err):
            raise ValueError(f"could not read map names from: {strings_fn}")
        localization_strs = yaml.safe_load(res.ok_value.decode(encoding="utf-8"))

        if (updated := maps.add_names(localization_strs)) == 0:
            error(f"failed to add map names from location strings: {strings_fn}")
        debug(f"read {len(maps)} maps, updated {updated}, maps names")
        await update_maps(outfile=outfile, maps=maps, force=force)
    except Exception as err:
        error(err)
    return None


# TODO: REFACTOR to dvplc.open_file_or_dvpl(path: Path) -> Result[str, str]


async def open_maps_yaml(
    blitz_app_dir: Path,
) -> Maps | None:
    maps_fn: Path = blitz_app_dir / BLITZAPP_MAPS
    is_dvpl: bool = False
    maps: Maps | None = None
    temp_fn: Path = get_temp_filename("blitz-data.")
    try:
        if (blitz_app_dir / "assets").is_dir():
            # WG has changed the location of Data directory - at least in steam client
            blitz_app_dir = blitz_app_dir / "assets"
        debug("base dir for game files: %s", str(blitz_app_dir))

        if maps_fn.is_file():
            pass
        elif (maps_fn := add_suffix(maps_fn, ".dvpl")).is_file():
            is_dvpl = True
        else:
            raise FileNotFoundError(f"could not open Maps file: {maps_fn}")

        if is_dvpl:
            async with open(maps_fn, "br") as file:
                if is_ok(res := decode_dvpl(await file.read())):
                    yaml_doc = str(res.ok_value)
                else:
                    return None
        else:
            async with open(maps_fn, "r", encoding="utf8") as file:
                yaml_doc = await file.read()

        return Maps.load_yaml(yaml_doc)

        # if maps_fn.is_file():
        #     maps_file = maps_fn
        # elif (maps_fn := add_suffix(maps_fn, ".dvpl")).is_file():
        #     is_dvpl = True

        #     debug("decoding DVPL file: %s", maps_fn.resolve())
        #     debug("using temporary file: %s", str(temp_fn))

        #     if not await decode_dvpl_file(maps_fn, temp_fn):
        #         raise IOError(f"could not decode DVPL file: {maps_fn}")
        #     maps_file = temp_fn
        # else:
        #     raise FileNotFoundError(f"could not open Maps file: {maps_fn}")

        # if (maps := await Maps.open_yaml(maps_file)) is None:
        #     raise ValueError(f"could not read maps from YAML file: {maps_fn}")

    except Exception as err:
        error(err)
        raise err
    finally:
        if is_dvpl:
            debug("deleting temp file: %s", str(temp_fn))
            unlink(temp_fn)
    return maps


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
        added: set[Idx] = set()
        updated: set[Idx] = set()

        if not force:
            if (maps_old := await Maps.open_json(outfile)) is None:
                error(f"could not parse old Maps file: {outfile}")
                return None
            added, updated = maps_old.update(maps)
            maps = maps_old
        else:
            maps_old = Maps()

        if await maps.save_json(outfile) > 0:
            if force:
                if logger.level < logging.WARNING:
                    for map in maps.values():
                        verbose(f"added: map_id={map.id} {map.name} ")
            else:
                if logger.level < logging.WARNING:
                    for key in added:
                        verbose(f"added:   {maps[key].name}")
                    for key in updated:
                        verbose(f"updated: {maps[key].name}")

                message(
                    f"added {len(added)} and updated {len(updated)} maps to map list"
                )

            message(f"saved {len(maps)} maps to map list ({outfile})")
        else:
            error(f"writing map list failed: {outfile}")

    except Exception as err:
        error(f"{type(err)}: {err}")
    return None


if __name__ == "__main__":
    typer_app()

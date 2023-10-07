from asyncio import Task
from datetime import datetime
from typing import Optional, Literal, Any, cast
from pathlib import Path
from os import unlink
from re import Pattern, Match, compile

import sys
import yaml
import logging
import click
import configparser

from pyutils.utils import get_temp_filename, set_config, coro
from blitzutils import Map, Maps, Region
from dvplc import decode_dvpl, decode_dvpl_file

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

BLITZAPP_STRINGS: str = "Data/Strings/en.yaml"
MAPS: str = "maps.json"
WG_APP_ID: str = "d6d03acb6bee0e9f361b6e02e1780b56"
WG_REGION: str = "eu"

########################################################
#
# add_args_ functions
#
########################################################


# def add_args(parser: ArgumentParser, config: Optional[ConfigParser] = None) -> bool:
#     try:
#         debug("starting")

#         MAPS_FILE: str = "maps.json"

#         maps_parsers = parser.add_subparsers(
#             dest="maps_cmd",
#             title="maps commands",
#             description="valid commands",
#             metavar="app-data | file | wg",
#         )
#         maps_parsers.required = True

#         app_parser = maps_parsers.add_parser(
#             "app", aliases=["app-data"], help="maps app help"
#         )
#         if not add_args_app(app_parser, config=config):
#             raise Exception("Failed to define argument parser for: maps app")

#         file_parser = maps_parsers.add_parser("file", help="maps file help")
#         if not add_args_file(file_parser, config=config):
#             raise Exception("Failed to define argument parser for: maps file")

#         if config is not None and "METADATA" in config.sections():
#             configOptions = config["METADATA"]
#             MAPS_FILE = configOptions.get("maps_json", MAPS_FILE)

#         parser.add_argument(
#             "--outfile",
#             type=str,
#             default=MAPS_FILE,
#             nargs="?",
#             metavar="MAPS_FILE",
#             help=f"Write maps to file ({MAPS_FILE})",
#         )
#         parser.add_argument("-u", "--update", action="store_true", help="Update maps")

#         debug("Finished")
#         return True
#     except Exception as err:
#         error(f"{err}")
#     return False


###########################################
#
# maps
#
###########################################


@click.group(help="extract tankopedia as JSON file for other tools")
@click.option(
    "-f",
    "--force",
    flag_value=True,
    default=False,
    help="Overwrite Tankopedia instead of updating it",
)
@click.option(
    "--outfile",
    type=click.Path(path_type=str),
    default=None,
    help=f"Write maps to file (default: {MAPS})",
)
@click.pass_context
def maps(ctx: click.Context, force: bool = False, outfile: str | None = None) -> None:
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
        ctx.obj["force"] = force
    except Exception as err:
        error(f"{type(err)}: {err}")
        sys.exit(1)


########################################################
#
# maps app
#
########################################################


@maps.command(help="extract maps from Blitz game files")  # type:ignore
@click.option("--wg-app-id", type=str, default=None, help="WG app ID")
@click.option(
    "--wg-region",
    type=click.Choice([r.name for r in Region.API_regions()], case_sensitive=False),
    default=None,
    help=f"WG API region (default: {WG_REGION})",
)
@click.argument(
    "blitz_app_dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    required=False,
    default=None,
    nargs=1,
)
@click.pass_context
@coro
async def app(
    ctx: click.Context,
    wg_app_id: str | None = None,
    wg_region: str | None = None,
    blitz_app_dir: Path | None = None,
):
    """Read Tankopedia from game files (Steam Client)"""
    debug("starting")
    try:
        config: configparser.ConfigParser = ctx.obj["config"]
        wg_app_id = set_config(config, WG_APP_ID, "WG", "app_id", wg_app_id)
        region: Region = Region(
            set_config(config, WG_REGION, "WG", "default_region", wg_region)
        )
        outfile: Path = Path(config.get("METADATA", "maps_json"))
        force: bool = ctx.obj["force"]
        if blitz_app_dir is None:
            blitz_app_dir = Path(config.get("METADATA", "blitz_app_dir"))
    except configparser.Error as err:
        error(f"could not read config file: {type(err)}: {err}")
        sys.exit(1)
    except Exception as err:
        error(f"{type(err)}: {err}")
        sys.exit(1)
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

        debug(f"Opening file: %s for reading map strings", str(filename))
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


# def add_args_app(parser: ArgumentParser, config: Optional[ConfigParser] = None) -> bool:
#     debug("starting")
#     BLITZAPP_DIR: str = "./BlitzApp"
#     try:
#         if config is not None and "METADATA" in config.sections():
#             configOptions = config["METADATA"]
#             BLITZAPP_DIR = configOptions.get("blitz_app_dir", BLITZAPP_DIR)
#         parser.add_argument(
#             "blitz_app_dir",
#             type=str,
#             nargs="?",
#             default=BLITZAPP_DIR,
#             metavar="BLITZ_APP_DIR",
#             help="Blitz app dir",
#         )
#     except Exception as err:
#         error(f"could not add arguments: {err}")
#         return False
#     return True


########################################################
#
# maps file
#
########################################################


@maps.command(  # type:ignore
    help="""read Maps from a JSON file
              
            INFILE is a JSON file to read maps from"""
)
@click.argument(
    "infile",
    type=click.Path(path_type=Path),
)
@click.pass_context
@coro
async def file(ctx: click.Context, infile: Path):
    """Read Maps from a file"""
    click.echo(infile)
    debug("starting")
    try:
        config: configparser.ConfigParser = ctx.obj["config"]
        outfile: Path = Path(config.get("METADATA", "maps_json"))
        force: bool = ctx.obj["force"]
    except configparser.Error as err:
        error(f"could not read config file: {type(err)}: {err}")
        sys.exit(1)
    except Exception as err:
        error(f"{type(err)}: {err}")
        sys.exit(1)
    if (maps := await Maps.open_json(infile)) is not None:
        await update_maps(outfile=outfile, maps=maps, force=force)
    else:
        error(f"could not read Maps from {infile}")


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


# async def cmd_app(args: Namespace) -> Maps | None:
#     """read maps from game files"""
#     debug("starting")
#     is_dvpl: bool = False
#     maps = Maps()
#     user_strs: dict[str, str] = dict()
#     filename: Path = Path(args.blitz_app_dir)
#     try:
#         if (filename / "assets").is_dir():
#             filename = filename / "assets"
#         filename = filename / BLITZAPP_STRINGS

#         if filename.is_file():
#             pass
#         elif (filename := filename.parent / (filename.name + ".dvpl")).is_file():
#             is_dvpl = True
#             debug("decoding DVPL file: %s", filename.resolve())
#             temp_fn: Path = get_temp_filename("blitz-data.")
#             debug("using temporary file: %s", str(temp_fn))
#             if not await decode_dvpl_file(filename, temp_fn):
#                 raise IOError(f"could not decode DVPL file: {filename}")
#             filename = temp_fn

#         debug(f"Opening file: %s for reading map strings", str(filename))
#         with open(filename, "r", encoding="utf8") as strings_file:
#             user_strs = yaml.safe_load(strings_file)
#     except:
#         raise
#     finally:
#         if is_dvpl:
#             debug("deleting temp file: %s", str(filename))
#             unlink(filename)
#     try:
#         re_map: Pattern = compile(r"^#maps:(\w+?):.+?$")
#         match: Match | None
#         for key, value in user_strs.items():
#             # some Halloween map variants have the same short name
#             if (match := re_map.match(key)) and key not in maps:
#                 maps.add(Map(name=value, key=match.group(1)))
#         return maps
#     except Exception as err:
#         error(f"unable to read maps from {filename.resolve()}: {err}")
#     return None


# async def cmd_file(args: Namespace) -> Maps | None:
#     debug("starting")
#     return await Maps.open_json(args.infile)
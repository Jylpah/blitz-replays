from argparse import ArgumentParser, Namespace, SUPPRESS
from configparser import ConfigParser
from datetime import datetime
from typing import Optional, Literal, Any, cast
from pathlib import Path
from os import unlink
from re import Pattern, Match, compile
import aiofiles
import yaml
from pydantic import ValidationError
import logging

from pyutils.utils import get_temp_filename
from blitzutils import Map, Maps
from dvplc import decode_dvpl, decode_dvpl_file

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

BLITZAPP_STRINGS: str = "Data/Strings/en.yaml"

########################################################
#
# add_args_ functions
#
########################################################


def add_args(parser: ArgumentParser, config: Optional[ConfigParser] = None) -> bool:
    try:
        debug("starting")

        MAPS_FILE: str = "maps.json"

        maps_parsers = parser.add_subparsers(
            dest="maps_cmd",
            title="maps commands",
            description="valid commands",
            metavar="app-data | file | wg",
        )
        maps_parsers.required = True

        app_parser = maps_parsers.add_parser(
            "app", aliases=["app-data"], help="maps app help"
        )
        if not add_args_app(app_parser, config=config):
            raise Exception("Failed to define argument parser for: maps app")

        file_parser = maps_parsers.add_parser("file", help="maps file help")
        if not add_args_file(file_parser, config=config):
            raise Exception("Failed to define argument parser for: maps file")

        if config is not None and "METADATA" in config.sections():
            configOptions = config["METADATA"]
            MAPS_FILE = configOptions.get("maps_json", MAPS_FILE)

        parser.add_argument(
            "--outfile",
            type=str,
            default=MAPS_FILE,
            nargs="?",
            metavar="MAPS_FILE",
            help=f"Write maps to file ({MAPS_FILE})",
        )
        parser.add_argument("-u", "--update", action="store_true", help="Update maps")

        debug("Finished")
        return True
    except Exception as err:
        error(f"{err}")
    return False


def add_args_app(parser: ArgumentParser, config: Optional[ConfigParser] = None) -> bool:
    debug("starting")
    BLITZAPP_DIR: str = "./BlitzApp"
    try:
        if config is not None and "METADATA" in config.sections():
            configOptions = config["METADATA"]
            BLITZAPP_DIR = configOptions.get("blitz_app_dir", BLITZAPP_DIR)
        parser.add_argument(
            "blitz_app_dir",
            type=str,
            default=BLITZAPP_DIR,
            metavar="BLITZ_APP_DIR",
            help="Blitz app dir",
        )
    except Exception as err:
        error(f"could not add arguments: {err}")
        return False
    return True


def add_args_file(
    parser: ArgumentParser, config: Optional[ConfigParser] = None
) -> bool:
    debug("starting")
    parser.add_argument(
        "file", type=str, metavar="FILE", help="Read Tankopedia from file"
    )
    return True


###########################################
#
# cmd_ functions
#
###########################################


async def cmd(args: Namespace) -> bool:
    try:
        debug("starting")
        maps_new: Maps | None
        maps_old: Maps | None

        if args.maps_cmd == "app":
            if (maps_new := await cmd_app(args)) is None:
                raise ValueError(
                    f"could not read maps from game files: {args.blitz_app_dir}"
                )
        elif args.maps_cmd == "file":
            if (maps_new := await cmd_file(args)) is None:
                raise ValueError(f"could not read maps from file: {args.infile}")
        else:
            raise NotImplementedError(f"unknown command: {args.maps_cmd}")

        if args.update:
            if (maps_old := await Maps.open_json(args.outfile)) is None:
                error(f"could not parse old tankopedia ({args.outfile})")
                return False
        else:
            maps_old = Maps()

        new: set[str] = {map.key for map in maps_new}
        old: set[str] = {map.key for map in maps_old}
        added: set[str] = new - old
        updated: set[str] = new & old
        updated = {key for key in updated if maps_new[key] != maps_old[key]}

        if args.update:
            maps_old.update(maps_new)
            maps_new = maps_old

        if await maps_new.save_json(args.outfile) > 0:
            if logger.level < logging.WARNING:
                for key in added:
                    verbose(f"added:   {maps_new[key].name}")

            if logger.level < logging.WARNING:
                for key in updated:
                    verbose(f"updated: {maps_new[key].name}")

            message(f"added {len(added)} and updated {len(updated)} maps to map list")
            message(f"saved {len(maps_new)} maps to map list ({args.outfile})")
        else:
            error(f"writing map list failed: {args.outfile}")

    except Exception as err:
        error(f"{err}")
    return False


async def cmd_app(args: Namespace) -> Maps | None:
    """read maps from game files"""
    debug("starting")
    is_dvpl: bool = False
    maps = Maps()
    user_strs: dict[str, str] = dict()
    filename: Path = Path(args.blitz_app_dir)
    try:
        if (filename / "assets").is_dir():
            filename = filename / "assets"
        filename = filename / BLITZAPP_STRINGS

        if filename.is_file():
            pass
        elif (filename := filename.parent / (filename.name + ".dvpl")).is_file():
            is_dvpl = True
            debug("decoding DVPL file: %s", filename.resolve())
            temp_fn: Path = get_temp_filename("blitz-data.")
            debug("using temporary file: %s", str(temp_fn))
            if not await decode_dvpl_file(str(filename), str(temp_fn)):
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
        return maps
    except Exception as err:
        error(f"unable to read maps from {filename.resolve()}: {err}")
    return None


async def cmd_file(args: Namespace) -> Maps | None:
    debug("starting")
    return await Maps.open_json(args.infile)

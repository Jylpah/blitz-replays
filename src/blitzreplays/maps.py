from argparse import ArgumentParser, Namespace, SUPPRESS
from configparser import ConfigParser
from datetime import datetime
from typing import Optional, Literal, Any, cast
from pathlib import Path
from os.path import isdir, isfile
from re import Pattern, Match, compile
import aiofiles
import yaml
from pydantic import ValidationError
import logging

from blitzutils import Map, Maps

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

        app_parser = maps_parsers.add_parser("app", aliases=["app-data"], help="maps app help")
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
            help="Write maps to file",
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
            "blitz_app_dir", type=str, default=BLITZAPP_DIR, metavar="BLITZ_APP_DIR", help="Blitz app dir"
        )
    except Exception as err:
        error(f"could not add arguments: {err}")
        return False
    return True


def add_args_file(parser: ArgumentParser, config: Optional[ConfigParser] = None) -> bool:
    debug("starting")
    parser.add_argument("file", type=str, metavar="FILE", help="Read Tankopedia from file")
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
                raise ValueError(f"could not read maps from game files: {args.blitz_app_dir}")
        elif args.maps_cmd == "file":
            if (maps_new := await cmd_file(args)) is None:
                raise ValueError(f"could not read maps from file: {args.infile}")
        else:
            raise NotImplementedError(f"unknown command: {args.maps_cmd}")

        if args.update and isfile(args.outfile):
            if (maps_old := await Maps.open_json(args.outfile)) is None:
                error(f"could not parse old tankopedia ({args.outfile})")
                return False
            maps_old.update(maps_new)
        else:
            maps_old = maps_new

        return await maps_old.save_json(args.outfile) > 0

    except Exception as err:
        error(f"{err}")
    return False


async def cmd_app(args: Namespace) -> Maps | None:
    """read maps from game files"""
    debug("starting")
    maps = Maps()
    filename: Path = Path(f"{args.blitz_app_dir}/{BLITZAPP_STRINGS}")
    try:
        debug(f"Opening file: %s for reading map strings", str(filename))
        user_strs: dict[str, str] = dict()
        with open(filename, "r", encoding="utf8") as strings_file:
            user_strs = yaml.safe_load(strings_file)

        re_map: Pattern = compile(r"^#maps:(\w+?):.+?$")

        for key, value in user_strs.items():
            # some Halloween map variants have the same short name
            if re_map.match(key) and key not in maps:
                maps.add(Map(name=value, key=key))
        return maps
    except Exception as err:
        error(f"unable to read maps from {filename.resolve()}: {err}")
    return None


async def cmd_file(args: Namespace) -> Maps | None:
    debug("starting")
    return await Maps.open_json(args.infile)

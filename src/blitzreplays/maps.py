from argparse import ArgumentParser, Namespace, SUPPRESS
from configparser import ConfigParser
from datetime import datetime
from typing import Optional, Literal, Any, cast
import logging

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

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

        if config is not None and "METADATA" in config:
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
        if config is not None and "METADATA" in config:
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
        if args.maps_cmd == "app":
            return await cmd_app(args)

        elif args.maps_cmd == "file":
            return await cmd_file(args)

        else:
            raise NotImplementedError(f"unknown command: {args.tankopedia_cmd}")

    except Exception as err:
        error(f"{err}")
    return False


async def cmd_app(args: Namespace) -> bool:
    return False


async def cmd_file(args: Namespace) -> bool:
    return False

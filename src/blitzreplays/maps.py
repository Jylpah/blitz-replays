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

        debug("Finished")
        return True
    except Exception as err:
        error(f"{err}")
    return False


def add_args_app(parser: ArgumentParser, config: Optional[ConfigParser] = None) -> bool:
    debug("starting")
    return False


def add_args_file(parser: ArgumentParser, config: Optional[ConfigParser] = None) -> bool:
    debug("starting")
    return False


def add_args_wg(parser: ArgumentParser, config: Optional[ConfigParser] = None) -> bool:
    debug("starting")
    return False

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
        tankopedia_parsers = parser.add_subparsers(
            dest="tankopedia_cmd",
            title="tankopedia commands",
            description="valid commands",
            metavar="app-data | file | wg",
        )
        tankopedia_parsers.required = True

        app_parser = tankopedia_parsers.add_parser("app", aliases=["app-data"], help="tankopedia app help")
        if not add_args_app(app_parser, config=config):
            raise Exception("Failed to define argument parser for: tankopedia app")

        file_parser = tankopedia_parsers.add_parser("file", help="tankopedia file help")
        if not add_args_file(file_parser, config=config):
            raise Exception("Failed to define argument parser for: tankopedia file")

        wg_parser = tankopedia_parsers.add_parser("wg", help="tankopedia wg help")
        if not add_args_wg(wg_parser, config=config):
            raise Exception("Failed to define argument parser for: tankopedia wg")

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

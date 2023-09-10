from argparse import ArgumentParser, Namespace, SUPPRESS
from configparser import ConfigParser
from datetime import datetime
from typing import Optional, Literal, Any, cast
from asyncio import Task, TaskGroup, create_task, gather
from os.path import isfile
from os import unlink
from pathlib import Path
from re import Pattern, Match, compile
from sortedcollections import SortedDict  # type: ignore
from pydantic import ValidationError
import aiofiles
import logging
import xmltodict  # type: ignore
import yaml
import os

from blitzutils import (
    Region,
    EnumNation,
    EnumVehicleTier,
    EnumVehicleTypeInt,
    EnumVehicleTypeStr,
)
from blitzutils import WGTank, WGApiTankopedia, WGApi, WoTBlitzTankString, add_args_wg
from dvplc import decode_dvpl, decode_dvpl_file
from pyutils.utils import get_temp_filename

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

BLITZAPP_STRINGS: str = "Data/Strings/en.yaml"
BLITZAPP_VEHICLES_DIR: str = "Data/XML/item_defs/vehicles/"
BLITZAPP_VEHICLE_FILE: str = "list.xml"

########################################################
#
# add_args_ functions
#
########################################################


def add_args(parser: ArgumentParser, config: Optional[ConfigParser] = None) -> bool:
    try:
        debug("starting")
        TANKS_FILE: str = "tanks.json"

        tankopedia_parsers = parser.add_subparsers(
            dest="tankopedia_cmd",
            title="tankopedia commands",
            description="valid commands",
            metavar="app | file | wg",
        )
        tankopedia_parsers.required = True

        app_parser = tankopedia_parsers.add_parser("app", help="tankopedia app help")
        if not add_args_app(app_parser, config=config):
            raise Exception("Failed to define argument parser for: tankopedia app")

        file_parser = tankopedia_parsers.add_parser("file", help="tankopedia file help")
        if not add_args_file(file_parser, config=config):
            raise Exception("Failed to define argument parser for: tankopedia file")

        wg_parser = tankopedia_parsers.add_parser("wg", help="tankopedia wg help")
        if not add_args_wgapi(wg_parser, config=config):
            raise Exception("Failed to define argument parser for: tankopedia wg")

        if config is not None and "METADATA" in config.sections():
            configOptions = config["METADATA"]
            TANKS_FILE = configOptions.get("tankopedia_json", TANKS_FILE)

        parser.add_argument(
            "--outfile",
            type=str,
            default=TANKS_FILE,
            nargs="?",
            metavar="TANKOPEDIA",
            help=f"Write Tankopedia to file ({TANKS_FILE})",
        )
        parser.add_argument(
            "-f",
            "--force",
            action="store_true",
            help="Overwrite Tankopedia instead of updating it",
        )

        debug("Finished")
        return add_args_wg(parser=parser, config=config)
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
            nargs="?",
            default=BLITZAPP_DIR,
            metavar="BLTIZ_APP_DIR",
            help="Read Tankopedia game files",
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
        "infile", type=str, metavar="FILE", help="Read Tankopedia from file"
    )
    return True


def add_args_wgapi(
    parser: ArgumentParser, config: Optional[ConfigParser] = None
) -> bool:
    """Dummy since the WGApi() params are read in the parent"""
    return True


###########################################
#
# cmd_ functions
#
###########################################


async def cmd(args: Namespace) -> bool:
    try:
        debug("starting")

        tankopedia_new: WGApiTankopedia | None
        tankopedia: WGApiTankopedia | None
        if args.tankopedia_cmd == "app":
            if (tankopedia_new := await cmd_app(args)) is None:
                raise ValueError(
                    f"could not read tankopedia from game files: {args.blitz_app_dir}"
                )
        elif args.tankopedia_cmd == "file":
            if (tankopedia_new := await cmd_file(args)) is None:
                raise ValueError(f"could not read tankopedia from file: {args.infile}")
        elif args.tankopedia_cmd == "wg":
            if (tankopedia_new := await cmd_wg(args)) is None:
                raise ValueError(
                    f"could not read tankopedia from WG API: {args.server}"
                )
        else:
            raise NotImplementedError(f"unknown command: {args.tankopedia_cmd}")

        if not args.force and isfile(args.outfile):
            if (tankopedia := await WGApiTankopedia.open_json(args.outfile)) is None:
                error(f"could not parse old tankopedia: {args.outfile}")
                return False
        else:
            tankopedia = WGApiTankopedia()

        added: set[int]
        updated: set[int]
        (added, updated) = tankopedia.update(tankopedia_new)

        if await tankopedia.save_json(args.outfile) > 0:
            if logger.level < logging.WARNING:
                for tank_id in added:
                    verbose(f"added:   tank_id={tank_id:<5} {tankopedia[tank_id].name}")

            if logger.level < logging.WARNING:
                for tank_id in updated:
                    verbose(f"updated: tank_id={tank_id:<5} {tankopedia[tank_id].name}")

            message(
                f"added {len(added)} and updated {len(updated)} tanks to Tankopedia"
            )
            message(f"saved {len(tankopedia)} tanks to Tankopedia ({args.outfile})")
        else:
            error(f"writing Tankopedia failed: {args.outfile}")

        return True
    except Exception as err:
        error(f"{err}")
    return False


async def cmd_app(args: Namespace) -> WGApiTankopedia | None:
    """Read Tankopedia from game files"""
    debug("starting")
    tasks: list[Task] = []
    try:
        blitz_app_dir: Path = Path(args.blitz_app_dir)
        if (blitz_app_dir / "assets").is_dir():
            # WG has changed the location of Data directory - at least in steam client
            blitz_app_dir = blitz_app_dir / "assets"
        debug("base dir for game files: %s", str(blitz_app_dir))

        for nation in EnumNation:
            tasks.append(create_task(extract_tanks(blitz_app_dir, nation)))

        tanks: list[WGTank] = list()
        # user_strs: dict[int, str] = dict()
        for nation_tanks in await gather(*tasks):
            tanks.extend(nation_tanks)

        tank_strs: dict[str, str] = await read_tank_strs(blitz_app_dir)
        tankopedia = WGApiTankopedia()

        tanks_ok: list[WGTank]
        tanks_nok: list[WGTank]
        tanks_ok, tanks_nok = convert_tank_names(tanks, tank_strs)
        for tank in tanks_ok:
            tankopedia.add(tank)

        async with WGApi(default_region=Region(args.wg_region), rate_limit=0) as wg:
            for tank in tanks_nok:
                if (
                    tank.name is not None
                    and (tank_str := await wg.get_tank_str(tank.name)) is not None
                ):
                    tank.name = tank_str.user_string
                else:
                    error(f"could not fetch tank name for tank_id={tank.tank_id}")
                tankopedia.add(tank)

        return tankopedia
    except Exception as err:
        error(err)
    return None


async def cmd_file(args: Namespace) -> WGApiTankopedia | None:
    debug("starting")
    return await WGApiTankopedia.open_json(args.infile)


async def cmd_wg(args: Namespace) -> WGApiTankopedia | None:
    debug("starting")
    async with WGApi(app_id=args.wg_app_id) as wg:
        return await wg.get_tankopedia(region=Region(args.wg_region))


def extract_tanks_xml(tankopedia: dict[str, Any], nation: EnumNation) -> list[WGTank]:
    """Extract tanks from a parsed XML"""
    tanks: list[WGTank] = list()
    for data in tankopedia["root"].keys():
        try:
            tank_xml: dict[str, Any] = tankopedia["root"][data]
            debug(f"reading tank: {tank_xml}")
            tank = WGTank(
                tank_id=mk_tank_id(nation, int(tank_xml["id"])), nation=nation
            )
            tank.is_premium = issubclass(type(tank_xml["price"]), dict)
            tank.tier = EnumVehicleTier(int(tank_xml["level"]))
            tank.type = read_tank_type(tank_xml["tags"])
            tank.name = tank_xml["userString"]  # Need to be converted later
            tanks.append(tank)
            debug("Read tank_id=%d", tank.tank_id)
        except KeyError as err:
            error("Failed to read item=%s: %s", data, str(err))
        except Exception as err:
            error("Failed to read item=%s: %s", data, str(err))
    return tanks


async def extract_tanks(blitz_app_dir: Path, nation: EnumNation) -> list[WGTank]:
    """Extract tanks from BLITZAPP_VEHICLE_FILE 'list.xml' file for a nation"""

    tanks: list[WGTank] = list()
    list_xml: Path = (
        blitz_app_dir / BLITZAPP_VEHICLES_DIR / nation.name / BLITZAPP_VEHICLE_FILE
    )
    tankopedia: dict[str, Any]
    if list_xml.is_file():
        debug(f"Opening file: {list_xml} nation={nation}")
        async with aiofiles.open(list_xml, "r", encoding="utf8") as f:
            tankopedia = xmltodict.parse(await f.read())
    elif (list_xml := list_xml.parent / (list_xml.name + ".dvpl")).is_file():
        debug(f"Opening file (DVPL): {list_xml} nation={nation}")
        async with aiofiles.open(list_xml, "rb") as f:
            data, _ = decode_dvpl(await f.read(), quiet=True)
            tankopedia = xmltodict.parse(data)
    else:
        error(f"cannot open tank file for nation={nation}: {list_xml}")
        return tanks
    return extract_tanks_xml(tankopedia, nation)


async def read_tank_strs(blitz_app_dir: Path) -> dict[str, str]:
    """Read user strings to convert map and tank names"""
    tank_strs: dict[str, str] = dict()
    filename: Path = blitz_app_dir / BLITZAPP_STRINGS
    user_strs: dict[str, str] = dict()
    is_dvpl: bool = False
    try:
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

        debug(f"Opening file: %s for reading UserStrings", str(filename))
        with open(filename, "r", encoding="utf8") as strings_file:
            user_strs = yaml.safe_load(strings_file)
    except:
        raise
    finally:
        if is_dvpl:
            debug("deleting temp file: %s", str(filename))
            unlink(filename)

    re_tank: Pattern = compile("^#\\w+?_vehicles:")
    # re_skip: Pattern = compile("(^Chassis_|^Turret_|_short$)")
    re_skip: Pattern = compile("(^Chassis_|^Turret_)")
    for key, value in user_strs.items():
        try:
            if re_tank.match(key):
                if re_skip.match(key.split(":")[1]):
                    continue
                if (
                    key not in tank_strs
                ):  # some Halloween map variants have the same short name
                    tank_strs[key] = value
        except KeyError as err:
            error(err)

    return tank_strs


def convert_tank_names(
    tanks: list[WGTank], tank_strs: dict[str, str]
) -> tuple[list[WGTank], list[WGTank]]:
    """Convert tank names for Tankopedia based on tank user strings in /Data/Strings/en.yaml
    Returns 2 lists: converted, not_converted"""
    debug("starting")

    converted: list[WGTank] = list()
    not_converted: list[WGTank] = list()

    for tank in tanks:
        try:
            if tank.name in tank_strs:
                tank.name = tank_strs[tank.name]
                converted.append(tank)
            elif tank.name is not None:
                tank.name = tank.name.split(":")[1]
                not_converted.append(tank)
            else:
                error(f"no name defined for tank_id={tank.tank_id}: {tank.name}")
        except KeyError as err:
            error(f"could not convert name tank_id={tank.tank_id}: {tank.name}: {err}")

    return converted, not_converted


def mk_tank_id(nation: EnumNation, tank_id: int) -> int:
    return (tank_id << 8) + (nation.value << 4) + 1


def read_tank_type(tagstr: str) -> EnumVehicleTypeStr:
    tags: set[str] = set(tagstr.split(" "))
    for tank_type in EnumVehicleTypeStr:
        if tank_type.value in tags:
            return tank_type
    raise ValueError(f"No known tank type found from 'tags' field: {tagstr}")

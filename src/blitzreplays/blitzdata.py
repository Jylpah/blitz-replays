#!/usr/bin/env python3

from os.path import isfile, isdir, dirname, realpath, expanduser, join as join_path
from pathlib import Path
from typing import Optional, Any
from configparser import ConfigParser
from sortedcontainers import SortedDict  # type: ignore
from asyncio import set_event_loop_policy, run, create_task, get_event_loop_policy, Task
from re import Pattern, Match, compile
from pydantic import ValidationError

import aiofiles  # type: ignore
import xmltodict  # type: ignore
import sys, argparse, json, os, inspect, asyncio, logging, time, configparser
import logging

sys.path.insert(0, dirname(dirname(realpath(__file__))))

from blitzutils import EnumNation, EnumVehicleTypeInt, EnumVehicleTypeStr, WGTank, EnumVehicleTier
from blitzutils import WGApiTankopedia
from pyutils import MultilevelFormatter
from blitzreplays import tankopedia
from blitzreplays import maps

# logging.getLogger("asyncio").setLevel(logging.DEBUG)
logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

FILE_CONFIG = "blitzstats.ini"
BLITZAPP_STRINGS = "Data/Strings/en.yaml"
BLITZAPP_VEHICLES_DIR = "Data/XML/item_defs/vehicles/"
BLITZAPP_VEHICLE_FILE = "list.xml"


## main() -------------------------------------------------------------
async def main() -> None:
    global logger, error, debug, verbose, message
    # set the directory for the script
    # os.chdir(os.path.dirname(sys.argv[0]))

    ## Read config
    BLITZAPP_FOLDER = "."
    _PKG_NAME = "blitzreplays"
    CONFIG = _PKG_NAME + ".ini"
    LOG = _PKG_NAME + ".log"
    config: Optional[ConfigParser] = None
    CONFIG_FILE: Optional[str] = None

    CONFIG = "blitzstats.ini"
    CONFIG_FILES: list[str] = [
        "./" + CONFIG,
        dirname(realpath(__file__)) + "/" + CONFIG,
        "~/." + CONFIG,
        "~/.config/" + CONFIG,
        f"~/.config/{_PKG_NAME}/config",
        "~/.config/blitzstats.ini",
        "~/.config/blitzstats/config",
    ]
    for fn in [expanduser(f) for f in CONFIG_FILES]:
        if isfile(fn):
            CONFIG_FILE = fn
            verbose(f"config file: {CONFIG_FILE}")
            break

    parser = argparse.ArgumentParser(description="Read/update Blitz metadata")
    arggroup_verbosity = parser.add_mutually_exclusive_group()
    arggroup_verbosity.add_argument(
        "--debug", "-d", dest="LOG_LEVEL", action="store_const", const=logging.DEBUG, help="Debug mode"
    )
    arggroup_verbosity.add_argument(
        "--verbose", "-v", dest="LOG_LEVEL", action="store_const", const=logging.INFO, help="Verbose mode"
    )
    arggroup_verbosity.add_argument(
        "--silent", "-s", dest="LOG_LEVEL", action="store_const", const=logging.CRITICAL, help="Silent mode"
    )
    parser.add_argument("--log", type=str, nargs="?", default=None, const=f"{LOG}", help="Enable file logging")
    parser.add_argument("--config", type=str, default=CONFIG_FILE, metavar="CONFIG", help="Read config from CONFIG")
    parser.set_defaults(LOG_LEVEL=logging.WARNING)

    args, argv = parser.parse_known_args()

    # setup logging
    logger.setLevel(args.LOG_LEVEL)
    logger_conf: dict[int, str] = {
        logging.INFO: "%(message)s",
        logging.WARNING: "%(message)s",
        # logging.ERROR: 		'%(levelname)s: %(message)s'
    }
    MultilevelFormatter.setLevels(
        logger, fmts=logger_conf, fmt="%(levelname)s: %(funcName)s(): %(message)s", log_file=args.log
    )
    error = logger.error
    message = logger.warning
    verbose = logger.info
    debug = logger.debug

    if args.config is not None and isfile(args.config):
        debug("Reading config from %f", args.config)
        config = ConfigParser()
        config.read(args.config)
        # if "METADATA" in config:
        #     configOptions = config["METADATA"]
        #     BLITZAPP_FOLDER = configOptions.get("blitz_app_dir", BLITZAPP_FOLDER)
    else:
        debug("No config file found")
    # Parse command args
    parser.add_argument("-h", "--help", action="store_true", help="Show help")

    cmd_parsers = parser.add_subparsers(
        dest="main_cmd",
        title="main commands",
        description="valid subcommands",
        metavar="tankopedia | maps",
    )
    cmd_parsers.required = True

    tankopedia_parser = cmd_parsers.add_parser("tankopedia", aliases=["tp"], help="tankopedia help")
    maps_parser = cmd_parsers.add_parser("maps", help="maps help")

    parser.add_argument(
        "blitz_app_dir",
        type=str,
        nargs="?",
        metavar="BLITZAPP_FOLDER",
        default=BLITZAPP_FOLDER,
        help="Base dir of the Blitz App files",
    )
    parser.add_argument(
        "tanks", type=str, default="tanks.json", nargs="?", metavar="TANKS_FILE", help="File to write Tankopedia"
    )
    parser.add_argument(
        "maps", type=str, default="maps.json", nargs="?", metavar="MAPS_FILE", help="File to write map names"
    )
    args = parser.parse_args(args=argv)

    tasks: list[Task] = []
    for nation in EnumNation:
        tasks.append(asyncio.create_task(extract_tanks(args.blitz_app_dir, nation)))

    tanks: list[WGTank] = list()
    # user_strs: dict[int, str] = dict()
    for nation_tanks in await asyncio.gather(*tasks):
        # user_strs.update(nation_user_strs)
        tanks.extend(nation_tanks)

    tank_strs, map_strs = await read_user_strs(args.blitz_app_dir)

    tankopedia = WGApiTankopedia()

    ## CONTINUE:
    # - add WGApiWoTBlitz.read(Path or filename)
    # - Create separate model for user strings

    tankopedia = WGApiTankopedia()
    if os.path.exists(args.tanks):
        try:
            tankopedia = WGApiTankopedia.parse_file(args.tanks)
        except ValidationError as err:
            pass

    async with aiofiles.open(args.tanks, "w", encoding="utf8") as outfile:
        new_tanks, new_userStrs = await convert_tank_names(tanklist, tank_strs)
        # merge old and new tankopedia
        tanks.update(new_tanks)
        userStrs.update(new_userStrs)
        tankopedia: SortedDict[str, str | int | dict] = SortedDict()
        tankopedia["status"] = "ok"
        tankopedia["meta"] = {"count": len(tanks)}
        tankopedia["data"] = sort_dict(tanks, number=True)
        tankopedia["userStr"] = sort_dict(userStrs)
        message(f"New tankopedia '{args.tanks}' contains {len(tanks)} tanks")
        message(f"New tankopedia '{args.tanks}' contains {len(userStrs)} tanks strings")
        await outfile.write(json.dumps(tankopedia, ensure_ascii=False, indent=4, sort_keys=False))

    if args.maps is not None:
        maps = {}
        if os.path.exists(args.maps):
            try:
                async with aiofiles.open(args.maps) as infile:
                    maps = json.loads(await infile.read())
            except Exception as err:
                error(f"Unexpected error when reading file: {args.maps} : {err}")
        # merge old and new map data
        maps.update(map_strs)
        async with aiofiles.open(args.maps, "w", encoding="utf8") as outfile:
            message(f"New maps file '{args.maps}' contains {len(maps)} maps")
            await outfile.write(json.dumps(maps, ensure_ascii=False, indent=4, sort_keys=True))

    return None


async def extract_tanks(blitz_app_dir: str, nation: EnumNation) -> list[WGTank]:
    """Extract tanks from BLITZAPP_VEHICLE_FILE 'list.xml' file for a nation"""

    tanks: list[WGTank] = list()
    # user_strs: dict[int, str] = dict()

    # WG has changed the location of Data directory - at least in steam client
    if isdir(join_path(blitz_app_dir, "assets")):
        blitz_app_dir = join_path(blitz_app_dir, "assets")

    list_xml: str = join_path(blitz_app_dir, BLITZAPP_VEHICLES_DIR, nation.name, BLITZAPP_VEHICLE_FILE)

    if not isfile(list_xml):
        error(f"cannot open {list_xml}")
        return tanks

    debug(f"Opening file: {list_xml} (Nation: {nation})")
    async with aiofiles.open(list_xml, "r", encoding="utf8") as f:
        tank_list: dict[str, Any] = xmltodict.parse(await f.read())
        for data in tank_list["root"].keys():
            try:
                tank_xml: dict[str, Any] = tank_list["root"][data]
                debug(f"reading tank: {tank_xml}")
                tank = WGTank(tank_id=mk_tank_id(nation, int(tank_xml["id"])), nation=nation)
                tank.is_premium = issubclass(type(tank_xml["price"]), dict)
                tank.tier = EnumVehicleTier(tank_xml["level"])
                tank.type = read_tank_type(tank_xml["tags"])
                tank.name = tank_xml["userString"]  # Need to be converted later
                tanks.append(tank)
                # user_strs[tank.tank_id] = tank_xml["userString"]  # is this needed?
                debug("Read tank_id=%d", tank.tank_id)
            except KeyError as err:
                error("Failed to read item=%s: %s", data, str(err))
    return tanks  # , user_strs


async def read_user_strs(blitz_app_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Read user strings to convert map and tank names"""
    tank_strs: dict[str, str] = dict()
    map_strs: dict[str, str] = dict()
    filename: Path = blitz_app_dir / BLITZAPP_STRINGS
    debug(f"Opening file: %s for reading UserStrings", str(filename))
    try:
        async with aiofiles.open(filename, "r", encoding="utf8") as strings_file:
            regexp_tank: Pattern = compile('^"(#\\w+?_vehicles:.+?)": "(.+)"$')
            regexp_map: Pattern = compile('^"#maps:([a-z_]+?):.+?: "(.+?)"$')
            match: Match | None
            async for line in strings_file:
                match = regexp_tank.match(line)
                if match is not None:
                    if match.group(1) not in tank_strs:  # some Halloween map variants have the same short name
                        tank_strs[match.group(1)] = match.group(2)
                    continue

                match = regexp_map.match(line)
                if match is not None:
                    map_strs[match.group(1)] = match.group(2)

    except Exception as err:
        error(err)
        sys.exit(1)

    return tank_strs, map_strs


async def convert_tank_names(tanklist: list, tank_strs: dict) -> tuple[dict, dict]:
    """Convert tank names for Tankopedia"""
    tankopedia = {}
    userStrs = {}

    debug(f"tank_strs:")
    for key, value in tank_strs.items():
        debug(f"{key}: {value}")
    debug("---------")
    try:
        for tank in tanklist:
            try:
                debug(f"tank: {tank}")
                if tank["userStr"] in tank_strs:
                    tank["name"] = tank_strs[tank["userStr"]]
                else:
                    tank["name"] = tank["userStr"].split(":")[1]
                tank.pop("userStr", None)
                tank_tmp = dict()
                for key in sorted(tank.keys()):
                    tank_tmp[key] = tank[key]
                tankopedia[str(tank["tank_id"])] = tank_tmp
            except:
                error(f"Could not process tank: {tank}")

        for tank_str in tank_strs:
            skip = False
            key = tank_str.split(":")[1]
            debug("Tank string: " + key + " = " + tank_strs[tank_str])
            re_strs = [r"^Chassis_", r"^Turret_", r"^_", r"_short$"]
            for re_str in re_strs:
                p = re.compile(re_str)
                if p.match(key):
                    skip = True
                    break
            if skip:
                continue

            userStrs[key] = tank_strs[tank_str]

        # sorting
        tankopedia_sorted = OrderedDict()
        for tank_id in sorted(tankopedia.keys(), key=int):
            tankopedia_sorted[str(tank_id)] = tankopedia[str(tank_id)]

        userStrs_sorted = OrderedDict()
        for userStr in sorted(userStrs.keys()):
            userStrs_sorted[userStr] = userStrs[userStr]
        # debug('Tank strings: ' + str(len(userStrs_sorted)))

    except Exception as err:
        error(err)
        sys.exit(1)

    return tankopedia_sorted, userStrs_sorted


def mk_tank_id(nation: EnumNation, tank_id: int) -> int:
    return (tank_id << 8) + (nation.value << 4) + 1


def read_tank_type(tagstr: str) -> EnumVehicleTypeStr:
    tags: set[str] = set(tagstr.split(" "))
    for tank_type in EnumVehicleTypeStr:
        if tank_type.value in tags:
            return tank_type
    raise ValueError(f"No known tank type found from 'tags' field: {tagstr}")


### main()
if __name__ == "__main__":
    # To avoid 'Event loop is closed' RuntimeError due to compatibility issue with aiohttp
    if sys.platform.startswith("win") and sys.version_info >= (3, 8):
        try:
            from asyncio import WindowsSelectorEventLoopPolicy
        except ImportError:
            pass
        else:
            if not isinstance(get_event_loop_policy(), WindowsSelectorEventLoopPolicy):
                set_event_loop_policy(WindowsSelectorEventLoopPolicy())
    run(main())

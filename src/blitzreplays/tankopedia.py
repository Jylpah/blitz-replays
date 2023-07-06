from argparse import ArgumentParser, Namespace, SUPPRESS
from configparser import ConfigParser
from datetime import datetime
from typing import Optional, Literal, Any, cast
from asyncio import Task, TaskGroup, create_task, gather
from os.path import isdir, isfile, exists
from pathlib import Path
from sortedcollections import SortedDict  # type: ignore
from pydantic import ValidationError
from aiofiles import open
import logging


from blitzutils import Region, EnumNation, EnumVehicleTier, EnumVehicleTypeInt, EnumVehicleTypeStr
from blitzutils import WGTank, WGApiTankopedia

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
        TANKS_FILE: str = "tanks.json"

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

        if config is not None and "METADATA" in config:
            configOptions = config["METADATA"]
            TANKS_FILE = configOptions.get("tankopedia_json", TANKS_FILE)

        parser.add_argument(
            "--outfile",
            type=str,
            default=TANKS_FILE,
            nargs="?",
            metavar="TANKOPEDIA",
            help="Write Tankopedia to file",
        )
        parser.add_argument("-u", "--update", action="store_true", help="Update Tankopedia")
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
            "blitz_app_dir", type=str, default=BLITZAPP_DIR, metavar="BLTIZ_APP_DIR", help="Read Tankopedia from file"
        )
    except Exception as err:
        error(f"could not add arguments: {err}")
        return False
    return True


def add_args_file(parser: ArgumentParser, config: Optional[ConfigParser] = None) -> bool:
    debug("starting")
    parser.add_argument("file", type=str, metavar="FILE", help="Read Tankopedia from file")
    return True


def add_args_wg(parser: ArgumentParser, config: Optional[ConfigParser] = None) -> bool:
    debug("starting")
    try:
        parser.add_argument(
            "server",
            default="eu",
            nargs="?",
            choices=list(Region.API_regions()),
            metavar="SERVER",
            help="Raed Tankopedia from file",
        )
    except Exception as err:
        error(f"could not add arguments: {err}")
        return False
    return True


###########################################
#
# cmd_ functions
#
###########################################


async def cmd(args: Namespace) -> bool:
    try:
        debug("starting")
        if args.tankopedia_cmd == "app":
            return await cmd_app(args)

        elif args.tankopedia_cmd == "file":
            return await cmd_file(args)

        elif args.tankopedia_cmd == "wg":
            return await cmd_wg(args)
        else:
            raise NotImplementedError(f"unknown command: {args.tankopedia_cmd}")

    except Exception as err:
        error(f"{err}")
    return False


async def cmd_app(args: Namespace) -> bool:
    debug("starting")
    tasks: list[Task] = []
    for nation in EnumNation:
        tasks.append(create_task(extract_tanks(args.blitz_app_dir, nation)))

    tanks: list[WGTank] = list()
    # user_strs: dict[int, str] = dict()
    for nation_tanks in await gather(*tasks):
        # user_strs.update(nation_user_strs)
        tanks.extend(nation_tanks)

    tank_strs, map_strs = await read_user_strs(args.blitz_app_dir)

    tankopedia = WGApiTankopedia()

    ## CONTINUE:
    # - add WGApiWoTBlitz.read(Path or filename)
    # - Create separate model for user strings

    tankopedia = WGApiTankopedia()
    if exists(args.tanks):
        try:
            tankopedia = WGApiTankopedia.parse_file(args.tanks)
        except ValidationError as err:
            pass

    async with open(args.tanks, "w", encoding="utf8") as outfile:
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

    return False


async def cmd_file(args: Namespace) -> bool:
    return False


async def cmd_wg(args: Namespace) -> bool:
    return False


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

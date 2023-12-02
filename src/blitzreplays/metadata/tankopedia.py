import configparser
from datetime import datetime
from typing import Optional, Any, Annotated

# from typing_extensions import Annotated
from asyncio import Task, create_task, gather, run
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

# import click
import sys
import typer

from blitzutils import (
    Region,
    EnumNation,
    EnumVehicleTier,
    EnumVehicleTypeInt,
    EnumVehicleTypeStr,
    Tank,
    WGApiWoTBlitzTankopedia,
    WGApi,
    WoTBlitzTankString,
    add_args_wg,
)
from dvplc import decode_dvpl, decode_dvpl_file
from pyutils.utils import get_temp_filename, coro, set_config
from pyutils import AsyncTyper

typer_app = AsyncTyper()

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

TANKOPEDIA: str = "tanks.json"
WG_APP_ID: str = "d6d03acb6bee0e9f361b6e02e1780b56"
WG_REGION: Region = Region.eu

BLITZAPP_STRINGS: str = "Data/Strings/en.yaml"
BLITZAPP_VEHICLES_DIR: str = "Data/XML/item_defs/vehicles/"
BLITZAPP_VEHICLE_FILE: str = "list.xml"


###########################################
#
# tankopedia
#
###########################################


# @click.group(help="extract tankopedia as JSON file for other tools")
# @click.option(
#     "-f",
#     "--force",
#     flag_value=True,
#     default=False,
#     help="Overwrite Tankopedia instead of updating it",
# )
# @click.option(
#     "--outfile",
#     type=click.Path(path_type=str),
#     default=None,
#     help=f"Write Tankopedia to file (default: {TANKOPEDIA})",
# )
# @click.pass_context


## app.callback() ??
@typer_app.callback()
def tankopedia(
    ctx: typer.Context,
    # force: bool = False,
    outfile: Annotated[
        Optional[str],
        typer.Option(help=f"Write Tankopedia to FILE", metavar="FILE"),
    ] = None,
) -> None:
    """
    extract tankopedia as JSON file for other tools
    """
    debug("starting")
    config: configparser.ConfigParser = ctx.obj["config"]
    set_config(
        config,
        TANKOPEDIA,
        "METADATA",
        "tankopedia_json",
        outfile,
    )


########################################################
#
# tankopedia app
#
########################################################


@typer_app.async_command()
async def app(
    ctx: typer.Context,
    wg_app_id: Annotated[
        Optional[str], typer.Option(show_default=False, help="WG app ID")
    ] = None,
    wg_region: Annotated[
        Optional[Region],
        typer.Option(
            help=f"WG API region", metavar="[eu|asia|com]", show_default=False
        ),
    ] = None,
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
    extract Tankopedia from Blitz game files
    """
    debug("starting")
    try:
        config: configparser.ConfigParser = ctx.obj["config"]
        wg_app_id = set_config(config, WG_APP_ID, "WG", "app_id", wg_app_id)
        region: Region
        if wg_region is None:
            region = Region(
                set_config(config, WG_REGION.value, "WG", "default_region", None)
            )
        else:
            region = wg_region
        outfile: Path = Path(config.get("METADATA", "tankopedia_json"))
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
    #     run(
    #         run_app(
    #             blitz_app_dir=blitz_app_dir, region=region, outfile=outfile, force=force
    #         )
    #     )

    # async def run_app(
    #     blitz_app_dir: Path, region: Region, outfile: Path, force: bool = False
    # ):
    tasks: list[Task] = []
    try:
        if (blitz_app_dir / "assets").is_dir():
            # WG has changed the location of Data directory - at least in steam client
            blitz_app_dir = blitz_app_dir / "assets"
        debug("base dir for game files: %s", str(blitz_app_dir))

        for nation in EnumNation:
            tasks.append(create_task(extract_tanks(blitz_app_dir, nation)))

        tanks: list[Tank] = list()
        # user_strs: dict[int, str] = dict()
        for nation_tanks in await gather(*tasks):
            tanks.extend(nation_tanks)

        tank_strs: dict[str, str] = await read_tank_strs(blitz_app_dir)
        tankopedia = WGApiWoTBlitzTankopedia()

        tanks_ok: list[Tank]
        tanks_nok: list[Tank]
        tanks_ok, tanks_nok = convert_tank_names(tanks, tank_strs)
        for tank in tanks_ok:
            tankopedia.add(tank)

        async with WGApi(default_region=region, rate_limit=0) as wg:
            _re_tank: Pattern = compile("^#\\w+?_vehicles:")
            for tank in tanks_nok:
                if (
                    tank.code is not None
                    and (tank_str := await wg.get_tank_str(tank.code)) is not None
                ):
                    tank.name = tank_str.user_string
                    if _re_tank.match(tank.name):
                        tank.name = tank.code
                else:
                    error(f"could not fetch tank name for tank_id={tank.tank_id}")
                tankopedia.add(tank)
        await update_tankopedia(outfile=outfile, tankopedia=tankopedia, force=force)

    except Exception as err:
        error(err)
        sys.exit(2)


########################################################
#
# tankopedia wg-api
#
########################################################


@typer_app.async_command()
async def wg(
    ctx: typer.Context,
    wg_app_id: Annotated[Optional[str], typer.Option(help="WG app ID")] = None,
    wg_region: Annotated[
        Optional[Region], typer.Option(help=f"WG API region (default: {WG_REGION})")
    ] = None,
):
    """
    get Tankopedia from WG API
    """
    debug(f"starting: wg_app_id={wg_app_id} wg_region={wg_region}")
    try:
        config: configparser.ConfigParser = ctx.obj["config"]
        wg_app_id = set_config(config, WG_APP_ID, "WG", "app_id", wg_app_id)
        region: Region
        if wg_region is None:
            region = Region(set_config(config, WG_REGION, "WG", "default_region", None))
        else:
            region = wg_region
        outfile: Path = Path(config.get("METADATA", "tankopedia_json"))

        force: bool = ctx.obj["force"]

    except configparser.Error as err:
        error(f"could not read config file: {type(err)}: {err}")
        sys.exit(1)
    except Exception as err:
        error(f"{type(err)}: {err}")
        sys.exit(1)

    async with WGApi(app_id=wg_app_id) as wg:
        if (tankopedia := await wg.get_tankopedia(region=region)) is not None:
            await update_tankopedia(outfile=outfile, tankopedia=tankopedia, force=force)
        else:
            error(f"could not read Tankopedia from WG API ({region} server)")


########################################################
#
# tankopedia file
#
########################################################


@typer_app.async_command()
async def file(
    ctx: typer.Context,
    infile: Annotated[
        Path,
        typer.Argument(
            show_default=False, dir_okay=False, help="read Tankopedia from file"
        ),
    ],
):
    """Read tankopedia from a file"""
    debug("starting")
    try:
        config: configparser.ConfigParser = ctx.obj["config"]
        outfile: Path = Path(config.get("METADATA", "tankopedia_json"))
        force: bool = ctx.obj["force"]
    except configparser.Error as err:
        error(f"could not read config file: {type(err)}: {err}")
        sys.exit(1)
    except Exception as err:
        error(f"{type(err)}: {err}")
        sys.exit(1)

    if (tankopedia := await WGApiWoTBlitzTankopedia.open_json(infile)) is not None:
        await update_tankopedia(outfile=outfile, tankopedia=tankopedia, force=force)
    else:
        error(f"could not read Tankopedia from {infile}")


async def update_tankopedia(
    outfile: Path, tankopedia: WGApiWoTBlitzTankopedia, force: bool = False
) -> bool:
    """Update Tankopedia JSON file with new tankopedia"""
    if not force and outfile.is_file():
        if (tankopedia_old := await WGApiWoTBlitzTankopedia.open_json(outfile)) is None:
            error(f"could not parse old tankopedia: {outfile}")
            return False
    else:
        tankopedia_old = WGApiWoTBlitzTankopedia()

    added: set[int]
    updated: set[int]
    (added, updated) = tankopedia_old.update(tankopedia)

    if await tankopedia_old.save_json(outfile) > 0:
        if logger.level < logging.WARNING:
            for tank_id in added:
                verbose(f"added:   tank_id={tank_id:<5} {tankopedia_old[tank_id].name}")

        if logger.level < logging.WARNING:
            for tank_id in updated:
                verbose(f"updated: tank_id={tank_id:<5} {tankopedia_old[tank_id].name}")

        message(f"added {len(added)} and updated {len(updated)} tanks to Tankopedia")
        message(f"saved {len(tankopedia_old)} tanks to Tankopedia ({outfile})")
        return True
    else:
        error(f"writing Tankopedia failed: {outfile}")
        return False


def extract_tanks_xml(tankopedia: dict[str, Any], nation: EnumNation) -> list[Tank]:
    """Extract tanks from a parsed XML"""
    tanks: list[Tank] = list()
    for data in tankopedia["root"].keys():
        try:
            tank_xml: dict[str, Any] = tankopedia["root"][data]
            debug(f"reading tank: {tank_xml}")
            tank = Tank(tank_id=mk_tank_id(nation, int(tank_xml["id"])), nation=nation)
            tank.is_premium = issubclass(type(tank_xml["price"]), dict)
            tank.tier = EnumVehicleTier(int(tank_xml["level"]))
            tank.type = read_tank_type(tank_xml["tags"])
            tank.code = tank_xml["userString"]  # Need to be converted later
            tanks.append(tank)
            debug("Read tank_id=%d", tank.tank_id)
        except KeyError as err:
            error("Failed to read item=%s: %s", data, str(err))
        except Exception as err:
            error("Failed to read item=%s: %s", data, str(err))
    return tanks


async def extract_tanks(blitz_app_dir: Path, nation: EnumNation) -> list[Tank]:
    """Extract tanks from BLITZAPP_VEHICLE_FILE 'list.xml' file for a nation"""

    tanks: list[Tank] = list()
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
            if not await decode_dvpl_file(filename, temp_fn):
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
    tanks: list[Tank], tank_strs: dict[str, str]
) -> tuple[list[Tank], list[Tank]]:
    """Convert tank names for Tankopedia based on tank user strings in /Data/Strings/en.yaml
    Returns 2 lists: converted, not_converted"""
    debug("starting")

    converted: list[Tank] = list()
    not_converted: list[Tank] = list()

    for tank in tanks:
        try:
            if tank.code in tank_strs:
                tank.name = tank_strs[tank.code]
                tank.code = tank.code.split(":")[1]
                converted.append(tank)
            elif tank.code is not None:
                tank.code = tank.code.split(":")[1]
                tank.name = tank.code
                not_converted.append(tank)
            else:
                error(f"no name defined for tank_id={tank.tank_id}: {tank.name}")
        except KeyError as err:
            error(f"could not convert name tank_id={tank.tank_id}: {tank.name}: {err}")
        except IndexError as err:
            error(
                f"extracting tank code from user string failed: tank_id={tank.tank_id}, {tank.code}: {err}"
            )

    return converted, not_converted


def mk_tank_id(nation: EnumNation, tank_id: int) -> int:
    return (tank_id << 8) + (nation.value << 4) + 1


def read_tank_type(tagstr: str) -> EnumVehicleTypeStr:
    tags: set[str] = set(tagstr.split(" "))
    for tank_type in EnumVehicleTypeStr:
        if tank_type.value in tags:
            return tank_type
    raise ValueError(f"No known tank type found from 'tags' field: {tagstr}")


if __name__ == "__main__":
    typer_app()

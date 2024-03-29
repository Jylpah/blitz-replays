import asyncio
import pytest  # type: ignore
from os.path import dirname, realpath
from pathlib import Path
from typer.testing import CliRunner
from click.testing import Result
import logging

from blitzmodels import Maps, WGApiWoTBlitzTankopedia

from blitzreplays.blitzdata import app


logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug


########################################################
#
# Test Plan
#
########################################################

# EnumVehicleTypeInt/Str
# 1) tankopedia app | file
# 2) tankopedia --update wg
# 2) map app | file
########################################################
#
# Fixtures
#
########################################################


@pytest.fixture
def enum_vehicle_type_names() -> list[str]:
    return ["light_tank", "medium_tank", "heavy_tank", "tank_destroyer"]


@pytest.fixture
def enum_vehicle_type_str_values() -> list[str]:
    return ["lightTank", "mediumTank", "heavyTank", "AT-SPG"]


@pytest.fixture
def enum_vehicle_tier() -> list[str]:
    return ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


@pytest.fixture
def enum_nation() -> list[str]:
    return [
        "ussr",
        "germany",
        "usa",
        "china",
        "france",
        "uk",
        "japan",
        "other",
        "european",
    ]


@pytest.fixture
def tankopedia_tanks() -> int:
    return 533  # number of tanks in the 01_Tankopedia.json


FIXTURE_DIR = Path(dirname(realpath(__file__)))

BLITZ_APP_DIR: str = "BlitzApp"
TANKOPEDIA_NEW: str = "01_Tankopedia_new.json"
TANKOPEDIA_OLD: str = "01_Tankopedia_old.json"

TANKOPEDIA_FILES = pytest.mark.datafiles(
    FIXTURE_DIR / TANKOPEDIA_OLD,  # 533 tanks
    FIXTURE_DIR / BLITZ_APP_DIR,  # 609 tanks
    FIXTURE_DIR / TANKOPEDIA_NEW,  # 609 tanks
    keep_top_dir=True,
)

MAPS_NEW: str = "02_maps_new.json"
MAPS_OLD: str = "02_maps_old.json"

MAPS_FILES = pytest.mark.datafiles(
    FIXTURE_DIR / MAPS_NEW,  # 57 maps
    FIXTURE_DIR / BLITZ_APP_DIR,  # 59 maps
    FIXTURE_DIR / MAPS_OLD,  # 54 maps
    keep_top_dir=True,
)

########################################################
#
# Tests
#
########################################################


@pytest.mark.parametrize(
    "args,added,updated",
    [
        (["app", BLITZ_APP_DIR], 609, 0),
        (["file", TANKOPEDIA_NEW], 609, 0),
    ],
)
@TANKOPEDIA_FILES
def test_1_blitzdata_tankopedia(
    tmp_path: Path, datafiles: Path, args: list[str], added: int, updated: int
) -> None:
    OUTFILE: str = f'{tmp_path / "test_1_tankopedia.json"}'
    cmd: str = args[0]
    args[-1] = f"{(tmp_path / args[-1]).resolve()}"

    result: Result = CliRunner().invoke(
        app, ["--force", "tankopedia", "--outfile", OUTFILE, *args]
    )
    assert result.exit_code == 0, f"blitzdata tankopedia {cmd} failed"

    assert (
        tankopedia := asyncio.run(WGApiWoTBlitzTankopedia.open_json(OUTFILE))
    ) is not None, f"could not open results: tankopedia {cmd}"

    assert len(tankopedia) == added, f"incorrect number of tanks: tankopedia {cmd}"


@pytest.mark.parametrize(
    "args,total,added",
    [
        (["app", BLITZ_APP_DIR], 609, 76),
        (["file", TANKOPEDIA_NEW], 609, 76),
    ],
)
@TANKOPEDIA_FILES
def test_2_blitzdata_tankopedia_update(
    tmp_path: Path, datafiles: Path, args: list[str], total: int, added: int
) -> None:
    OUTFILE: str = f"{tmp_path / TANKOPEDIA_OLD}"
    cmd: str = args[0]
    args[-1] = f"{(tmp_path / args[-1]).resolve()}"

    assert (
        tankopedia := asyncio.run(WGApiWoTBlitzTankopedia.open_json(OUTFILE))
    ) is not None, f"could not open results: tankopedia {cmd}"
    tankopedia_tanks: int = len(tankopedia)
    assert (
        tankopedia_tanks == total - added
    ), "incorrect number of tanks read from existing tankopedia"

    result = CliRunner().invoke(app, ["tankopedia", "--outfile", OUTFILE, *args])
    assert result.exit_code == 0, f"blitzdata tankopedia {cmd} failed"

    assert (
        tankopedia := asyncio.run(WGApiWoTBlitzTankopedia.open_json(OUTFILE))
    ) is not None, f"could not open results: tankopedia {cmd}"

    assert len(tankopedia) == total, f"incorrect number of tanks: tankopedia {cmd}"
    assert (
        len(tankopedia) - tankopedia_tanks == added
    ), f"incorrect number of tanks: tankopedia {cmd}"


def test_3_blitzdata_tankopedia_wg(tmp_path: Path) -> None:
    OUTFILE: str = f"{tmp_path / 'tankopedia-exported.json'}"

    result = CliRunner().invoke(app, ["tankopedia", "--outfile", OUTFILE, "wg"])
    assert result.exit_code == 0, "blitzdata tankopedia wg failed"

    assert (
        tankopedia := asyncio.run(WGApiWoTBlitzTankopedia.open_json(OUTFILE))
    ) is not None, "could not open results: tankopedia wg"

    assert len(tankopedia) > 500, "incorrect number of tanks: tankopedia wg"


############################################
#
# Maps
#
############################################


@pytest.mark.parametrize(
    "args,added,updated",
    [
        (["app", BLITZ_APP_DIR], 52, 0),
        (["file", MAPS_NEW], 52, 0),
        (["file", MAPS_OLD], 49, 0),
    ],
)
@MAPS_FILES
def test_4_blitzdata_maps(
    tmp_path: Path, datafiles: Path, args: list[str], added: int, updated: int
) -> None:
    OUTFILE: str = f'{tmp_path / "test_4_maps.json"}'
    cmd: str = args[0]
    args[-1] = f"{(tmp_path / args[-1]).resolve()}"

    result: Result = CliRunner().invoke(
        app, ["--force", "maps", "--outfile", OUTFILE, *args]
    )
    assert result.exit_code == 0, f"blitzdata maps {cmd} failed"

    assert (
        maps := asyncio.run(Maps.open_json(OUTFILE))
    ) is not None, f"could not open results: maps {cmd}"

    assert len(maps) == added, f"incorrect number of tanks: maps {cmd}"


@pytest.mark.parametrize(
    "args,total,added",
    [
        (["app", BLITZ_APP_DIR], 52, 3),
        (["file", MAPS_NEW], 52, 3),
    ],
)
@MAPS_FILES
def test_5_blitzdata_maps_update(
    tmp_path: Path, datafiles: Path, args: list[str], total: int, added: int
) -> None:
    OUTFILE: str = f"{tmp_path / MAPS_OLD}"
    cmd: str = args[0]
    args[-1] = f"{(tmp_path / args[-1]).resolve()}"

    assert (
        maps := asyncio.run(Maps.open_json(OUTFILE))
    ) is not None, f"could not open results: maps {cmd}"
    maps_N: int = len(maps)
    debug(f"maps_old.json: {maps_N} maps")
    assert maps_N == total - added, "incorrect number of maps read from file"

    result = CliRunner().invoke(app, ["maps", "--outfile", OUTFILE, *args])
    assert result.exit_code == 0, f"blitzdata maps {cmd} failed"

    assert (
        maps := asyncio.run(Maps.open_json(OUTFILE))
    ) is not None, f"could not open results: maps {cmd}"

    debug(f"maps_old.json updated: {len(maps)} maps")
    assert len(maps) == total, f"incorrect number of maps: maps {cmd}"
    assert len(maps) - maps_N == added, f"incorrect number of maps: maps {cmd}"

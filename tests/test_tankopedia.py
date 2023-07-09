import sys
import pytest  # type: ignore
from typing import Sequence
import subprocess
from os.path import dirname, realpath, join as pjoin, basename
from pathlib import Path
import aiofiles
from pydantic import BaseModel
from random import shuffle
import logging

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

sys.path.insert(0, str(Path(__file__).parent.parent.resolve() / "src"))

from blitzutils import (
    WGTank,
    EnumNation,
    EnumVehicleTier,
    EnumVehicleTypeInt,
    EnumVehicleTypeStr,
)
from blitzutils import WGApiTankopedia


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

TANKOPEDIA_FILES = pytest.mark.datafiles(
    FIXTURE_DIR / "01_Tankopedia_old.json",
    FIXTURE_DIR / BLITZ_APP_DIR,
    FIXTURE_DIR / TANKOPEDIA_NEW,
    keep_top_dir=True,
)


########################################################
#
# Tests
#
########################################################


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "args,added,updated",
    [
        (["app", BLITZ_APP_DIR], 609, 0),
        (["file", TANKOPEDIA_NEW], 609, 0),
    ],
)
@TANKOPEDIA_FILES
async def test_1_blitz_data_tankopedia_app(
    tmp_path: Path, datafiles: Path, args: list[str], added: int, updated: int
) -> None:
    OUTFILE: str = f'{tmp_path / "test_1_tankopedia.json"}'
    args[-1] = f"{(tmp_path / args[-1]).resolve()}"

    completed_process = subprocess.run(
        ["python", "blitzdata.py", "tankopedia", "--outfile", OUTFILE] + args
    )
    assert completed_process.returncode == 0, f"blitzdata tankopedia {args[0]} failed"

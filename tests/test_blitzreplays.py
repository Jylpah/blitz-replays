import asyncio
import sys
import pytest  # type: ignore
from typing import Sequence
import subprocess
from os.path import dirname, realpath, join as pjoin, basename
from pathlib import Path
import aiofiles
from typer.testing import CliRunner
from click.testing import Result
from pydantic import BaseModel
from random import shuffle
import logging

# sys.path.insert(0, str(Path(__file__).parent.parent.resolve() / "src"))

from blitzreplays.blitzreplays import app

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

from blitzmodels import Maps, WGApiWoTBlitzTankopedia


########################################################
#
# Test Plan
#
########################################################


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


FIXTURE_DIR = Path(dirname(realpath(__file__)))

REPLAY_FILES = pytest.mark.datafiles(
    FIXTURE_DIR / "20200229_2332__jylpah_E-50_lumber.wotbreplay",
    FIXTURE_DIR / "20200229_2337__jylpah_E-50_skit.wotbreplay",
    on_duplicate="overwrite",
)

TANKOPEDIA: str = "01_Tankopedia_new.json"
TANKOPEDIA_FILE = pytest.mark.datafiles(
    FIXTURE_DIR / TANKOPEDIA,  # 609 tanks
    keep_top_dir=True,
)

MAPS: str = "02_maps_new.json"
MAPS_FILE = pytest.mark.datafiles(
    FIXTURE_DIR / MAPS,  # 58 maps
    keep_top_dir=True,
)


@pytest.fixture
def tankopedia_fn() -> str:
    return TANKOPEDIA


@pytest.fixture
def maps_fn() -> str:
    return MAPS


########################################################
#
# Tests
#
########################################################


@REPLAY_FILES
@TANKOPEDIA_FILE
@MAPS_FILE
def test_1_blitzreplays_upload(
    tmp_path: Path, datafiles: Path, tankopedia_fn: str, maps_fn: str
) -> None:
    result: Result = CliRunner().invoke(
        app,
        [
            "--debug",
            "--tankopedia",
            str(tmp_path.resolve() / tankopedia_fn),
            "--maps",
            str(tmp_path.resolve() / maps_fn),
            "upload",
        ]
        + [
            str(replay)
            for replay in datafiles.iterdir()
            if replay.name.endswith(".wotbreplay")
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"blitzreplays upload failed: {result.output}"

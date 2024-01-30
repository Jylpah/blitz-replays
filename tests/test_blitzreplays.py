import pytest  # type: ignore
from os.path import dirname, realpath
from pathlib import Path
from typer.testing import CliRunner
from click.testing import Result
from typing import List
import logging

from blitzreplays.blitzreplays import app

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
def analyze_dir() -> str:
    """Dir that contains replays to analyze"""
    return "replays-analyze"


FIXTURE_DIR = Path(dirname(realpath(__file__)))

REPLAY_FILES = pytest.mark.datafiles(
    FIXTURE_DIR / "20240101_0124__jylpah_M48A1_49248854089005095.wotbreplay",
    FIXTURE_DIR / "20240106_1649__jylpah_Pl22_CS_59_2318488532804003941.wotbreplay",
    on_duplicate="overwrite",
)

REPLAY_ANALYZE_FILES = pytest.mark.datafiles(
    FIXTURE_DIR / "replays-analyze",
    on_duplicate="overwrite",
    keep_top_dir=True,
)

ANALYZE_CONFIG = pytest.mark.datafiles(
    FIXTURE_DIR / "analyze_config.toml",
    on_duplicate="ignore",
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


@pytest.mark.parametrize(
    "args",
    [
        (["--stats-type", "player", "files", "--export"]),
        (["--stats-type", "tier", "files"]),
        (["--stats-type", "tank", "files"]),
    ],
)
@REPLAY_ANALYZE_FILES
def test_2_blitzreplays_analyze_files(
    tmp_path: Path, datafiles: Path, args: List[str], analyze_dir: str
) -> None:
    result: Result = CliRunner().invoke(
        app,
        ["analyze"] + args + [str(tmp_path / analyze_dir)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"blitzreplays analyze failed: {result.output}"


@pytest.mark.parametrize(
    "args",
    [
        (["--fields", "+extra,tank", "files"]),
        (["--player", "521458531", "files"]),
        (["--reports", "extra", "files"]),
        (
            [
                "--reports",
                "+extra",
                "--fields",
                "+extra",
                "files",
                "--wg-rate-limit",
                "10",
            ]
        ),
    ],
)
@REPLAY_ANALYZE_FILES
def test_3_blitzreplays_analyze(
    tmp_path: Path,
    datafiles: Path,
    args: List[str],
    analyze_dir: str,
) -> None:
    result: Result = CliRunner().invoke(
        app,
        ["analyze"] + args + [str(tmp_path / analyze_dir)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, f"blitzreplays analyze failed: {result.output}"


@pytest.mark.parametrize(
    "args",
    [
        (["fields", "list"]),
        (["fields", "available"]),
        (["reports", "list"]),
        (
            [
                "--analyze-config",
                "analyze_config.toml",
                "--reports",
                "+example",
                "reports",
                "list",
            ]
        ),
    ],
)
@ANALYZE_CONFIG
def test_4_blitzreplays_analyze(
    tmp_path: Path,
    datafiles: Path,
    args: List[str],
    analyze_dir: str,
) -> None:
    result: Result = CliRunner().invoke(
        app,
        ["analyze"] + args,
        catch_exceptions=False,
    )
    assert (
        result.exit_code == 0
    ), f"blitzreplays analyze {' '.join(args)}: {result.output}"

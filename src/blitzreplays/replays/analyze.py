import typer
from typer import Context, Option, Argument
from typing import Annotated, Optional, List, Dict
from asyncio import create_task, Task, sleep
import logging
from pathlib import Path
from configparser import ConfigParser
from alive_progress import alive_bar  # type: ignore
from importlib.resources.abc import Traversable
from importlib.resources import as_file
import importlib
from tomlkit.toml_file import TOMLFile

from tomlkit.items import Item as TOMLItem, Table as TOMLTable
from tomlkit.toml_document import TOMLDocument
from pyutils import FileQueue, EventCounter, AsyncTyper, IterableQueue
from pyutils.utils import set_config
from blitzmodels import (
    WGApiWoTBlitzTankopedia,
    Maps,
    Region,
    WGApi,
)
from blitzmodels.wotinspector.wi_apiv1 import ReplayJSON
from .analyze_models import (
    EnrichedReplay,
    StatsCache,
    AccountId,
    FieldStore,
    Reports,
    Category,
    ValueStore,
)

app = AsyncTyper()

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug


############################################################################################
#
# Defaults
#
############################################################################################

TANKOPEDIA: str = "tanks.json"
WG_APP_ID: str = "d6d03acb6bee0e9f361b6e02e1780b56"
WG_RATE_LIMIT: float = 10.0  # 10/sec
WG_REGION: Region = Region.eu
WG_WORKERS: int = 5
REPLAY_READERS: int = 3


def callback_paths(value: Optional[list[Path]]) -> list[Path]:
    return value if value is not None else []


@app.callback()
def analyze(
    ctx: Context,
    analyze_config_fn: Annotated[
        Optional[str],
        Option(
            "--analyze-config",
            show_default=False,
            help="TOML config file for 'analyze' reports",
        ),
    ] = None,
    fields_param: Annotated[
        str, Option("--fields", help="set report fields, combine field modes with '+'")
    ] = "default",
    reports_param: Annotated[
        str, Option("--reports", help="reports to create. use '+' to add extra reports")
    ] = "default",
) -> None:
    """
    analyze replays
    """
    analyze_config: TOMLDocument | None = None
    field_store = FieldStore()
    reports = Reports()
    try:
        config: ConfigParser = ctx.obj["config"]
        if analyze_config_fn is None:
            def_config: Traversable = importlib.resources.files(
                "blitzreplays.replays"
            ).joinpath("config.toml")  # REFACTOR in Python 3.12
            with as_file(def_config) as default_config:
                analyze_config_fn = set_config(
                    config,
                    str(default_config.resolve()),
                    "REPLAYS",
                    "analyze_config",
                    None,
                )
        analyze_config_file = TOMLFile(analyze_config_fn)
        analyze_config = analyze_config_file.read()

        debug("analyze-config: -------------------------------------------------")
        for key, value in analyze_config.items():
            debug(f"{key} = {value}")
        debug("analyze-config EOF-----------------------------------------------")

        # Create fields
        config_item: TOMLItem | None = None
        if (config_item := analyze_config.item("FIELDS")) is None:
            raise ValueError(
                f"'FIELDS' is not defined in analyze_config file: {analyze_config_fn}"
            )
        if not (isinstance(config_item, TOMLTable)):
            raise ValueError(f"FIELDS is not TOML Table: {type(config_item)}")

        fld: Dict[str, str]
        for field_mode in fields_param.split("+"):
            try:
                for fld in config_item[field_mode].unwrap():
                    debug(
                        ", ".join(
                            ["=".join([key, value]) for key, value in fld.items()]
                        )
                    )  # type: ignore
                    field = field_store.create(**fld)
                    debug(f"field key={field.key}")
            except KeyError:
                error(f"undefined --fields mode: {field_mode}")
                message(
                    f"valid report --fields modes: { ', '.join(mode for mode in config_item.keys())}"
                )
        ctx.obj["fields"] = field_store

        # create reports
        if (config_item := analyze_config.item("REPORTS")) is None:
            raise ValueError(
                f"'REPORTS' is not defined in analyze_config file: {analyze_config_fn}"
            )
        if not (isinstance(config_item, TOMLTable)):
            raise ValueError(f"REPORTS is not TOML Table: {type(config_item)}")

        debug("Reports -------------------------------------------------------")
        report_item: TOMLItem | None = None
        if (report_item := analyze_config.item("REPORT")) is None:
            raise ValueError(
                f"'REPORT' is not defined in analyze_config file: {analyze_config_fn}"
            )
        if not (isinstance(report_item, TOMLTable)):
            raise ValueError(f"REPORT is not TOML Table: {type(report_item)}")

        report_key: str
        for report_list in reports_param.split("+"):
            debug(f"report list={report_list}")
            try:
                if (reports_table := config_item.get(report_list)) is None:
                    error(f"report list not defined: 'REPORTS.{report_list}'")
                    raise KeyError()
                for report_key in reports_table.unwrap():
                    debug(f"report key={report_key}")
                    if (rpt_config := report_item.get(report_key)) is None:
                        error(f"report REPORT.'{report_key}' is not defined")
                        raise KeyError
                    rpt = rpt_config.unwrap()
                    debug(f"adding report: {rpt}")
                    reports.add(key=report_key, **rpt)
            except KeyError:
                error(f"failed to define report list: {report_list}")
        ctx.obj["reports"] = reports
        debug("Reports EOF -----------------------------------------------------")

    except KeyError as err:
        error(f"could not read all the params: {err}")
        typer.Exit(code=1)
        # assert False, "trick Mypy..."
    except Exception as err:
        error(err)
        typer.Exit(code=2)


@app.async_command()
async def db(
    ctx: Context,
    filter: Annotated[
        Optional[List[str]],
        Option(
            "--filter",
            "-f",
            show_default=False,
            help="filter replays based on criteria. Use <, >, = for values and ranges",
        ),
    ] = None,
) -> None:
    """analyze replays from database"""
    error("not implemented yet :-(")
    pass


@app.async_command()
async def files(
    ctx: Context,
    player: Annotated[
        int,
        Option(
            show_default=False,
            help="player to analyze (WG account_id), default: player who recorded the replay",
        ),
    ] = 0,
    wg_app_id: Annotated[Optional[str], Option(help="WG app ID")] = None,
    wg_region: Annotated[
        Optional[Region],
        Option(show_default=False, help=f"WG API region (default: {WG_REGION})"),
    ] = None,
    wg_rate_limit: Annotated[
        Optional[float],
        Option(show_default=False, help="WG API rate limit, default=10/sec"),
    ] = None,
    replays: List[Path] = Argument(help="replays to upload", callback=callback_paths),
) -> None:
    """
    analyze replays from JSON files
    """
    tankopedia: WGApiWoTBlitzTankopedia
    maps: Maps
    try:
        config: ConfigParser = ctx.obj["config"]
        tankopedia = ctx.obj["tankopedia"]
        maps = ctx.obj["maps"]

        wg_app_id = set_config(config, WG_APP_ID, "WG", "app_id", wg_app_id)
        region: Region
        if wg_region is None:
            region = Region(set_config(config, WG_REGION, "WG", "default_region", None))
        else:
            region = wg_region
        wg_rate_limit = set_config(
            config, WG_RATE_LIMIT, "WG", "rate_limit", wg_rate_limit
        )
        player = set_config(config, 0, "WG", "wg_id", player)

    except KeyError as err:
        error(f"could not read all the params: {err}")
        typer.Exit(code=2)
        assert False, "trick Mypy..."

    stats = EventCounter("Upload replays")
    fileQ = FileQueue(filter="*.wotbreplay.json", case_sensitive=False)
    replayQ: IterableQueue[EnrichedReplay] = IterableQueue()
    wg_api = WGApi(app_id=wg_app_id, rate_limit=wg_rate_limit, default_region=region)

    # TODO: add config file reading and set stats types accordingly
    stats_cache: StatsCache = StatsCache(
        wg_api=wg_api, stat_types=["player", "tier"], tankopedia=tankopedia
    )

    create_task(fileQ.mk_queue(replays))
    replay_readers: List[Task] = list()
    api_workers: List[Task] = list()
    for _ in range(REPLAY_READERS):
        replay_readers.append(
            create_task(
                replay_read_worker(
                    fileQ=fileQ,
                    replayQ=replayQ,
                    stats_cache=stats_cache,
                    tankopedia=tankopedia,
                    maps=maps,
                )
            )
        )
    for _ in range(WG_WORKERS):
        api_workers.append(create_task(stats_cache.tank_stats_worker()))

    # replay: EnrichedReplay | None
    count: int = 0
    new: int = 0
    with alive_bar(total=None, title="Reading replays", enrich_print=False) as bar:
        while not fileQ.is_done:
            new = fileQ.count - count
            bar(new)
            count += new
            await sleep(0.5)
    await fileQ.join()  # all replays have been read now
    await stats.gather_stats(replay_readers, merge_child=False)

    ## Fetch stats
    accountQ: IterableQueue[AccountId] = stats_cache.accountQ
    count = accountQ.count
    new = 0
    with alive_bar(
        total=accountQ.qsize() + count,
        title="Fetching player stats",
        enrich_print=False,
    ) as bar:
        bar(count)
        while not accountQ.is_done:
            new = accountQ.count - count
            bar(new)
            count += new
            await sleep(0.5)
    await accountQ.join()
    await stats.gather_stats(api_workers)
    stats_cache.fill_cache()

    fields: FieldStore = ctx.obj["fields"]
    reports: Reports = ctx.obj["reports"]
    await analyze_replays(
        replayQ=replayQ, stats_cache=stats_cache, fields=fields, reports=reports
    )
    reports.print(fields=fields)

    debug(stats.print(do_print=False))


async def analyze_replays(
    replayQ: IterableQueue[EnrichedReplay],
    stats_cache: StatsCache,
    fields: FieldStore,
    reports: Reports,
) -> EventCounter:
    """
    Apply stats to replays and perform analysis
    """
    stats = EventCounter("Analyze")

    async for replay in replayQ:
        try:
            message(f"analyzing replay: {replay.title}")
            stats_cache.add_stats(replay)

            categories: List[Category] = list()
            for report in reports.reports:
                if (cat := report.get_category(replay=replay)) is None:
                    continue
                categories.append(cat)

            for field_key, field in fields.items():
                value: ValueStore = field.calc(replay=replay)
                for cat in categories:
                    cat.record(field=field_key, value=value)
            message("analysis done")
        except Exception as err:
            error(err)
    return stats


async def replay_read_worker(
    fileQ: FileQueue,
    replayQ: IterableQueue[EnrichedReplay],
    stats_cache: StatsCache,
    tankopedia: WGApiWoTBlitzTankopedia,
    maps: Maps,
) -> EventCounter:
    """
    Async worker to read and pre-process replay files
    """
    stats = EventCounter("replay")
    await replayQ.add_producer()
    await stats_cache.accountQ.add_producer()
    async for fn in fileQ:
        replay: EnrichedReplay | None = None
        try:
            if (
                replay := await EnrichedReplay.open_json(await fileQ.get())
            ) is not None:
                stats.log("replays read")
            elif (
                old_replay := await ReplayJSON.open_json(await fileQ.get())
            ) is not None:
                stats.log("replays read (v1)")
                debug(f"converting old replay file format: {fn}")
                if (
                    replay := EnrichedReplay.from_obj(old_replay, in_type=ReplayJSON)
                ) is None:
                    error(
                        f"""could not convert replay to the v2 format: {fn}
                            please re-fetch the replay JSON file with 'blitz-replays update'"""
                    )
                    stats.log("replay conversion errors")
                    raise ValueError()
        except Exception as err:
            error(f"could not read replay: {fn}: {type(err)}: {err}")
            stats.log("errors")
            continue
        try:
            if replay is not None:
                await replay.enrich(tankopedia=tankopedia, maps=maps)
                await stats_cache.fetch_stats(replay)
                await replayQ.put(replay)
            else:
                stats.log("read replay errors")
                raise ValueError()
        except Exception as err:
            error(f"could not enrich replay: {fn}: {type(err)}: {err}")
            stats.log("errors")

    await replayQ.finish()
    await stats_cache.accountQ.finish()
    return stats

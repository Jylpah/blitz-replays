import typer
from typer import Context, Option, Argument
from typing import Annotated, Optional, List, Dict, Final, Tuple, Literal
from asyncio import create_task, Task, sleep
import logging
from pathlib import Path
from configparser import ConfigParser
from alive_progress import alive_bar  # type: ignore
from result import is_ok, is_err, Result, Err, Ok

from importlib.resources.abc import Traversable
from importlib.resources import as_file
import importlib

from tomlkit.toml_file import TOMLFile
from tomlkit.items import Item as TOMLItem, Table as TOMLTable
from tomlkit.toml_document import TOMLDocument

from pyutils import FileQueue, EventCounter, AsyncTyper, IterableQueue
from pyutils.utils import set_config
from blitzmodels import (
    AccountId,
    Maps,
    Region,
    WGApi,
    WGApiWoTBlitzTankopedia,
)
# from blitzmodels.wotinspector.wi_apiv1 import ReplayJSON

from .args import EnumStatsTypes
from .models_reports import (
    Category,
    EnrichedReplay,
    FieldStore,
    Reports,
    ValueStore,
)
from .cache import (
    QueryCache,
    StatsCache,
    StatsType,
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
DEFAULT_STATS_TYPE: Final[str] = "player"
TANKOPEDIA: str = "tanks.json"
WG_APP_ID: str = "d6d03acb6bee0e9f361b6e02e1780b56"
WG_RATE_LIMIT: float = 10.0  # 10/sec
WG_REGION: Region = Region.eu
WG_WORKERS: int = 5
REPLAY_READERS: int = 3

REPORTS_DEFAULT: str = "default"
FIELDS_DEFAULT: str = "default"


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
    stats_type_param: Annotated[
        Optional[EnumStatsTypes],
        Option("--stats-type", help="stats to use for player stats"),
    ] = None,
    fields_param: Annotated[
        Optional[str],
        Option("--fields", help="set report fields, combine field modes with '+'"),
    ] = None,
    reports_param: Annotated[
        Optional[str],
        Option("--reports", help="reports to create. use '+' to add extra reports"),
    ] = None,
    player: Annotated[
        Optional[int],
        Option(
            "--player",
            show_default=False,
            help="player to analyze (WG account_id), default: player who recorded the replay",
        ),
    ] = None,
) -> None:
    """
    analyze replays
    """
    fields = FieldStore()
    reports = Reports()
    try:
        config: ConfigParser = ctx.obj["config"]
        ctx.obj["player"] = set_config(
            config, fallback=0, section="WG", option="wg_id", value=player
        )

        if stats_type_param is None:
            stats_type = set_config(
                config, DEFAULT_STATS_TYPE, "REPLAYS_ANALYZE", "stats_type", None
            )
            try:
                stats_type_param = EnumStatsTypes[stats_type]
            except Exception as err:
                error(err)
                raise ValueError(
                    f"invalid config file setting for 'stats_type': {stats_type}"
                )
        debug("--stats-type=%s", stats_type_param.value)
        ctx.obj["stats_type"] = stats_type_param.value
    except KeyError as err:
        error("%s: %s", type(err), err)
        typer.Exit(code=1)
        raise SystemExit

    try:
        # TODO: default_report .ini config param ?
        fields_param = set_config(
            config, FIELDS_DEFAULT, "REPLAYS_ANALYZE", "fields", fields_param
        )
        reports_param = set_config(
            config, REPORTS_DEFAULT, "REPLAYS_ANALYZE", "reports", reports_param
        )

        def_config: Traversable = importlib.resources.files(
            "blitzreplays.replays"
        ).joinpath("config.toml")  # REFACTOR in Python 3.12
        with as_file(def_config) as config_fn:
            if isinstance(
                res_reports := read_analyze_config(
                    config_fn, fields=fields_param, reports=reports_param
                ),
                Ok,
            ):
                reports, fields = res_reports.ok_value
            else:
                error(res_reports.err_value)
                typer.Exit(code=1)
                raise SystemExit
    except Exception as err:
        error(f"could not read default analyze: {type(err)}: {err}")
        typer.Exit(code=1)
        raise SystemExit

    try:
        NO_ANALYZE_CONFIG = Literal["__NO_ANALYZE_CONFIG__"]
        analyze_config_fn = set_config(
            config,
            "__NO_ANALYZE_CONFIG__",
            "REPLAYS",
            "analyze_config",
            analyze_config_fn,
        )
        if analyze_config_fn != NO_ANALYZE_CONFIG:
            if isinstance(
                res_reports := read_analyze_config(
                    Path(analyze_config_fn), fields=fields_param, reports=reports_param
                ),
                Ok,
            ):
                user_reports, user_fields = res_reports.ok_value
                reports.update(user_reports)
                fields.update(user_fields)

            else:
                debug(res_reports.err_value)

        ctx.obj["reports"] = reports
        ctx.obj["fields"] = fields

    except Exception as err:
        error(f"could not parse analyze TOML config file: {type(err)} {err}")
        typer.Exit(code=2)


# @app.async_command()
# async def db(
#     ctx: Context,
#     filter: Annotated[
#         Optional[List[str]],
#         Option(
#             "--filter",
#             "-f",
#             show_default=False,
#             help="filter replays based on criteria. Use <, >, = for values and ranges",
#         ),
#     ] = None,
# ) -> None:
#     """analyze replays from database"""
#     error("not implemented yet :-(")
#     pass


@app.async_command()
async def files(
    ctx: Context,
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
    stats_type: StatsType
    player: int

    try:
        config: ConfigParser = ctx.obj["config"]
        tankopedia = ctx.obj["tankopedia"]
        maps = ctx.obj["maps"]
        stats_type = ctx.obj["stats_type"]
        player = ctx.obj["player"]
        wg_app_id = set_config(config, WG_APP_ID, "WG", "app_id", wg_app_id)
        region: Region
        if wg_region is None:
            region = Region(set_config(config, WG_REGION, "WG", "default_region", None))
        else:
            region = wg_region
        wg_rate_limit = set_config(
            config, WG_RATE_LIMIT, "WG", "rate_limit", wg_rate_limit
        )

    except KeyError as err:
        error(f"could not read all the arguments: {err}")
        typer.Exit(code=3)
        assert False, "trick Mypy..."

    stats = EventCounter("Analyze replays")
    fileQ = FileQueue(filter="*.wotbreplay.json", case_sensitive=False)
    replayQ: IterableQueue[EnrichedReplay] = IterableQueue()
    accountQ: IterableQueue[AccountId] = IterableQueue()

    wg_api = WGApi(app_id=wg_app_id, rate_limit=wg_rate_limit, default_region=region)
    query_cache = QueryCache()
    # TODO: add config file reading and set stats types accordingly
    stats_cache: StatsCache = StatsCache(
        wg_api=wg_api, stats_type=stats_type, tankopedia=tankopedia
    )
    replay_readers: List[Task] = list()
    api_workers: List[Task] = list()
    try:
        create_task(fileQ.mk_queue(replays))
        for _ in range(REPLAY_READERS):
            replay_readers.append(
                create_task(
                    replay_read_worker(
                        fileQ=fileQ,
                        replayQ=replayQ,
                        accountQ=accountQ,
                        query_cache=query_cache,
                        stats_cache=stats_cache,
                        tankopedia=tankopedia,
                        maps=maps,
                        player=player,
                    )
                )
            )
        for _ in range(WG_WORKERS):
            api_workers.append(create_task(stats_cache.stats_worker(accountQ=accountQ)))

        # replay: EnrichedReplay | None
        count: int = 0
        new: int = 0
        with alive_bar(total=None, title="Reading replays", enrich_print=False) as bar:
            while not fileQ.is_done:
                new = fileQ.count - count
                if new > 0:
                    bar(new)
                count += new
                await sleep(0.5)
            if (new := fileQ.count - count) > 0:
                bar(new)
        await fileQ.join()  # all replays have been read now
        verbose(f"replays found: {fileQ.count}")
        if fileQ.count == 0:
            error("no replays found")
            raise SystemExit

        await stats.gather_stats(replay_readers)

        ## Fetch stats
        # accountQ: IterableQueue[AccountId] = stats_cache.accountQ
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
        stats_cache.fill_cache(query_cache)

        fields: FieldStore = ctx.obj["fields"]
        reports: Reports = ctx.obj["reports"]
        await analyze_replays(
            replayQ=replayQ,
            stats_cache=stats_cache,
            fields=fields,
            reports=reports,
            player=player,
        )
        reports.print(fields=fields)
        print()
        verbose(stats.print(do_print=False))
    except SystemExit:
        debug("canceling workers... ")
        for task in replay_readers + api_workers:
            task.cancel()

    except Exception as err:
        error(f"{type(err)}: {err}")
    finally:
        await wg_api.close()


def read_analyze_config(
    filename: Path, fields: str, reports: str
) -> Result[Tuple[Reports, FieldStore], str]:
    """
    Read analyze config TOML file
    """
    # TODO: move TOML file reading into a separate function
    # TODO: merge / update default config with user config (verbose(default config overwritten))
    # TODO: default_report .ini config param ?

    try:
        if filename is None:
            return Err("no TOML config file given")
        config_file = TOMLFile(filename)
        config: TOMLDocument | None = None

        if (config := config_file.read()) is None:
            return Err(f"could not read analyze TOML config file: {filename}")

        if isinstance(res_fields := read_analyze_fields(config, fields), Err):
            return Err(f"could not read FIELDS from analyze config file {filename}")

        if isinstance(res_reports := read_analyze_reports(config, reports), Err):
            return Err(f"could not read REPORTS from analyze config file {filename}")

        return Ok((res_reports.ok_value, res_fields.ok_value))
    except Exception as err:
        return Err(str(err))


def read_analyze_reports(config: TOMLDocument, reports: str) -> Result[Reports, str]:
    """
    read REPORT config from analyze TOML config
    """

    config_item: TOMLItem | None = None
    if (config_item := config.item("REPORTS")) is None:
        return Err("'REPORTS' is not defined in analyze_config file")
    if not (isinstance(config_item, TOMLTable)):
        return Err(f"REPORTS is not a TOML Table: {type(config_item)}")

    report_store = Reports()
    debug("Reports -------------------------------------------------------")
    report_item: TOMLItem | None = None
    if (report_item := config.item("REPORT")) is None:
        return Err("'REPORT' is not defined in analyze_config file")
    if not (isinstance(report_item, TOMLTable)):
        return Err(f"REPORT is not TOML Table: {type(report_item)}")

    # '+' appends to default reports
    if reports.startswith("+"):
        reports = f"default,{reports[1:]}"
    report_key: str
    for report_list in reports.split(","):
        debug("report list=%s", report_list)
        try:
            if (reports_table := config_item.get(report_list)) is None:
                error("report list not defined: 'REPORTS.%s'", report_list)
                raise KeyError()
            for report_key in reports_table.unwrap():
                debug("report key=%s", report_key)
                if (rpt_config := report_item.get(report_key)) is None:
                    error("report 'REPORT.%s' is not defined", report_key)
                    raise KeyError
                rpt = rpt_config.unwrap()
                debug("adding report: %s", str(rpt))
                report_store.add(key=report_key, **rpt)
        except KeyError:
            error(f"failed to define report list: {report_list}")
    if len(report_store) == 0:
        debug(f"no reports defined: {reports}")
    return Ok(report_store)


def read_analyze_fields(config: TOMLDocument, fields: str) -> Result[FieldStore, str]:
    """
    Read FIELD config from analyze TOML config
    """

    config_item: TOMLItem | None = None
    if (config_item := config.item("FIELDS")) is None:
        return Err("'FIELDS' is not defined in analyze_config file")
    if not (isinstance(config_item, TOMLTable)):
        return Err(f"FIELDS is not TOML Table: {type(config_item)}")

    if (fields_item := config.item("FIELD")) is None:
        return Err("'FIELD' is not defined in analyze_config file")
    if not (isinstance(fields_item, TOMLTable)):
        return Err(f"FIELD is not TOML Table: {type(fields_item)}")

    field_store = FieldStore()
    fld: Dict[str, str]

    # append field set to the
    if fields.startswith("+"):
        fields = f"default,{fields[1:]}"
    field_key: str
    for field_list in fields.split(","):
        debug("FIELDS.%s", field_list)
        try:
            if (fields_table := config_item.get(field_list)) is None:
                error("field list not defined: 'FIELDS.%s'", field_list)
                raise KeyError()
            for field_key in fields_table.unwrap():
                debug("field key=%s", field_key)
                # for fld in config_item[field_mode].unwrap():
                if (fld_config := fields_item.get(field_key)) is None:
                    error("field 'FIELD.%s' is not defined", field_key)
                    raise KeyError
                fld = fld_config.unwrap()
                debug("adding FIELD: %s", str(fld))
                field_store.create(**fld)

        except KeyError:
            error(f"undefined --fields mode: {field_list}")
            message(
                f"valid report --fields modes: { ', '.join(mode for mode in config_item.keys())}"
            )
    return Ok(field_store)


async def analyze_replays(
    replayQ: IterableQueue[EnrichedReplay],
    stats_cache: StatsCache,
    fields: FieldStore,
    reports: Reports,
    player: int = 0,
) -> EventCounter:
    """
    Apply stats to replays and perform analysis
    """
    stats = EventCounter("Analyze")

    async for replay in replayQ:
        try:
            debug("analyzing replay: %s", replay.title)
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
            debug("analysis done")
        except Exception as err:
            error(err)
    return stats


async def replay_read_worker(
    fileQ: FileQueue,
    replayQ: IterableQueue[EnrichedReplay],
    accountQ: IterableQueue[AccountId],
    query_cache: QueryCache,
    stats_cache: StatsCache,
    tankopedia: WGApiWoTBlitzTankopedia,
    maps: Maps,
    player: int = 0,
) -> EventCounter:
    """
    Async worker to read and pre-process replay files
    """
    stats = EventCounter("replays")
    await replayQ.add_producer()
    await accountQ.add_producer()
    async for fn in fileQ:
        replay: EnrichedReplay | None = None
        try:
            stats.log("found")
            if (replay := await EnrichedReplay.open_json(fn)) is None:
                # elif (old_replay := await ReplayJSON.open_json(fn)) is not None:
                #     stats.log("read (v1)")
                #     debug(f"converting old replay file format: {fn}")
                #     if (
                #         replay := EnrichedReplay.from_obj(old_replay, in_type=ReplayJSON)
                #     ) is None:
                #         message(
                #             f"""ERROR: could not convert replay to the v2 format: {fn.name}
                #                 please re-fetch the replay JSON file with 'blitz-replays upload --force'"""
                #         )
                #         stats.log("conversion errors")
                #         raise ValueError()
                message(f"ERROR: could not read replay: {fn.name}")
                stats.log("errors")
                continue
        except Exception as err:
            message(f"ERROR: could not read replay: {fn.name}")
            debug("%s: %s", type(err), err)
            stats.log("errors")
            continue
        try:
            if is_ok(
                res := await replay.enrich(
                    tankopedia=tankopedia, maps=maps, player=player
                )
            ):
                await stats_cache.queue_stats(
                    replay, accountQ=accountQ, query_cache=query_cache
                )
                await replayQ.put(replay)
                stats.log("OK")
            elif is_err(res):
                message(f"{res.err_value}: {fn.name}")
                stats.log("incomplete")
        except Exception as err:
            if logger.getEffectiveLevel() == logging.WARNING:  # normal
                message(f"ERROR: could not process replay: {fn}")
            else:
                verbose(
                    "could not process replay: %s: %s: %s",
                    str(fn.name),
                    type(err),
                    err,
                )
            stats.log("processing errors")

    await replayQ.finish()
    await accountQ.finish()
    return stats

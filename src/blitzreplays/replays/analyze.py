import typer
from typer import Context, Option, Argument
from typing import Annotated, Optional, List
from asyncio import create_task, Task, sleep
import logging
from pathlib import Path
from configparser import ConfigParser
from alive_progress import alive_bar  # type: ignore

from pyutils import FileQueue, EventCounter, AsyncTyper, IterableQueue
from pyutils.utils import set_config
from blitzmodels import (
    WGApiWoTBlitzTankopedia,
    Maps,
    Region,
    WGApi,
)
from blitzmodels.wotinspector.wi_apiv2 import Replay
from blitzmodels.wotinspector.wi_apiv1 import ReplayJSON, ReplaySummary
from .analyze_models import (
    EnrichedPlayerData,
    EnrichedReplay,
    StatsCache,
    StatsQuery,
    StatsType,
    AccountId,
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
def analyze() -> None:
    pass


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
    """analyze replays from replay DB"""
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
        typer.Exit(code=1)
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
    # TODO: Apply stats to the replays in the queue
    # TODO: do analysis
    # TODO: print results

    debug(stats.print(do_print=False))


async def analyze_replays(
    replayQ: IterableQueue[EnrichedReplay], stats_cache: StatsCache
) -> EventCounter:
    """
    Apply stats to replays and perform analysis
    """
    stats = EventCounter("Analyze")
    async for replay in replayQ:
        replay = stats_cache.add_stats(replay)
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

            if replay is not None:
                await replay.enrich(tankopedia=tankopedia, maps=maps)
                await stats_cache.fetch_stats(replay)
                await replayQ.put(replay)
            else:
                stats.log("read replay errors")
                raise ValueError()

        except Exception as err:
            error(f"could not read replay: {fn}: {type(err)}: {err}")
            stats.log("errors")
    await replayQ.finish()
    await stats_cache.accountQ.finish()
    return stats

import click
from asyncio import run, Task, create_task, wait
import logging
from pathlib import Path
from configparser import ConfigParser
import sys
from aiostream import stream, async_
from aiostream.core import Stream
from functools import wraps

from pyutils import FileQueue, EventCounter
from blitzutils import (
    WoTinspector,
    WGApiWoTBlitzTankopedia,
    ReplayJSON,
    Maps,
    get_config_file,
)


def coro(f):
    """decorator for async coroutines"""

    @wraps(f)
    def wrapper(*args, **kwargs):
        return run(f(*args, **kwargs))

    return wrapper


logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

##############################################
#
## Constants
#
##############################################

_PKG_NAME = "blitz-replays"
LOG = _PKG_NAME + ".log"
CONFIG_FILE: Path | None = get_config_file()

WI_RATE_LIMIT: float = 20 / 3600
WI_AUTH_TOKEN: str | None = None
WI_WORKERS: int = 3

##############################################
#
## cli_xxx()
#
##############################################


@click.command()
@click.option(
    "--json",
    "fetch_json",
    flag_value=True,
    default=None,
    help="fetch replay JSON files for analysis (default=False)",
)
@click.option(
    "--uploaded_by",
    type=int,
    default=0,
    help="WG account_id of the uploader",
)
@click.option(
    "--private",
    "private",
    flag_value=True,
    default=None,
    help="upload replays as private without listing those publicly (default=False)",
)
@click.argument("replays", type=click.Path(path_type=Path), nargs=-1)
@click.pass_context
@coro
async def upload(
    ctx: click.Context,
    fetch_json: bool | None = None,
    uploaded_by: int = 0,
    private: bool | None = None,
    replays: list[Path] = list(),
) -> int:
    tankopedia_fn: Path | None = None
    maps_fn: Path | None = None
    try:
        config: ConfigParser = ctx.obj["config"]
        configWI = config["WOTINSPECTOR"]
        wi_rate_limit: float = configWI.getfloat("rate_limit")
        wi_auth_token: str = configWI.get("auth_token")
        wi_workers: int = configWI.getint("workers")
    except KeyError as err:
        error(f"could not read all the params: {err}")
        sys.exit(1)

    debug(
        f"wi_rate_limit={wi_rate_limit}, wi_auth_token={wi_auth_token}, wi_workers={wi_workers}"
    )
    WI = WoTinspector(rate_limit=wi_rate_limit, auth_token=wi_auth_token)

    if fetch_json is None:
        fetch_json = configWI.getboolean("fetch_json", False)
    debug(f"fetch_json={fetch_json}")
    if private is None:
        private = configWI.getboolean("upload_private", False)
    debug(f"private={private}")
    if uploaded_by == 0:
        uploaded_by = config.getint(section="WG", option="wg_id", fallback=0)
    debug(f"uploaded_by={uploaded_by}")

    try:
        tankopedia_fn = Path(config.get(section="METADATA", option="tankopedia_json"))
        maps_fn = Path(config.get(section="METADATA", option="maps_json"))
    except (TypeError, KeyError) as err:
        debug(f"could not open maps or tankopedia: {err}")

    tankopedia: WGApiWoTBlitzTankopedia | None = None
    maps: Maps | None = None

    if (
        tankopedia_fn is None
        or (tankopedia := await WGApiWoTBlitzTankopedia.open_json(tankopedia_fn))
        is None
    ):
        verbose(f"could not open tankopedia: {tankopedia_fn}")
    if maps_fn is None or (maps := await Maps.open_json(maps_fn)) is None:
        verbose(f"could not open maps: {maps_fn}")

    stats = EventCounter("Upload replays")
    replayQ = FileQueue(filter="*.wotbreplay")
    scanner: Task = create_task(replayQ.mk_queue(replays))

    try:
        replay_stream: Stream[tuple[str | None, bool, bool]] = stream.map(
            replayQ,
            async_(
                lambda replay_fn: post_save_replay(  # type: ignore
                    WI=WI,
                    filename=replay_fn,
                    uploaded_by=uploaded_by,
                    tankopedia=tankopedia,
                    maps=maps,
                    fetch_json=fetch_json,  # type: ignore
                    priv=private,  # type: ignore
                )
            ),
            task_limit=wi_workers,
        )

        await scanner

        res: list[tuple[str | None, bool, bool]] = await stream.list(replay_stream)
        stats.log("found", replayQ.count)
        for replay_id, saved, skipped in res:
            debug("replay_id=%s", replay_id)
            if skipped:
                stats.log("skipped")
            elif replay_id is None:
                stats.log("errors")
            else:
                stats.log("uploaded")
                if saved:
                    stats.log("JSON saved")

    except Exception as err:
        error(f"{err}")
    finally:
        await WI.close()

    stats.print()

    return 0


async def post_save_replay(
    WI: WoTinspector,
    filename: Path,
    uploaded_by: int,
    tankopedia: WGApiWoTBlitzTankopedia | None,
    maps: Maps | None,
    fetch_json: bool = False,
    priv: bool = False,
) -> tuple[str | None, bool, bool]:
    """Helper to post and save a replay
    Returns: (replay_id, saved, skipped)"""
    try:
        if (filename.parent / (filename.name + ".json")).is_file():
            message(f"skipped {filename.name}: replay already uploaded")
            return (None, False, True)

        replay_id: str | None = None
        replay_json: ReplayJSON | None = None
        replay_id, replay_json = await WI.post_replay(
            replay=filename,
            uploaded_by=uploaded_by,
            tankopedia=tankopedia,
            maps=maps,
            fetch_json=fetch_json,
            priv=priv,
        )
        debug(f"replay_id={replay_id}, replay_json={replay_json}")
        if replay_id is None or replay_json is None:
            raise ValueError(f"could not upload replay: {filename}")
        message(f"posted {filename.name}: {replay_json.data.summary.title}")
        if fetch_json:
            if (
                _ := await replay_json.save_json(
                    filename.parent / (filename.name + ".json")
                )
            ) > 0:
                return (replay_id, True, False)
            else:
                return (replay_id, False, False)
        else:
            return (replay_id, False, False)

    except Exception as err:
        error(f"{filename}: {type(err)}: {err}")
    return (None, False, False)


########################################################
#
# main() entry
#
########################################################


def cli_main():
    run(upload())


if __name__ == "__main__":
    # asyncio.run(main(sys.argv[1:]), debug=True)
    cli_main()

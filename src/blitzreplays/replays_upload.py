import click
from asyncio import run, Task, create_task, wait
import logging
from pathlib import Path
from configparser import ConfigParser
import sys
from aiostream import stream, async_
from aiostream.core import Stream
from functools import wraps
from alive_progress import alive_bar  # type: ignore

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
    except KeyError as err:
        error(f"could not read all the params: {err}")
        sys.exit(1)

    debug(f"wi_rate_limit={wi_rate_limit}, wi_auth_token={wi_auth_token}")
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
    await replayQ.mk_queue(replays)

    try:
        with alive_bar(
            replayQ.qsize(), title="Posting replays", enrich_print=False
        ) as bar:
            async for fn in replayQ:
                try:
                    if (fn.parent / (fn.name + ".json")).is_file():
                        message(f"skipped {fn.name}: replay already uploaded")
                        stats.log("skipped")
                        continue

                    replay_id: str | None = None
                    replay_json: ReplayJSON | None = None
                    replay_id, replay_json = await WI.post_replay(
                        replay=fn,
                        uploaded_by=uploaded_by,
                        tankopedia=tankopedia,
                        maps=maps,
                        fetch_json=fetch_json,
                        priv=private,
                    )
                    debug(f"replay_id=%s, replay_json=%s", replay_id, replay_json)

                    if replay_id is None or replay_json is None:
                        raise ValueError(f"could not upload replay: {fn}")
                    message(f"posted {fn.name}: {replay_json.data.summary.title}")
                    stats.log("uploaded")
                    if fetch_json:
                        if (
                            _ := await replay_json.save_json(
                                fn.parent / (fn.name + ".json")
                            )
                        ) > 0:
                            stats.log("JSON saved")
                except KeyboardInterrupt:
                    message("cancelled")
                    raise
                except Exception as err:
                    error(f"could not post replay: {fn}: {type(err)}: {err}")
                    stats.log("errors")
                finally:
                    bar()

    except Exception as err:
        error(f"{err}")
    finally:
        await WI.close()

    stats.print()

    return 0


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

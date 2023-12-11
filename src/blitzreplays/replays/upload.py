import typer
from typing import Annotated, Optional, List
from asyncio import run, Task, create_task, wait
import logging
from pathlib import Path
from configparser import ConfigParser
import sys
from aiostream import stream, async_
from aiostream.core import Stream

from alive_progress import alive_bar  # type: ignore

from pyutils import FileQueue, EventCounter, AsyncTyper
from pyutils.utils import coro
from blitzmodels import (
    WoTinspector,
    WGApiWoTBlitzTankopedia,
    ReplayJSON,
    Maps,
    get_config_file,
)

typer_app = AsyncTyper()

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

# _PKG_NAME = "blitz-replays"
# LOG = _PKG_NAME + ".log"
# CONFIG_FILE: Path | None = get_config_file()

WI_RATE_LIMIT: float = 20 / 3600
WI_AUTH_TOKEN: str | None = None
WI_WORKERS: int = 3

##############################################
#
## upload()
#
##############################################


@typer_app.async_command()
async def upload(
    ctx: typer.Context,
    fetch_json: Annotated[
        Optional[bool],
        typer.Option(
            "--json",
            show_default=False,
            help="fetch replay JSON file for replay analysis. Default is False",
        ),
    ] = None,
    uploaded_by: Annotated[
        int, typer.Option(help="WG account_id of the uploader (you)")
    ] = 0,
    private: Annotated[
        Optional[bool],
        typer.Option(
            show_default=False,
            help="upload replays as private without listing those publicly (default=False)",
        ),
    ] = None,
    replays: Annotated[List[Path], typer.Argument(help="replays to upload")] = list(),
) -> int:
    """
    upload replays to https://WoTinspector.com
    """
    tankopedia: WGApiWoTBlitzTankopedia
    maps: Maps
    wi_rate_limit: float
    wi_auth_token: str | None
    try:
        config: ConfigParser = ctx.obj["config"]
        configWI = config["WOTINSPECTOR"]
        if not isinstance(
            wi_rate_limit := configWI.getfloat("rate_limit", fallback=WI_RATE_LIMIT),
            float,
        ):
            raise ValueError("could not set WI rate limit")
        wi_auth_token = configWI.get("auth_token", fallback=WI_AUTH_TOKEN)
        if not (wi_auth_token is None or isinstance(wi_auth_token, str)):
            raise ValueError("could not set WI authentication token")
        debug(f"wi_rate_limit={wi_rate_limit}, wi_auth_token={wi_auth_token}")

        if fetch_json is None:
            fetch_json = configWI.getboolean("fetch_json", False)
        debug(f"fetch_json={fetch_json}")

        if private is None:
            private = configWI.getboolean("upload_private", False)
        debug(f"private={private}")
        if uploaded_by == 0:
            uploaded_by = config.getint(section="WG", option="wg_id", fallback=0)
        debug(f"uploaded_by={uploaded_by}")

        tankopedia = ctx.obj["tankopedia"]
        maps = ctx.obj["maps"]

    except KeyError as err:
        error(f"could not read all the params: {err}")
        typer.Exit(code=1)
        assert False, "trick Mypy..."
    except ValueError as err:
        error(f"could not set configuration option: {err}")
        typer.Exit(code=2)
        assert False, "trick Mypy..."

    WI = WoTinspector(rate_limit=wi_rate_limit, auth_token=wi_auth_token)
    stats = EventCounter("Upload replays")
    replayQ = FileQueue(filter="*.wotbreplay")
    await replayQ.mk_queue(replays)

    try:
        with alive_bar(
            replayQ.qsize(), title="Uploading replays", enrich_print=False
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

if __name__ == "__main__":
    typer_app()

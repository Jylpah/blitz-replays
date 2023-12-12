import typer
from typing import Annotated, Optional, List
import logging
from pathlib import Path
from configparser import ConfigParser
from alive_progress import alive_bar  # type: ignore

from pyutils import FileQueue, EventCounter, AsyncTyper
from pyutils.utils import set_config
from blitzmodels import (
    WGApiWoTBlitzTankopedia,
    Maps,
)
from blitzmodels.wotinspector.wi_apiv2 import WoTinspector, Replay

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

WI_RATE_LIMIT: float = 1.0
WI_AUTH_TOKEN: str | None = None
WI_WORKERS: int = 3

##############################################
#
## upload()
#
##############################################


def callback_paths(value: Optional[list[Path]]) -> list[Path]:
    return value if value is not None else []


@typer_app.async_command()
async def upload(
    ctx: typer.Context,
    force: Annotated[
        Optional[bool],
        typer.Option(
            "--force",
            show_default=False,
            is_flag=True,
            flag_value=True,
            help="force upload even JSON file exists",
        ),
    ] = False,
    private: Annotated[
        Optional[bool],
        typer.Option(
            show_default=False,
            help="upload replays as private without listing those publicly (default=False)",
        ),
    ] = None,
    wi_rate_limit: Annotated[
        Optional[float], typer.Option(help="rate-limit for WoTinspector.com")
    ] = None,
    wi_auth_token: Annotated[
        Optional[str], typer.Option(help="authentication token for WoTinsepctor.com")
    ] = None,
    replays: List[Path] = typer.Argument(
        help="replays to upload", callback=callback_paths
    ),
) -> int:
    """
    upload replays to https://WoTinspector.com
    """
    tankopedia: WGApiWoTBlitzTankopedia
    maps: Maps
    # wi_rate_limit: float
    # wi_auth_token: str | None
    try:
        config: ConfigParser = ctx.obj["config"]

        wi_rate_limit = set_config(
            config, WI_RATE_LIMIT, "WOTINSPECTOR", "rate_limit_upload", wi_rate_limit
        )
        configWI = config["WOTINSPECTOR"]
        wi_auth_token = configWI.get("auth_token", fallback=WI_AUTH_TOKEN)
        if not (wi_auth_token is None or isinstance(wi_auth_token, str)):
            raise ValueError("could not set WI authentication token")
        debug(
            f"wi_rate_limit={wi_rate_limit}({type(wi_rate_limit)}), wi_auth_token={wi_auth_token}"
        )

        if private is None:
            private = configWI.getboolean("upload_private", False)
        debug(f"private={private}")

        tankopedia = ctx.obj["tankopedia"]
        maps = ctx.obj["maps"]

    except KeyError as err:
        error(f"could not read all the params: {err}")
        typer.Exit(code=6)
        assert False, "trick Mypy..."
    except ValueError as err:
        error(f"could not set configuration option: {err}")
        typer.Exit(code=7)
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
                    if not force and (fn.parent / (fn.name + ".json")).is_file():
                        message(f"skipped {fn.name}: replay already uploaded")
                        stats.log("skipped")
                        continue

                    replay: Replay | None = None
                    if (
                        replay := await WI.post_replay(
                            replay=fn,
                            tankopedia=tankopedia,
                            maps=maps,
                            priv=private,
                        )
                    ) is None:
                        raise ValueError(f"could not upload replay: {fn}")
                    message(f"posted {fn.name}: {replay.title}")
                    stats.log("uploaded")
                    # save JSON
                    if (
                        _ := await replay.save_json(fn.parent / (fn.name + ".json"))
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
        typer.Exit(code=3)
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

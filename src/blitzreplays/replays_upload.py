import click
from asyncio import run
import logging
from os.path import isfile, dirname, realpath, expanduser
from configparser import ConfigParser
from typing import Optional, Callable
import sys

from pyutils import MultilevelFormatter, FileQueue
from pyutils.utils import read_config
from blitzutils import WoTinspector

sys.path.insert(0, dirname(dirname(realpath(__file__))))


def async_click(callable_: Callable):
    def wrapper(*args, **kwargs):
        run(callable_(*args, **kwargs))

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
CONFIG = _PKG_NAME + ".ini"
LOG = _PKG_NAME + ".log"
CONFIG_FILES: list[str] = [
    "./" + CONFIG,
    dirname(realpath(__file__)) + "/" + CONFIG,
    "~/." + CONFIG,
    "~/.config/" + CONFIG,
    "~/.config/" + _PKG_NAME + "/config",
    "~/.config/blitzstats.ini",
    "~/.config/blitzstats/config",
]

WI_RATE_LIMIT: float = 20 / 3600
WI_AUTH_TOKEN: str | None = None
WI_WORKERS: int = 3


##############################################
#
## cli_xxx()
#
##############################################


@click.command()
@click.option("--normal", "LOG_LEVEL", flag_value=logging.WARNING, default=True)
@click.option("--verbose", "LOG_LEVEL", flag_value=logging.INFO)
@click.option("--debug", "LOG_LEVEL", flag_value=logging.DEBUG)
@click.option("--config", "config_file", type=str, default=None)
@click.option("--log", type=str, default=None)
@click.option("--json", default=False)
@click.option("--wi-rate-limit", type=float, default=WI_RATE_LIMIT)
@click.option("--wi-auth_token", type=str, default=WI_AUTH_TOKEN)
@click.option("--wi-workers", type=int, default=WI_WORKERS)
@click.argument("files", nargs=-1)
def cli_upload(
    LOG_LEVEL: int = logging.WARNING,
    config_file: str | None = None,
    log: str | None = None,
    json: bool = False,
    wi_rate_limit: float = WI_RATE_LIMIT,
    wi_auth_token: str | None = WI_AUTH_TOKEN,
    wi_workers: int = WI_WORKERS,
    files: list[str] = list(),
):
    global logger, error, debug, verbose, message

    logger.setLevel(LOG_LEVEL)
    MultilevelFormatter.setDefaults(logger, log_file=log)

    config: ConfigParser | None
    if (config := read_config(config_file, CONFIG_FILES)) is None:
        debug("could not find a config file")
    elif config.has_section("WOTINSPECTOR"):
        configWI = config["WOTINSPECTOR"]
        wi_rate_limit = configWI.getfloat("rate_limit", wi_rate_limit)
        wi_auth_token = configWI.get("auth_token", wi_auth_token)
        wi_workers = configWI.getint("workers", wi_workers)

    if not run(
        upload(
            files=files,
            wi_rate_limit=wi_rate_limit,
            wi_auth_token=wi_auth_token,
            wi_workers=wi_workers,
        )
    ):
        sys.exit(1)


async def upload(
    files: list[str],
    wi_rate_limit: float = WI_RATE_LIMIT,
    wi_auth_token: str | None = None,
    wi_workers: int = WI_WORKERS,
) -> bool:
    wi = WoTinspector(rate_limit=wi_rate_limit, auth_token=wi_auth_token)
    replayQ = FileQueue(filter="*.wotbreplay")

    await replayQ.mk_queue(files)
    # FIX WoTinsepector.post_replay() first
    return False


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

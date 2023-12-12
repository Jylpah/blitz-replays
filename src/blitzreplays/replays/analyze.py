import logging
from typing import Optional, Literal, Any, Annotated, List
from typer import Context, Exit, Option, Argument
from pyutils.utils import set_config
from pyutils import AsyncTyper
from blitzmodels import (
    WGApiWoTBlitzTankopedia,
    Maps,
)
from blitzmodels.wotinspector.wi_apiv2 import WoTinspector, Replay

app = AsyncTyper()

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug


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
    pass


@app.async_command()
async def files() -> None:
    """files to analyze"""
    pass

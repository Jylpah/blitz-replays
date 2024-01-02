import logging
from typing import Optional, Annotated, List
from typer import Context, Option
from pyutils import AsyncTyper

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

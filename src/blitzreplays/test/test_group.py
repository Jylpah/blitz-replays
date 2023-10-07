import click
from pyutils.utils import coro
from asyncio import sleep


@click.group(help="Test click group")
@click.option(
    "-s",
    "--success",
    flag_value=True,
    default=False,
    help="Test is successful (unlikely)",
)
@click.pass_context
def group(ctx: click.Context, success: str | None = None) -> None:
    print(f"success={success}")


@group.command()
@click.pass_context
@coro
async def ok(ctx: click.Context):
    await sleep(0.5)
    print("OK")


@group.command()
@click.pass_context
@coro
async def nok(ctx: click.Context):
    await sleep(0.1)
    print("NOT OK")

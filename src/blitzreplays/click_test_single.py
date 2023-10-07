#!/usr/bin/env python3

import click
from pathlib import Path
from sys import path
from pyutils.utils import coro
from asyncio import sleep

path.insert(0, str(Path(__file__).parent.resolve()))

# from test import test_group


@click.group(help="CLI tool to test click groups")
@click.option(
    "--name",
    type=str,
    default=None,
    help="name param",
)
@click.pass_context
def cli(ctx: click.Context, name: str | None):
    print(f"--name={name}")


@cli.group()
@click.pass_context
def test(ctx: click.Context, success: str | None = None) -> None:
    print(f"success={success}")


@test.command()
@click.pass_context
@coro
async def ok(ctx: click.Context):
    await sleep(0.5)
    print("OK")


@test.command()
@click.pass_context
@coro
async def nok(ctx: click.Context):
    await sleep(0.1)
    print("NOT OK")


def cli_main():
    cli(obj={})


if __name__ == "__main__":
    # asyncio.run(main(sys.argv[1:]), debug=True)
    cli_main()

#!/usr/bin/env python3

import click
from pathlib import Path
from sys import path
from pyutils.utils import coro
from asyncio import sleep

path.insert(0, str(Path(__file__).parent.parent.resolve()))

from blitzreplays.test import test_group


@click.group(help="CLI tool to test click groups")
@click.option(
    "--name",
    type=str,
    default=None,
    help="name param",
)
@click.pass_context
def cli(ctx: click.Context, name: str | None):
    print(f"cli(): --name={name}")


# cli.group(test_group.group)


def cli_main():
    cli(obj={})


if __name__ == "__main__":
    # asyncio.run(main(sys.argv[1:]), debug=True)
    cli_main()

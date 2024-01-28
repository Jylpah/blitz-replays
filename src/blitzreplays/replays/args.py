# module for CLI arguments related classes
from typing import List, Set
from pathlib import Path
from enum import StrEnum
from dataclasses import dataclass
from typing import (
    Self,
    Literal,
)
import logging
from re import Pattern
import typer
import sys
from os import makedirs

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug


class EnumTeamFilter(StrEnum):
    player = "player"
    # plat_mate   = "plat_mate"
    allies = "allies"
    enemies = "enemies"
    all = "all"


class EnumGroupFilter(StrEnum):
    default = "default"
    all = "all"
    solo = "solo"
    platoon = "platoon"
    light_tank = "light_tank"
    medium_tank = "medium_tank"
    heavy_tank = "heavy_tank"
    tank_destroyer = "tank_destroyer"
    top = "top"
    bottom = "bottom"


@dataclass
class PlayerFilter:
    team: EnumTeamFilter
    group: EnumGroupFilter

    def __str__(self) -> str:
        return f"{self.team}:{self.group}"

    @property
    def key(self) -> str:
        return self.__str__()

    @classmethod
    def from_str(cls, filter: str) -> Self:
        team: EnumTeamFilter
        group: EnumGroupFilter
        filters: list[str] = filter.split(":")
        if len(filters) == 1:
            team = EnumTeamFilter(filters[0])
            group = EnumGroupFilter.default
        elif len(filters) == 2:
            team = EnumTeamFilter(filters[0])
            group = EnumGroupFilter(filters[1])
        else:
            raise ValueError(f"incorrect filter format: {filter} != '<team>:<group>'")
        return cls(team=team, group=group)


class EnumStatsTypes(StrEnum):
    player = "player"
    tier = "tier"
    tank = "tank"


StatsType = Literal["player", "tier", "tank"]
StatsMeasure = Literal["wr", "avgdmg", "battles"]


def ask_config_file() -> Path:
    """
    Ask for users analyze config file
    """
    while True:
        config_file: Path = (
            Path.home() / ".config" / "blitz-replays" / "analyze_config.toml"
        )
        typer.echo()
        typer.echo(
            f"""Please enter path to a new analyze config file:\n
                   default={config_file.resolve()}"""
        )
        typer.echo()
        try:
            config_filename: str = sys.stdin.read().rstrip()
            if config_file != "":
                if not config_filename.endswith(".toml"):
                    config_filename = config_filename + ".toml"
                config_file = Path(config_filename)

            makedirs(str(config_file.parent.resolve()), mode=0o750, exist_ok=True)
            return config_file
        except Exception as err:
            error("%s: %s", type(err), err)


def ask_input(
    text: str, query: str, regexp: Pattern | None = None, options: List[str] = list()
) -> str | None:
    """
    Read user input and validate it matches the 'regexp'
    """
    opts: Set[str] = set(options)
    while True:
        try:
            typer.echo()
            typer.echo(text)
            typer.echo("(Press CTRL + C to cancel): ")
            answer: str = input(query)
            if (len(opts) > 0 and answer in opts) or (
                regexp is not None and regexp.match(answer) is not None
            ):
                return answer
            elif len(opts) == 0 and regexp is None:
                return answer
            else:
                typer.echo(f"The input is not valid: {answer}")

        except KeyboardInterrupt:
            return None

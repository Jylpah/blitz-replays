# module for CLI arguments related classes

from enum import StrEnum
from dataclasses import dataclass
from typing import (
    Self,
    Literal,
)


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

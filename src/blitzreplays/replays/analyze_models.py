import logging
from typing import (
    List,
    Self,
    Dict,
    Tuple,
    Set,
    ClassVar,
    Type,
    Optional,
    Literal,
    Final,
    # Union,
    # get_args,
    Iterable,
)
from pydantic import Field, model_validator, ConfigDict
from abc import abstractmethod, ABC

# from itertools import product
from asyncio import Lock
from enum import StrEnum
from dataclasses import dataclass, field as data_field
from re import compile, match
import re
from pyutils import IterableQueue, EventCounter
from pydantic_exportables import JSONExportable, JSONExportableRootDict, Idx
from collections import defaultdict
from tabulate import tabulate  # type: ignore

from blitzmodels import (
    Tank,
    WGApiWoTBlitzTankopedia,
    WGApiWoTBlitzTankStats,
    EnumVehicleTypeStr,
    Maps,
    Map,
    WGApi,
    TankStat,
    # AccountInfo,
    AccountId,
    TankId,
)
from blitzmodels.wotinspector.wi_apiv2 import Replay, PlayerData
from blitzmodels.wotinspector.wi_apiv1 import EnumBattleResult


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
    platoon = "plat"
    light_tank = "lt"
    medium_tank = "mt"
    heavy_tank = "ht"
    tank_destroyer = "td"
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


StatsType = Literal["player", "tier", "tank"]
StatsMeasure = Literal["wr", "avgdmg", "battles"]


class PlayerTankStat(TankStat):
    """Helper class for TankStatsDict"""

    @property
    def index(self) -> Idx:
        """return backend index"""
        return self.tank_id


class PlayerStats(JSONExportable):
    # stat_type: StatsType
    account_id: AccountId
    tank_id: int = 0
    tier: int = 0

    wr: float = 0
    avgdmg: float = 0
    battles: int = 0
    # tier_wr: float = 0
    # tier_avgdmg: float = 0
    # tier_battles: int = 0
    # tank_wr: float = 0
    # tank_avgdmg: float = 0
    # tank_battles: int = 0

    # @property
    # def key(self) -> str:
    #     return StatsCache.stat_key(self.account_id, self.tier, self.tank_id)

    @property
    def stats_type(self) -> StatsType:
        if self.tank_id == 0 and self.tier == 0:
            return "player"
        elif self.tank_id > 0:
            return "tank"
        elif self.tier > 0:
            return "tier"
        else:
            raise ValueError("player stats record has invalid value")

    def get(self, stats_type: StatsType, measure: StatsMeasure) -> int | float:
        """get stats measure from the PlayerStats instance. Returns '0' if error or no stat"""
        if stats_type != self.stats_type:
            error(f"wrong type of stats record: {self.stats_type} != {stats_type}")
        return getattr(self, measure, 0)

    @classmethod
    def from_tank_stat(cls, ts=TankStat) -> Self:
        """
        Create PlayerStats from a TankStat for a tank
        """
        return cls(
            account_id=ts.account_id,
            tank_id=ts.tank_id,
            wr=ts.all.wins / ts.all.battles,
            avgdmg=ts.all.damage_dealt / ts.all.battles,
            battles=ts.all.battles,
        )

    @classmethod
    def from_tank_stats(cls, stats=Iterable[TankStat], tier: int = 0) -> Optional[Self]:
        """
        Create an aggregate PlayerStats from a list of Iterable[TankStats]

        Creates tank
        """
        try:
            ts: TankStat = next(stats)
            res = cls(
                account_id=ts.account_id,
                tier=tier,
                wr=ts.all.wins / ts.all.battles,
                avgdmg=ts.all.damage_dealt / ts.all.battles,
                battles=ts.all.battles,
            )
            for ts in stats:
                try:
                    res.battles = res.battles + ts.all.battles
                    res.wr = res.wr + ts.all.wins
                    res.avgdmg = res.avgdmg + ts.all.damage_dealt
                except Exception as err:
                    error(err)
            res.wr = res.wr / res.battles
            res.avgdmg = res.avgdmg / res.battles
            return res
        except Exception as err:
            error(err)
        return None

    # @classmethod
    # def tank_stats(cls, stats: List[TankStat]) -> List[Self]:
    #     """Create PlayerStats from WG API Tank Stats for each tank"""
    #     res: List[Self] = list()
    #     for ts in stats:
    #         res.append(cls.from_tank_stat(ts))
    #     return res

    # @classmethod
    # def tier_stats(
    #     cls, account_id: AccountId, stats: List[TankStat], tier: int
    # ) -> Self:
    #     """
    #     Create PlayerStats from WG API Tank Stats

    #     Assumes all the TankStats are for the same tier tanks
    #     """
    #     res = cls(account_id=account_id, tier=tier)
    #     try:
    #         for ts in stats:
    #             res.battles = res.battles + ts.all.battles
    #             res.wr = res.wr + ts.all.wins
    #             res.avgdmg = res.avgdmg + ts.all.damage_dealt

    #         res.wr = res.wr / res.battles
    #         res.avgdmg = res.avgdmg / res.battles
    #     except Exception as err:
    #         debug(err)
    #     return res

    # @classmethod
    # def player_stats(cls, stats: AccountInfo) -> "PlayerStats":
    #     """ "Create PlayerStats from WG API Tank Stats"""

    #     try:
    #         if (
    #             stats.statistics is not None
    #             and (ps := stats.statistics["all"]) is not None
    #         ):
    #             return PlayerStats(
    #                 account_id=stats.account_id,
    #                 wr=ps.wins / ps.battles,
    #                 avgdmg=ps.damage_dealt / ps.battles,
    #                 battles=ps.battles,
    #             )
    #     except KeyError:
    #         debug(f"no player stats for account_id={stats.account_id}")
    #     return PlayerStats(account_id=stats.account_id)


class TankStatsDict(JSONExportableRootDict[PlayerTankStat]):
    """
    Helper class to store tank stats in a dict vs list for search performance
    """

    @classmethod
    def from_WGApiWoTBlitzTankStats(
        cls, api_stats: WGApiWoTBlitzTankStats
    ) -> "TankStatsDict":
        res = cls()
        # tank_stats: list[TankStat] | None

        if api_stats.data is not None:
            try:
                if (tank_stats := list(api_stats.data.values())[0]) is not None:
                    for tank_stat in tank_stats:
                        if (
                            pts := PlayerTankStat.from_obj(tank_stat, in_type=TankStat)
                        ) is not None:
                            res[tank_stat.tank_id] = pts
            except KeyError:
                debug("no stats in WG API tank stats")
        return res

    def get_many(self, tank_ids: Iterable[TankId]) -> Set[PlayerTankStat]:
        res: Set[PlayerTankStat] = set()
        for tank_id in tank_ids:
            res.add(self.root[tank_id])
        return res

    def get_player_stats(self) -> PlayerStats | None:
        return PlayerStats.from_tank_stats(self.root.values(), tier=0)

    def get_tank_stat(self, tank_id: TankId) -> PlayerStats | None:
        try:
            return PlayerStats.from_tank_stat(self.root[tank_id])
        except Exception as err:
            error(err)
        return None

    def get_tank_stats(
        self, tank_ids: Iterable[TankId], tier: int = 0
    ) -> PlayerStats | None:
        return PlayerStats.from_tank_stats(
            [self.root[tank_id] for tank_id in tank_ids], tier=tier
        )


@dataclass
class StatsQuery:
    """Class for defining player stats query"""

    account_id: AccountId
    stats_type: StatsType
    tier: int = 0
    tank_id: int = 0

    @property
    def key(self) -> str:
        return StatsCache.stat_key(
            stats_type=self.stats_type,
            account_id=self.account_id,
            tier=self.tier,
            tank_id=self.tank_id,
        )


class StatsCache:
    def __init__(
        self: Self,
        wg_api: WGApi,
        # accountQ: IterableQueue[AccountId],
        stat_types: Iterable[StatsType],
        tankopedia: WGApiWoTBlitzTankopedia,
    ):
        """creator of StatsCache must add_producer() to the statsQ before calling __init__()"""
        # fmt:off
        self._stats_cache   : Dict[str, PlayerStats] = dict()
        self._query_cache   : Set[StatsQuery] = set()  # account_id as a key
        self._wg_api        : WGApi = wg_api
        self._api_cache     : Dict[AccountId, TankStatsDict | None ] = dict()
        self._api_cache_lock: Lock = Lock()
        self._query_cache_lock: Lock = Lock()
        self.accountQ       : IterableQueue[AccountId] = IterableQueue()
        self._stats_types   : Iterable[StatsType] = stat_types
        self._tankopedia    : WGApiWoTBlitzTankopedia = tankopedia 

        # fmt: on

    @classmethod
    def stat_key(
        cls,
        stats_type: StatsType,
        account_id: AccountId = 0,
        tier: int = 0,
        tank_id: int = 0,
        stats: PlayerStats | None = None,
    ) -> str:
        if stats is not None:
            account_id = stats.account_id
            tier = stats.tier
            tank_id = stats.tank_id
        match stats_type:
            case "player":
                tank_id = 0
                tier = 0
            case "tier":
                tank_id = 0
            case "tank":
                tier = 0
        return (
            hex(account_id)[2:].zfill(10)
            + hex(tier)[2:].zfill(2)
            + hex(tank_id)[2:].zfill(6)
        )

    async def fetch_stats(self, replay: "EnrichedReplay"):
        """
        Put account_ids to a queue for a API worker to fetch those.

        Add specific stats queries requestesd to a set.
        """
        for account_id in replay.allies + replay.enemies:
            await self.accountQ.put(account_id)

        async with self._query_cache_lock:
            for stats_type in self._stats_types:
                try:
                    self._query_cache.update(
                        replay.get_stats_queries(stats_type=stats_type)
                    )
                except Exception as err:
                    error(err)

    async def tank_stats_worker(self) -> EventCounter:
        """
        Async worker for retrieving player stats using WG APT tank/stats
        """
        fields: List[str] = [
            "account_id",
            "last_battle_time",
            "all.battles",
            "all.wins",
            "all.damage_dealt",
        ]
        stats = EventCounter("WG API")
        async for account_id in self.accountQ:
            try:
                async with self._api_cache_lock:
                    fetch_stats: bool = account_id not in self._api_cache
                    if fetch_stats:
                        self._api_cache[account_id] = None

                if fetch_stats:
                    # TODO: Add support for DB stats cache
                    if (
                        tank_stats := await self._wg_api.get_tank_stats_full(
                            account_id, fields=fields
                        )
                    ) is None:
                        stats.log("no stats")
                    else:
                        stats.log("stats retrieved")
                        self._api_cache[
                            account_id
                        ] = TankStatsDict.from_WGApiWoTBlitzTankStats(
                            api_stats=tank_stats
                        )

            except Exception as err:
                error(f"could not fetch stats for account_id={account_id}: {err}")
        return stats

    def fill_cache(self: Self):
        stats: PlayerStats | None
        for query in self._query_cache:
            account_id: int = query.account_id
            player_tank_stats: TankStatsDict | None
            try:
                player_tank_stats = self._api_cache[account_id]
            except KeyError:
                player_tank_stats = None

            if player_tank_stats is None:
                stats = PlayerStats(account_id=account_id)
                match query.stats_type:
                    case "player":
                        pass
                    case "tier":
                        stats.tier = query.tier
                    case "tank":
                        stats.tank_id = query.tank_id
                self._stats_cache[query.key] = stats
            else:
                match query.stats_type:
                    case "player":
                        if (stats := player_tank_stats.get_player_stats()) is None:
                            stats = PlayerStats(account_id=account_id)
                    case "tier":
                        if (
                            stats := player_tank_stats.get_tank_stats(
                                self._tankopedia.get_tank_ids_by_tier(tier=query.tier)
                            )
                        ) is None:
                            stats = PlayerStats(account_id=account_id, tier=query.tier)
                    case "tank":
                        if (
                            stats := player_tank_stats.get_tank_stat(
                                tank_id=query.tank_id
                            )
                        ) is None:
                            stats = PlayerStats(
                                account_id=account_id, tank_id=query.tank_id
                            )
                self._stats_cache[query.key] = stats

    def add_stats(self, replay: "EnrichedReplay") -> None:
        """
        Add player stats to the replay
        """
        battle_tier: int = replay.battle_tier
        stats: PlayerStats
        for player_data in replay.players_dict.values():
            account_id: AccountId = player_data.dbid
            tank_id: TankId = player_data.vehicle_descr
            for stats_type in self._stats_types:
                try:
                    stats_key: str = self.stat_key(
                        stats_type=stats_type,
                        account_id=account_id,
                        tier=battle_tier,
                        tank_id=tank_id,
                    )
                    stats = self._stats_cache[stats_key]
                except Exception as err:
                    error(err)
                    stats = PlayerStats(account_id=account_id)
                player_data.add_stats(stats)

    # async def player_stats_worker(self) -> None:
    #     """Async worker for retrieving player stats"""
    #     # TODO: add database cache
    #     regionQ: Dict[Region, Set[int]] = dict()
    ##     region: Region
    #     res: Dict[str, PlayerStats]
    #     debug("starting")
    #     for region in Region.API_regions():
    #         regionQ[region] = set()

    #     async for stats_query in self._Q:
    #         try:
    ##             region = Region.from_id(stats_query.account_id)
    #             regionQ[region].add(stats_query.account_id)
    #             if len(regionQ[region]) == 100:
    #                 res = await self.get_player_stats(
    #                     account_ids=regionQ[region], region=region
    #                 )
    #                 self._db.update(res)
    #                 regionQ[region] = set()
    #         except QueueDone:
    #             debug("finished")

    #         except Exception as err:
    #             error(err)
    #         for region, account_ids in regionQ.items():
    #             if len(account_ids) > 0:
    #                 res = await self.get_player_stats(account_ids, region=region)
    #                 self._db.update(res)

    # async def get_player_stats(
    #     self, account_ids: Set[int], region: Region
    # ) -> Dict[str, PlayerStats]:
    #     """
    #     Actually fetch the player stats from WG API
    #     """
    #     fields: List[str] = [
    #         "account_id",
    #         "last_battle_time",
    #         "statistics.all.battles",
    #         "statistics.all.wins",
    #         "statistics.all.damage_dealt",
    #     ]
    #     res: Dict[str, PlayerStats] = dict()
    #     if (
    #         player_stats := await self._wg_api.get_account_info(
    #             account_ids=list(account_ids),
    ##             region=region,
    #             fields=fields,
    #         )
    #     ) is not None:
    #         for player_stat in player_stats:
    #             key = self.stat_key(
    #                 stats_type="player",
    #                 account_id=player_stat.account_id,
    #             )
    #             res[key] = PlayerStats.player_stats(player_stat)
    #             account_ids.remove(player_stat.account_id)

    #     if len(account_ids) > 0:
    #         for account_id in account_ids:
    #             key = self.stat_key(
    #                 stats_type="player",
    #                 account_id=account_id,
    #             )
    #             res[key] = PlayerStats(account_id=account_id)
    #     return res

    # async def get_stats(
    #     self,
    #     stats_type: StatsType,
    #     account_id: int,
    #     tier: int = 0,
    #     tank_id: int = 0,
    # ) -> PlayerStats:
    #     # TODO: if stats not in db, fetch those
    #     # TODO: if fetched stats are None, store None
    #     key: str = self.stat_key(stats_type, account_id, tier, tank_id)

    #     if key not in self._query_cache:
    #         self._query_cache.add(key)
    #         await self._Q.put(
    #             StatsQuery(
    #                 account_id=account_id,
    #                 stats_type=stats_type,
    #                 tier=tier,
    #                 tank_id=tank_id,
    #             )
    #         )

    #     while True:
    #         try:
    #             return self._db[key]
    #         except KeyError:
    #             await sleep(2)


class EnrichedPlayerData(PlayerData):
    tank: Tank | None = None
    # player stats
    wr: float = 0
    avgdmg: float = 0
    battles: int = 0
    tier_wr: float = 0
    tier_avgdmg: float = 0
    tier_battles: int = 0
    tank_wr: float = 0
    tank_avgdmg: float = 0
    tank_battles: int = 0

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        validate_assignment=False,
    )

    def add_stats(self, stats: PlayerStats):
        match stats.stats_type:
            case "player":
                self.wr = stats.wr
                self.avgdmg = stats.avgdmg
                self.battles = stats.battles
            case "tier":
                self.tier_wr = stats.wr
                self.tier_avgdmg = stats.avgdmg
                self.tier_battles = stats.battles
            case "tank":
                self.tank_wr = stats.wr
                self.tank_avgdmg = stats.avgdmg
                self.tank_battles = stats.battles
            case other:
                raise ValueError(f"unknown stats type: {other}")


class EnrichedReplay(Replay):
    """
    EnrichedReplay to store additional metadata for speed up and simplify replay analysis
    """

    players_dict: Dict[AccountId, EnrichedPlayerData] = Field(default_factory=dict)
    player: AccountId = -1
    plat_mate: List[AccountId] = Field(default_factory=list)
    battle_tier: int = 0
    map: Map | None = None
    top_tier: bool = False

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        validate_assignment=False,
    )

    @model_validator(mode="after")
    def read_players_dict(self) -> Self:
        for player_data in self.players_data:
            self.players_dict[player_data.dbid] = EnrichedPlayerData.model_validate(
                player_data
            )
        self.players_data = list()
        return self

    async def enrich(
        self,
        # stats_cache: StatsCache,
        # stats_type: StatsType,
        tankopedia: WGApiWoTBlitzTankopedia,
        maps: Maps,
        player: AccountId = 0,
    ):
        """
        Prepare the (static) replay data for the particular analysis
        """

        data: EnrichedPlayerData
        # add tanks
        for data in self.players_dict.values():
            tank_id: TankId = data.vehicle_descr
            try:
                tank: Tank = tankopedia[tank_id]
                data.tank = tank
                self.battle_tier = max(self.battle_tier, int(tank.tier))
            except KeyError:
                debug(f"could not find tank_id={tank_id} from Tankopedia")

        # set player
        if player <= 0:
            self.player = self.protagonist
        else:
            self.player = player

        if self.player in self.allies:
            pass
        elif self.player in self.enemies:  # swap teams
            tmp_team: list[AccountId] = self.allies
            self.allies = self.enemies
            self.enemies = tmp_team
            if self.battle_result == EnumBattleResult.win:
                self.battle_result = EnumBattleResult.loss
            elif self.battle_result == EnumBattleResult.loss:
                self.battle_result = EnumBattleResult.win
        else:
            raise ValueError(f"no account_id={self.player} in the replay")

        # set top_tier
        if (player_tank := self.players_dict[self.player].tank) is not None:
            self.top_tier = player_tank.tier == self.battle_tier

        # set platoon mate
        if self.players_dict[self.player].squad_index is not None:
            plat_id: int = self.players_dict[self.player].squad_index
            for player in self.allies:
                if player == self.player:
                    continue
                if self.players_dict[player].squad_index == plat_id:
                    self.plat_mate = [player]

        # remove player and his plat mate from allies
        self.allies.remove(self.player)
        if len(self.plat_mate) == 1:
            self.allies.remove(self.plat_mate[0])

        try:
            self.map = maps[self.map_id]
        except (KeyError, ValueError):
            error(f"no map (id={self.map_id}) in Maps file")

    def get_players(
        self,
        filter: PlayerFilter = PlayerFilter(
            team=EnumTeamFilter.all, group=EnumGroupFilter.all
        ),
    ) -> List[AccountId]:
        """
        Get players matching the filter from the replay
        """
        players: List[AccountId] = list()
        try:
            if filter.team == EnumTeamFilter.player:
                match filter.group:
                    case EnumGroupFilter.default:
                        return [self.player]
                    case EnumGroupFilter.platoon:
                        return self.plat_mate
                    case EnumGroupFilter.all:
                        return [self.player] + self.plat_mate
                    case EnumGroupFilter.solo:
                        if len(self.plat_mate) == 0:
                            return [self.player]

            elif filter.group == EnumGroupFilter.all:
                match filter.team:
                    case EnumTeamFilter.allies:
                        return [self.player] + self.plat_mate + self.allies
                    case EnumTeamFilter.enemies:
                        return self.enemies
                    case EnumTeamFilter.all:
                        return (
                            [self.player] + self.plat_mate + self.allies + self.enemies
                        )

            elif filter.team == EnumTeamFilter.allies:
                players = self.allies
            elif filter.team == EnumTeamFilter.enemies:
                players = self.enemies
            elif filter.team == EnumTeamFilter.all:
                players = self.allies + self.enemies

            res: list[AccountId] = list()
            data: EnrichedPlayerData

            match filter.group:
                case EnumGroupFilter.default:
                    return players
                case EnumGroupFilter.solo:
                    return [
                        player
                        for player in players
                        if self.players_dict[player].squad_index is None
                    ]
                case EnumGroupFilter.platoon:
                    return [
                        player
                        for player in players
                        if self.players_dict[player].squad_index is not None
                    ]

                case (
                    EnumGroupFilter.tank_destroyer
                    | EnumGroupFilter.light_tank
                    | EnumGroupFilter.medium_tank
                    | EnumVehicleTypeStr.heavy_tank
                ):
                    tank_type = EnumVehicleTypeStr[filter.group.name]
                    for player in players:
                        data = self.players_dict[player]
                        if data.tank is not None and data.tank.type == tank_type:
                            res.append(player)
                    return res

                case EnumGroupFilter.top:
                    for player in players:
                        data = self.players_dict[player]
                        if data.tank is not None and data.tank.tier == self.battle_tier:
                            res.append(player)
                    return res
                case EnumGroupFilter.bottom:
                    for player in players:
                        data = self.players_dict[player]
                        if data.tank is not None and data.tank.tier < self.battle_tier:
                            res.append(player)
                    return res
        except Exception as err:
            error(err)
        return []

    def get_stats_queries(self, stats_type: StatsType) -> Set[StatsQuery]:
        queries: Set[StatsQuery] = set()

        for account_id in self.get_players():
            query = StatsQuery(account_id=account_id, stats_type=stats_type)
            match stats_type:
                case "tier":
                    query.tier = self.battle_tier
                case "tank":
                    query.tank_id = self.players_dict[account_id].vehicle_descr
        return queries


# @dataclass
# class StringStore:
#     value: str

#     def get(self) -> str:
#         return self.value

#     def record(self, value: Self) -> None:
#         raise ValueError("cannot overwrite StringStore")


@dataclass
class ValueStore:
    """
    ValueStore stores a single cell's value for the reports
    """

    value: int | float = 0
    n: int | float = 0

    # def get(self) -> Self:
    #     return self

    def record(self, value: Self):
        self.value += value.value
        self.n += value.n


ValueType = Tuple[int | float, int | float]
FieldKey = str
PLAYER_FIELD_PREFIX: Final[str] = "player."


@dataclass
class ReportField:
    """
    An abstract base class for "report fields" i.e. different measures what can be show on
    a single column on the analyzer reports.

    A concrete example: an AverageField() for a enemy teams' average win rate.
    """

    metric: ClassVar[str]

    name: str
    fields: str  # key, player.key or key,player.key
    format: str
    filter: PlayerFilter | None = None

    _replay_fields: ClassVar[List[str]] = [
        "battle_duration",
        "exp",
        "exp_total",
        "exp_free",
        "exp_free_base",
        "exp_penalty",
        "credits_penalty",
        "credits_contribution_in",
        "credits_contribution_out",
        "enemies_spotted",
        "enemies_destroyed",
        "damage_assisted",
        "damage_made",
        "credits_base",
        "credits_total",
        "repair_cost",
    ]

    _player_fields: ClassVar[List[str]] = [
        f"player.{key}"
        for key in [
            "base_capture_points",
            "base_defend_points",
            "credits",
            "damage_assisted",
            "damage_assisted_track",
            "damage_blocked",
            "damage_made",
            "damage_received",
            "death_reason",
            "distance_travelled",
            "enemies_damaged",
            "enemies_destroyed",
            "enemies_spotted",
            "exp",
            "exp_for_assist",
            "exp_for_damage",
            "exp_team_bonus",
            "hero_bonus_credits",
            "hero_bonus_exp",
            "hitpoints_left",
            "hits_bounced",
            "hits_pen",
            "hits_received",
            "hits_splash",
            "shots_made",
            "shots_hit",
            "shots_pen",
            "shots_splash",
            "wp_points_earned",
            "wp_points_stolen",
        ]
    ]

    # _fields: ClassVar[Set[str]] = data_field(default_factory=set)
    _fields: ClassVar[Set[str]] = {f for f in _player_fields + _replay_fields}

    _field: str = ""

    def __post_init__(self: Self) -> None:
        debug(f"called: {type(self)}")
        self._field = self.check_field_config()

    @abstractmethod
    def calc(self, replay: EnrichedReplay) -> ValueStore:
        raise NotImplementedError

    @property
    def key(self) -> FieldKey:
        if self.filter is None:
            return "-".join([self.metric, self.fields])
        else:
            return "-".join([self.metric, self.fields, self.filter.key])

    def is_player_field(self, field: str) -> bool:
        """Test if the field is player field (True) or replay field (False)"""
        return field.startswith(PLAYER_FIELD_PREFIX)

    def check_field_config(self, field: str | None = None) -> str:
        if field is None:
            field = self.fields
        if self.filter is None:
            if self.is_player_field(field):
                raise ValueError(
                    f"player field given even there is no filter defined: {field}"
                )
            return field
        elif field.startswith(PLAYER_FIELD_PREFIX):
            return field.removeprefix(PLAYER_FIELD_PREFIX)
        else:
            raise ValueError(
                f"Invalid field config: a player filter is defined, but 'fields' is not form of 'player.field_name': {field}"
            )

    # @abstractmethod
    # def record(self, value: ValueType):
    #     raise NotImplementedError

    @abstractmethod
    def value(self, value: ValueStore) -> int | float:
        """Return value"""
        raise NotImplementedError

    # def print(self, value: ValueType) -> str:
    #     return self.fmt.format(self.value(value))

    def print(self, value: ValueStore | str) -> str:
        """return value as formatted string"""
        if isinstance(value, str):
            return value
        else:
            return format(self.value(value=value), self.format)


@dataclass
class FieldStore:
    """
    Register of available field metrics and report fields
    """

    registry: ClassVar[Dict[str, Type[ReportField]]] = dict()
    db: Dict[FieldKey, ReportField] = data_field(default_factory=dict)

    @classmethod
    def register(cls, measure: Type[ReportField]):
        cls.registry[measure.metric] = measure

    def create(
        self,
        name: str,
        metric: str,
        fields: str,
        format: str,
        filter: str | None = None,
    ) -> ReportField:
        """Create a Field from specification

        Format:

        * filter: team_filter:group_filter
        * fields: replay_field,player.player_field
        """
        try:
            player_filter: PlayerFilter | None = None
            if filter is not None:
                player_filter = PlayerFilter.from_str(filter=filter)

            try:
                field_type: Type[ReportField] = self.registry[metric]
            except KeyError:
                raise ValueError(f"unsupported metric: {metric}")

            field = field_type(
                name=name, filter=player_filter, fields=fields, format=format
            )

            if field.key not in self.db:
                self.db[field.key] = field
            return self.db[field.key]
        except Exception as err:
            error(
                f"could not create metric: metric={metric}, filter={filter}, fields={fields}"
            )
            error(err)
            raise err

    def items(self) -> List[Tuple[FieldKey, ReportField]]:
        """Return list of stored keys & fields as tuples"""
        return list(self.db.items())

    def keys(self) -> List[FieldKey]:
        """return field keys"""
        return list(self.db.keys())

    def fields(self) -> List[ReportField]:
        """Return a list of ReportFields"""
        return list(self.db.values())

    @classmethod
    def ops(cls) -> List[str]:
        return list(cls.registry.keys())


@dataclass
class CountField(ReportField):
    metric = "count"
    fields = "exp"

    def calc(self, replay: EnrichedReplay) -> ValueStore:
        if self.filter is None:
            return ValueStore(1, 1)
        else:
            return ValueStore(len(replay.get_players(self.filter)), 1)

    def value(self, value: ValueStore) -> int:
        v: int | float = value.value
        if isinstance(v, int):
            return v
        raise TypeError("value is not int")


FieldStore.register(CountField)


@dataclass
class SumField(ReportField):
    metric = "sum"

    # def __post_init__(self: Self) -> None:
    #     """Remove 'player.' from 'fields'"""
    #     self._field = self.check_field_config()

    def calc(self, replay: EnrichedReplay) -> ValueStore:
        if self.filter is None:
            try:
                return ValueStore(getattr(replay, self._field), 1)
            except AttributeError:
                debug(f"not attribute '{self.fields}' found in replay: {replay.title}'")
                return ValueStore(0, 0)
        else:
            res: int = 0
            n: int = 0
            for p in replay.get_players(self.filter):
                try:
                    res += getattr(replay.players_dict[p], self._field)
                    n += 1
                except AttributeError:
                    debug(
                        f"not attribute '{self.fields}' found in replay: {replay.title}'"
                    )
            return ValueStore(res, n)

    def value(self, value: ValueStore) -> int | float:
        return value.value


FieldStore.register(SumField)


@dataclass
class AverageField(SumField):
    metric = "average"

    def calc(self, replay: EnrichedReplay) -> ValueStore:
        if self.filter is None:
            try:
                return ValueStore(getattr(replay, self._field), 1)
            except AttributeError:
                debug(f"not attribute '{self.fields}' found in replay: {replay.title}'")
                return ValueStore(0, 0)
        else:
            res: int = 0
            n: int = 0
            for p in replay.get_players(self.filter):
                try:
                    res += getattr(replay.players_dict[p], self._field)
                    n += 1
                except AttributeError:
                    debug(
                        f"not attribute '{self.fields}' found in replay: {replay.title}'"
                    )
            return ValueStore(res, n)

    def value(self, value: ValueStore) -> float:
        return value.value / value.n


FieldStore.register(AverageField)

CmpOps = Literal["eq", "gt", "lt", "gte", "lte"]


@dataclass
class AverageIfField(SumField):
    metric = "average_if"

    _if_value: float = 1
    _if_ops: CmpOps = "eq"
    _field_re: ClassVar[re.Pattern] = compile(r"^([a-z_.]+)([<=>])(-?[0-9.])$")

    def __post_init__(self) -> None:
        debug(f"called: {type(self)}")
        try:
            if (m := match(self._field_re, self.fields)) is None:
                raise ValueError(
                    f"invalid 'fields' specification: {self.fields}. format = 'FIELD[<|=|>]VALUE', e.g. top_tier=1"
                )

            self._field = self.check_field_config(m.group(1))
            match m.group(2):
                case "=":
                    self._if_ops = "eq"
                case ">":
                    self._if_ops = "gt"
                case "<":
                    self._if_ops = "lt"
                case other:
                    raise ValueError(f"invalid comparison operator {other}")
            self._if_value = float(m.group(3))

        except Exception as err:
            error(f"invalid field config: {self.fields}")
            error(err)
            raise

    def _test_if(self, value: int | float) -> int:
        match self._if_ops:
            case "eq":
                return int(value == self._if_value)
            case "gt":
                return int(value > self._if_value)
            case "lt":
                return int(value < self._if_value)
            case other:
                raise ValueError(f"invalid IF metric: {other}")

    def calc(self, replay: EnrichedReplay) -> ValueStore:
        if self.filter is None:
            try:
                return ValueStore(self._test_if(getattr(replay, self._field)), 1)
            except AttributeError:
                debug(f"not attribute '{self._field}' found in replay: {replay.title}'")
                return ValueStore(0, 0)
        else:
            res: int = 0
            n: int = 0
            for p in replay.get_players(self.filter):
                try:
                    res += self._test_if(getattr(replay.players_dict[p], self._field))
                    n += 1
                except AttributeError:
                    debug(
                        f"not attribute '{self._field}' found in replay: {replay.title}'"
                    )
            return ValueStore(res, n)

    def value(self, value: ValueStore) -> float:
        return value.value / value.n


FieldStore.register(AverageIfField)


@dataclass
class MinField(ReportField):
    """
    Field for finding min value
    """

    metric = "min"

    def calc(self, replay: EnrichedReplay) -> ValueStore:
        if self.filter is None:
            return ValueStore(getattr(replay, self._field), 1)
        else:
            res: float = 10e8  # big enough
            n = 0
            for p in replay.get_players(self.filter):
                res = min(
                    getattr(
                        replay.players_dict[p],
                        self._field,
                        10.0e8,
                    ),
                    res,
                )
                n += 1
            return ValueStore(res, n)

    def value(self, value: ValueStore) -> float | int:
        return value.value


FieldStore.register(MinField)


@dataclass
class MaxField(ReportField):
    """
    Field for finding max value
    """

    metric = "max"

    def calc(self, replay: EnrichedReplay) -> ValueStore:
        if self.filter is None:
            return ValueStore(getattr(replay, self._field), 1)
        else:
            res: float = -10e8  # small enough
            n = 0
            for p in replay.get_players(self.filter):
                res = max(
                    getattr(replay.players_dict[p], self._field, -1),
                    res,
                )
                n += 1
            return ValueStore(res, n)

    def value(self, value: ValueStore) -> float | int:
        return value.value


FieldStore.register(MaxField)


@dataclass
class RatioField(SumField):
    metric = "ratio"

    _value_field: str = ""
    _div_field: str = ""
    _is_player_field_value: bool = False
    _is_player_field_div: bool = False

    def __post_init__(self):
        debug(f"called: {type(self)}")
        try:
            self._value_field, self._div_field = self.fields.split(",")
            if self.is_player_field(self._value_field):
                self._value_field = self.check_field_config(self._value_field)
                self._is_player_field_value = True
            if self.is_player_field(self._div_field):
                self._div_field = self.check_field_config(self._div_field)
                self._is_player_field_div = True
        except Exception as err:
            error(f"invalid field config: {self.fields}")
            error("'ratio' metric's field key is format 'value_field,divider_field'")
            error(err)
            raise

    def calc(self, replay: EnrichedReplay) -> ValueStore:
        if self.filter is None:
            try:
                return ValueStore(
                    getattr(replay, self._value_field), getattr(replay, self._div_field)
                )
            except AttributeError as err:
                debug(
                    f"no attribute '{self._value_field}' or '{self._div_field}' found in replay: {replay.title}'"
                )
                error(err)
                return ValueStore(0, 0)
        else:
            val: float = 0
            div: float = 0

            if not self._is_player_field_value:
                val = getattr(replay, self._value_field)
            if not self._is_player_field_div:
                div = getattr(replay, self._div_field)
            if self._is_player_field_value or self._is_player_field_div:
                for p in replay.get_players(self.filter):
                    try:
                        if self._is_player_field_value:
                            val += getattr(replay.players_dict[p], self._value_field)
                        else:
                            div += getattr(replay, self._div_field)
                        if self._is_player_field_div:
                            div += getattr(replay.players_dict[p], self._div_field)
                        else:
                            val += getattr(replay, self._value_field)
                    except AttributeError as err:
                        debug(
                            f"not attribute 'players_data.{self._value_field}' found in replay: {replay.title}'"
                        )
                        error(err)

            return ValueStore(val, div)

    def value(self, value: ValueStore) -> float:
        return value.value / value.n


FieldStore.register(RatioField)


############################################################################################
#
# Categorizations
#
############################################################################################


def default_ValueStore() -> ValueStore:
    return ValueStore()


class Category:
    def __init__(
        self,
        # title: str,
    ) -> None:
        # self.title: str = title
        # self.fields: List[str]
        self.values: Dict[FieldKey, ValueStore] = defaultdict(default_ValueStore)
        self.strings: Dict[FieldKey, str] = dict()

    # def __post_init__(self) -> None:
    #     for field in self.fields:
    #         self.values[field] = ValueStore()

    def record(self, field: FieldKey, value: ValueStore | str) -> None:
        try:
            if isinstance(value, FieldKey):
                self.strings[field] = value
            else:
                self.values[field].record(value)
        except KeyError as err:
            error(err)
        except Exception as err:
            error(err)
        return None

    def get(self, field: FieldKey) -> ValueStore | str:
        if field in self.values:
            return self.values[field]
        elif field in self.strings:
            return self.strings[field]
        else:
            raise KeyError(f"field not found in category: {field}")


def default_Category() -> Category:
    return Category()


CategoryKey = str


class Categorization(ABC):
    """
    Abstract base class for replay categorization
    """

    categorization: ClassVar[str] = "<NOT DEFINED>"

    def __init__(self, name: str):
        self.name: str = name
        # self._battles: int = 0
        # self._field: str = field
        self._categories: Dict[CategoryKey, Category] = defaultdict(default_Category)

    @property
    def categories(self) -> List[CategoryKey]:
        """Get category keys sorted"""
        return sorted(self._categories.keys(), key=str.casefold)

    @abstractmethod
    def get_category(self, replay: EnrichedReplay) -> Category | None:
        """Get category for a replay"""
        raise NotImplementedError("needs to implement in subclasses")

    @classmethod
    def help(cls) -> None:
        """Print help"""
        print(f'categorization = "{cls.categorization}": {cls.__doc__}')

    def print(self, fields: FieldStore) -> None:
        """Print a report"""
        header: List[str] = [field.name for field in fields.fields()]
        data: List[List[str]] = list()
        for cat_key in self.categories:
            cat: Category = self._categories[cat_key]
            row: List[str] = [cat_key]
            for field_key, field in fields.items():
                row.append(field.print(cat.get(field=field_key)))
            data.append(row)
        tabulate(data, headers=header)


class Reports:
    """
    Reports to create
    """

    _db: ClassVar[Dict[str, Type[Categorization]]] = dict()

    def __init__(self) -> None:
        self._reports: Dict[str, Categorization] = dict()

    def add(self, key: str, name: str, categorization: str, **kwargs):
        """
        Add a report
        """
        try:
            cat: Type[Categorization] = self._db[categorization]
            if key in self._reports:
                raise KeyError(f"duplicate definition of report='{key}'")
            self._reports[key] = cat(name=name, **kwargs)
        except KeyError as err:
            error(
                f"could not create report: key={key}, name={name}, categorization={categorization}, {', '.join('='.join([k,v]) for k,v in kwargs.items())}"
            )
            error(err)
            raise
        except Exception as err:
            error(err)
            raise

    @property
    def reports(self) -> List[Categorization]:
        return list(self._reports.values())

    def get(self, key: str) -> Categorization | None:
        """Get a report by key"""
        try:
            return self._reports[key]
        except KeyError:
            error(f"no report with key={key} defined")
        return None

    @classmethod
    def register(cls, categorization: Type[Categorization]):
        """Register a known report type"""
        cls._db[categorization.categorization] = categorization

    def print(self, fields: FieldStore) -> None:
        """Print reports"""
        for report in self._reports.values():
            print()
            print(report.name.upper())
            report.print(fields)


class Totals(Categorization):
    """
    Calculate overall stats over all replays
    """

    categorization = "total"

    def __init__(self, name: str):
        super().__init__(name="Total")
        self._categories["Total"] = Category()

    def get_category(self, replay: EnrichedReplay) -> Category | None:
        return self._categories["Total"]

    @classmethod
    def help(cls) -> None:
        print(f'categorization = "{cls.categorization}" reports stats over all replays')


Reports.register(Totals)


class IntCategorization(Categorization):
    """
    Categorize replays based on a replay field's integer value.
    """

    categorization = "category"

    def __init__(self, name: str, field: str, categories: List[str]):
        super().__init__(name=name)
        self._field: str = field
        self._category_cache: Dict[int, str] = dict()
        for ndx, cat in enumerate(categories):
            self._category_cache[ndx] = cat

    def get_category(self, replay: EnrichedReplay) -> Category | None:
        try:
            field_value: int = getattr(replay, self._field)
            category: CategoryKey = self._category_cache[field_value]
            return self._categories[category]
        except AttributeError:
            error(f"no field={self._field} found in replay: {replay.title}")
        except KeyError as err:
            error(err)
        return None


Reports.register(IntCategorization)


############################################################################################
#
# Test
#
############################################################################################


# _ratio_fields_value: List[str] = []

# _ratio_fields_div: List[str] = []

# for team, group, ops, field in product(
#     EnumTeamFilter, EnumGroupFilter, FieldStore.ops(), ReportField._replay_fields
# ):
#     print(f"{team}-{group}-{ops}-{field}")

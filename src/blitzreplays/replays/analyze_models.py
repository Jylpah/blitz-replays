import logging
from typing import List, Self, Dict, Tuple, Set, ClassVar, Type, Literal
from pydantic import Field, model_validator
from abc import abstractmethod
from itertools import product
from asyncio import sleep

from pyutils import IterableQueue, QueueDone
from pydantic_exportables import JSONExportable
from blitzmodels import WGApi, TankStat, Region, AccountInfo
from blitzmodels.wotinspector.wi_apiv2 import Replay, PlayerData
from blitzmodels.wotinspector.wi_apiv1 import EnumBattleResult
from blitzmodels import Tank, WGApiWoTBlitzTankopedia, EnumVehicleTypeStr, Maps, Map
from enum import StrEnum
from dataclasses import dataclass, field as data_field

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
    # _group = TypeAdapter(Literal["default", "all","solo", "plat", "lt", "mt", "ht", "td", "top", "bottom" ])

    def __str__(self) -> str:
        return f"{self.team}:{self.group}"

    @classmethod
    def from_str(cls, filter: str) -> "PlayerFilter":
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
            raise ValueError("incorrect filter format: {filter} != '<team>:<group>'")
        return PlayerFilter(team=team, group=group)


StatsType = Literal["player", "tier", "tank"]


class PlayerStats(JSONExportable):
    # stat_type: StatsType
    account_id: int
    tank_id: int = 0
    tier: int = 0
    wr: float = 0
    avgdmg: float = 0
    battles: int = 0
    tier_wr: float = 0
    tier_avgdmg: float = 0
    tier_battles: int = 0
    tank_wr: float = 0
    tank_avgdmg: float = 0
    tank_battles: int = 0

    # @property
    # def key(self) -> str:
    #     return StatsCache.stat_key(self.account_id, self.tier, self.tank_id)

    @classmethod
    def from_tank_stat(cls, ts=TankStat) -> "PlayerStats":
        return PlayerStats(
            account_id=ts.account_id,
            tank_id=ts.tank_id,
            tank_wr=ts.all.wins / ts.all.battles,
            tank_avgdmg=ts.all.damage_dealt / ts.all.battles,
            tank_battles=ts.all.battles,
        )

    @classmethod
    def tank_stats(cls, stats: List[TankStat]) -> List["PlayerStats"]:
        """Create PlayerStats from WG API Tank Stats for each tank"""
        res: List[PlayerStats] = list()
        for ts in stats:
            res.append(PlayerStats.from_tank_stat(ts))
        return res

    @classmethod
    def tier_stats(
        cls, account_id: int, stats: List[TankStat], tier: int
    ) -> "PlayerStats":
        """
        Create PlayerStats from WG API Tank Stats

        Assumes all the TankStats are for the same tier tanks
        """

        res: PlayerStats = PlayerStats(account_id=account_id, tier=tier)
        try:
            for ts in stats:
                res.tier_battles = res.tier_battles + ts.all.battles
                res.tier_wr = res.tier_wr + ts.all.wins
                res.tier_avgdmg = res.tier_avgdmg + ts.all.damage_dealt

            res.tier_wr = res.tier_wr / res.tier_battles
            res.tier_avgdmg = res.tier_avgdmg / res.tier_battles
        except Exception as err:
            debug(err)
        return res

    @classmethod
    def player_stats(cls, stats: AccountInfo) -> "PlayerStats":
        """ "Create PlayerStats from WG API Tank Stats"""

        try:
            if (
                stats.statistics is not None
                and (ps := stats.statistics["all"]) is not None
            ):
                return PlayerStats(
                    account_id=stats.account_id,
                    wr=ps.wins / ps.battles,
                    avgdmg=ps.damage_dealt / ps.battles,
                    battles=ps.battles,
                )
        except KeyError:
            debug(f"no player stats for account_id={stats.account_id}")
        return PlayerStats(account_id=stats.account_id)


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

    account_id: int
    stats_type: StatsType
    tier: int = 0
    tank_id: int = 0


class StatsCache:
    def __init__(self: Self, wg_api: WGApi, statsQ: IterableQueue[StatsQuery]):
        """creator of StatsCache must add_producer() to the statsQ before calling __init__()"""
        self._db: Dict[str, PlayerStats] = dict()
        self._query_cache: Set[str] = set()
        self._wg_api = wg_api
        self._Q: IterableQueue[StatsQuery] = statsQ

    @classmethod
    def stat_key(
        cls,
        stats_type: StatsType,
        account_id: int = 0,
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

    async def player_stats_worker(self) -> None:
        """Async worker for retrieving player stats"""
        # TODO: add database cache
        regionQ: Dict[Region, Set[int]] = dict()
        region: Region
        res: Dict[str, PlayerStats]
        debug("starting")
        for region in Region.API_regions():
            regionQ[region] = set()

        async for stats_query in self._Q:
            try:
                region = Region.from_id(stats_query.account_id)
                regionQ[region].add(stats_query.account_id)
                if len(regionQ[region]) == 100:
                    res = await self.get_player_stats(
                        account_ids=regionQ[region], region=region
                    )
                    self._db.update(res)
                    regionQ[region] = set()
            except QueueDone:
                debug("finished")

            except Exception as err:
                error(err)
            for region, account_ids in regionQ.items():
                if len(account_ids) > 0:
                    res = await self.get_player_stats(account_ids, region=region)
                    self._db.update(res)

    async def get_player_stats(
        self, account_ids: Set[int], region: Region
    ) -> Dict[str, PlayerStats]:
        """
        Actually fetch the player stats from WG API
        """
        fields: List[str] = [
            "account_id",
            "last_battle_time",
            "statistics.all.battles",
            "statistics.all.wins",
            "statistics.all.damage_dealt",
        ]
        res: Dict[str, PlayerStats] = dict()
        if (
            player_stats := await self._wg_api.get_account_info(
                account_ids=list(account_ids),
                region=region,
                fields=fields,
            )
        ) is not None:
            for player_stat in player_stats:
                key = self.stat_key(
                    stats_type="player",
                    account_id=player_stat.account_id,
                )
                res[key] = PlayerStats.player_stats(player_stat)
                account_ids.remove(player_stat.account_id)

        if len(account_ids) > 0:
            for account_id in account_ids:
                key = self.stat_key(
                    stats_type="player",
                    account_id=account_id,
                )
                res[key] = PlayerStats(account_id=account_id)
        return res

    async def get_stats(
        self,
        stats_type: StatsType,
        account_id: int,
        tier: int = 0,
        tank_id: int = 0,
    ) -> PlayerStats:
        # TODO: if stats not in db, fetch those
        # TODO: if fetched stats are None, store None
        key: str = self.stat_key(stats_type, account_id, tier, tank_id)

        if key not in self._query_cache:
            self._query_cache.add(key)
            await self._Q.put(
                StatsQuery(
                    account_id=account_id,
                    stats_type=stats_type,
                    tier=tier,
                    tank_id=tank_id,
                )
            )

        while True:
            try:
                return self._db[key]
            except KeyError:
                await sleep(2)


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

    def add_stats(self, stats: PlayerStats):
        self.wr = stats.wr
        self.avgdmg = stats.avgdmg
        self.battles = stats.battles

        self.tier_wr = stats.tier_wr
        self.tier_avgdmg = stats.tier_avgdmg
        self.tier_battles = stats.tier_battles

        self.tank_wr = stats.tank_wr
        self.tank_avgdmg = stats.tank_avgdmg
        self.tank_battles = stats.tank_battles


class EnrichedReplay(Replay):
    players_dict: Dict[int, EnrichedPlayerData] = Field(default_factory=dict)
    player: int = -1
    plat_mate: List[int] = Field(default_factory=list)
    battle_tier: int = 0
    map: Map | None = None

    @model_validator(mode="after")
    def read_players_dict(self) -> Self:
        for data in self.players_data:
            self.players_dict[data.dbid] = EnrichedPlayerData.model_validate(data)
        self.players_data = list()
        return self

    async def enrich(
        self,
        stats_cache: StatsCache,
        stats_type: StatsType,
        tankopedia: WGApiWoTBlitzTankopedia,
        maps: Maps,
        player: int = -1,
    ):
        data: EnrichedPlayerData
        # add tanks
        for account_id in self.players_dict:
            data = self.players_dict[account_id]
            tank_id: int = data.vehicle_descr
            try:
                tank: Tank = tankopedia[tank_id]
                data.tank = tank
                self.battle_tier = max(self.battle_tier, int(tank.tier))
            except KeyError:
                debug(f"could not find tank_id={tank_id} from Tankopedia")

        # add player stats
        for account_id in self.players_dict:
            data = self.players_dict[account_id]
            await data.add_stats(
                await stats_cache.get_stats(
                    stats_type, account_id, self.battle_tier, self.vehicle_descr
                )
            )

        # set player
        if player < 0:
            self.player = self.protagonist
        elif player in self.allies:
            self.player = player
        elif player in self.enemies:  # swapt teams
            tmp_team: list[int] = self.allies
            self.allies = self.enemies
            self.enemies = tmp_team
            if self.battle_result == EnumBattleResult.win:
                self.battle_result = EnumBattleResult.loss
            elif self.battle_result == EnumBattleResult.loss:
                self.battle_result = EnumBattleResult.win
        else:
            raise ValueError(f"no account_id={player} in the replay")

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

    def get_players(self, filter: PlayerFilter) -> List[int]:
        """
        Get players matching the filter from the replay
        """
        players: List[int] = list()
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
                    return [self.player] + self.plat_mate + self.allies + self.enemies

        elif filter.team == EnumTeamFilter.allies:
            players = self.allies
        elif filter.team == EnumTeamFilter.enemies:
            players = self.enemies
        elif filter.team == EnumTeamFilter.all:
            players = self.allies + self.enemies

        res: list[int] = list()
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
                tank_type = EnumVehicleTypeStr.heavy_tank
                match filter.group:
                    case EnumGroupFilter.tank_destroyer:
                        tank_type = EnumVehicleTypeStr.tank_destroyer
                    case EnumGroupFilter.medium_tank:
                        tank_type = EnumVehicleTypeStr.medium_tank
                    case EnumGroupFilter.light_tank:
                        tank_type = EnumVehicleTypeStr.light_tank
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
        return []


ValueType = Tuple[str | float | int, int | float]


@dataclass
class Metric:
    operation: ClassVar[str]

    field: str  # key or data.key
    # name: str
    # fmt: str
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

    _fields: Set[str] = set(_player_fields + _replay_fields)

    def rm_prefix(self, field: str) -> str:
        """Remove xxxx. from the beginning of the field"""
        if len(field.split(".")) > 1:
            return ".".join(field.split(".")[1:])
        else:
            return field

    def __post__init__(self):
        for fld in self.field.split(","):
            if fld not in self._fields:
                raise ValueError(f"field '{fld}' is not found in replays")
        if (
            "," not in self.field
        ):  # multi-fields have be dealt in each child class separately
            self.field = self.rm_prefix(self.field)

    @abstractmethod
    def calc(self, replay: EnrichedReplay) -> ValueType:
        raise NotImplementedError

    @property
    def key(self) -> str:
        if self.filter is None:
            return "-".join([self.operation, self.field])
        else:
            return "-".join(
                [self.filter.team, self.filter.group, self.operation, self.field]
            )

    # @abstractmethod
    # def record(self, value: ValueType):
    #     raise NotImplementedError

    @abstractmethod
    def value(self, value: ValueType) -> str | int | float:
        """Return value"""
        raise NotImplementedError

    # def print(self, value: ValueType) -> str:
    #     return self.fmt.format(self.value(value))


@dataclass
class Metrics:
    """
    An abstract base class for "metrics" i.e. different measures what can be show on
    a single column on the analyzer reports.

    A concrete example: an AverageMetric() for a enemy teams' average win rate.
    """

    measures: ClassVar[Dict[str, Type[Metric]]] = dict()
    db: Dict[str, Metric] = data_field(default_factory=dict)

    @classmethod
    def register(cls, measure: Type[Metric]):
        cls.measures[measure.operation] = measure

    def parse(self, keystr: str) -> Metric:
        """Parse a config for a Metric

        Format is:
        player_measure: team_filter-group_filter-field_operation-fields
        replay measure: field_operation-fields

        where the 'key' has to be unique
        """
        try:
            team_filter: str | None = None
            group_filter: str | None = None
            key: List[str] = keystr.split("-")
            if len(key) == 2:
                ops, fields = key
            elif len(key) == 4:
                team_filter, group_filter, ops, fields = key
            else:
                raise ValueError(f"invalid metric key: {keystr}")

            if keystr not in self.db:
                metric: Type[Metric] = CountMetric
                match ops:
                    case "count":
                        metric = CountMetric
                    case "sum":
                        metric = SumMetric
                    case "avg":
                        metric = AverageMetric
                    case "min":
                        metric = MinMetric
                    case "max":
                        metric = MaxMetric
                    case "ratio":
                        metric = RatioMetric
                    case _:
                        raise ValueError(f"unsupported field operation key: {ops}")
                if team_filter is not None and group_filter is not None:
                    self.db[keystr] = metric(
                        filter=PlayerFilter(
                            team=EnumTeamFilter(team_filter),
                            group=EnumGroupFilter(group_filter),
                        ),
                        field=fields,
                    )
                else:
                    self.db[keystr] = metric(
                        filter=None,
                        field=fields,
                    )
            return self.db[keystr]
        except Exception as err:
            error(f"could not parse metric from: {keystr}")
            error(err)
            raise err

    @classmethod
    def ops(cls) -> List[str]:
        return list(cls.measures.keys())


class CountMetric(Metric):
    operation = "count"

    def calc(self, replay: EnrichedReplay) -> ValueType:
        if self.filter is None:
            return 1, 1
        else:
            return len(replay.get_players(self.filter)), 1

    def value(self, value: ValueType) -> int:
        v: int | float | str = value[0]
        if isinstance(v, int):
            return v
        raise TypeError("value is not int")


Metrics.register(CountMetric)


class SumMetric(Metric):
    operation = "sum"

    def calc(self, replay: EnrichedReplay) -> ValueType:
        if self.filter is None:
            try:
                return getattr(replay, self.field), 1
            except AttributeError:
                debug(f"not attribute '{self.field}' found in replay: {replay.title}'")
                return 0, 0
        else:
            res: int = 0
            n: int = 0
            for p in replay.get_players(self.filter):
                try:
                    res += getattr(replay.players_dict[p], self.field)
                    n += 1
                except AttributeError:
                    debug(
                        f"not attribute 'players_data.{self.field}' found in replay: {replay.title}'"
                    )
            return res, n

    def value(self, value: ValueType) -> int | float:
        v: int | float | str = value[0]
        if isinstance(v, str):
            raise TypeError("value cannot be string")
        return v


Metrics.register(SumMetric)


class AverageMetric(SumMetric):
    operation = "avg"

    def calc(self, replay: EnrichedReplay) -> ValueType:
        if self.filter is None:
            try:
                return getattr(replay, self.field), 1
            except AttributeError:
                debug(f"not attribute '{self.field}' found in replay: {replay.title}'")
                return 0, 0
        else:
            res: int = 0
            n: int = 0
            for p in replay.get_players(self.filter):
                try:
                    res += getattr(replay.players_dict[p], self.field)
                    n += 1
                except AttributeError:
                    debug(
                        f"not attribute 'players_data.{self.field}' found in replay: {replay.title}'"
                    )
            return res, n

    def value(self, value: ValueType) -> float:
        v: int | float | str = value[0]
        if isinstance(v, str):
            raise TypeError("value cannot be string")
        return v / value[1]


Metrics.register(AverageMetric)


class MinMetric(Metric):
    """
    Metric for finding min value
    """

    operation = "min"

    def calc(self, replay: EnrichedReplay) -> ValueType:
        if self.filter is None:
            return getattr(replay, self.field), 1
        else:
            res: float = 10e8  # big enough
            n = 0
            for p in replay.get_players(self.filter):
                res = min(getattr(replay.players_dict[p], self.field, 10.0e8), res)
                n += 1
            return res, n

    def value(self, value: ValueType) -> float | int:
        v: int | float | str = value[0]
        if isinstance(v, str):
            raise TypeError("value cannot be string")
        return v


Metrics.register(MinMetric)


class MaxMetric(Metric):
    """
    Metric for finding max value
    """

    operation = "max"

    def calc(self, replay: EnrichedReplay) -> ValueType:
        if self.filter is None:
            return getattr(replay, self.field), 1
        else:
            res: float = -10e8  # small enough
            n = 0
            for p in replay.get_players(self.filter):
                res = max(getattr(replay.players_dict[p], self.field, -1), res)
                n += 1
            return res, n

    def value(self, value: ValueType) -> float | int:
        v: int | float | str = value[0]
        if isinstance(v, str):
            raise TypeError("value cannot be string")
        return v


Metrics.register(MaxMetric)


class RatioMetric(SumMetric):
    operation = "ratio"

    _value_field: str = ""
    _div_field: str = ""
    _is_player_field_value: bool = False
    _is_player_field_div: bool = False

    def __post__init__(self):
        super().__post__init__(self)
        try:
            self._value_field, self._div_field = self.field.split(",")
            if len(parts := self._value_field.split(".")) == 2:
                self._is_player_field_value = True
                self._value_field = parts[1]
            if len(parts := self._div_field.split(".")) == 2:
                self._is_player_field_div = True
                self._div_field = parts[1]
        except Exception as err:
            error(f"invalid field config: {self.field}")
            error("'ratio' metric's field key is format 'value_field,divider_field'")
            error(err)
            raise

    def calc(self, replay: EnrichedReplay) -> ValueType:
        if self.filter is None:
            try:
                return getattr(replay, self._value_field), getattr(
                    replay, self._div_field
                )
            except AttributeError as err:
                debug(
                    f"no attribute '{self._value_field}' or '{self._div_field}' found in replay: {replay.title}'"
                )
                error(err)
                return 0, 0
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

            return val, div

    def value(self, value: ValueType) -> float:
        v: int | float | str = value[0]
        if isinstance(v, str):
            raise TypeError("value cannot be string")
        return v / value[1]


Metrics.register(RatioMetric)

############################################################################################
#
# Define fields
#
############################################################################################


_ratio_fields_value: List[str] = []

_ratio_fields_div: List[str] = []

for team, group, ops, field in product(
    EnumTeamFilter, EnumGroupFilter, Metrics.ops(), Metric._replay_fields
):
    print(f"{team}-{group}-{ops}-{field}")

import logging
from typing import (
    List,
    Self,
    Dict,
    Optional,
    Literal,
    Iterable,
)
from pydantic import Field, model_validator, ConfigDict

from pydantic_exportables import JSONExportable
from blitzmodels import (
    AccountId,
    EnumVehicleTypeStr,
    Maps,
    Tank,
    TankStat,
    TankId,
    WGApiWoTBlitzTankopedia,
)
from result import Result, Err, Ok
from blitzmodels.wotinspector.wi_apiv2 import Replay, PlayerData
from blitzmodels.wotinspector.wi_apiv1 import EnumBattleResult

from .args import StatsType, StatsMeasure, EnumTeamFilter, EnumGroupFilter, PlayerFilter

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug


def stat_key(
    stats_type: StatsType,
    account_id: AccountId,
    tier: int = 0,
    tank_id: int = 0,
) -> str:
    """
    create a stat key used to identify a StatsQuery or Single PlayerStats
    """
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

    model_config = ConfigDict(validate_assignment=False)

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

    @property
    def key(self) -> str:
        return stat_key(
            stats_type=self.stats_type,
            account_id=self.account_id,
            tier=self.tier,
            tank_id=self.tank_id,
        )

    @classmethod
    def mk_zero(
        cls,
        stats_type: StatsType,
        account_id: AccountId,
        tier: int = 0,
        tank_id: TankId = 0,
    ) -> Self:
        """
        create new zero-stats PlayerStats instance of 'stats_type'
        """
        ps = cls(account_id=account_id)
        match stats_type:
            case "tier":
                ps.tier = tier
            case "tank":
                ps.tank_id = tank_id
        return ps

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
        try:
            if ts.all.battles > 0:
                return cls(
                    account_id=ts.account_id,
                    tank_id=ts.tank_id,
                    battles=ts.all.battles,
                    wr=ts.all.wins / ts.all.battles,
                    avgdmg=ts.all.damage_dealt / ts.all.battles,
                )
        except Exception as err:
            error("%s: %s", type(err), err)
            error(f"could not transform TankStat: {ts.json_src()}")
        return cls.mk_zero(
            stats_type="tank", account_id=ts.account_id, tank_id=ts.tank_id
        )

    @classmethod
    def from_tank_stats(cls, stats=Iterable[TankStat], tier: int = 0) -> Optional[Self]:
        """
        Create an aggregate PlayerStats from a list of Iterable[TankStats]

        Creates tank
        """
        try:
            debug("stats=%s", str(stats))
            iter_stats = iter(stats)
            ts: TankStat = next(iter_stats)
            # res = cls(
            #     account_id=ts.account_id,
            #     tier=tier,
            #     wr=ts.all.wins / ts.all.battles,
            #     avgdmg=ts.all.damage_dealt / ts.all.battles,
            #     battles=ts.all.battles,
            # )
            res = cls.from_tank_stat(ts)
            res.tank_id = 0
            res.tier = tier
            for ts in iter_stats:
                try:
                    res.battles = res.battles + ts.all.battles
                    res.wr = res.wr + ts.all.wins
                    res.avgdmg = res.avgdmg + ts.all.damage_dealt
                except Exception as err:
                    error(f"{type(err)}: {err}")
            if res.battles > 0:
                res.wr = res.wr / res.battles
                res.avgdmg = res.avgdmg / res.battles
            else:
                res.wr = 0
                res.avgdmg = 0
            debug("account_id=%d, tier=%d: %s", res.account_id, res.tier, str(res))
            return res
        except StopIteration:
            debug("Null tank-stats")
        except Exception as err:
            error(f"{type(err)}: {err}")
        return None


TankType = Literal["light_tank", "medium_tank", "heavy_tank", "tank_destroyer", "-"]


class EnrichedPlayerData(PlayerData):
    # tank: Tank | None = None
    # player stats
    wr: float = 0
    avgdmg: float = 0
    battles: int = 0

    tank: str = "-"
    tank_id: TankId = 0
    tank_type: TankType = "-"
    tank_tier: int = 0
    tank_is_premium: bool = False
    tank_nation: str = "-"

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        validate_assignment=False,
    )

    def add_stats(self, stats: PlayerStats):
        """
        add stats to EnrichedReplay.EnrichedPlayerData

        NOT SUITABLE for storing over sessions since the same fields are used regardless of stat_type
        """

        self.wr = stats.wr
        self.avgdmg = stats.avgdmg
        self.battles = stats.battles


class EnrichedReplay(Replay):
    """
    EnrichedReplay to store additional metadata for speed up and simplify replay analysis
    """

    players_dict: Dict[AccountId, EnrichedPlayerData] = Field(default_factory=dict)
    player: AccountId = -1
    plat_mate: List[AccountId] = Field(default_factory=list)
    battle_tier: int = 0
    map: str = "-"
    top_tier: bool = False

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        validate_assignment=False,
    )

    @model_validator(mode="after")
    def read_players_dict(self) -> Self:
        for player_data in self.players_data:
            try:
                self.players_dict[player_data.dbid] = EnrichedPlayerData.model_validate(
                    player_data
                )
            except Exception:
                error(f"could not enrich player data for account_id={player_data.dbid}")
        self.players_data = list()
        return self

    async def enrich(
        self,
        tankopedia: WGApiWoTBlitzTankopedia,
        maps: Maps,
        player: AccountId = 0,
    ) -> Result[None, str]:
        """
        Prepare the (static) replay data for the particular analysis
        """

        data: EnrichedPlayerData
        if not self.is_complete:
            # message(f"replay is incomplete: {self.title}")
            return Err("replay is incomplete")

        # remove tournament observe
        # message()rs
        players: List[AccountId] = list()
        for player in self.allies:
            if player in self.players_dict:
                players.append(player)
        self.allies = players
        players = list()
        for player in self.enemies:
            if player in self.players_dict:
                players.append(player)
        self.enemies = players

        # add tanks
        for data in self.players_dict.values():
            tank_id: TankId = data.vehicle_descr
            try:
                tank: Tank = tankopedia[tank_id]
                data.tank = tank.name
                data.tank_id = tank.tank_id
                data.tank_type = tank.type.name  # type: ignore
                data.tank_tier = tank.tier.value
                data.tank_is_premium = tank.is_premium
                data.tank_nation = str(tank.nation)

                self.battle_tier = max(self.battle_tier, int(tank.tier))
            except KeyError:
                debug("could not find tank_id=%d from Tankopedia", tank_id)

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
            return Err(f"no account_id={self.player} in the replay")

        if self.player not in self.players_dict:
            return Err(f"account_id={self.player} is not a player in the replay")
        # set top_tier
        self.top_tier = self.players_dict[self.player].tank_tier == self.battle_tier

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
            self.map = maps[self.map_id].name
        except (KeyError, ValueError):
            verbose(f"WARNING: no map (id={self.map_id}) in Maps file")
        return Ok(None)

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
                    tank_type = EnumVehicleTypeStr[filter.group.name].name
                    for player in players:
                        data = self.players_dict[player]
                        if data.tank_type == tank_type:
                            res.append(player)
                    return res

                case EnumGroupFilter.top:
                    for player in players:
                        data = self.players_dict[player]
                        if data.tank_tier == self.battle_tier:
                            res.append(player)
                    return res
                case EnumGroupFilter.bottom:
                    for player in players:
                        data = self.players_dict[player]
                        if data.tank_tier < self.battle_tier:
                            res.append(player)
                    return res
        except Exception as err:
            error(err)
        return []

    def get_player_data(self, account_id: AccountId) -> EnrichedPlayerData:
        """Get player_data for account_id. Raise an exception if not found"""
        return self.players_dict[account_id]

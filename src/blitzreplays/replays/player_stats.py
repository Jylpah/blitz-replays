import logging
from typing import Self, Iterable, Optional
from pydantic import ConfigDict

from pydantic_exportables import JSONExportable

from blitzmodels import AccountId, TankId, TankStat

from .types import StatsType, StatsMeasure


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
    """
    Player's stats. Calculation depends on stats_type = player | tier | tank
    """

    # stat_type: StatsType
    account_id: AccountId
    tank_id: int = 0
    tier: int = 0

    wr: float = 0
    avgdmg: float = 0
    battles: int = 0
    last_battle_time: int = 0

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
                    last_battle_time=ts.last_battle_time,
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
                    res.last_battle_time = max(
                        res.last_battle_time, ts.last_battle_time
                    )
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

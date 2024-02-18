import logging
from typing import (
    Iterable,
    Tuple,
    Protocol,
    TypeVar,
    Generic,
    Self,
    Set,
    Optional,
)
from configparser import ConfigParser
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.exc import NoResultFound, InvalidRequestError
from sqlalchemy import Engine
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodel import Field, SQLModel, create_engine, select, Session
from pydantic import model_validator

# from icecream import ic  # type: ignore

from pyutils.utils import epoch_now
from pydantic_exportables import Idx, JSONExportableRootDict
from blitzmodels import (
    AccountId,
    AccountInfo,
    AccountInfoStats,
    TankId,
    TankStat,
    WGApiWoTBlitzAccountInfo,
    WGApiWoTBlitzTankStats,
)

from .types import LastBattleTime, StatsType
from .player_stats import PlayerStats


logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug


T = TypeVar("T")


class DBCache(Protocol[T]):
    @classmethod
    async def init(cls, stats_type: StatsType, config: ConfigParser) -> Self:
        """
        Init DB connection based on 'config'
        """

    async def get(
        self,
        stats_type: StatsType,
        account_id: AccountId,
        last_battle_time: LastBattleTime,
    ) -> T | None:
        """ "
        Get stats from DB cache.

        Raises KeyError if stats not found.
        """

    async def put(
        self,
        stats_type: StatsType,
        account_id: AccountId,
        last_battle_time: LastBattleTime,
        stats: T | None,
    ) -> bool:
        """ "
        Store stats from DB cache. Stats can be None.
        """

    async def prune(self, last_battle_time: LastBattleTime) -> Tuple[int, int]:
        """
        Prune stats older than 'last_battle_time' from the DB cache.

        Returns Tuple[pruned, left]
        """


class ApiPlayerStats(AccountInfo):
    """
    Helper class for PlayerStatsDict to store individual player's stats
    """

    stats: Optional[AccountInfoStats] = Field(default=None)

    @property
    def index(self) -> Idx:
        """return backend index"""
        return self.account_id

    @model_validator(mode="after")
    def populate_stats(self) -> Self:
        if self.statistics is not None and "all" in self.statistics:
            self._set_skip_validation("stats", self.statistics["all"])
        return self

    def get_player_stats(self) -> PlayerStats:
        ps = PlayerStats(account_id=self.account_id)
        if (acc_info_stats := self.stats) is not None:
            ps.battles = acc_info_stats.battles
            if ps.battles > 0:
                ps.avgdmg = acc_info_stats.damage_dealt / ps.battles
                ps.wr = acc_info_stats.wins / ps.battles
        return ps


class ApiTankStat(TankStat):
    """
    Helper class for TankStatsDict to store individual player's tank stats
    """

    @property
    def index(self) -> Idx:
        """return backend index"""
        return self.tank_id


class PlayerStatsDict(JSONExportableRootDict[AccountId, ApiPlayerStats]):
    """
    Helper class to store player stats in a dict vs list for search performance
    """

    @classmethod
    def from_WGApiWoTBlitzAccountInfo(
        cls, api_stats: WGApiWoTBlitzAccountInfo
    ) -> "PlayerStatsDict":
        res = cls()
        account_info = AccountInfo | None
        if api_stats.data is not None:
            try:
                for account_id, account_info in api_stats.data.items():
                    ps = ApiPlayerStats(account_id=int(account_id))
                    if (
                        account_info is not None
                        and (ps_conv := ApiPlayerStats.from_obj(account_info))
                        is not None
                    ):
                        res.add(ps_conv)
                    else:
                        res.add(ps)
            except KeyError:
                debug("no stats in WG API tank stats")
        return res


class TankStatsDict(JSONExportableRootDict[TankId, ApiTankStat]):
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
                        if (pts := ApiTankStat.from_obj(tank_stat)) is not None:
                            res.add(pts)
            except KeyError:
                debug("no stats in WG API tank stats")
        return res

    def get_many(self, tank_ids: Iterable[TankId]) -> Set[ApiTankStat]:
        res: Set[ApiTankStat] = set()
        for tank_id in tank_ids:
            try:
                res.add(self.root[tank_id])
            except KeyError:
                pass
        return res

    def get_player_stats(self) -> PlayerStats | None:
        return PlayerStats.from_tank_stats(self.root.values(), tier=0)

    def get_tank_stat(self, tank_id: TankId) -> PlayerStats | None:
        try:
            return PlayerStats.from_tank_stat(self.root[tank_id])
        except KeyError:
            error(f"no tank stat for tank_id={tank_id}")
        except Exception as err:
            error("%s: %s", type(err), err)
        return None

    def get_tank_stats(
        self, tank_ids: Iterable[TankId], tier: int = 0
    ) -> PlayerStats | None:
        return PlayerStats.from_tank_stats(
            [self.root[tank_id] for tank_id in tank_ids if tank_id in self.root],
            tier=tier,
        )

    @property
    def last_battle_time(self) -> int:
        last_battle_time: int = 0
        for ts in self.values():
            last_battle_time = max(last_battle_time, ts.last_battle_time)
        if last_battle_time > 0:
            return last_battle_time
        else:
            return epoch_now()


class PlayerStatsCache(SQLModel, table=True):
    """
    DB table definition for player stats
    """

    account_id: int = Field(default=..., primary_key=True)
    last_battle_time: int = Field(default=epoch_now())
    stats: Optional[ApiPlayerStats] = None


class TankStatsCache(SQLModel, table=True):
    """
    DB table definition for player tank-stats
    """

    account_id: int = Field(default=..., primary_key=True)
    last_battle_time: int = Field(default=epoch_now())
    stats: Optional[TankStatsDict] = None


class SQLCache:
    """
    SQLMolde based DBcache
    """

    def __init__(self, config: ConfigParser):
        if (db_fn := config.get("REPLAYS_ANALYZE", "db_path", fallback=None)) is None:
            raise ValueError(
                "No DB cache defined. Set 'REPLAYS_ANALYZE.db_path' in config"
            )
        db = config.get("REPLAYS_ANALYZE", "db", fallback="sqlite+aiosqlite")
        self.db: Engine | None = None
        self.db_async: AsyncEngine | None = None
        self._async: bool = False
        # self.stats_type : StatsType = stats_type
        db_url: str = f"{db}://{db_fn}"
        match db:
            case "sqlite+aiosqlite":
                self.db_async = create_async_engine(db_url, echo=True)
                self._async = True
            case _:
                self.db = create_engine(db_url, echo=True)

    @classmethod
    async def init(cls, config: ConfigParser) -> Self:
        sql_cache: Self = cls(config=config)
        if sql_cache.db_async is not None:
            async with sql_cache.db_async.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)
            return sql_cache
        elif sql_cache.db is not None:
            with sql_cache.db.begin() as conn:
                SQLModel.metadata.create_all(sql_cache.db)
            return sql_cache
        else:
            raise ValueError("could not init SQLCache")

    async def get_player_stats(
        self,
        account_id: AccountId,
        last_battle_time: LastBattleTime,
    ) -> ApiPlayerStats | None:
        """ "
        Get stats from DB cache.

        Raises sqlalchemy.excNoResultFound if stats not found.
        """
        if self.db_async is not None:
            async with AsyncSession(self.db_async) as a_session:
                try:
                    res = await a_session.exec(
                        select(PlayerStatsCache).where(
                            PlayerStatsCache.account_id == account_id,
                            PlayerStatsCache.last_battle_time >= last_battle_time,
                        )
                    )
                    return res.one().stats
                except InvalidRequestError as err:
                    debug("%s: %s", type(err), err)
                    raise NoResultFound
        elif self.db is not None:
            with Session(self.db) as session:
                try:
                    res = session.exec(
                        select(PlayerStatsCache).where(
                            PlayerStatsCache.account_id == account_id,
                            PlayerStatsCache.last_battle_time >= last_battle_time,
                        )
                    )
                    return res.one().stats
                except InvalidRequestError as err:
                    debug("%s: %s", type(err), err)
                    raise NoResultFound
        else:
            raise ValueError("no DB cache defined")

    async def get_tank_stats(
        self,
        account_id: AccountId,
        last_battle_time: LastBattleTime,
    ) -> TankStatsDict | None:
        """ "
        Get stats from DB cache.

        Raises sqlalchemy.excNoResultFound if stats not found.
        """
        if self.db_async is not None:
            async with AsyncSession(self.db_async) as a_session:
                try:
                    res = await a_session.exec(
                        select(TankStatsCache).where(
                            TankStatsCache.account_id == account_id,
                            TankStatsCache.last_battle_time >= last_battle_time,
                        )
                    )
                    return res.one().stats
                except InvalidRequestError as err:
                    debug("%s: %s", type(err), err)
                    raise NoResultFound
        elif self.db is not None:
            with Session(self.db) as session:
                try:
                    res = session.exec(
                        select(TankStatsCache).where(
                            TankStatsCache.account_id == account_id,
                            TankStatsCache.last_battle_time >= last_battle_time,
                        )
                    )
                    return res.one().stats
                except InvalidRequestError as err:
                    debug("%s: %s", type(err), err)
                    raise NoResultFound
        else:
            raise ValueError("no DB cache defined")

    async def put_player_stats(
        self,
        account_id: AccountId,
        stats: ApiPlayerStats,
    ) -> bool:
        """ "
        Put stats to DB cache.
        """
        if self.db_async is not None:
            async with AsyncSession(self.db_async) as a_session:
                try:
                    res = await a_session.exec(
                        select(PlayerStatsCache).where(
                            PlayerStatsCache.account_id == account_id,
                            PlayerStatsCache.last_battle_time >= last_battle_time,
                        )
                    )
                    return res.one().stats
                except InvalidRequestError as err:
                    debug("%s: %s", type(err), err)
                    raise NoResultFound
        elif self.db is not None:
            with Session(self.db) as session:
                try:
                    res = session.exec(
                        select(PlayerStatsCache).where(
                            PlayerStatsCache.account_id == account_id,
                            PlayerStatsCache.last_battle_time >= last_battle_time,
                        )
                    )
                    return res.one().stats
                except InvalidRequestError as err:
                    debug("%s: %s", type(err), err)
                    raise NoResultFound
        else:
            raise ValueError("no DB cache defined")

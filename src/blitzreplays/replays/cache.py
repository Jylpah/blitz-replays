import logging
from typing import (
    List,
    Self,
    Dict,
    Set,
    Tuple,
    Optional,
    Iterable,
)
from abc import ABC, abstractmethod
from pydantic import Field, model_validator, ConfigDict
from asyncio import Lock
from pyutils import IterableQueue, EventCounter
from pydantic_exportables import JSONExportable, JSONExportableRootDict, Idx

from blitzmodels import (
    AccountInfo,
    AccountInfoStats,
    AccountId,
    Region,
    TankStat,
    TankId,
    WGApi,
    WGApiWoTBlitzAccountInfo,
    WGApiWoTBlitzTankopedia,
    WGApiWoTBlitzTankStats,
)

from .args import (
    # EnumGroupFilter,
    # EnumTeamFilter,
    StatsType,
)
from .models_replay import PlayerStats, EnrichedReplay, stat_key

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug


class PlayerTankStat(TankStat):
    """Helper class for TankStatsDict to store individual player's tank stats"""

    @property
    def index(self) -> Idx:
        """return backend index"""
        return self.tank_id


class PlayerStat(AccountInfo):
    """Helper class for PlayerStatsDict to store individual player's stats"""

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


class PlayerStatsDict(JSONExportableRootDict[AccountId, PlayerStat]):
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
                    ps = PlayerStat(account_id=int(account_id))
                    if (
                        account_info is not None
                        and (ps_conv := PlayerStat.from_obj(account_info)) is not None
                    ):
                        res.add(ps_conv)
                    else:
                        res.add(ps)
            except KeyError:
                debug("no stats in WG API tank stats")
        return res


class TankStatsDict(JSONExportableRootDict[TankId, PlayerTankStat]):
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
                        if (pts := PlayerTankStat.from_obj(tank_stat)) is not None:
                            res.add(pts)
            except KeyError:
                debug("no stats in WG API tank stats")
        return res

    def get_many(self, tank_ids: Iterable[TankId]) -> Set[PlayerTankStat]:
        res: Set[PlayerTankStat] = set()
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


class StatsQuery(JSONExportable):
    """Class for defining player stats query"""

    stats_type: StatsType = Field(default=...)
    account_id: AccountId = Field(default=...)
    tier: int = Field(default=0)
    tank_id: int = Field(default=0)
    key: str = Field(default="")

    model_config = ConfigDict(
        frozen=False,
        # validate_assignment=False,  # To reduce constant validation
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def set_key(self: Self) -> Self:
        self._set_skip_validation(
            "key",
            stat_key(
                stats_type=self.stats_type,
                account_id=self.account_id,
                tier=self.tier,
                tank_id=self.tank_id,
            ),
        )
        if self.stats_type != "tier":
            self._set_skip_validation("tier", 0)
        if self.stats_type != "tank":
            self._set_skip_validation("tank_id", 0)
        return self

    def __hash__(self) -> int:
        return hash(self.key)

    # def mk_zero_player_stats(self) -> PlayerStats:
    #     """
    #     Create zero PlayerStats instance based on the query
    #     """
    #     ps = PlayerStats(account_id=self.account_id)
    #     match self.stats_type:
    #         case "tank":
    #             ps.tank_id = self.tank_id
    #         case "tier":
    #             ps.tier = self.tier
    #     return ps


class QueryCache(Set[StatsQuery]):
    """Cache (set) for stats queries"""

    def __init__(self: Self):
        self._lock = Lock()

    async def update_async(self, *s: Iterable[StatsQuery]) -> None:
        async with self._lock:
            return super().update(*s)


class APICache(ABC):
    """
    Abstract base class for API cache
    """

    stats_type: StatsType

    def __init__(self: Self, wg_api: WGApi, **kwargs):
        self._wg_api: WGApi = wg_api
        self._memcache_lock: Lock = Lock()

    # @abstractmethod
    # async def queue_stats(
    #     self,
    #     replay: "EnrichedReplay",
    #     accountQ: IterableQueue[AccountId],
    #     query_cache: QueryCache,
    # ):
    #     """
    #     add account_ids to the queue for fetching from the cache or API
    #     """
    #     raise NotImplementedError

    @abstractmethod
    async def stats_worker(self, accountQ: IterableQueue[AccountId]) -> EventCounter:
        """
        async worker to fetch stats from WG API
        """
        raise NotImplementedError

    @abstractmethod
    def get_stats(self, query: StatsQuery) -> PlayerStats:
        """
        get PlayerStats for account_id
        """
        raise NotImplementedError

    # @abstractmethod
    # def add_stats(self, replay: "EnrichedReplay") -> None:
    #     """
    #     add player stats to a replay
    #     """
    #     raise NotImplementedError


class PlayertatsAPICache(APICache):
    def __init__(self: Self, wg_api: WGApi):
        super().__init__(wg_api)

        self._api_cache: Dict[AccountId, PlayerStat | None] = dict()
        self._stats_queries: Set[AccountId] = set()

    async def stats_worker(self, accountQ: IterableQueue[AccountId]) -> EventCounter:
        """
        async worker to fetch stats from WG API
        """
        # TODO: add database cache
        stats = EventCounter("WG API")
        regionQ: Dict[Region, Set[AccountId]] = dict()
        # res: Dict[str, PlayerStats]
        debug("starting")
        for region in Region.API_regions():
            regionQ[region] = set()

        has_stats: int = 0
        no_stats: int = 0
        async for account_id in accountQ:
            async with self._memcache_lock:
                if account_id in self._api_cache:
                    continue
                self._api_cache[account_id] = None

            try:
                region = Region.from_id(account_id)
                regionQ[region].add(account_id)
                if len(regionQ[region]) == 100:
                    has_stats, no_stats = await self._fetch_api_stats(
                        account_ids=regionQ[region], region=region
                    )
                    stats.log("stats found", has_stats)
                    stats.log("no stats", no_stats)
                    regionQ[region] = set()
            except Exception as err:
                error(f"{type(err)}: {err}")

        for region, account_ids in regionQ.items():
            if len(account_ids) > 0:
                has_stats, no_stats = await self._fetch_api_stats(
                    account_ids=regionQ[region], region=region
                )
                stats.log("stats found", has_stats)
                stats.log("no stats", no_stats)
        return stats

    async def _fetch_api_stats(
        self, account_ids: Set[AccountId], region: Region
    ) -> Tuple[int, int]:
        """
        Actually fetch the player stats from WG API
        Returns number of accounts that have / do not have stats
        """
        fields: List[str] = [
            "account_id",
            "last_battle_time",
            "statistics.all.battles",
            "statistics.all.wins",
            "statistics.all.damage_dealt",
        ]
        player_stats: WGApiWoTBlitzAccountInfo | None
        psd: PlayerStatsDict
        has_stats: int = 0
        no_stats: int = 0

        if (
            player_stats := await self._wg_api.get_account_info_full(
                account_ids=list(account_ids),
                region=region,
                fields=fields,
            )
        ) is not None:
            psd = PlayerStatsDict.from_WGApiWoTBlitzAccountInfo(player_stats)
            for account_id in account_ids:
                if account_id in psd:
                    self._api_cache[account_id] = psd[account_id]
                    has_stats += 1
                    debug("player stats found for account_id=%d", account_id)
                else:
                    debug("player stats not found for account_id=%d", account_id)
            no_stats += len(account_ids) - has_stats
        else:
            no_stats += len(account_ids)
            if logger.level >= logging.DEBUG:
                for account_id in account_ids:
                    debug("player stats not found for account_id=%d", account_id)

        return (has_stats, no_stats)

        #     for player_stat in player_stats:
        #         key = stat_key(
        #             stats_type="player",
        #             account_id=player_stat.account_id,
        #         )
        #         res[key] = PlayerStats.player_stats(player_stat)
        #         account_ids.remove(player_stat.account_id)

        # if len(account_ids) > 0:
        #     for account_id in account_ids:
        #         key = self.stat_key(
        #             stats_type="player",
        #             account_id=account_id,
        #         )
        #         res[key] = PlayerStats(account_id=account_id)
        # return res

    def get_stats(self, query: StatsQuery) -> PlayerStats:
        """
        get PlayerStats for account_id
        """
        account_id: int = query.account_id
        player_stats: PlayerStat | None = None
        try:
            player_stats = self._api_cache[account_id]
        except KeyError:
            pass

        if player_stats is None:
            debug("query=%s: no player stats found", str(query))
            return PlayerStats(account_id=account_id)

        else:
            debug("query=%s: stats found", query)
            return player_stats.get_player_stats()


class TankStatsAPICache(APICache):
    """
    Helper class to store tank stats in a dict vs list for search performance
    """

    def __init__(self: Self, wg_api: WGApi, tankopedia: WGApiWoTBlitzTankopedia):
        super().__init__(wg_api)
        self._tankopedia: WGApiWoTBlitzTankopedia = tankopedia
        self._api_cache: Dict[AccountId, TankStatsDict | None] = dict()

    async def stats_worker(self, accountQ: IterableQueue[AccountId]) -> EventCounter:
        """
        Async worker for fetching player stats into in-memory cache
        from WG tank-stats API or a DB backend
        """
        fields: List[str] = [
            "account_id",
            "tank_id",
            "last_battle_time",
            "all.battles",
            "all.wins",
            "all.damage_dealt",
        ]
        stats = EventCounter("WG API")
        async for account_id in accountQ:
            try:
                async with self._memcache_lock:
                    if account_id in self._api_cache:
                        continue
                    self._api_cache[account_id] = None

                # TODO: Add support for DB stats cache
                if (
                    tank_stats := await self._wg_api.get_tank_stats_full(
                        account_id, fields=fields
                    )
                ) is None or tank_stats.data is None:
                    stats.log("no stats")
                    debug("no stats: account_id=%d", account_id)
                else:
                    stats.log("stats retrieved")
                    debug(
                        "stats OK: account_id=%d, tank-stats found: %d",
                        account_id,
                        len(tank_stats),
                    )
                    self._api_cache[
                        account_id
                    ] = TankStatsDict.from_WGApiWoTBlitzTankStats(api_stats=tank_stats)

            except Exception as err:
                error(f"could not fetch stats for account_id={account_id}: {err}")
        return stats

    def get_stats(self, query: StatsQuery) -> PlayerStats:
        stats: PlayerStats | None = None
        account_id: int = query.account_id
        tank_stats: TankStatsDict | None
        try:
            tank_stats = self._api_cache[account_id]
        except KeyError:
            tank_stats = None

        if tank_stats is None:
            debug("query=%s: stats not found", str(query))
        else:
            debug("query=%s: stats found", query)
            match query.stats_type:
                case "player":
                    # TODO: Raise error once PlayerStatsAPICache() is ready?
                    stats = tank_stats.get_player_stats()
                case "tier":
                    stats = tank_stats.get_tank_stats(
                        tank_ids=self._tankopedia.get_tank_ids_by_tier(tier=query.tier),
                        tier=query.tier,
                    )
                case "tank":
                    stats = tank_stats.get_tank_stat(tank_id=query.tank_id)
        if tank_stats is None or stats is None:
            debug("returing zero stats for query=%s", str(query))
            return PlayerStats.mk_zero(
                stats_type=query.stats_type,
                account_id=account_id,
                tier=query.tier,
                tank_id=query.tank_id,
            )
        else:
            return stats

    # def add_stats(self, replay: "EnrichedReplay") -> None:
    #     """
    #     add player stats to a replay
    #     """
    #     battle_tier: int = replay.battle_tier
    #     stats: PlayerStats
    #     for player_data in replay.players_dict.values():
    #         account_id: AccountId = player_data.dbid
    #         tank_id: TankId = player_data.vehicle_descr
    #         try:
    #             stats_key: str = PlayerStats.stat_key(
    #                 stats_type=self.stats_type,
    #                 account_id=account_id,
    #                 tier=battle_tier,
    #                 tank_id=tank_id,
    #             )
    #             stats = self._stats_cache[stats_key]
    #         except Exception as err:
    #             error(f"{type(err)}: {err}")
    #             stats = PlayerStats(account_id=account_id)
    #         player_data.add_stats(stats)


class StatsCache:
    def __init__(
        self: Self,
        wg_api: WGApi,
        # accountQ: IterableQueue[AccountId],
        stats_type: StatsType,
        tankopedia: WGApiWoTBlitzTankopedia,
    ):
        """creator of StatsCache must add_producer() to the statsQ before calling __init__()"""
        # fmt:off
        self._stats_cache       : Dict[str, PlayerStats] = dict()
        # self._wg_api            : WGApi = wg_api
        self._stats_type        : StatsType = stats_type
        self._api_cache         : APICache 
        # self._api_cache_tanks   : Dict[AccountId, TankStatsDict | None ] = dict()
        # self._api_cache_player  : Dict[AccountId, PlayerStatsDict | None ] = dict()
        # self._api_cache_lock    : Lock = Lock()
        self._tankopedia        : WGApiWoTBlitzTankopedia = tankopedia 
        # fmt: on

        match stats_type:
            case "player":
                self._api_cache = PlayertatsAPICache(wg_api=wg_api)
            case _:
                self._api_cache = TankStatsAPICache(
                    wg_api=wg_api, tankopedia=tankopedia
                )

    @property
    def stats_type(self) -> StatsType:
        return self._stats_type

    async def stats_worker(self, accountQ: IterableQueue[AccountId]) -> EventCounter:
        return await self._api_cache.stats_worker(accountQ)

    async def queue_stats(
        self,
        replay: "EnrichedReplay",
        accountQ: IterableQueue[AccountId],
        query_cache: QueryCache,
    ):
        """
        Put account_ids to a queue for a API worker to fetch those.

        Add specific stats queries requestesd to a set.
        """
        for account_id in replay.allies + replay.enemies:
            await accountQ.put(account_id)
        stats_queries: Set[StatsQuery] = set()
        for account_id in replay.get_players():
            try:
                match self.stats_type:
                    case "player":
                        query = StatsQuery(
                            stats_type=self.stats_type, account_id=account_id
                        )
                    case "tier":
                        query = StatsQuery(
                            stats_type=self.stats_type,
                            account_id=account_id,
                            tier=replay.battle_tier,
                        )
                    case "tank":
                        tank_id: int = replay.get_player_data(account_id).vehicle_descr
                        query = StatsQuery(
                            stats_type=self.stats_type,
                            account_id=account_id,
                            tank_id=tank_id,
                        )
                stats_queries.add(query)
            except KeyError as err:
                error(f"no player data for account_id={account_id}: {type(err)} {err}")
            except Exception as err:
                error(f"{type(err)}: {err}")
        await query_cache.update_async(stats_queries)

    # async def tank_stats_worker(
    #     self, accountQ: IterableQueue[AccountId]
    # ) -> EventCounter:
    #     """
    #     Async worker for retrieving player stats using WG APT tank/stats
    #     """
    #     fields: List[str] = [
    #         "account_id",
    #         "tank_id",
    #         "last_battle_time",
    #         "all.battles",
    #         "all.wins",
    #         "all.damage_dealt",
    #     ]
    #     stats = EventCounter("WG API")
    #     async for account_id in accountQ:
    #         try:
    #             async with self._api_cache_lock:
    #                 if account_id in self._api_cache_tanks:
    #                     continue
    #                 self._api_cache_tanks[account_id] = None

    #             # TODO: Add support for DB stats cache
    #             if (
    #                 tank_stats := await self._wg_api.get_tank_stats_full(
    #                     account_id, fields=fields
    #                 )
    #             ) is None or tank_stats.data is None:
    #                 stats.log("no stats")
    #                 debug("no stats: account_id=%d", account_id)
    #             else:
    #                 stats.log("stats retrieved")
    #                 debug(
    #                     "stats OK: account_id=%d, tank-stats found: %d",
    #                     account_id,
    #                     len(tank_stats),
    #                 )
    #                 self._api_cache_tanks[
    #                     account_id
    #                 ] = TankStatsDict.from_WGApiWoTBlitzTankStats(api_stats=tank_stats)

    #         except Exception as err:
    #             error(f"could not fetch stats for account_id={account_id}: {err}")
    #     return stats

    def fill_cache(self: Self, query_cache: QueryCache):
        stats: PlayerStats | None
        for query in query_cache:
            try:
                debug("query=%s", str(query))
                stats = self._api_cache.get_stats(query=query)
                self._stats_cache[stats.key] = stats
            except Exception as err:
                error(f"query={query}: {type(err)}: {err}")

            # account_id: int = query.account_id
            # player_tank_stats: TankStatsDict | None
            # try:
            #     player_tank_stats = self._api_cache_tanks[account_id]
            # except KeyError:
            #     player_tank_stats = None

            # if player_tank_stats is None:
            #     debug("query=%s: no stats found", str(query))
            #     stats = PlayerStats(account_id=account_id)
            #     match query.stats_type:
            #         case "player":
            #             pass
            #         case "tier":
            #             stats.tier = query.tier
            #         case "tank":
            #             stats.tank_id = query.tank_id
            #     self._stats_cache[query.key] = stats
            # else:
            #     debug("query=%s: stats found", query)
            #     match query.stats_type:
            #         case "player":
            #             if (stats := player_tank_stats.get_player_stats()) is None:
            #                 stats = PlayerStats(account_id=account_id)
            #         case "tier":
            #             if (
            #                 stats := player_tank_stats.get_tank_stats(
            #                     self._tankopedia.get_tank_ids_by_tier(tier=query.tier)
            #                 )
            #             ) is None:
            #                 stats = PlayerStats(account_id=account_id, tier=query.tier)
            #         case "tank":
            #             if (
            #                 stats := player_tank_stats.get_tank_stat(
            #                     tank_id=query.tank_id
            #                 )
            #             ) is None:
            #                 stats = PlayerStats(
            #                     account_id=account_id, tank_id=query.tank_id
            #                 )
            #     self._stats_cache[query.key] = stats
            #     debug("%s: %s", query.key, str(stats))
        debug(f"stats_cache has {len(self._stats_cache)} stats")

    # def get_stats(self, account_id: AccountId) -> TankStatsDict | None:
    #     try:
    #         return self._api_cache_tanks[account_id]
    #     except KeyError:
    #         debug("no cached stats for account_id=%d", account_id)
    #         return None

    def add_stats(self, replay: "EnrichedReplay") -> None:
        """
        Add player stats to the replay
        """
        battle_tier: int = replay.battle_tier
        stats: PlayerStats
        for player_data in replay.players_dict.values():
            account_id: AccountId = player_data.dbid
            tank_id: TankId = player_data.vehicle_descr
            try:
                query = StatsQuery(
                    stats_type=self.stats_type,
                    account_id=account_id,
                    tier=battle_tier,
                    tank_id=tank_id,
                )
                stats = self._stats_cache[query.key]

            except Exception as err:
                error(f"{type(err)}: {err}")
                error(
                    f"no {self.stats_type} stats in stats cache for account_id={account_id}, tier={battle_tier}, tank_id={tank_id}"
                )
                error("query=%s", str(query))  # type: ignore

                stats = PlayerStats.mk_zero(
                    stats_type=self.stats_type,
                    account_id=account_id,
                    tier=battle_tier,
                    tank_id=tank_id,
                )
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

    # def get_stats_queries(self, stats_type: StatsType) -> Set[StatsQuery]:
    #     queries: Set[StatsQuery] = set()

    #     for account_id in self.get_players():
    #         query = StatsQuery(account_id=account_id, stats_type=stats_type)
    #         match stats_type:
    #             case "tier":
    #                 query.tier = self.battle_tier
    #             case "tank":
    #                 query.tank_id = self.players_dict[account_id].vehicle_descr
    #     return queries


# @dataclass
# class StringStore:
#     value: str

#     def get(self) -> str:
#         return self.value

#     def record(self, value: Self) -> None:
#         raise ValueError("cannot overwrite StringStore")

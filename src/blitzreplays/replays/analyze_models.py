import logging
from typing import Optional, Annotated, List, Self, Dict
from pydantic import Field, model_validator

from blitzmodels.wotinspector.wi_apiv2 import Replay, PlayerData, PlatformEnum
from blitzmodels.wotinspector.wi_apiv1 import EnumBattleResult, EnumWinnerTeam
from blitzmodels import Tank, Account, WGApiWoTBlitzTankopedia, EnumVehicleTier, EnumNation, EnumVehicleTypeInt
from enum import StrEnum
import logging

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug


        

class EnumPLayerFilter(StrEnum):
    player          = "player"
    plat_mate       = "plat_mate"
    allies          = "a"
    allies_all      = "a_all"
    allies_solo     = "a_solo"
    allies_platoons = "a_plat"
    allies_platoons_all = "a_plat_all"
    enemies         = "e"
    enemies_solo    = "e_solo"
    enemies_platoons= "e_plat"
    allies_lt       = "a_lt"
    allies_mt       = "a_mt"
    allies_ht       = "a_ht"
    allies_td       = "a_td"
    ememies_lt      = "e_lt"
    ememies_mt      = "e_mt"
    ememies_ht      = "e_ht"
    ememies_td      = "e_td"
    allies_top      = "a_top"
    allies_bottom   = "a_bottom"
    enemies_top      = "e_top"
    enemies_bottom   = "e_bottom"


class PlayerDataEnriched(PlayerData):
    tank_type       : EnumVehicleTypeInt| None = None
    tank_tier       : EnumVehicleTier   | None = None
    tank_nation     : EnumNation        | None = None
    tank_is_premium : bool              = False


    def update_tank(self, tank: Tank) -> bool:
        if self.vehicle_descr != tank.tank_id:
            error(f"tank_id does not match: {self.vehicle_descr} != {tank.tank_id}")
            return False
        else:
            self.tank_is_premium = tank.is_premium
            self.tank_nation = tank.nation
            self.tank_tier = tank.tier
            if tank.type is not None:
                self.tank_type = tank.type.as_int
            return True


class ReplayEnriched(Replay):
    players_dict: Dict[int, PlayerDataEnriched] = Field(default_factory=dict)
    player : int = -1

    @model_validator(mode='after')
    def read_players_dict(self) -> Self:
        for data in self.players_data:
            self.players_dict[data.dbid] = PlayerDataEnriched.model_validate(data)
        self.players_data = list()
        return self
    
    def enrich(self, tankopedia: WGApiWoTBlitzTankopedia, player: int | None = None):
        # add tanks
        for account_id in self.players_dict:
            data : PlayerDataEnriched = self.players_dict[account_id]
            tank_id : int = data.vehicle_descr
            try:
                tank : Tank = tankopedia[tank_id]
                data.update_tank(tank=tank)
            except KeyError:
                debug(f"could not find tank_id={tank_id} from Tankopedia")

        # set player
        if player is None:
            self.player = self.protagonist
        elif player in self.allies:
            self.player = player
        elif player in  self.enemies:  # swapt teams
            tmp_team : list[int] = self.allies
            self.allies = self.enemies
            self.enemies = tmp_team
            if self.battle_result == EnumBattleResult.win:
                self.battle_result = EnumBattleResult.loss
            elif self.battle_result == EnumBattleResult.loss:
                self.battle_result = EnumBattleResult.win
        else:
            raise ValueError(f"no account_id={player} in the replay")
    
    def get_players(self, player_filter: EnumPLayerFilter, tankopedia: WGApiWoTBlitzTankopedia) -> [ int ]:
        """
        Get players matching the filter from the replay
        """
        players : List[int]
        match player_filter:
            case EnumPLayerFilter.player:
                if self.player > 0:
                    return [ self.player ]
            case EnumPLayerFilter.plat_mate:
                if self.players_dict[self.player].squad_index is None:
                    return []
                else:
                    platoon_id : int = self.players_dict[self.player].squad_index
                    for player in self.allies:
                        if player == self.player:
                            continue
                        team_mate_platoon_id : int | None = self.players_dict[player].squad_index
                        if  team_mate_platoon_id is not None and team_mate_platoon_id == platoon_id:
                            return [ player ]
                    return []
            case EnumPLayerFilter.allies:
                players = self.allies
                players.remove(self.player)
                return players
            case EnumPLayerFilter.allies_all:
                return self.allies
            case EnumPLayerFilter.allies_solo:
                players = list()
                for player in self.allies:
                    if player == self.player:
                        continue
                    if self.players_dict[player].squad_index is None:
                        players.append(player)
                return players
            case EnumPLayerFilter.allies_platoons:
                players = list()
                for player in self.allies:
                    if player == self.player:
                        continue
                    if self.players_dict[player].squad_index is not None:
                        players.append(player)
                return players
            case EnumPLayerFilter.allies_platoons_all:
                players = list()
                for player in self.allies:
                    if self.players_dict[player].squad_index is not None:
                        players.append(player)
                return players

            case EnumPLayerFilter.enemies:
                return self.enemies


    





class ReportColumn():
    name : str
    key: str
    filter: EnumPLayerFilter
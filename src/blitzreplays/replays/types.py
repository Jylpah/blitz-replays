# Types for blitz-replays
from typing import Literal

LastBattleTime = int
StatsType = Literal["player", "tier", "tank"]
StatsMeasure = Literal["wr", "avgdmg", "battles"]
TankType = Literal["light_tank", "medium_tank", "heavy_tank", "tank_destroyer", "-"]

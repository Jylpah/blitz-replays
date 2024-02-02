import logging
from typing import (
    List,
    Dict,
    Tuple,
    ClassVar,
    Type,
)
from math import inf
from pathlib import Path
from abc import abstractmethod, ABC
from collections import defaultdict
from sortedcollections import NearestDict  # type: ignore
from tabulate import tabulate  # type: ignore
import aiofiles

# from icecream import ic  # type: ignore

import tomlkit

from blitzmodels import AccountId

from .args import (
    # EnumGroupFilter,
    # EnumTeamFilter,
    PlayerFilter,
)
from .models_replay import EnrichedReplay
from .models_fields import ValueStore, FieldKey, Fields

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug


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
            if isinstance(value, str):
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

    def __init__(self, name: str, field: str):
        self.name: str = name
        # self._battles: int = 0
        self.field: str = field
        is_player_field: bool
        field, is_player_field = self.parse_field(field)
        self._field: str = field
        self._is_player_field: bool = is_player_field
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

    def print(self, fields: Fields, export: bool = False) -> str:
        """Print a report"""
        debug("Report: %s", str(fields))
        header: List[str] = [self.name.upper()] + [
            field.name for field in fields.fields()
        ]
        data: List[List[str]] = list()
        for cat_key in self.categories:
            try:
                cat: Category = self._categories[cat_key]
                row: List[str] = [cat_key]
                for field_key, field in fields.items():
                    try:
                        row.append(field.print(cat.get(field=field_key)))
                    except Exception as err:
                        error(
                            f"Category={cat_key} field={field.name}: {type(err)}: {err}"
                        )
                data.append(row)
            except KeyError as err:
                error("category=%s: %s: %s", cat_key, type(err), str(err))
        debug("data=%s", str(data))
        if export:
            return tabulate(data, headers=header, tablefmt="tsv")
        else:
            return tabulate(data, headers=header)

    def parse_field(self, field: str) -> Tuple[str, bool]:
        """parse field and check is it a player field"""
        if field.startswith("player."):
            return field.removeprefix("player."), True
        else:
            return field, False

    def get_toml(self) -> tomlkit.items.Table:
        """
        get TOML config of the report
        """
        table: tomlkit.items.Table = tomlkit.table()
        table.add("name", self.name)
        table.add("categorization", self.categorization)
        table.add("field", self.field)
        return table

    @property
    def category_field(self) -> str:
        """return full category field"""
        if self._is_player_field:
            return "player." + self._field
        else:
            return self._field

    def get_category_int(self, replay: EnrichedReplay) -> int:
        """Return integer field value"""
        if self._is_player_field:
            return int(getattr(replay.players_dict[replay.player], self._field))
        else:
            return int(getattr(replay, self._field))

    def get_category_float(
        self, replay: EnrichedReplay, players: List[AccountId] = list()
    ) -> float:
        """Get category field's value as float for the replay"""
        if len(players) == 0:
            if self._is_player_field:
                return float(getattr(replay.players_dict[replay.player], self._field))
            else:
                return float(getattr(replay, self._field))
        else:
            if not self._is_player_field:
                raise ValueError("cannot use 'players' without a player field")
            i: int = 0
            res: float = 0
            # ic(self.categorization)
            for player in players:
                if (
                    val := float(getattr(replay.players_dict[player], self._field))
                ) > 0:
                    res += val
                    i += 1
            return res / i if i > 0 else inf

    def get_category_str(self, replay: EnrichedReplay) -> str:
        """Get category field's value as str for the replay"""
        if self._is_player_field:
            return str(getattr(replay.players_dict[replay.player], self._field))
        else:
            return str(getattr(replay, self._field))


class Reports:
    """
    Reports to create
    """

    _db: ClassVar[Dict[str, Type[Categorization]]] = dict()

    def __init__(self) -> None:
        self.db: Dict[str, Categorization] = dict()
        self.report_sets: Dict[str, List[str]] = dict()

    def add(self, key: str, name: str, categorization: str, **kwargs):
        """
        Add a report
        """
        try:
            cat: Type[Categorization] = self._db[categorization]
            if key in self.db:
                raise ValueError(f"duplicate definition of report='{key}'")
            self.db[key] = cat(name=name, **kwargs)
        except KeyError as err:
            error(
                f"could not create report: key={key}, name={name}, categorization={categorization}, {', '.join('='.join([k,v]) for k,v in kwargs.items())}"
            )
            error(err)
            raise
        except ValueError as err:
            error(err)
            raise
        except Exception as err:
            error(err)
            raise

    def add_report_set(self, key: str, report_set: List[str]):
        self.report_sets[key] = report_set

    def with_config(self, report_sets: List[str]) -> "Reports":
        """
        get FieldStore according to the 'report_set' config
        """
        res = Reports()
        for key in report_sets:
            try:
                res.report_sets[key] = self.report_sets[key]
                for report_key in res.report_sets[key]:
                    try:
                        res.db[report_key] = self.db[report_key]
                    except KeyError:
                        error(f"no such a report key defined: {report_key}")
            except KeyError:
                error(f"no such a report set defined: {key}")
        return res

    @property
    def reports(self) -> List[Categorization]:
        return list(self.db.values())

    def get(self, key: str) -> Categorization | None:
        """Get a report by key"""
        try:
            return self.db[key]
        except KeyError:
            error(f"no report with key={key} defined")
        return None

    def __len__(self) -> int:
        """Return the number of reports"""
        return len(self.db)

    def update(self, other: "Reports") -> None:
        """update reports with 'other'"""
        self.db.update(other.db)
        self.report_sets.update(other.report_sets)
        return None

    @classmethod
    def register(cls, categorization: Type[Categorization]):
        """Register a known report type"""
        cls._db[categorization.categorization] = categorization

    def print(self, fields: Fields) -> None:
        """Print reports"""
        for report in self.db.values():
            print()
            print(report.print(fields))

    async def export(self, fields: Fields, filename: Path):
        """
        Export reports to a TSV file
        """
        async with aiofiles.open(filename, "w") as f:
            for report in self.db.values():
                await f.write("\n\n")
                await f.write(report.print(fields, export=True))

    def get_toml(self) -> tomlkit.items.Table:
        """
        get REPORT TOML config
        """
        table: tomlkit.items.Table = tomlkit.table()
        for key, report in self.db.items():
            table.add(key, report.get_toml())
            table.add(tomlkit.nl())
        return table

    def get_toml_report_sets(self) -> tomlkit.items.Table:
        """
        get REPORTS TOML config
        """
        table: tomlkit.items.Table = tomlkit.table()
        for name, report_set in self.report_sets.items():
            table.add(name, report_set)
        return table


class Totals(Categorization):
    """
    Calculate overall stats over all replays
    """

    categorization = "total"

    def __init__(self, name: str):
        super().__init__(name="Total", field="exp")
        self._categories["Total"] = Category()

    def get_category(self, replay: EnrichedReplay) -> Category | None:
        return self._categories["Total"]

    def get_toml(self) -> tomlkit.items.Table:
        """
        get TOML config of the report
        """
        table: tomlkit.items.Table = super().get_toml()
        del table["field"]
        return table

    @classmethod
    def help(cls) -> None:
        print(f'categorization = "{cls.categorization}" reports stats over all replays')


Reports.register(Totals)


class ClassCategorization(Categorization):
    """
    Categorize replays based on a replay field's integer value.
    """

    categorization = "category"

    def __init__(self, name: str, field: str, categories: List[str]):
        super().__init__(name=name, field=field)
        self._category_cache: Dict[int, str] = dict()
        for ndx, cat in enumerate(categories):
            self._category_cache[int(ndx)] = cat

    def get_category(self, replay: EnrichedReplay) -> Category | None:
        try:
            field_value: int = self.get_category_int(replay)
            category: CategoryKey = self._category_cache[field_value]
            return self._categories[category]
        except AttributeError:
            error(f"no field={self._field} found in replay: {replay.title}")
        except KeyError as err:
            error(err)
        return None

    @property
    def categories(self) -> List[CategoryKey]:
        """Get category keys in in order specified"""
        return [
            cat
            for cat in self._category_cache.values().__reversed__()
            if cat in self._categories
        ]

    def get_toml(self) -> tomlkit.items.Table:
        """
        get TOML config of the report
        """
        table: tomlkit.items.Table = super().get_toml()
        table.add("categories", list(self._category_cache.values()))
        return table


Reports.register(ClassCategorization)


class NumberCategorization(Categorization):
    """
    "protagonist": ["account_id", "number"],
    "battle_i": ["Battle #", "number"],
    "enemies_destroyed": ["Player Kills", "number"],
    "enemies_spotted": ["Player Spots", "number"],
    "tank_tier": ["Tank Tier", "number"],
    """

    categorization = "number"

    def get_category(self, replay: EnrichedReplay) -> Category | None:
        try:
            return self._categories[self.get_category_str(replay)]
        except AttributeError as err:
            error(
                f"field={self.category_field} not found in replay: {replay.title}: {err}"
            )
        except KeyError as err:
            error(f"{type(err)}: {err}")
        return None


Reports.register(NumberCategorization)


class StrCategorization(Categorization):
    """
    "player_name": ["Player", "string", 25],
    "tank_name": ["Tank", "string", 25],
    "map_name": ["Map", "string", 20],
    "battle": ["Battle", "string", 40],
    """

    categorization = "string"

    def get_category(self, replay: EnrichedReplay) -> Category | None:
        try:
            return self._categories[self.get_category_str(replay)]
        except AttributeError as err:
            error(
                f"field={self.category_field} not found in replay: {replay.title}: {err}"
            )
        except KeyError as err:
            error(f"{type(err)}: {err}")
        return None


Reports.register(StrCategorization)


# TODO: could bucket categorization support any field value (metric, filter, etc) for categorization?
class BucketCategorization(Categorization):
    """
    "allies_battles": [
            "Player Battles",
            "bucket",
            [0, 500, 1000, 2500, 5e3, 10e3, 15e3, 25e3],
            "int",
        ],
        "allies_damage_dealt": [
            "Player Avg Dmg",
            "bucket",
            [0, 500, 1000, 1250, 1500, 1750, 2000, 2500],
            "int",
        ],
        "enemies_wins": [
            "Enemies WR",
            "bucket",
            [0, 0.35, 0.45, 0.50, 0.55, 0.65],
            "%",
        ],
        "enemies_battles": [
            "Player Battles",
            "bucket",
            [0, 500, 1000, 2500, 5e3, 10e3, 15e3, 25e3],
            "int",
        ],
        "enemies_damage_dealt": [
            "Player Avg Dmg",
            "bucket",
            [0, 500, 1000, 1250, 1500, 1750, 2000, 2500],
            "int",
        ],
    """

    categorization = "bucket"

    def __init__(
        self,
        name: str,
        field: str,
        buckets: List[int | float],
        bucket_labels: List[str],
        filter: str | None = None,
    ):
        super().__init__(name=name, field=field)
        self._buckets: NearestDict[float, str] = NearestDict(
            rounding=NearestDict.NEAREST_PREV
        )
        self._filter: PlayerFilter | None = None
        if filter is not None:
            self._filter = PlayerFilter.from_str(filter)

        if len(buckets) != len(bucket_labels):
            message(
                f"check report config: the number of 'buckets' ({len(buckets)}) and 'bucket_labels' ({bucket_labels}) does not match"
            )
        debug(f"buckets={buckets}")
        debug(f"labels={bucket_labels}")
        for bucket_start, label in zip(buckets, bucket_labels):
            # debug(f"bucket_start={bucket_start}, label={label}")
            self._buckets[bucket_start] = label

    def get_category(self, replay: EnrichedReplay) -> Category | None:
        try:
            field_value: float
            if self._filter is None:
                field_value = self.get_category_float(replay)
            else:
                field_value = self.get_category_float(
                    replay, replay.get_players(self._filter)
                )

            category: CategoryKey = self._buckets[field_value]
            debug(
                f"replay={replay.title}: field={self.category_field}, value={field_value}, category={category}"
            )
            return self._categories[category]
        except AttributeError:
            error(f"no field={self._field} found in replay: {replay.title}")
        except KeyError as err:
            error(f"{type(err)}: {err}")
        return None

    @property
    def categories(self) -> List[CategoryKey]:
        """Get category keys in in order specified"""
        return [
            cat
            for cat in self._buckets.values().__reversed__()
            if cat in self._categories
        ]

    def get_toml(self) -> tomlkit.items.Table:
        """
        get TOML config of the report
        """
        table: tomlkit.items.Table = super().get_toml()
        table.add("buckets", list(self._buckets.keys()))
        table.add("bucket_labels", list(self._buckets.values()))
        if self._filter is not None:
            table.add("filter", self._filter.key)
        return table


Reports.register(BucketCategorization)

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

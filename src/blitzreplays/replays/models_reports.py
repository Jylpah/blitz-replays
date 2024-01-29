import logging
from typing import (
    List,
    Self,
    Dict,
    Tuple,
    Set,
    ClassVar,
    Type,
    Literal,
    Final,
)
from math import inf

from abc import abstractmethod, ABC
from dataclasses import dataclass, field as data_field
from re import compile, match
import re
from collections import defaultdict
from sortedcollections import NearestDict  # type: ignore
from tabulate import tabulate  # type: ignore

# from icecream import ic  # type: ignore

import tomlkit

from blitzmodels import AccountId

from .args import (
    # EnumGroupFilter,
    # EnumTeamFilter,
    PlayerFilter,
)
from .models_replay import EnrichedReplay

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug


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

    key: FieldKey
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
        debug("called: %s", type(self))
        self._field = self.check_field_config()

    @abstractmethod
    def calc(self, replay: EnrichedReplay) -> ValueStore:
        raise NotImplementedError

    # @property
    # def key(self) -> FieldKey:
    #     if self.filter is None:
    #         return "-".join([self.metric, self.fields])
    #     else:
    #         return "-".join([self.metric, self.fields, self.filter.key])

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

    def get_toml(self) -> tomlkit.items.Table:
        """
        Return TOML config of the object
        """
        table = tomlkit.table()
        table.add("name", self.name)
        table.add("fields", self.fields)
        table.add("format", self.format)
        if self.filter is not None:
            table.add("filter", self.filter.key)
        return table

    # @abstractmethod
    # def record(self, value: ValueType):
    #     raise NotImplementedError

    @abstractmethod
    def value(self, value: ValueStore) -> float:
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
    field_sets: Dict[str, List[str]] = data_field(default_factory=dict)
    db: Dict[FieldKey, ReportField] = data_field(default_factory=dict)

    @classmethod
    def register(cls, measure: Type[ReportField]):
        cls.registry[measure.metric] = measure

    def add(
        self,
        key: FieldKey,
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
                key=key, name=name, filter=player_filter, fields=fields, format=format
            )

            if key not in self.db:
                self.db[key] = field
            return self.db[key]
        except Exception as err:
            error(
                f"could not create metric: metric={metric}, filter={filter}, fields={fields}"
            )
            error(err)
            raise err

    def __getitem__(self, key: str) -> ReportField:
        return self.db[key]

    def items(self) -> List[Tuple[FieldKey, ReportField]]:
        """Return list of stored keys & fields as tuples"""
        return list(self.db.items())

    def keys(self) -> List[FieldKey]:
        """return field keys"""
        return list(self.db.keys())

    def fields(self) -> List[ReportField]:
        """Return a list of ReportFields"""
        return list(self.db.values())

    def update(self, other: "FieldStore") -> None:
        """
        update instance with other
        """
        self.db.update(other.db)
        return None

    @classmethod
    def ops(cls) -> List[str]:
        return list(cls.registry.keys())

    def __len__(self) -> int:
        """Return the number of fields"""
        return len(self.db)

    def get_toml(self) -> tomlkit.items.Table:
        """
        get field TOML config
        """
        table: tomlkit.items.Table = tomlkit.table()
        for key, field in self.items():
            table.add(key, field.get_toml())
            table.add(tomlkit.nl())
        return table

    def get_toml_field_sets(self) -> tomlkit.items.Table:
        """
        get field TOML config
        """
        table: tomlkit.items.Table = tomlkit.table()
        for name, field_set in self.field_sets.items():
            table.add(name, field_set)
        return table

    def with_config(self, field_sets: List[str]) -> "FieldStore":
        """
        get FieldStore according to the 'field_set' config
        """
        res = FieldStore()
        for key in field_sets:
            try:
                res.field_sets[key] = self.field_sets[key]
                for field_key in res.field_sets[key]:
                    try:
                        res.db[field_key] = self.db[field_key]
                    except KeyError:
                        error(f"no such a field keyy defined: {field_key}")
            except KeyError:
                error(f"no such a field set defined: {key}")
        return res


@dataclass
class CountField(ReportField):
    metric = "count"
    fields = "exp"

    def calc(self, replay: EnrichedReplay) -> ValueStore:
        if self.filter is None:
            return ValueStore(1, 1)
        else:
            return ValueStore(len(replay.get_players(self.filter)), 1)

    def value(self, value: ValueStore) -> float:
        v: int | float = value.value
        return float(v)


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
                debug(
                    "not attribute '%s' found in replay: %s", self.fields, replay.title
                )
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
                        "not attribute '%s' found in replay: %s",
                        self.fields,
                        replay.title,
                    )
            return ValueStore(res, n)

    def value(self, value: ValueStore) -> float:
        return float(value.value)


FieldStore.register(SumField)


@dataclass
class AverageField(SumField):
    metric = "average"

    def calc(self, replay: EnrichedReplay) -> ValueStore:
        if self.filter is None:
            try:
                return ValueStore(getattr(replay, self._field), 1)
            except AttributeError:
                debug(
                    "no attribute '%s' found in replay: %s", self.fields, replay.title
                )
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
                        "no attribute '%s' found in replay: %s",
                        self.fields,
                        replay.title,
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
        debug("called: %s", type(self))
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
                raise ValueError("invalid IF metric: %s", other)

    def calc(self, replay: EnrichedReplay) -> ValueStore:
        if self.filter is None:
            try:
                return ValueStore(self._test_if(getattr(replay, self._field)), 1)
            except AttributeError:
                debug(
                    "no attribute '%s' found in replay: %s", self._field, replay.title
                )
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
                        "replay=%s account_id=%d no attribute '%s' found in replay: %s",
                        replay.title,
                        p,
                        self._field,
                        replay.title,
                    )
            return ValueStore(res, n)

    def value(self, value: ValueStore) -> float:
        return float(value.value / value.n)


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

    def value(self, value: ValueStore) -> float:
        return float(value.value)


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

    def value(self, value: ValueStore) -> float:
        return float(value.value)


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
            self._value_field, self._div_field = self.fields.split("/")
            if self.is_player_field(self._value_field):
                self._value_field = self.check_field_config(self._value_field)
                self._is_player_field_value = True
            if self.is_player_field(self._div_field):
                self._div_field = self.check_field_config(self._div_field)
                self._is_player_field_div = True
        except Exception as err:
            error(f"invalid field config: {self.fields}")
            error("'ratio' metric's field key is format 'value_field/divider_field'")
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
        if value.n > 0:
            return value.value / value.n
        else:
            return inf


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

    def print(self, fields: FieldStore) -> None:
        """Print a report"""
        debug("Report: %s", str(fields))
        header: List[str] = [field.name for field in fields.fields()]
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
        print(tabulate(data, headers=header))

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
        return None

    @classmethod
    def register(cls, categorization: Type[Categorization]):
        """Register a known report type"""
        cls._db[categorization.categorization] = categorization

    def print(self, fields: FieldStore) -> None:
        """Print reports"""
        for report in self.db.values():
            print()
            print(report.name.upper())
            report.print(fields)

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

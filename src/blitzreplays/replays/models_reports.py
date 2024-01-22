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

from abc import abstractmethod, ABC
from dataclasses import dataclass, field as data_field
from re import compile, match
import re
from collections import defaultdict
from tabulate import tabulate  # type: ignore


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
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

from abc import abstractmethod
from dataclasses import dataclass, field as data_field
from re import compile, match
import re

# from icecream import ic  # type: ignore

import tomlkit

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
        "battle_tier",
        "plat_mate",
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
        "map",
        "repair_cost",
        "solo",
        "title",
        "title_uniq",
        "top_tier",
    ]

    _player_fields: ClassVar[List[str]] = [
        f"player.{key}"
        for key in [
            "avgdmg",
            "base_capture_points",
            "base_defend_points",
            "battles",
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
            "tank",
            "tank_tier",
            "tank_type",
            "tank_nation",
            "tank_is_premium",
            "shots_made",
            "shots_hit",
            "shots_pen",
            "shots_splash",
            "wp_points_earned",
            "wp_points_stolen",
            "wr",
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
class Fields:
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
        # fields: str,
        # format: str,
        filter: str | None = None,
        **kwargs,
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
                key=key,
                name=name,
                filter=player_filter,
                **kwargs,
            )

            if key not in self.db:
                self.db[key] = field
            return self.db[key]
        except Exception as err:
            error(f"could not create metric: metric={metric}, filter={filter}")
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

    def update(self, other: "Fields") -> None:
        """
        update instance with other
        """
        self.db.update(other.db)
        self.field_sets.update(other.field_sets)
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

    def with_config(self, field_sets: List[str]) -> "Fields":
        """
        get FieldStore according to the 'field_set' config
        """
        res = Fields()
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
    """
    Count total number of matching replays
    """

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


Fields.register(CountField)


# TODO: Add ShareField: Share of battles


@dataclass
class SumField(ReportField):
    """
    Sum a replay field value over matching replays
    """

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


Fields.register(SumField)


@dataclass
class AverageField(SumField):
    """
    Calculate an average of field values in matching replays
    """

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
        return value.value / value.n if value.n > 0 else inf


Fields.register(AverageField)

CmpOps = Literal["eq", "gt", "lt", "gte", "lte"]


@dataclass
class AverageIfField(SumField):
    """
    Calculate an average of field values with a =,>,< condition in matching replays
    """

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
        return float(value.value / value.n) if value.n > 0 else inf


Fields.register(AverageIfField)


@dataclass
class MinField(ReportField):
    """
    Find a field's minimum value over replays
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


Fields.register(MinField)


@dataclass
class MaxField(ReportField):
    """
    Find a field's maximum value over replays
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


Fields.register(MaxField)


@dataclass
class RatioField(SumField):
    """
    Calculate a ratio between two fields over matching replays
    """

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
        return value.value / value.n if value.n > 0 else inf


Fields.register(RatioField)


@dataclass
class DiffField(SumField):
    """
    Calculate a difference of averages between two player groups over matching replays
    """

    metric = "difference"

    filter2: str = "- NOT DEFINED -"

    _filter2: PlayerFilter | None = None

    def __post_init__(self):
        debug(f"called: {type(self)}")
        super().__post_init__()
        try:
            self._filter2 = PlayerFilter.from_str(self.filter2)
            if self.filter is None:
                raise ValueError(f"'filter' not defined for FIELD {self.name}")
            if self._filter2 is None:
                raise ValueError(f"'filter2' not defined for FIELD {self.name}")
        except Exception as err:
            error(f"FIELD '{self.key}' has invalid field config: {err}")
            raise

    def calc(self, replay: EnrichedReplay) -> ValueStore:
        val1: float = 0
        val2: float = 0
        i: int = 0

        if self.filter is None:
            raise ValueError(f"FIELD={self.key}: 'filter' is not defined")
        if self._filter2 is None:
            raise ValueError(f"FIELD={self.key}: 'filter2' is not defined")

        try:
            for p in replay.get_players(self.filter):
                try:
                    val1 += getattr(replay.players_dict[p], self._field)
                    i += 1
                except AttributeError as err:
                    debug(
                        f"not attribute 'players_data.{self._field}' (account_id={p}) found in replay: {replay.title}'"
                    )
                    error(err)

            val1 = val1 / i

            i = 0
            for p in replay.get_players(self._filter2):
                try:
                    val2 += getattr(replay.players_dict[p], self._field)
                    i += 1
                except AttributeError as err:
                    debug(
                        f"not attribute 'players_data.{self._field}' (account_id={p}) found in replay: {replay.title}'"
                    )
                    error(err)
            val2 = val2 / i

            return ValueStore(val1 - val2, 1)
        except ZeroDivisionError:
            debug(f"{replay.title_uniq}: divide by zero")
        return ValueStore(0, 0)

    def value(self, value: ValueStore) -> float:
        return value.value / value.n if value.n > 0 else inf


Fields.register(DiffField)

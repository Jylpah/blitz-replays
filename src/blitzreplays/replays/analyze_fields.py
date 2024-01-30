import typer
from typer import Context
import logging
from enum import Enum
from result import Result, Err, Ok

from tomlkit.toml_document import TOMLDocument
from tomlkit.items import Item as TOMLItem, Table as TOMLTable
import tomlkit

from pyutils import AsyncTyper

from .models_reports import Fields
from .args import read_param_list

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

app = AsyncTyper()

metrics = list(Fields.registry.keys())

FieldMetric = Enum("FieldMetric", dict(zip(metrics, metrics)))  # type: ignore


@app.callback()
def fields():
    """
    Report field config
    """


@app.command("list")
def fields_list(ctx: Context):
    """
    List available fields
    """
    field_store: Fields = ctx.obj["fields"]
    fields_param: str | None = ctx.obj["fields_param"]
    if fields_param is not None:
        field_store = field_store.with_config(read_param_list(fields_param))
    doc: TOMLDocument = tomlkit.document()
    doc.add("FIELDS", field_store.get_toml_field_sets())
    typer.echo()
    typer.echo("Configured options for --fields FIELD_SET")
    typer.echo()
    typer.echo(tomlkit.dumps(doc))
    typer.echo()
    doc = tomlkit.document()
    doc.add("FIELD", field_store.get_toml())
    typer.echo("Configured fields for field sets:")
    typer.echo()
    typer.echo(tomlkit.dumps(doc))


# @app.async_command("add")
# async def fields_add(
#     ctx: Context,
# ):
#     """
#     Add new fields to user config
#     """
#     analyze_config_fn: str
#     analyze_config: Path
#     config_file: TOMLFile
#     config: TOMLDocument = tomlkit.document()
#     field_store = FieldStore()
#     try:
#         analyze_config_fn = ctx.obj["analyze_config_fn"]
#         analyze_config = Path(analyze_config_fn)
#     except KeyError:
#         analyze_config = ask_config_file()

#     if analyze_config.is_file():
#         config_file = TOMLFile(analyze_config)
#         config = config_file.read()
#         if isinstance(res_fields := read_analyze_fields(config), Ok):
#             field_store = res_fields.ok_value
#         else:
#             error(f"could not read analyze user config: {analyze_config}")

#     key: str | None = None
#     name: str | None = None
#     metric: str | None = None
#     filter: str | None = None
#     fields: str | None = None
#     frmt: str | None = None
#     try:
#         key_re: re.Pattern = re.compile(r"^[A-Za-z0-9_-]+$")
#         name_re: re.Pattern = re.compile(r"^[\w ]{1,10}$")
#         filter_re: re.Pattern = re.compile(
#             f"(^$)|(^({'|'.join([f.value for f in EnumTeamFilter])})(:({'|'.join([f.value for f in EnumGroupFilter])}))?$)"
#         )
#         metric_opts: List[str] = [v.value for v in FieldMetric]
#         fields_re: re.Pattern | None
#         fields_opts: List[str]

#         while True:
#             typer.echo("Add new FIELD (i.e. column) for reports")

#             if (
#                 key := ask_input(
#                     f"""Field KEY is used to identify the field, but it is not shown in reports. It has to be unique within all FIELDs.
# Allowed characters: A-Za-z0-9_-
# Existing field keys: {', '.join(field_store.db.keys())}""",
#                     "Please enter field key: ",
#                     regexp=key_re,
#                 )
#             ) is None:
#                 raise ValueError("No field KEY given, cancelling...")

#             if (
#                 name := ask_input(
#                     "Please enter a field NAME. This is shown as colum header in reports.",
#                     "Please enter field name: ",
#                     regexp=name_re,
#                 )
#             ) is None:
#                 raise ValueError("No field NAME given, cancelling...")

#             if (
#                 metric := ask_input(
#                     f"""Please enter a field METRIC. It describes the type of field.
# Allowed values: {', '.join(metric_opts)}""",
#                     "Please enter field metric: ",
#                     options=metric_opts,
#                 )
#             ) is None:
#                 raise ValueError("No field METRIC given, cancelling...")

#             if metric == "count":
#                 filter = None
#             else:
#                 if (
#                     filter := ask_input(
#                         f"""Please enter a PLAYER FILTER. It is used to limit the field calculations to only certain players in a replay.
# syntax: TEAM_FILTER[:GROUP_FILTER], where
# \tTEAM_FILTER: {', '.join([v.value for v in EnumTeamFilter])}
# \tGROUP_FILTER: {', '.join([v.value for v in EnumGroupFilter])}
# Leave filter empty to skip filter.
#                         """,
#                         "Please enter player filter: ",
#                         regexp=filter_re,
#                     )
#                 ) is None:
#                     raise ValueError("No field NAME given, cancelling...")
#                 if len(filter) == 0:
#                     filter = None
#             if metric == "count":
#                 fields = "exp"
#             else:
#                 match metric:
#                     case "sum" | "average" | "min" | "max":
#                         fields_re = None
#                         fields_opts = list(ReportField._fields)
#                     case "average_if":
#                         fields_re = re.compile(r"^[a-z_.]+[=<>]-?\d+$")
#                         fields_opts = list()
#                     case "ratio":
#                         fields_re = re.compile(
#                             f"^({'|'.join(ReportField._fields)})/({'|'.join(ReportField._fields)})$"
#                         )
#                         fields_opts = list()
#                     case other:
#                         raise ValueError(f"unsupported metric: {other}")

#                 if (
#                     fields := ask_input(
#                         f"""Please enter replay field for the metric ({metric}). The syntax depends on the metric.
# Allowed replay fields: {', '.join(fld for fld in ReportField._replay_fields)}
# Allowed replay player fields: {', '.join(fld for fld in ReportField._player_fields)}""",
#                         "Please enter the 'fields' param: ",
#                         regexp=fields_re,
#                         options=fields_opts,
#                     )
#                 ) is None:
#                     raise ValueError("No field NAME given, cancelling...")

#                 while True:
#                     if (
#                         frmt := ask_input(
#                             """Please enter a field FORMAT. Use 'Python format syntax'
# Examples:
# \tpercent format: '.1%'
# \ttwo decimals: '.2f'""",
#                             "Please enter field format: ",
#                         )
#                     ) is None:
#                         raise ValueError("No field FORMAT given, cancelling...")
#                     try:
#                         _ = format(3.5, frmt)
#                         break
#                     except Exception:
#                         error(f"invalid format given: {frmt}")
#                 field_store.add(
#                     key=key,
#                     name=name,
#                     filter=filter,
#                     metric=metric,
#                     fields=fields,
#                     format=frmt,
#                 )
#                 typer.echo()
#                 typer.echo(tomlkit.dumps(field_store[key].get_toml()))

#     except ValueError as err:
#         error(err)
#         typer.Exit(code=1)
#         raise SystemExit


# @app.async_command("add2")
# async def fields_add(
#     ctx: Context,
#     field_set: Annotated[str, Argument(help="add the FIELD to a field set")],
#     key: Annotated[
#         str,
#         Option("--key", help="field key, must be unique in the user TOML config file"),
#     ],
#     name: Annotated[
#         str,
#         Option("--name", help="field name that is shown in the reports"),
#     ],
#     metric: Annotated[
#         FieldMetric,
#         Option("--metric", help="metric to calculate the field value"),
#     ],
#     field_config: Annotated[
#         str,
#         Option(
#             "--field-config",
#             help="replay fields that are used to calculate the field value",
#         ),
#     ],
#     field_format: Annotated[
#         str,
#         Option(
#             "--format",
#             help="field value format, uses 'Python Format String Syntax'",
#         ),
#     ],
#     team_filter: Annotated[
#         Optional[EnumTeamFilter],
#         Option(
#             "--team-filter",
#             help="calculate the field value based on the filter",
#         ),
#     ] = None,
#     group_filter: Annotated[
#         EnumGroupFilter,
#         Option(
#             "--group-filter",
#             help="additional filter to be used with --team-filter",
#         ),
#     ] = EnumGroupFilter.default,
#     force: Annotated[
#         bool, Option("--force", help="overwrite existing field configuration")
#     ] = False,
# ):
#     """
#     Add new fields to user config
#     """
#     field_store: FieldStore
#     try:
#         try:
#             analyze_config_fn: str = ctx.obj["analyze_config_fn"]
#         except KeyError:
#             raise ValueError(
#                 "user analyze config not defined: add 'analyze_config' to config file or use '--analyze-config'"
#             )
#         config_file = TOMLFile(analyze_config_fn)
#         config: TOMLDocument | None = None

#         if (config := config_file.read()) is None:
#             raise ValueError(
#                 f"could not read analyze TOML config file: {analyze_config_fn}"
#             )

#         if isinstance(res := read_analyze_fields(config), Err):
#             raise ValueError(f"could not read FIELD config from: {analyze_config_fn}")
#         field_store = res.ok_value
#         if key in field_store.db:
#             if force:
#                 del field_store.db[key]
#             else:
#                 raise ValueError(
#                     f"'FIELD.{key}' is already defined in config file: {analyze_config_fn}\nUse --force to overwrite"
#                 )

#         player_filter: str | None = None
#         if team_filter is not None:
#             player_filter = PlayerFilter(team=team_filter, group=group_filter).key
#         field_store.add(
#             key=key,
#             name=name,
#             metric=metric.value,
#             fields=field_config,
#             filter=player_filter,
#             format=field_format,
#         )
#         field: ReportField = field_store[key]
#         message(f"adding new field: FIELD.{key}")
#         message("")
#         message(tomlkit.dumps(field.get_toml()))
#         message("")

#     except Exception as err:
#         debug("%s: %s", type(err), err)
#         error(err)


def read_analyze_fields(config: TOMLDocument) -> Result[Fields, str]:
    """
    Read FIELD config from analyze TOML config
    """
    try:
        toml_item: TOMLItem | None = None
        field_store = Fields()

        if "FIELDS" in config and isinstance(
            toml_item := config.item("FIELDS"), TOMLTable
        ):
            for key, field_set in toml_item.items():
                field_store.field_sets[key] = field_set
        else:
            debug("'FIELDS' is not defined in analyze config")

        if "FIELD" in config and isinstance(
            toml_item := config.item("FIELD"), TOMLTable
        ):
            for key, field in toml_item.items():
                field_store.add(key=key, **field.unwrap())
        else:
            debug("'FIELD' is not defined in analyze config")

        return Ok(field_store)

    except Exception as err:
        return Err(f"{err}")


# if fields.startswith("+"):

# fld: Dict[str, str]
#             fields = f"default,{fields[1:]}"
#         field_key: str
#         for field_list in fields.split(","):
#             debug("FIELDS.%s", field_list)
#             try:
#                 if (fields_table := fields_item.get(field_list)) is None:
#                     debug("field list not defined: 'FIELDS.%s'", field_list)
#                     raise KeyError()
#                 field_store.field_sets[field_list] = fields_table.unwrap()
#                 for field_key in fields_table.unwrap():
#                     debug("field key=%s", field_key)
#                     # for fld in config_item[field_mode].unwrap():
#                     if (fld_config := field_item.get(field_key)) is None:
#                         debug("field 'FIELD.%s' is not defined", field_key)
#                         raise KeyError
#                     fld = fld_config.unwrap()
#                     debug("adding FIELD: %s", str(fld))
#                     field_store.add(key=field_key, **fld)
#             except KeyError:
#                 debug(f"failed to define field list: {field_list}")

from typing import Dict, List
import typer
from typer import Context
import logging
from result import Result, Err, Ok

from tomlkit.toml_document import TOMLDocument
from tomlkit.items import Item as TOMLItem, Table as TOMLTable
import tomlkit

from pyutils import AsyncTyper

from .models_reports import FieldStore

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

app = AsyncTyper()


@app.async_command("list")
async def fields_list(ctx: Context):
    """
    List available fields
    """
    field_store: FieldStore = ctx.obj["fields"]
    doc: TOMLDocument = tomlkit.document()
    doc.add("FIELDS", field_store.get_toml_field_sets())
    typer.echo()
    typer.echo("Configured field sets for --fields FIELD_SET")
    typer.echo()
    typer.echo(tomlkit.dumps(doc))
    typer.echo()
    doc = tomlkit.document()
    doc.add("FIELD", field_store.get_toml_fields())
    typer.echo("Configured fields for field sets:")
    typer.echo()
    typer.echo(tomlkit.dumps(doc))


def read_analyze_fields(
    config: TOMLDocument, fields: str | None = None
) -> Result[FieldStore, str]:
    """
    Read FIELD config from analyze TOML config
    """

    fields_item: TOMLItem | None = None
    if (fields_item := config.item("FIELDS")) is None:
        return Err("'FIELDS' is not defined in analyze_config file")
    if not (isinstance(fields_item, TOMLTable)):
        return Err(f"FIELDS is not TOML Table: {type(fields_item)}")

    if (field_item := config.item("FIELD")) is None:
        return Err("'FIELD' is not defined in analyze_config file")
    if not (isinstance(field_item, TOMLTable)):
        return Err(f"FIELD is not TOML Table: {type(field_item)}")

    field_store = FieldStore()
    fld: Dict[str, str]

    if fields is not None:
        # append field set to the
        if fields.startswith("+"):
            fields = f"default,{fields[1:]}"
        field_key: str
        for field_list in fields.split(","):
            debug("FIELDS.%s", field_list)
            try:
                if (fields_table := fields_item.get(field_list)) is None:
                    debug("field list not defined: 'FIELDS.%s'", field_list)
                    raise KeyError()
                field_store.field_sets[field_list] = fields_table.unwrap()
                for field_key in fields_table.unwrap():
                    debug("field key=%s", field_key)
                    # for fld in config_item[field_mode].unwrap():
                    if (fld_config := field_item.get(field_key)) is None:
                        debug("field 'FIELD.%s' is not defined", field_key)
                        raise KeyError
                    fld = fld_config.unwrap()
                    debug("adding FIELD: %s", str(fld))
                    field_store.add(key=field_key, **fld)
            except KeyError:
                debug(f"failed to define field list: {field_list}")
    else:
        # return all FIELDs
        for key, field_set in fields_item.items():
            field_store.field_sets[key] = field_set
        for key, field in field_item.items():
            field_store.add(key=key, **field.unwrap())

    return Ok(field_store)


def read_param_fields(fields: str) -> List[str]:
    """
    read --fields [+]FIELD_SET[,FIELD_SET1...]
    """
    res: List[str] = list()
    if fields.startswith("+"):
        fields = f"default,{fields[1:]}"
    for report_set in fields.split(","):
        res.append(report_set)
    return res

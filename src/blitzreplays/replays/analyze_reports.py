import logging
from result import Result, Err, Ok
import typer
from typer import Context

from tomlkit.items import Item as TOMLItem, Table as TOMLTable
from tomlkit.toml_document import TOMLDocument
import tomlkit

# from icecream import ic  # type: ignore

from pyutils import AsyncTyper

from .models_reports import Reports
from .args import read_param_list


logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

app = AsyncTyper()


@app.callback()
def reports():
    """
    Report table config
    """


@app.command("list")
def reports_list(ctx: Context):
    """
    List available reports
    """
    reports: Reports = ctx.obj["reports"]
    reports_param: str | None = ctx.obj["reports_param"]
    if reports_param is not None:
        reports = reports.with_config(read_param_list(reports_param))
    doc: TOMLDocument = tomlkit.document()
    doc.add("REPORTS", reports.get_toml_report_sets())
    typer.echo()
    typer.echo("Configured options for --reports REPORT_SET")
    typer.echo()
    typer.echo(tomlkit.dumps(doc))
    typer.echo()
    doc = tomlkit.document()
    doc.add("REPORT", reports.get_toml())
    typer.echo("Configured reports:")
    typer.echo()
    typer.echo(tomlkit.dumps(doc))


def read_analyze_reports(config: TOMLDocument) -> Result[Reports, str]:
    """
    read REPORT config from analyze TOML config
    """
    try:
        toml_item: TOMLItem | None = None
        report_store = Reports()

        if "REPORTS" in config and isinstance(
            toml_item := config.item("REPORTS"), TOMLTable
        ):
            for key, report_set in toml_item.items():
                report_store.add_report_set(key, report_set)
        else:
            debug("'REPORTS' is not defined in analyze_config")

        if "REPORT" in config and isinstance(
            toml_item := config.item("REPORT"), TOMLTable
        ):
            for key, rpt in toml_item.items():
                report_store.add(key=key, **rpt)
        else:
            debug("'REPORT' is not defined in analyze_config")

        return Ok(report_store)

    except Exception as err:
        return Err(str(err))


# if reports is not None:
#         # '+' appends to default reports
#         if reports.startswith("+"):
#             reports = f"default,{reports[1:]}"
#         report_key: str
#         for report_list in reports.split(","):
#             debug("report list=%s", report_list)
#             try:
#                 if (reports_table := reports_item.get(report_list)) is None:
#                     debug("report list not defined: 'REPORTS.%s'", report_list)
#                     raise KeyError()
#                 for report_key in reports_table.unwrap():
#                     debug("report key=%s", report_key)
#                     if (rpt_config := report_item.get(report_key)) is None:
#                         debug("report 'REPORT.%s' is not defined", report_key)
#                         raise KeyError
#                     rpt = rpt_config.unwrap()
#                     debug("adding report: %s", str(rpt))
#                     report_store.add(key=report_key, **rpt)
#             except KeyError:
#                 debug(f"failed to define report list: {report_list}")
#     else:

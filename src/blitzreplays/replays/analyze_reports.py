import typer
from typer import Context, Option, Argument
from typing import Annotated, Optional, List, Dict, Final, Tuple, Literal
import logging
from result import Result, Err, Ok

from tomlkit.toml_file import TOMLFile
from tomlkit.items import Item as TOMLItem, Table as TOMLTable
from tomlkit.toml_document import TOMLDocument

from pyutils import FileQueue, EventCounter, AsyncTyper, IterableQueue

from .models_reports import Reports

logger = logging.getLogger()
error = logger.error
message = logger.warning
verbose = logger.info
debug = logger.debug

app = AsyncTyper()


def read_analyze_reports(
    config: TOMLDocument, reports: str | None = None
) -> Result[Reports, str]:
    """
    read REPORT config from analyze TOML config
    """

    reports_item: TOMLItem | None = None
    if (reports_item := config.item("REPORTS")) is None:
        return Err("'REPORTS' is not defined in analyze_config file")
    if not (isinstance(reports_item, TOMLTable)):
        return Err(f"REPORTS is not a TOML Table: {type(reports_item)}")

    report_store = Reports()
    debug("Reports -------------------------------------------------------")
    report_item: TOMLItem | None = None
    if (report_item := config.item("REPORT")) is None:
        return Err("'REPORT' is not defined in analyze_config file")
    if not (isinstance(report_item, TOMLTable)):
        return Err(f"REPORT is not TOML Table: {type(report_item)}")

    if reports is not None:
        # '+' appends to default reports
        if reports.startswith("+"):
            reports = f"default,{reports[1:]}"
        report_key: str
        for report_list in reports.split(","):
            debug("report list=%s", report_list)
            try:
                if (reports_table := reports_item.get(report_list)) is None:
                    debug("report list not defined: 'REPORTS.%s'", report_list)
                    raise KeyError()
                for report_key in reports_table.unwrap():
                    debug("report key=%s", report_key)
                    if (rpt_config := report_item.get(report_key)) is None:
                        debug("report 'REPORT.%s' is not defined", report_key)
                        raise KeyError
                    rpt = rpt_config.unwrap()
                    debug("adding report: %s", str(rpt))
                    report_store.add(key=report_key, **rpt)
            except KeyError:
                debug(f"failed to define report list: {report_list}")
    else:
        # return all REPORTs
        for key, report_set in reports_item.items():
            report_store.add_report_set(key, report_set)
        for key, rpt in report_item.items():
            report_store.add(key=key, **rpt)

    return Ok(report_store)


def read_param_reports(reports: str) -> List[str]:
    """
    read --reports [+]REPORT_SET[,REPORT_SET1...]
    """
    res: List[str] = list()
    if reports.startswith("+"):
        reports = f"default,{reports[1:]}"
    for report_set in reports.split(","):
        res.append(report_set)
    return res

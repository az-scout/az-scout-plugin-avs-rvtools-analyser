"""MCP tools for AVS RVTools migration risk analysis."""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import Field


def list_avs_migration_risks() -> str:
    """List all AVS migration risk checks that can be performed on RVTools data.

    Returns a JSON list of risk check names, display names, and categories.
    """
    from az_scout_avs_rvtools_analyser.risk_analysis import get_available_risks

    return json.dumps(get_available_risks(), indent=2)


def analyze_rvtools_json(
    json_data: Annotated[
        str,
        Field(
            description=(
                "RVTools data as a JSON string. Must be a dict of sheet names to "
                'lists of row dicts, e.g. {"vInfo": [{"VM": "vm1", ...}], ...}.'
            )
        ),
    ],
    exclude_powered_off: Annotated[
        bool,
        Field(description="Exclude powered-off VMs from the analysis."),
    ] = False,
) -> str:
    """Analyse RVTools JSON for AVS migration risks (STEP 2 — after convert).

    Requires the JSON output from ``convert_rvtools_excel_to_json``.
    Returns a comprehensive migration risk report covering 19 risk categories
    including vUSB devices, risky disks, network switches, hardware versions,
    shared disks, clear-text passwords, and more.

    Risk levels: emergency, blocking, warning, info.
    """
    import io

    import pandas as pd

    from az_scout_avs_rvtools_analyser.risk_analysis import gather_all_risks

    sheets: dict[str, list[dict[str, object]]] = json.loads(json_data)

    # Build an in-memory Excel file from the JSON data
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, rows in sheets.items():
            df = pd.DataFrame(rows)
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    buf.seek(0)

    excel = pd.ExcelFile(buf)
    result = gather_all_risks(excel, exclude_powered_off=exclude_powered_off)
    return json.dumps(result, indent=2, default=str)


def analyze_rvtools_statistics(
    json_data: Annotated[
        str,
        Field(
            description=(
                "RVTools data as a JSON string. Must be a dict of sheet names to "
                'lists of row dicts, e.g. {"vInfo": [{"VM": "vm1", ...}], ...}.'
            )
        ),
    ],
) -> str:
    """Extract infrastructure statistics from RVTools JSON (STEP 2 — after convert).

    Requires the JSON output from ``convert_rvtools_excel_to_json``.
    Returns VM counts (on/off), total vCPUs, memory (GB), provisioned and
    used storage (GB), disk count, ESXi host count with average CPU/memory
    usage, datastore capacity/usage, and OS distribution.
    """
    import io

    import pandas as pd

    from az_scout_avs_rvtools_analyser.statistics import gather_statistics

    sheets: dict[str, list[dict[str, object]]] = json.loads(json_data)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for sheet_name, rows in sheets.items():
            df = pd.DataFrame(rows)
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    buf.seek(0)

    excel = pd.ExcelFile(buf)
    result = gather_statistics(excel)
    return json.dumps(result, indent=2, default=str)


def convert_rvtools_excel_to_json(
    file_path: Annotated[
        str,
        Field(
            description=(
                "Absolute path to a local RVTools Excel file (.xlsx or .xls). "
                "The file will be read and converted to a JSON string suitable "
                "for analyze_rvtools_json and analyze_rvtools_statistics tools."
            )
        ),
    ],
) -> str:
    """Convert a local RVTools Excel file to JSON (STEP 1 — call this first).

    When a user provides an RVTools Excel file, always call this tool first
    to convert it to JSON. Then pass the returned JSON string as the
    ``json_data`` argument to ``analyze_rvtools_json`` (risk analysis) or
    ``analyze_rvtools_statistics`` (infrastructure statistics).
    """
    from pathlib import Path

    import pandas as pd

    path = Path(file_path)
    if not path.is_file():
        return json.dumps({"error": f"File not found: {file_path}"})
    if path.suffix.lower() not in (".xlsx", ".xls"):
        return json.dumps({"error": f"Unsupported file type: {path.suffix}. Use .xlsx or .xls"})

    excel = pd.ExcelFile(path)

    # Validate this is a genuine RVTools export
    if "vMetaData" not in excel.sheet_names:
        return json.dumps({"error": "Not an RVTools file: missing vMetaData sheet"})
    meta = excel.parse("vMetaData")
    if "RVTools version" not in meta.columns:
        return json.dumps({"error": "Not an RVTools file: vMetaData missing 'RVTools version'"})

    sheets: dict[str, object] = {}
    for name in excel.sheet_names:
        sheet_name = str(name)
        if sheet_name not in _RELEVANT_COLUMNS:
            continue
        df = excel.parse(sheet_name)
        cols = [c for c in _RELEVANT_COLUMNS[sheet_name] if c in df.columns]
        sheets[sheet_name] = df[cols].to_dict(orient="records")

    return json.dumps(sheets, default=str)


# Sheets and columns used by risk_analysis.py and statistics.py
_RELEVANT_COLUMNS: dict[str, list[str]] = {
    "dvPort": [
        "Allow Promiscuous",
        "Forged Transmits",
        "Mac Changes",
        "Object ID",
        "Port",
        "Switch",
        "Type",
        "VLAN",
    ],
    "dvSwitch": ["Switch"],
    "vCD": ["Connected", "Device Type", "Powerstate", "Starts Connected", "VM"],
    "vDatastore": ["Capacity MiB", "In Use MiB"],
    "vDisk": [
        "Capacity MiB",
        "Disk",
        "Disk Mode",
        "Path",
        "Powerstate",
        "Raw",
        "Raw Com. Mode",
        "Shared Bus",
        "VM",
    ],
    "vHost": [
        "# VMs",
        "CPU Model",
        "CPU usage %",
        "Cluster",
        "Datacenter",
        "ESX Version",
        "Host",
        "Memory usage %",
    ],
    "vInfo": [
        "Annotation",
        "CPUs",
        "FT Role",
        "FT State",
        "Guest state",
        "HW version",
        "In Use MiB",
        "Memory",
        "OS according to the configuration file",
        "OS according to the VMware Tools",
        "Powerstate",
        "Provisioned MiB",
        "VM",
    ],
    "vNetwork": ["Network", "Powerstate", "Switch", "VM"],
    "vSnapshot": [
        "Date / time",
        "Description",
        "Name",
        "Powerstate",
        "Size MiB (vmsn)",
        "VM",
    ],
    "vSC_VMK": ["Port Group"],
    "vUSB": ["Connected", "Device Type", "Powerstate", "VM"],
}

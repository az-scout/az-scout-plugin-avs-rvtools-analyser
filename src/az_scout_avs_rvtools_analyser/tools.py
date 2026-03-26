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
    """Analyse RVTools JSON data for Azure VMware Solution migration risks.

    Accepts pre-parsed RVTools data (sheet name → list of row dicts) and
    returns a comprehensive migration risk report covering 19 risk categories
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

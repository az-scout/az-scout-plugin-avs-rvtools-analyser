"""API routes for the AVS RVTools Analyser plugin."""

from __future__ import annotations

import asyncio
import io
from typing import Any

from az_scout.plugin_api import PluginError, PluginValidationError
from fastapi import APIRouter, UploadFile

from az_scout_avs_rvtools_analyser._log import logger
from az_scout_avs_rvtools_analyser.risk_analysis import (
    gather_all_risks,
    get_available_risks,
)
from az_scout_avs_rvtools_analyser.statistics import gather_statistics

router = APIRouter()

_ALLOWED_EXT = {".xlsx", ".xls"}
_MAX_SIZE = 100 * 1024 * 1024  # 100 MB


async def _read_excel(file: UploadFile) -> tuple[bytes, str]:
    """Validate and read an uploaded Excel file. Returns (contents, filename)."""
    if not file.filename:
        raise PluginValidationError("No file provided")
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in _ALLOWED_EXT:
        raise PluginValidationError(f"Invalid file type '{ext}'. Accepted: .xlsx, .xls")
    contents = await file.read()
    if len(contents) > _MAX_SIZE:
        raise PluginValidationError("File exceeds 100 MB limit")
    if len(contents) == 0:
        raise PluginValidationError("Uploaded file is empty")
    return contents, file.filename


def _parse_excel(contents: bytes) -> Any:
    """Parse bytes into a pandas ExcelFile."""
    import pandas

    try:
        return pandas.ExcelFile(io.BytesIO(contents))
    except Exception as exc:
        raise PluginValidationError(f"Cannot parse Excel file: {exc}") from exc


@router.get("/risks")
async def list_risks() -> dict[str, Any]:
    """List all available migration risk checks.

    Available at ``/plugins/avs-rvtools-analyser/risks``.
    """
    risks = get_available_risks()
    return {"total": len(risks), "risks": risks}


@router.post("/analyze-upload")
async def analyze_upload(
    file: UploadFile,
    exclude_powered_off: bool = False,
) -> dict[str, Any]:
    """Upload an RVTools Excel file and run migration risk analysis.

    Available at ``/plugins/avs-rvtools-analyser/analyze-upload``.
    """
    contents, filename = await _read_excel(file)
    logger.debug(
        "Received file '%s' (%d bytes, exclude_powered_off=%s)",
        filename,
        len(contents),
        exclude_powered_off,
    )

    excel = await asyncio.to_thread(_parse_excel, contents)
    logger.debug("Parsed Excel with %d sheets: %s", len(excel.sheet_names), excel.sheet_names)

    try:
        result = await asyncio.to_thread(
            gather_all_risks, excel, exclude_powered_off=exclude_powered_off
        )
    except Exception as exc:
        raise PluginError(f"Analysis failed: {exc}") from exc

    result["filename"] = filename
    result["sheets"] = excel.sheet_names
    logger.debug(
        "Analysis complete: %d total issues (%d blocking, %d warning, %d emergency)",
        result["summary"]["total_issues"],
        result["summary"]["blocking"],
        result["summary"]["warning"],
        result["summary"]["emergency"],
    )
    return result


@router.post("/stats-upload")
async def stats_upload(
    file: UploadFile,
    exclude_powered_off: bool = False,
) -> dict[str, Any]:
    """Upload an RVTools Excel file and extract infrastructure statistics.

    Available at ``/plugins/avs-rvtools-analyser/stats-upload``.
    """
    contents, filename = await _read_excel(file)
    logger.debug(
        "Received file '%s' (%d bytes, exclude_powered_off=%s) for statistics",
        filename,
        len(contents),
        exclude_powered_off,
    )

    excel = await asyncio.to_thread(_parse_excel, contents)

    try:
        result = await asyncio.to_thread(gather_statistics, excel, exclude_powered_off)
    except Exception as exc:
        raise PluginError(f"Statistics extraction failed: {exc}") from exc

    result["filename"] = filename
    result["sheets"] = excel.sheet_names
    return result

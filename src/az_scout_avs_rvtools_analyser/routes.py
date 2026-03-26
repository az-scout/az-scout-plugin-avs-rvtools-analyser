"""API routes for the AVS RVTools Analyser plugin."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd
from az_scout.plugin_api import PluginError, PluginValidationError, get_plugin_logger
from fastapi import APIRouter, UploadFile

from az_scout_avs_rvtools_analyser.risk_analysis import (
    gather_all_risks,
    get_available_risks,
)

logger = get_plugin_logger("avs-rvtools-analyser")
router = APIRouter()

_ALLOWED_EXT = {".xlsx", ".xls"}
_MAX_SIZE = 100 * 1024 * 1024  # 100 MB


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
    if not file.filename:
        raise PluginValidationError("No file provided")

    # Validate extension
    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in _ALLOWED_EXT:
        raise PluginValidationError(f"Invalid file type '{ext}'. Accepted: .xlsx, .xls")

    # Read into memory
    contents = await file.read()
    if len(contents) > _MAX_SIZE:
        raise PluginValidationError("File exceeds 100 MB limit")
    if len(contents) == 0:
        raise PluginValidationError("Uploaded file is empty")

    logger.debug(
        "Received file '%s' (%d bytes, exclude_powered_off=%s)",
        file.filename,
        len(contents),
        exclude_powered_off,
    )

    try:
        excel = pd.ExcelFile(io.BytesIO(contents))
        logger.debug("Parsed Excel with %d sheets: %s", len(excel.sheet_names), excel.sheet_names)
    except Exception as exc:
        raise PluginValidationError(f"Cannot parse Excel file: {exc}") from exc

    try:
        result = gather_all_risks(excel, exclude_powered_off=exclude_powered_off)
    except Exception as exc:
        raise PluginError(f"Analysis failed: {exc}") from exc

    result["filename"] = file.filename
    result["sheets"] = excel.sheet_names
    logger.debug(
        "Analysis complete: %d total issues (%d blocking, %d warning, %d emergency)",
        result["summary"]["total_issues"],
        result["summary"]["blocking"],
        result["summary"]["warning"],
        result["summary"]["emergency"],
    )
    return result

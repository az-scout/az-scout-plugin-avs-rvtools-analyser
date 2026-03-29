"""az-scout AVS RVTools Analyser plugin.

Analyses RVTools Excel exports to detect migration risks for
Azure VMware Solution (AVS). Covers 19 risk categories including
vUSB devices, risky disks, network switches, hardware versions,
shared disks, clear-text passwords, and more.
"""

from collections.abc import Callable
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Any

from az_scout.plugin_api import ChatMode, TabDefinition
from fastapi import APIRouter

_STATIC_DIR = Path(__file__).parent / "static"

try:
    __version__ = _pkg_version("az-scout-plugin-avs-rvtools-analyser")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"


class AvsRvtoolsAnalyserPlugin:
    """AVS RVTools migration risk analysis plugin for az-scout."""

    name = "avs-rvtools-analyser"
    version = __version__

    def get_router(self) -> APIRouter | None:
        from az_scout_avs_rvtools_analyser.routes import router

        return router

    def get_mcp_tools(self) -> list[Callable[..., Any]] | None:
        from az_scout_avs_rvtools_analyser.tools import (
            analyze_rvtools_json,
            analyze_rvtools_statistics,
            convert_rvtools_excel_to_json,
            list_avs_migration_risks,
        )

        return [
            list_avs_migration_risks,
            convert_rvtools_excel_to_json,
            analyze_rvtools_json,
            analyze_rvtools_statistics,
        ]

    def get_static_dir(self) -> Path | None:
        return _STATIC_DIR

    def get_tabs(self) -> list[TabDefinition] | None:
        return [
            TabDefinition(
                id="avs-rvtools-analyser",
                label="AVS RVTools Analyser",
                icon="bi bi-shield-exclamation",
                js_entry="js/avs-rvtools-analyser-tab.js",
                css_entry="css/avs-rvtools-analyser.css",
            )
        ]

    def get_chat_modes(self) -> list[ChatMode] | None:
        return None

    def get_system_prompt_addendum(self) -> str | None:
        return (
            "The `convert_rvtools_excel_to_json` tool converts a local RVTools Excel "
            "file to JSON. The `analyze_rvtools_json` tool analyses that JSON data for "
            "AVS migration risks. The `analyze_rvtools_statistics` tool extracts "
            "infrastructure statistics (VM counts, compute, storage, hosts, OS "
            "distribution). Use `convert_rvtools_excel_to_json` first, then pass the "
            "result to the analysis tools. The `list_avs_migration_risks` tool lists "
            "the 19 risk categories."
        )


# Module-level instance — referenced by the entry point
plugin = AvsRvtoolsAnalyserPlugin()

"""Tests for MCP tools."""

from __future__ import annotations

import json

from az_scout_avs_rvtools_analyser.tools import (
    analyze_rvtools_json,
    list_avs_migration_risks,
)


class TestListRisksTool:
    def test_returns_valid_json(self) -> None:
        result = json.loads(list_avs_migration_risks())
        assert isinstance(result, list)
        assert len(result) > 0
        assert "name" in result[0]


class TestAnalyzeJsonTool:
    def test_analyzes_simple_data(self) -> None:
        data = {
            "vInfo": [
                {
                    "VM": "vm1",
                    "Powerstate": "poweredOn",
                    "CPUs": 2,
                    "Memory": 4096,
                    "Guest state": "running",
                    "Provisioned MiB": 100,
                    "In Use MiB": 50,
                    "OS according to the VMware Tools": "Windows",
                },
            ],
        }
        result = json.loads(analyze_rvtools_json(json.dumps(data)))
        assert "summary" in result
        assert "risks" in result

    def test_empty_data(self) -> None:
        result = json.loads(analyze_rvtools_json(json.dumps({"Empty": [{"A": 1}]})))
        assert result["summary"]["total_issues"] == 0

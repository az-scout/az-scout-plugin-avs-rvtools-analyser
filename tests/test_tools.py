"""Tests for MCP tools."""

from __future__ import annotations

import json
from pathlib import Path

from az_scout_avs_rvtools_analyser.tools import (
    analyze_rvtools_json,
    analyze_rvtools_statistics,
    convert_rvtools_excel_to_json,
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


class TestStatisticsTool:
    def test_returns_statistics(self) -> None:
        data = {
            "vInfo": [
                {
                    "VM": "vm1",
                    "Powerstate": "poweredOn",
                    "CPUs": 4,
                    "Memory": 8192,
                    "Provisioned MiB": 102400,
                    "In Use MiB": 51200,
                    "OS according to the VMware Tools": "Windows",
                },
            ],
        }
        result = json.loads(analyze_rvtools_statistics(json.dumps(data)))
        assert result["vms"]["total"] == 1
        assert result["compute"]["total_vcpus"] == 4

    def test_empty_data(self) -> None:
        result = json.loads(analyze_rvtools_statistics(json.dumps({"Empty": [{"A": 1}]})))
        assert result["vms"]["total"] == 0


class TestConvertExcelToJson:
    def test_converts_valid_file(self, tmp_path: Path) -> None:
        import io

        import pandas as pd

        path = tmp_path / "test.xlsx"
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            pd.DataFrame([{"VM": "vm1", "CPUs": 2}]).to_excel(w, sheet_name="vInfo", index=False)
            pd.DataFrame([{"RVTools version": "4.6.2"}]).to_excel(
                w, sheet_name="vMetaData", index=False
            )
        path.write_bytes(buf.getvalue())

        result = json.loads(convert_rvtools_excel_to_json(str(path)))
        assert "vInfo" in result
        assert len(result["vInfo"]) == 1
        assert result["vInfo"][0]["VM"] == "vm1"

    def test_rejects_non_rvtools_excel(self, tmp_path: Path) -> None:
        import io

        import pandas as pd

        path = tmp_path / "random.xlsx"
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            pd.DataFrame([{"A": 1}]).to_excel(w, sheet_name="Sheet1", index=False)
        path.write_bytes(buf.getvalue())

        result = json.loads(convert_rvtools_excel_to_json(str(path)))
        assert "error" in result
        assert "RVTools" in result["error"]

    def test_file_not_found(self) -> None:
        result = json.loads(convert_rvtools_excel_to_json("/nonexistent/file.xlsx"))
        assert "error" in result

    def test_wrong_extension(self, tmp_path: Path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("a,b\n1,2")
        result = json.loads(convert_rvtools_excel_to_json(str(path)))
        assert "error" in result

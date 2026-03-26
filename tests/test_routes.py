"""Tests for the API routes."""

from __future__ import annotations

import io

import pandas as pd
import pytest
from az_scout.plugin_api import PluginValidationError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from az_scout_avs_rvtools_analyser.routes import router


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/plugins/avs-rvtools-analyser")

    @app.exception_handler(PluginValidationError)
    async def _validation_handler(request: Request, exc: PluginValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    return TestClient(app, raise_server_exceptions=False)


def _make_xlsx(**sheets: dict[str, list[dict]]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(w, sheet_name=name, index=False)
    buf.seek(0)
    return buf.read()


class TestListRisks:
    def test_returns_risks(self, client: TestClient) -> None:
        resp = client.get("/plugins/avs-rvtools-analyser/risks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0
        assert len(data["risks"]) == data["total"]


class TestAnalyzeUpload:
    def test_rejects_no_file(self, client: TestClient) -> None:
        resp = client.post("/plugins/avs-rvtools-analyser/analyze-upload")
        assert resp.status_code == 422

    def test_rejects_wrong_extension(self, client: TestClient) -> None:
        resp = client.post(
            "/plugins/avs-rvtools-analyser/analyze-upload",
            files={"file": ("data.txt", b"hello", "text/plain")},
        )
        assert resp.status_code == 422

    def test_analyzes_valid_file(self, client: TestClient) -> None:
        xlsx = _make_xlsx(
            vInfo=[
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
            ]
        )
        resp = client.post(
            "/plugins/avs-rvtools-analyser/analyze-upload",
            files={"file": ("export.xlsx", xlsx, "application/vnd.ms-excel")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "risks" in data
        assert data["filename"] == "export.xlsx"

    def test_exclude_powered_off(self, client: TestClient) -> None:
        xlsx = _make_xlsx(
            vInfo=[
                {
                    "VM": "on-vm",
                    "Powerstate": "poweredOn",
                    "CPUs": 2,
                    "Memory": 4096,
                    "Guest state": "running",
                    "Provisioned MiB": 100,
                    "In Use MiB": 50,
                    "OS according to the VMware Tools": "Windows",
                },
                {
                    "VM": "off-vm",
                    "Powerstate": "poweredOff",
                    "CPUs": 2,
                    "Memory": 4096,
                    "Guest state": "notRunning",
                    "Provisioned MiB": 100,
                    "In Use MiB": 50,
                    "OS according to the VMware Tools": "Windows",
                },
            ]
        )
        resp = client.post(
            "/plugins/avs-rvtools-analyser/analyze-upload?exclude_powered_off=true",
            files={"file": ("export.xlsx", xlsx, "application/vnd.ms-excel")},
        )
        assert resp.status_code == 200

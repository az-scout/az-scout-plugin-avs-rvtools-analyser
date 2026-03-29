"""Tests for the statistics extraction engine."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd

from az_scout_avs_rvtools_analyser.statistics import gather_statistics


def _make_excel(**sheets: dict[str, list[dict[str, Any]]]) -> pd.ExcelFile:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(w, sheet_name=name, index=False)
    buf.seek(0)
    return pd.ExcelFile(buf)


class TestVmStats:
    def test_counts_power_states(self) -> None:
        excel = _make_excel(
            vInfo=[
                {"VM": "vm1", "Powerstate": "poweredOn", "CPUs": 2, "Memory": 4096},
                {"VM": "vm2", "Powerstate": "poweredOff", "CPUs": 4, "Memory": 8192},
                {"VM": "vm3", "Powerstate": "poweredOn", "CPUs": 1, "Memory": 2048},
                {"VM": "vm4", "Powerstate": "Suspended", "CPUs": 2, "Memory": 4096},
            ]
        )
        result = gather_statistics(excel)
        vms = result["vms"]
        assert vms["total"] == 4
        assert vms["powered_on"] == 2
        assert vms["powered_off"] == 1
        assert vms["suspended"] == 1

    def test_empty_excel(self) -> None:
        excel = _make_excel(Empty=[{"A": 1}])
        result = gather_statistics(excel)
        assert result["vms"]["total"] == 0


class TestComputeStats:
    def test_aggregates_cpu_and_memory(self) -> None:
        excel = _make_excel(
            vInfo=[
                {"VM": "vm1", "Powerstate": "poweredOn", "CPUs": 4, "Memory": 8192},
                {"VM": "vm2", "Powerstate": "poweredOn", "CPUs": 8, "Memory": 16384},
            ]
        )
        result = gather_statistics(excel)
        assert result["compute"]["total_vcpus"] == 12
        # 24576 MiB = 24 GiB
        assert result["compute"]["total_memory_gb"] == 24.0


class TestStorageStats:
    def test_aggregates_storage_and_disks(self) -> None:
        excel = _make_excel(
            vInfo=[
                {
                    "VM": "vm1",
                    "Powerstate": "poweredOn",
                    "CPUs": 2,
                    "Memory": 4096,
                    "Provisioned MiB": 102400,
                    "In Use MiB": 51200,
                },
            ],
            vDisk=[
                {"VM": "vm1", "Disk": "disk1"},
                {"VM": "vm1", "Disk": "disk2"},
            ],
        )
        result = gather_statistics(excel)
        assert result["storage"]["provisioned_gb"] == 100.0
        assert result["storage"]["in_use_gb"] == 50.0
        assert result["storage"]["disk_count"] == 2


class TestHostStats:
    def test_counts_hosts_and_averages(self) -> None:
        excel = _make_excel(
            vHost=[
                {"Host": "esx1", "CPU usage %": 40.0, "Memory usage %": 60.0},
                {"Host": "esx2", "CPU usage %": 60.0, "Memory usage %": 80.0},
            ]
        )
        result = gather_statistics(excel)
        assert result["hosts"]["count"] == 2
        assert result["hosts"]["avg_cpu_usage_pct"] == 50.0
        assert result["hosts"]["avg_memory_usage_pct"] == 70.0


class TestDatastoreStats:
    def test_aggregates_datastore_capacity(self) -> None:
        excel = _make_excel(
            vDatastore=[
                {"Datastore": "ds1", "Capacity MiB": 1048576, "In Use MiB": 524288},
                {"Datastore": "ds2", "Capacity MiB": 524288, "In Use MiB": 262144},
            ]
        )
        result = gather_statistics(excel)
        assert result["datastores"]["count"] == 2
        assert result["datastores"]["total_capacity_gb"] == 1536.0
        assert result["datastores"]["total_in_use_gb"] == 768.0


class TestOsDistribution:
    def test_counts_os_types(self) -> None:
        excel = _make_excel(
            vInfo=[
                {
                    "VM": "vm1",
                    "Powerstate": "poweredOn",
                    "CPUs": 2,
                    "Memory": 4096,
                    "OS according to the VMware Tools": "Microsoft Windows Server 2022",
                },
                {
                    "VM": "vm2",
                    "Powerstate": "poweredOn",
                    "CPUs": 2,
                    "Memory": 4096,
                    "OS according to the VMware Tools": "Microsoft Windows Server 2022",
                },
                {
                    "VM": "vm3",
                    "Powerstate": "poweredOn",
                    "CPUs": 2,
                    "Memory": 4096,
                    "OS according to the VMware Tools": "Ubuntu Linux (64-bit)",
                },
            ]
        )
        result = gather_statistics(excel)
        os_dist = result["os_distribution"]
        assert len(os_dist) == 2
        # Sorted by count desc
        assert os_dist[0]["os"] == "Microsoft Windows Server 2022"
        assert os_dist[0]["count"] == 2
        assert os_dist[1]["os"] == "Ubuntu Linux (64-bit)"
        assert os_dist[1]["count"] == 1

    def test_missing_os_column(self) -> None:
        excel = _make_excel(
            vInfo=[{"VM": "vm1", "Powerstate": "poweredOn", "CPUs": 2, "Memory": 4096}]
        )
        result = gather_statistics(excel)
        assert result["os_distribution"] == []

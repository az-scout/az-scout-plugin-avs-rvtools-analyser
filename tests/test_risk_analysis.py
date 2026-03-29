"""Tests for the risk analysis engine."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd

from az_scout_avs_rvtools_analyser.risk_analysis import (
    RISK_FUNCTIONS,
    gather_all_risks,
    get_available_risks,
)


def _make_excel(**sheets: dict[str, list[dict[str, Any]]]) -> pd.ExcelFile:
    """Build an in-memory ExcelFile from sheet_name → list-of-row-dicts."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(w, sheet_name=name, index=False)
    buf.seek(0)
    return pd.ExcelFile(buf)


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------


class TestPluginInterface:
    def test_plugin_has_required_attributes(self) -> None:
        from az_scout_avs_rvtools_analyser import plugin

        assert hasattr(plugin, "name")
        assert hasattr(plugin, "version")
        assert plugin.name == "avs-rvtools-analyser"

    def test_get_router_returns_router(self) -> None:
        from az_scout_avs_rvtools_analyser import plugin

        router = plugin.get_router()
        assert router is not None

    def test_get_mcp_tools_returns_list(self) -> None:
        from az_scout_avs_rvtools_analyser import plugin

        tools = plugin.get_mcp_tools()
        assert tools is not None
        assert len(tools) == 6

    def test_get_tabs_returns_tab(self) -> None:
        from az_scout_avs_rvtools_analyser import plugin

        tabs = plugin.get_tabs()
        assert tabs is not None
        assert len(tabs) == 1
        assert tabs[0].id == "avs-rvtools-analyser"

    def test_get_chat_modes_returns_none(self) -> None:
        from az_scout_avs_rvtools_analyser import plugin

        assert plugin.get_chat_modes() is None


# ---------------------------------------------------------------------------
# Risk analysis engine
# ---------------------------------------------------------------------------


class TestAvailableRisks:
    def test_returns_all_risks(self) -> None:
        risks = get_available_risks()
        assert len(risks) == len(RISK_FUNCTIONS)

    def test_risk_has_required_fields(self) -> None:
        risks = get_available_risks()
        for r in risks:
            assert "name" in r
            assert "display_name" in r
            assert "category" in r


class TestGatherAllRisks:
    def test_empty_excel(self) -> None:
        excel = _make_excel(Sheet1=[{"A": 1}])
        result = gather_all_risks(excel)
        assert "summary" in result
        assert "risks" in result
        assert result["summary"]["total_issues"] == 0

    def test_detects_suspended_vms(self) -> None:
        excel = _make_excel(
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
                {
                    "VM": "vm2",
                    "Powerstate": "Suspended",
                    "CPUs": 2,
                    "Memory": 4096,
                    "Guest state": "running",
                    "Provisioned MiB": 100,
                    "In Use MiB": 50,
                    "OS according to the VMware Tools": "Linux",
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_suspended_vms"]
        assert risk["count"] == 1
        assert risk["data"][0]["VM"] == "vm2"

    def test_detects_vusb_devices(self) -> None:
        excel = _make_excel(
            vUSB=[
                {"VM": "vm1", "Powerstate": "poweredOn", "Device Type": "USB", "Connected": "true"},
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_vusb_devices"]
        assert risk["count"] == 1
        assert risk["risk_level"] == "blocking"

    def test_detects_risky_disks_rdm_physical(self) -> None:
        excel = _make_excel(
            vDisk=[
                {
                    "VM": "vm1",
                    "Powerstate": "poweredOn",
                    "Disk": "disk1",
                    "Capacity MiB": 1000,
                    "Raw": "true",
                    "Disk Mode": "persistent",
                    "Raw Com. Mode": "physicalMode",
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_risky_disks"]
        assert risk["count"] == 1
        assert risk["risk_level"] == "blocking"

    def test_detects_risky_disks_independent(self) -> None:
        excel = _make_excel(
            vDisk=[
                {
                    "VM": "vm1",
                    "Powerstate": "poweredOn",
                    "Disk": "disk1",
                    "Capacity MiB": 1000,
                    "Raw": "false",
                    "Disk Mode": "independent_persistent",
                    "Raw Com. Mode": "",
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_risky_disks"]
        assert risk["count"] == 1
        assert risk["risk_level"] == "warning"

    def test_detects_oracle_vms(self) -> None:
        excel = _make_excel(
            vInfo=[
                {
                    "VM": "oracle-db",
                    "Powerstate": "poweredOn",
                    "CPUs": 8,
                    "Memory": 32768,
                    "Guest state": "running",
                    "OS according to the VMware Tools": "Oracle Linux 8",
                    "Provisioned MiB": 100,
                    "In Use MiB": 50,
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_oracle_vms"]
        assert risk["count"] == 1

    def test_detects_snapshots(self) -> None:
        excel = _make_excel(
            vSnapshot=[
                {
                    "VM": "vm1",
                    "Powerstate": "poweredOn",
                    "Name": "snap1",
                    "Date / time": "2025-01-01",
                    "Size MiB (vmsn)": 100,
                    "Description": "before update",
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_snapshots"]
        assert risk["count"] == 1

    def test_redacts_passwords_in_snapshots(self) -> None:
        excel = _make_excel(
            vSnapshot=[
                {
                    "VM": "vm1",
                    "Powerstate": "poweredOn",
                    "Name": "snap1",
                    "Date / time": "2025-01-01",
                    "Size MiB (vmsn)": 100,
                    "Description": "password=s3cret",
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_snapshots"]
        assert "REDACTED" in str(risk["data"][0]["Description"])

    def test_detects_clear_text_passwords(self) -> None:
        excel = _make_excel(
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
                    "Annotation": "admin password is 123",
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_clear_text_passwords"]
        assert risk["count"] == 1
        assert risk["risk_level"] == "emergency"

    def test_detects_cdrom_connected(self) -> None:
        excel = _make_excel(
            vCD=[
                {
                    "VM": "vm1",
                    "Powerstate": "poweredOn",
                    "Connected": "true",
                    "Starts Connected": "false",
                    "Device Type": "CD/DVD",
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_cdrom_issues"]
        assert risk["count"] == 1

    def test_detects_non_intel_hosts(self) -> None:
        excel = _make_excel(
            vHost=[
                {
                    "Host": "esx1",
                    "Datacenter": "dc1",
                    "Cluster": "cl1",
                    "CPU Model": "AMD EPYC 7542",
                    "# VMs": 10,
                    "ESX Version": "ESXi 7.0.3",
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_non_intel_hosts"]
        assert risk["count"] == 1

    def test_detects_esx_old_version(self) -> None:
        excel = _make_excel(
            vHost=[
                {
                    "Host": "esx1",
                    "Datacenter": "dc1",
                    "Cluster": "cl1",
                    "CPU Model": "Intel Xeon Gold 6140",
                    "ESX Version": "ESXi 6.0.0",
                    "# VMs": 5,
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_esx_versions"]
        assert risk["count"] == 1
        # Old version should trigger escalated risk
        assert any(d["Risk Level"] == "blocking" for d in risk["data"])

    def test_detects_hw_version_issues(self) -> None:
        excel = _make_excel(
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
                    "HW version": 4,
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_hw_version_compatibility"]
        assert risk["count"] == 1

    def test_detects_fault_tolerance(self) -> None:
        excel = _make_excel(
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
                    "FT State": "running",
                    "FT Role": "primary",
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_fault_tolerance_vms"]
        assert risk["count"] == 1

    def test_detects_vmtools_not_running(self) -> None:
        excel = _make_excel(
            vInfo=[
                {
                    "VM": "vm1",
                    "Powerstate": "poweredOn",
                    "CPUs": 2,
                    "Memory": 4096,
                    "Guest state": "notRunning",
                    "Provisioned MiB": 100,
                    "In Use MiB": 50,
                    "OS according to the VMware Tools": "Windows",
                    "OS according to the configuration file": "Windows 10",
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_vmtools_not_running"]
        assert risk["count"] == 1

    def test_exclude_powered_off(self) -> None:
        excel = _make_excel(
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
        result = gather_all_risks(excel, exclude_powered_off=True)
        # vmtools_not_running should only see powered-on VMs
        risk = result["risks"]["detect_vmtools_not_running"]
        # off-vm is excluded, so it shouldn't count
        for item in risk["data"]:
            assert item["VM"] != "off-vm"

    def test_shared_disks_multi_vm(self) -> None:
        excel = _make_excel(
            vDisk=[
                {
                    "VM": "vm1",
                    "Powerstate": "poweredOn",
                    "Path": "/shared/disk.vmdk",
                    "Raw": "false",
                    "Disk Mode": "persistent",
                },
                {
                    "VM": "vm2",
                    "Powerstate": "poweredOn",
                    "Path": "/shared/disk.vmdk",
                    "Raw": "false",
                    "Disk Mode": "persistent",
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_shared_disks"]
        assert risk["count"] == 1

    def test_non_dvs_switches(self) -> None:
        excel = _make_excel(
            vNetwork=[
                {"VM": "vm1", "Switch": "vSwitch0", "Network": "VM Network"},
            ],
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_non_dvs_switches"]
        assert risk["count"] == 1

    def test_dvport_vlan_zero(self) -> None:
        excel = _make_excel(
            dvPort=[
                {
                    "Port": "1",
                    "Switch": "dvs1",
                    "Object ID": "obj1",
                    "VLAN": None,
                    "Allow Promiscuous": "false",
                    "Mac Changes": "false",
                    "Forged Transmits": "false",
                    "Type": "earlyBinding",
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_dvport_issues"]
        assert risk["count"] == 1

    def test_large_provisioned_vms(self) -> None:
        # 11 TB in MiB
        mib_11tb = int(11 * 1024 * 1024 / 1.048576)
        excel = _make_excel(
            vInfo=[
                {
                    "VM": "big-vm",
                    "Powerstate": "poweredOn",
                    "CPUs": 2,
                    "Memory": 4096,
                    "Guest state": "running",
                    "Provisioned MiB": mib_11tb,
                    "In Use MiB": 1000,
                    "OS according to the VMware Tools": "Linux",
                },
            ]
        )
        result = gather_all_risks(excel)
        risk = result["risks"]["detect_large_provisioned_vms"]
        assert risk["count"] == 1

"""AVS migration risk analysis engine for RVTools data.

Analyses RVTools Excel exports to detect migration risks for Azure VMware Solution.
Each risk detection function examines specific sheets and returns structured results.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd
from az_scout.plugin_api import get_plugin_logger

logger = get_plugin_logger("avs-rvtools-analyser")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ESX_WARNING_THRESHOLD = "7.0.0"
ESX_ERROR_THRESHOLD = "6.5.0"
LARGE_VM_THRESHOLD_TB = 10
MIB_TO_TB = 1.048576 / (1024 * 1024)

MIGRATION_METHODS: dict[str, int] = {
    "HCX vMotion": 9,
    "Cold Migration": 9,
    "Replication Assisted vMotion": 9,
    "Bulk Migration": 7,
}
MIN_SUPPORTED_HW_VERSION = 7

PASSWORD_PATTERN = re.compile(
    r"\bpassword\b|\bpwd\b|\bpass\b|\bpasswd\b|\bpassphrase\b"
    r"|\bpasskey\b|\bsecret\b|\bcredential\b",
    re.IGNORECASE,
)


def _load_sku_data() -> list[dict[str, Any]]:
    from az_scout_avs_sku.avs_data import get_avs_sku_technical_data  # type: ignore[import-untyped]

    return get_avs_sku_technical_data()  # type: ignore[no-any-return]


def _safe_sheet(excel: pd.ExcelFile, name: str) -> pd.DataFrame | None:
    if name in excel.sheet_names:
        return excel.parse(name)
    return None


def _contains_password(text: object) -> bool:
    if not text or text is None:
        return False
    return bool(PASSWORD_PATTERN.search(str(text)))


def _redact(text: object) -> object:
    if not text or text is None:
        return text
    if _contains_password(text):
        return "[REDACTED — password reference removed for security]"
    return text


def _risk_result(
    function_name: str,
    level: str,
    description: str,
    alert_message: str,
    count: int,
    data: list[dict[str, Any]] | list[dict[Any, Any]],
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "function_name": function_name,
        "risk_level": level,
        "risk_info": {"description": description, "alert_message": alert_message},
        "count": count,
        "data": data,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Risk detection functions
# ---------------------------------------------------------------------------


def detect_esx_versions(excel: pd.ExcelFile) -> dict[str, Any]:
    """ESX version distribution and compatibility."""
    desc = "This shows the distribution of ESX versions found in the uploaded file."
    alert = (
        "Having multiple ESX versions in the environment can lead to compatibility issues and "
        "increased complexity during migration.<br><br>It's recommended to standardize on a "
        "single ESX version if possible."
    )
    vhost = _safe_sheet(excel, "vHost")
    if vhost is None:
        return _risk_result("detect_esx_versions", "info", desc, alert, 0, [])

    counts = vhost["ESX Version"].value_counts()
    card_risk = "info"
    rows: list[dict[str, Any]] = []
    for ver_str, cnt in counts.items():
        risk = "info"
        m = re.search(r"ESXi (\d+\.\d+\.\d+)", str(ver_str))
        if m:
            v = m.group(1)
            if v < ESX_ERROR_THRESHOLD:
                risk = "blocking"
                card_risk = "danger"
            elif v < ESX_WARNING_THRESHOLD:
                risk = "warning"
                if card_risk != "danger":
                    card_risk = "warning"
        rows.append({"ESX Version": str(ver_str), "Count": int(cnt), "Risk Level": risk})

    return _risk_result(
        "detect_esx_versions",
        card_risk if card_risk != "info" else "info",
        desc,
        alert,
        len(counts),
        rows,
        {"card_risk": card_risk},
    )


def detect_vusb_devices(excel: pd.ExcelFile) -> dict[str, Any]:
    """vUSB devices attached to VMs (blocking for migration)."""
    desc = (
        "vUSB devices are USB devices connected to a virtual machine (VM) in a VMware environment."
    )
    alert = (
        "Having vUSB devices connected to VMs can pose a risk during migration, as they "
        "cannot be transferred to an Azure Managed environment.<br><br>It's recommended to "
        "review the list of vUSB devices and ensure that they are necessary for the VM's "
        "operation before proceeding with the migration."
    )
    vusb = _safe_sheet(excel, "vUSB")
    if vusb is None:
        return _risk_result("detect_vusb_devices", "blocking", desc, alert, 0, [])

    cols = [c for c in ["VM", "Powerstate", "Device Type", "Connected"] if c in vusb.columns]
    data = vusb[cols].to_dict(orient="records")
    return _risk_result("detect_vusb_devices", "blocking", desc, alert, len(data), data)


def detect_risky_disks(excel: pd.ExcelFile) -> dict[str, Any]:
    """Raw Device Mappings and independent persistent disks."""
    desc = (
        "Risky disks are virtual disks that are configured in a way that may pose a risk "
        "during migration."
    )
    alert = (
        'This can include disks that are set to "Independent" mode or configured with '
        "Raw Device Mapping capability:<br>"
        "<ul>"
        "<li>Raw Device Mapping in physicalMode: Blocking risk — cannot be migrated</li>"
        "<li>Raw Device Mapping in virtualMode: Warning — bulk migration possible "
        "with disk conversion</li>"
        "<li>Independent persistent mode: Warning — requires special consideration</li>"
        "</ul>"
        "It's recommended to review the list of risky disks and consider reconfiguring "
        "them before proceeding with the migration."
    )
    vdisk = _safe_sheet(excel, "vDisk")
    if vdisk is None:
        return _risk_result("detect_risky_disks", "warning", desc, alert, 0, [])

    mask = (vdisk["Raw"].astype(str).str.lower() == "true") | (
        vdisk["Disk Mode"] == "independent_persistent"
    )
    cols = [
        c
        for c in ["VM", "Powerstate", "Disk", "Capacity MiB", "Raw", "Disk Mode", "Raw Com. Mode"]
        if c in vdisk.columns
    ]
    risky = vdisk[mask][cols].copy()

    def _level(row: pd.Series) -> str:
        if str(row.get("Raw", "")).lower() == "true":
            mode = str(row.get("Raw Com. Mode", "")).lower()
            return "blocking" if mode == "physicalmode" else "warning"
        return "warning"

    risky["Risk Level"] = risky.apply(_level, axis=1)
    data = risky.to_dict(orient="records")
    blocking = sum(1 for d in data if d.get("Risk Level") == "blocking")
    card_risk = "blocking" if blocking > 0 else "warning"
    return _risk_result(
        "detect_risky_disks",
        card_risk,
        desc,
        alert,
        len(data),
        data,
        {"blocking_risks": blocking, "warning_risks": len(data) - blocking},
    )


def detect_non_dvs_switches(excel: pd.ExcelFile) -> dict[str, Any]:
    """Standard vSwitches (HCX requires distributed switches)."""
    desc = "This shows the distribution of VMs and ports using dvSwitches or standard vSwitches."
    alert = (
        "HCX network extension functionality requires the use of distributed switches "
        "(dvSwitches). In case of standard vSwitches, the migration process will be "
        "more complex."
    )
    vnet = _safe_sheet(excel, "vNetwork")
    if vnet is None:
        return _risk_result("detect_non_dvs_switches", "blocking", desc, alert, 0, [])

    vnet = vnet[vnet["Switch"].notna() & (vnet["Switch"] != "")]
    dvswitch_list: list[str] = []
    if "dvSwitch" in excel.sheet_names:
        dv = excel.parse("dvSwitch")
        if "Switch" in dv.columns:
            dvswitch_list = list(dv["Switch"].dropna().unique())

    vnet = vnet.copy()
    vnet["Switch Type"] = vnet["Switch"].apply(
        lambda x: "Standard" if x not in dvswitch_list else "Distributed"
    )
    summary = vnet.groupby(["Switch", "Switch Type"]).size().reset_index(name="Port Count")
    non_dvs = int((vnet["Switch Type"] == "Standard").sum())
    data = summary.to_dict(orient="records")
    return _risk_result(
        "detect_non_dvs_switches",
        "blocking" if non_dvs > 0 else "info",
        desc,
        alert,
        non_dvs,
        data if non_dvs > 0 else [],
    )


def detect_snapshots(excel: pd.ExcelFile) -> dict[str, Any]:
    """VM snapshots that complicate migration."""
    desc = (
        "vSnapshots are virtual machine snapshots that capture the state of a VM "
        "at a specific point in time."
    )
    alert = (
        "Having multiple vSnapshots can pose a risk during migration, as they can "
        "increase complexity and may lead to data loss if not handled properly."
        "<br><br>It's recommended to review and consider consolidating or deleting "
        "unnecessary snapshots."
    )
    snap = _safe_sheet(excel, "vSnapshot")
    if snap is None:
        return _risk_result("detect_snapshots", "warning", desc, alert, 0, [])

    rows: list[dict[str, Any]] = []
    for _, r in snap.iterrows():
        dt = r.get("Date / time", "")
        if hasattr(dt, "isoformat"):
            dt = dt.isoformat()
        rows.append(
            {
                "VM": r.get("VM", ""),
                "Powerstate": r.get("Powerstate", ""),
                "Name": r.get("Name", ""),
                "Date / time": str(dt) if dt else "",
                "Size MiB (vmsn)": r.get("Size MiB (vmsn)", ""),
                "Description": _redact(r.get("Description", "")),
            }
        )
    return _risk_result("detect_snapshots", "warning", desc, alert, len(rows), rows)


def detect_suspended_vms(excel: pd.ExcelFile) -> dict[str, Any]:
    """Suspended VMs that must be powered on or off before migration."""
    desc = (
        "Suspended VMs are virtual machines that are not currently running but "
        "have their state saved."
    )
    alert = (
        "Suspended VMs can pose a risk during migration, as it will be necessary to "
        "power them on or off before proceeding.<br><br>It's recommended to review the "
        "list of suspended VMs and consider powering them on or off."
    )
    vinfo = _safe_sheet(excel, "vInfo")
    if vinfo is None:
        return _risk_result("detect_suspended_vms", "warning", desc, alert, 0, [])
    data = vinfo[vinfo["Powerstate"] == "Suspended"][["VM"]].to_dict(orient="records")
    return _risk_result("detect_suspended_vms", "warning", desc, alert, len(data), data)


def detect_oracle_vms(excel: pd.ExcelFile) -> dict[str, Any]:
    """Oracle VMs that may require costly licensing on AVS."""
    desc = "Oracle VMs are virtual machines specifically configured to run Oracle software."
    alert = (
        "Oracle VMs hosting in Azure VMware Solution is supported but may require costly "
        "licensing.<br><br>It's recommended to review the list of Oracle VMs and envision "
        "alternative hosting options to avoid unnecessary costs."
    )
    vinfo = _safe_sheet(excel, "vInfo")
    if vinfo is None:
        return _risk_result("detect_oracle_vms", "info", desc, alert, 0, [])
    col = "OS according to the VMware Tools"
    if col not in vinfo.columns:
        return _risk_result("detect_oracle_vms", "info", desc, alert, 0, [])
    mask = vinfo[col].str.contains("Oracle", na=False)
    cols = [c for c in ["VM", col, "Powerstate", "CPUs", "Memory"] if c in vinfo.columns]
    data = vinfo[mask][cols].to_dict(orient="records")
    return _risk_result("detect_oracle_vms", "info", desc, alert, len(data), data)


def detect_dvport_issues(excel: pd.ExcelFile) -> dict[str, Any]:
    """dvPort configuration issues (VLAN 0, promiscuous, ephemeral, etc.)."""
    desc = (
        "dvPort issues are related to the configuration of distributed virtual ports "
        "in a VMware environment."
    )
    alert = (
        "Multiple dvPort issues can pose a risk during migration:"
        "<ul>"
        "<li>VLAN ID 0 or empty — they cannot be extended via HCX.</li>"
        "<li>Allow Promiscuous mode enabled — This configuration may require "
        "additional setup on destination side.</li>"
        "<li>Mac Changes enabled — This configuration may require additional "
        "setup on destination side.</li>"
        "<li>Forged Transmits enabled — This configuration may require additional "
        "setup on destination side.</li>"
        "<li>Ephemeral binding — VMs will be migrated with NIC being disconnected.</li>"
        "</ul>"
    )
    dvp = _safe_sheet(excel, "dvPort")
    if dvp is None:
        return _risk_result("detect_dvport_issues", "warning", desc, alert, 0, [])

    vlan_null = dvp["VLAN"].isnull()
    dvp = dvp.copy()
    dvp["VLAN"] = dvp["VLAN"].fillna(0).astype(int)
    mask = (
        vlan_null
        | (dvp["Allow Promiscuous"].astype(str).str.lower() == "true")
        | (dvp["Mac Changes"].astype(str).str.lower() == "true")
        | (dvp["Forged Transmits"].astype(str).str.lower() == "true")
        | (dvp["Type"].astype(str).str.lower() == "ephemeral")
    )
    cols = [
        c
        for c in [
            "Port",
            "Switch",
            "Object ID",
            "VLAN",
            "Allow Promiscuous",
            "Mac Changes",
            "Forged Transmits",
            "Type",
        ]
        if c in dvp.columns
    ]
    data = dvp[mask][cols].to_dict(orient="records")
    return _risk_result("detect_dvport_issues", "warning", desc, alert, len(data), data)


def detect_non_intel_hosts(excel: pd.ExcelFile) -> dict[str, Any]:
    """Non-Intel CPU hosts requiring cold migration."""
    desc = (
        "Hosts with CPU models that are not Intel may pose compatibility issues during migration."
    )
    alert = (
        "As Azure VMware Solution is an Intel-based service, a cold migration strategy "
        "will be required for the workloads in these hosts."
    )
    vhost = _safe_sheet(excel, "vHost")
    if vhost is None:
        return _risk_result("detect_non_intel_hosts", "warning", desc, alert, 0, [])
    mask = ~vhost["CPU Model"].str.lower().str.contains("intel", na=False)
    cols = [c for c in ["Host", "Datacenter", "Cluster", "CPU Model", "# VMs"] if c in vhost]
    data = vhost[mask][cols].to_dict(orient="records")
    return _risk_result("detect_non_intel_hosts", "warning", desc, alert, len(data), data)


def detect_vmtools_not_running(excel: pd.ExcelFile) -> dict[str, Any]:
    """Powered-on VMs without VMware Tools running."""
    desc = "VMs that are powered on but their VMware Tools are not running."
    alert = (
        "VMs without VMware Tools running may not be able to use all the features of "
        "VMware HCX during migration.<br><br>It's recommended to ensure that VMware "
        "Tools are installed, running and up-to-date on all powered-on VMs."
    )
    vinfo = _safe_sheet(excel, "vInfo")
    if vinfo is None:
        return _risk_result("detect_vmtools_not_running", "warning", desc, alert, 0, [])
    mask = (vinfo["Powerstate"] == "poweredOn") & (vinfo["Guest state"] == "notRunning")
    cols = [
        c
        for c in ["VM", "Powerstate", "Guest state", "OS according to the configuration file"]
        if c in vinfo.columns
    ]
    data = vinfo[mask][cols].to_dict(orient="records")
    return _risk_result("detect_vmtools_not_running", "warning", desc, alert, len(data), data)


def detect_cdrom_issues(excel: pd.ExcelFile) -> dict[str, Any]:
    """Connected CD-ROM devices that may block migration."""
    desc = "VMs have CD-ROM devices that are connected."
    alert = (
        "CD-ROM devices connected to VMs can cause issues during migration. It's "
        "recommended to review and disconnect unnecessary CD-ROM devices before proceeding."
    )
    vcd = _safe_sheet(excel, "vCD")
    if vcd is None:
        return _risk_result("detect_cdrom_issues", "warning", desc, alert, 0, [])
    mask = vcd["Connected"].astype(str).str.lower() == "true"
    cols = [
        c
        for c in ["VM", "Powerstate", "Connected", "Starts Connected", "Device Type"]
        if c in vcd.columns
    ]
    data = vcd[mask][cols].to_dict(orient="records")
    return _risk_result("detect_cdrom_issues", "warning", desc, alert, len(data), data)


def detect_large_provisioned_vms(excel: pd.ExcelFile) -> dict[str, Any]:
    """VMs with provisioned storage exceeding 10 TB."""
    desc = "VMs have provisioned storage exceeding 10TB."
    alert = (
        "Large provisioned storage can lead to increased migration times and potential "
        "compatibility issues. It's recommended to review these VMs and optimize "
        "storage usage if possible."
    )
    vinfo = _safe_sheet(excel, "vInfo")
    if vinfo is None:
        return _risk_result("detect_large_provisioned_vms", "warning", desc, alert, 0, [])
    vinfo = vinfo.copy()
    vinfo["Provisioned MiB"] = pd.to_numeric(vinfo["Provisioned MiB"], errors="coerce")
    vinfo["Provisioned TB"] = vinfo["Provisioned MiB"] * MIB_TO_TB
    mask = vinfo["Provisioned TB"] > LARGE_VM_THRESHOLD_TB
    cols = [c for c in ["VM", "Provisioned MiB", "In Use MiB", "CPUs", "Memory"] if c in vinfo]
    data = vinfo[mask][cols].to_dict(orient="records")
    return _risk_result("detect_large_provisioned_vms", "warning", desc, alert, len(data), data)


def detect_high_vcpu_vms(excel: pd.ExcelFile) -> dict[str, Any]:
    """VMs with vCPU count exceeding the cores of all available AVS SKUs."""
    desc = "VMs have a vCPU count higher than the core count of available SKUs."
    alert = (
        "The VMs with more vCPUs configured than the available SKUs core count will "
        "not be able to run on the target hosts."
    )
    vinfo = _safe_sheet(excel, "vInfo")
    if vinfo is None:
        return _risk_result("detect_high_vcpu_vms", "blocking", desc, alert, 0, [])
    try:
        sku_data = _load_sku_data()
    except FileNotFoundError:
        return _risk_result("detect_high_vcpu_vms", "blocking", desc, alert, 0, [])

    vinfo = vinfo.copy()
    vinfo["CPUs"] = pd.to_numeric(vinfo["CPUs"], errors="coerce")
    sku_cores = {s["name"]: s["cores"] for s in sku_data}
    min_cores = min(sku_cores.values())

    rows: list[dict[str, Any]] = []
    for _, vm in vinfo.iterrows():
        cpus = vm["CPUs"]
        if pd.notna(cpus) and cpus > min_cores:
            entry: dict[str, Any] = {"VM": vm["VM"], "vCPU Count": int(cpus)}
            for sku, cores in sku_cores.items():
                entry[sku] = cpus <= cores
            rows.append(entry)
    return _risk_result("detect_high_vcpu_vms", "blocking", desc, alert, len(rows), rows)


def detect_high_memory_vms(excel: pd.ExcelFile) -> dict[str, Any]:
    """VMs with memory exceeding the capacity of all available AVS SKUs."""
    desc = "VMs have memory usage exceeding the capabilities of available SKUs."
    alert = (
        "The VMs with more memory configured than the available capacity per node will "
        "not be able to run on the target hosts.<br><br>For performance best practices, "
        "it is also recommended not to exceed half of the available memory per node "
        "on a single VM."
    )
    vinfo = _safe_sheet(excel, "vInfo")
    if vinfo is None:
        return _risk_result("detect_high_memory_vms", "blocking", desc, alert, 0, [])
    try:
        sku_data = _load_sku_data()
    except FileNotFoundError:
        return _risk_result("detect_high_memory_vms", "blocking", desc, alert, 0, [])

    vinfo = vinfo.copy()
    vinfo["Memory"] = pd.to_numeric(vinfo["Memory"], errors="coerce")
    min_mem_mb = min(s["ram"] * 1024 for s in sku_data)

    rows: list[dict[str, Any]] = []
    for _, vm in vinfo.iterrows():
        mem = vm["Memory"]
        if pd.notna(mem) and mem > min_mem_mb:
            entry: dict[str, Any] = {"VM": vm["VM"], "Memory (GB)": round(float(mem) / 1024, 2)}
            for s in sku_data:
                entry[s["name"]] = mem <= s["ram"] * 1024
            rows.append(entry)
    return _risk_result("detect_high_memory_vms", "blocking", desc, alert, len(rows), rows)


def detect_hw_version_compatibility(excel: pd.ExcelFile) -> dict[str, Any]:
    """VMs with legacy hardware versions that limit HCX migration methods."""
    desc = (
        "Virtual machines with legacy hardware version have limited HCX migration "
        "capabilities to Azure VMware Solution. Hardware version determines the "
        "virtual machine's feature set and migration compatibility."
    )
    alert = (
        "You should consider upgrading the hardware version of these VMs before "
        "migration. This requires powering off the VM temporarily."
    )
    vinfo = _safe_sheet(excel, "vInfo")
    if vinfo is None:
        return _risk_result("detect_hw_version_compatibility", "blocking", desc, alert, 0, [])
    if "HW version" not in vinfo.columns:
        return _risk_result("detect_hw_version_compatibility", "blocking", desc, alert, 0, [])

    rows: list[dict[str, Any]] = []
    for _, vm in vinfo.iterrows():
        hw = vm.get("HW version")
        if pd.isna(hw):
            continue
        try:
            hw_num = int(hw)
        except (ValueError, TypeError):
            continue
        unsupported: list[str] = []
        if hw_num < MIN_SUPPORTED_HW_VERSION:
            unsupported = ["All migration methods (HW version too old)"]
        else:
            for method, min_hw in MIGRATION_METHODS.items():
                if hw_num < min_hw:
                    unsupported.append(method)
        if unsupported:
            rows.append(
                {
                    "VM": vm.get("VM", "Unknown"),
                    "HW Version": hw,
                    "Powerstate": vm.get("Powerstate", ""),
                    "Unsupported migration methods": ", ".join(unsupported),
                }
            )
    return _risk_result("detect_hw_version_compatibility", "blocking", desc, alert, len(rows), rows)


def detect_shared_disks(excel: pd.ExcelFile) -> dict[str, Any]:
    """VMs sharing disk paths or using shared SCSI bus."""
    desc = "VMs sharing disks with the same path cannot be migrated."
    alert = (
        "Virtual machines cannot be migrated while they are using a shared SCSI bus, "
        "flagged for multi-writer, or configured for shared VMDK disk sharing."
    )
    vdisk = _safe_sheet(excel, "vDisk")
    if vdisk is None:
        return _risk_result("detect_shared_disks", "blocking", desc, alert, 0, [])
    if "Path" not in vdisk.columns or "VM" not in vdisk.columns:
        return _risk_result("detect_shared_disks", "blocking", desc, alert, 0, [])

    vdisk = vdisk[vdisk["Path"].notna() & (vdisk["Path"] != "")]
    detected_paths: set[str] = set()
    groups: list[dict[str, Any]] = []

    # Multi-VM shared paths
    for path, grp in vdisk.groupby("Path"):
        vms = grp["VM"].unique()
        if len(vms) > 1:
            entry: dict[str, Any] = {
                "Path": path,
                "VM Count": len(vms),
                "VMs": ", ".join(sorted(str(v) for v in vms)),
            }
            if "Shared Bus" in grp.columns:
                vals = grp["Shared Bus"].dropna()
                entry["Shared Bus"] = str(vals.iloc[0]) if len(vals) > 0 else ""
            groups.append(entry)
            detected_paths.add(str(path))

    # Single-VM shared bus != noSharing
    if "Shared Bus" in vdisk.columns:
        mask = (
            vdisk["Shared Bus"].notna()
            & (vdisk["Shared Bus"] != "")
            & (vdisk["Shared Bus"].astype(str).str.lower() != "nosharing")
        )
        for _, row in vdisk[mask].iterrows():
            p = str(row["Path"])
            if p not in detected_paths:
                groups.append(
                    {
                        "Path": p,
                        "VM Count": 1,
                        "VMs": str(row["VM"]),
                        "Shared Bus": str(row["Shared Bus"]),
                    }
                )
                detected_paths.add(p)

    return _risk_result("detect_shared_disks", "blocking", desc, alert, len(groups), groups)


def detect_clear_text_passwords(excel: pd.ExcelFile) -> dict[str, Any]:
    """Clear-text passwords in VM annotations or snapshot descriptions."""
    desc = (
        "Critical security risk: Clear text passwords detected in VM annotations "
        "or snapshot descriptions."
    )
    alert = (
        "<strong>CRITICAL SECURITY ALERT:</strong> Clear text passwords have been "
        "detected in your VMware environment! This poses a significant security risk. "
        "Passwords may have been found in:"
        "<ul>"
        "<li>VM Annotations (vInfo sheet)</li>"
        "<li>Snapshot Descriptions (vSnapshot sheet)</li>"
        "</ul>"
        "<strong>IMPORTANT:</strong> This RVTools file has NOT been stored on our server "
        "and was analyzed in memory only. However, you should immediately:"
        "<ul>"
        "<li>Remove all clear text passwords from VM annotations and snapshot descriptions</li>"
        "<li>Rotate any exposed passwords</li>"
        "<li>Implement secure password management practices</li>"
        "<li>Review access to your vCenter environment</li>"
        "</ul>"
    )
    exposures: list[dict[str, Any]] = []

    vinfo = _safe_sheet(excel, "vInfo")
    if vinfo is not None and "Annotation" in vinfo.columns:
        for _, r in vinfo[vinfo["Annotation"].notna() & (vinfo["Annotation"] != "")].iterrows():
            if _contains_password(r["Annotation"]):
                exposures.append(
                    {
                        "Source": "VM Annotation",
                        "VM Name": r.get("VM", "Unknown"),
                        "Risk Level": "emergency",
                    }
                )

    vsnap = _safe_sheet(excel, "vSnapshot")
    if vsnap is not None and "Description" in vsnap.columns:
        for _, r in vsnap[vsnap["Description"].notna() & (vsnap["Description"] != "")].iterrows():
            if _contains_password(r["Description"]):
                exposures.append(
                    {
                        "Source": "Snapshot Description",
                        "VM Name": r.get("VM", "Unknown"),
                        "Risk Level": "emergency",
                    }
                )

    return _risk_result(
        "detect_clear_text_passwords", "emergency", desc, alert, len(exposures), exposures
    )


def detect_vmkernel_network_vms(excel: pd.ExcelFile) -> dict[str, Any]:
    """VMs connected to ESXi VMkernel networks."""
    desc = "VMs connected to ESXi VMkernel networks instead of standard VM networks."
    alert = (
        "VMkernel networks are designed for ESXi management traffic (vMotion, storage, "
        "management, etc.) and should not be used for virtual machine network "
        "connectivity.<br><br>VMkernel networks cannot be extended with HCX."
        "<br><br>It's recommended to move these VMs to dedicated VM networks "
        "before migration."
    )
    vmk = _safe_sheet(excel, "vSC_VMK")
    if vmk is None or "Port Group" not in vmk.columns:
        return _risk_result("detect_vmkernel_network_vms", "warning", desc, alert, 0, [])

    vmk_networks = set(vmk["Port Group"].dropna().unique())
    if not vmk_networks:
        return _risk_result("detect_vmkernel_network_vms", "warning", desc, alert, 0, [])

    vnet = _safe_sheet(excel, "vNetwork")
    if vnet is None or "Network" not in vnet.columns:
        return _risk_result("detect_vmkernel_network_vms", "warning", desc, alert, 0, [])

    rows: list[dict[str, Any]] = []
    for _, r in vnet.iterrows():
        net = r.get("Network", "")
        if net in vmk_networks:
            rows.append(
                {
                    "VM": r.get("VM", "Unknown"),
                    "Powerstate": r.get("Powerstate", ""),
                    "Network": net,
                    "Switch": r.get("Switch", ""),
                }
            )
    return _risk_result("detect_vmkernel_network_vms", "warning", desc, alert, len(rows), rows)


def detect_fault_tolerance_vms(excel: pd.ExcelFile) -> dict[str, Any]:
    """VMs with Fault Tolerance enabled (must be disabled for migration)."""
    desc = "VMs with Fault Tolerance enabled cannot be migrated."
    alert = (
        "Fault Tolerance (FT) is a feature that provides continuous availability for "
        "VMs by creating a live shadow instance. However, Virtual machines cannot be "
        "migrated while they are Fault Tolerance enabled."
        "<br><br>To migrate FT-enabled VMs:"
        "<ol>"
        "<li><strong>Temporarily</strong> turn off Fault Tolerance,</li>"
        "<li>Perform migration,</li>"
        "<li>When this operation is complete, turn Fault Tolerance back on</li>"
        "</ol>"
    )
    vinfo = _safe_sheet(excel, "vInfo")
    if vinfo is None or "FT State" not in vinfo.columns:
        return _risk_result("detect_fault_tolerance_vms", "warning", desc, alert, 0, [])

    rows: list[dict[str, Any]] = []
    for _, r in vinfo.iterrows():
        ft = r.get("FT State", "notConfigured")
        if ft != "notConfigured":
            rows.append(
                {
                    "VM": r.get("VM", "Unknown"),
                    "Powerstate": r.get("Powerstate", ""),
                    "FT State": ft,
                    "FT Role": r.get("FT Role", ""),
                }
            )
    return _risk_result("detect_fault_tolerance_vms", "warning", desc, alert, len(rows), rows)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

RISK_FUNCTIONS = [
    detect_esx_versions,
    detect_vusb_devices,
    detect_risky_disks,
    detect_non_dvs_switches,
    detect_snapshots,
    detect_suspended_vms,
    detect_oracle_vms,
    detect_dvport_issues,
    detect_non_intel_hosts,
    detect_vmtools_not_running,
    detect_cdrom_issues,
    detect_large_provisioned_vms,
    detect_high_vcpu_vms,
    detect_high_memory_vms,
    detect_hw_version_compatibility,
    detect_shared_disks,
    detect_clear_text_passwords,
    detect_vmkernel_network_vms,
    detect_fault_tolerance_vms,
]


def get_risk_category(name: str) -> str:
    if "esx" in name or "host" in name:
        return "Infrastructure"
    if any(k in name for k in ("vm", "memory", "vcpu", "provisioned", "suspended", "oracle", "ft")):
        return "Virtual Machines"
    if any(k in name for k in ("disk", "cdrom", "snapshot")):
        return "Storage"
    if any(k in name for k in ("switch", "dvport", "network", "vmkernel")):
        return "Networking"
    if any(k in name for k in ("usb", "vmtools", "hw_version", "fault")):
        return "Compatibility"
    if "password" in name:
        return "Security"
    return "General"


def get_available_risks() -> list[dict[str, Any]]:
    """Return metadata about all available risk checks."""
    risks: list[dict[str, Any]] = []
    for fn in RISK_FUNCTIONS:
        # Call with a dummy to extract metadata — instead, infer from function structure
        name = fn.__name__
        display = name.replace("detect_", "").replace("_", " ").title()
        risks.append(
            {
                "name": name,
                "display_name": display,
                "category": get_risk_category(name),
            }
        )
    return risks


def gather_all_risks(
    excel: pd.ExcelFile,
    exclude_powered_off: bool = False,
) -> dict[str, Any]:
    """Run all risk detection functions and return aggregated results.

    Args:
        excel: Parsed RVTools Excel file.
        exclude_powered_off: If True, filter powered-off VMs from vInfo before analysis.
    """
    if exclude_powered_off:
        logger.debug("Filtering powered-off VMs from analysis")
        _filter_powered_off(excel)

    results: dict[str, Any] = {}
    summary: dict[str, int] = {
        "total_issues": 0,
        "blocking": 0,
        "warning": 0,
        "info": 0,
        "emergency": 0,
    }
    for fn in RISK_FUNCTIONS:
        try:
            result = fn(excel)
            logger.debug(
                "  %s: %d issues (%s)",
                fn.__name__,
                result.get("count", 0),
                result.get("risk_level", "info"),
            )
        except Exception as exc:
            logger.exception("Risk detection %s failed", fn.__name__)
            result = {
                "function_name": fn.__name__,
                "risk_level": "info",
                "risk_info": {"description": "", "alert_message": ""},
                "count": 0,
                "data": [],
                "error": str(exc),
            }
        name = result.get("function_name", fn.__name__)
        results[name] = result
        count = result.get("count", 0)
        level = result.get("risk_level", "info")
        if count > 0:
            summary["total_issues"] += count
            if level in summary:
                summary[level] += count

    return {"summary": summary, "risks": results}


def _filter_powered_off(excel: pd.ExcelFile) -> None:
    """Pre-filter powered-off VMs from cached sheet data.

    This modifies the ExcelFile's internal cache so subsequent sheet_names
    reads for vInfo only return powered-on VMs.
    """
    if "vInfo" not in excel.sheet_names:
        return
    vinfo = excel.parse("vInfo")
    powered_on = vinfo[vinfo["Powerstate"] != "poweredOff"]
    powered_on_vms = set(powered_on["VM"].dropna().unique())

    # Replace the cached parse for sheets that reference VMs
    original_parse = excel.parse

    def filtered_parse(sheet_name: str, **kwargs: Any) -> pd.DataFrame:
        df = original_parse(sheet_name, **kwargs)
        if sheet_name == "vInfo":
            return df[df["Powerstate"] != "poweredOff"]
        if "VM" in df.columns:
            return df[df["VM"].isin(powered_on_vms)]
        return df

    excel.parse = filtered_parse  # type: ignore[assignment,method-assign]

#!/usr/bin/env python3
"""Generate a comprehensive RVTools test Excel file with all 19 risk categories represented.

Usage::

    uv run python tools/create_test_data.py                      # default output
    uv run python tools/create_test_data.py -o /tmp/rvtools.xlsx  # custom path
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

# =============================================================================
# Data definitions — modify these to change the generated test data
# =============================================================================

VM_DEFAULTS: dict[str, object] = {
    "powerstate": "poweredOn",
    "guest_state": "running",
    "os": "Microsoft Windows Server 2022",
    "os_config": "Microsoft Windows Server 2022 (64-bit)",
    "hw_version": 17,
    "cpus": 4,
    "memory": 8192,
    "provisioned": 102400,
    "datacenter": "DC-Primary",
    "cluster": "Cluster-01",
    "host": "esxi-host-01",
    "capacity": 51200,
}

VMS = [
    # --- Oracle VMs (info risk) ---
    {
        "name": "vm-db-oracle-01",
        "type": "oracle",
        "os": "Oracle Linux Server 8.5",
        "os_config": "Oracle Linux 8 (64-bit)",
    },
    {
        "name": "vm-db-oracle-02",
        "type": "oracle",
        "os": "Oracle Linux Server 9.1",
        "os_config": "Oracle Linux 9 (64-bit)",
    },
    # --- Suspended VMs (warning) ---
    {
        "name": "vm-suspended-01",
        "type": "suspended",
        "powerstate": "Suspended",
        "guest_state": "notRunning",
        "hw_version": 11,
    },
    {
        "name": "vm-suspended-02",
        "type": "suspended",
        "powerstate": "Suspended",
        "guest_state": "notRunning",
        "hw_version": 8,
    },
    # --- Old hardware versions (blocking) ---
    {
        "name": "vm-old-hw-01",
        "type": "old_hw",
        "hw_version": 6,
        "powerstate": "poweredOff",
        "guest_state": "notRunning",
    },
    {
        "name": "vm-old-hw-02",
        "type": "old_hw",
        "hw_version": 7,
        "powerstate": "poweredOff",
        "guest_state": "notRunning",
    },
    # --- High vCPU (blocking) ---
    {
        "name": "vm-high-cpu-01",
        "type": "high_cpu",
        "cpus": 72,
        "os": "Red Hat Enterprise Linux 8.6",
    },
    {
        "name": "vm-high-cpu-02",
        "type": "high_cpu",
        "cpus": 64,
        "os": "Red Hat Enterprise Linux 9.1",
    },
    # --- High memory (blocking) ---
    {"name": "vm-high-memory-01", "type": "high_memory", "memory": 1048576},  # 1 TB
    {"name": "vm-high-memory-02", "type": "high_memory", "memory": 786432},  # 768 GB
    # --- Large provisioned storage (warning) ---
    {
        "name": "vm-large-storage-01",
        "type": "large_storage",
        "provisioned": 10737418240,
        "capacity": 10485760,
    },  # >10 TB
    {
        "name": "vm-large-storage-02",
        "type": "large_storage",
        "provisioned": 20971520000,
        "capacity": 20971520,
    },  # >20 TB
    # --- VMware Tools not running (warning) ---
    {
        "name": "vm-tools-issue-01",
        "type": "tools_issue",
        "guest_state": "notRunning",
        "os": "Ubuntu Linux 18.04",
    },
    {
        "name": "vm-tools-issue-02",
        "type": "tools_issue",
        "guest_state": "notRunning",
        "os": "Debian GNU/Linux 11",
    },
    # --- Shared disks (blocking) ---
    {"name": "vm-cluster-node-01", "type": "shared_disk", "shared_group": "cluster1"},
    {"name": "vm-cluster-node-02", "type": "shared_disk", "shared_group": "cluster1"},
    {"name": "vm-cluster-node-03", "type": "shared_disk", "shared_group": "cluster2"},
    {"name": "vm-cluster-node-04", "type": "shared_disk", "shared_group": "cluster2"},
    {"name": "vm-shared-storage-01", "type": "shared_disk", "shared_group": "multi_shared"},
    {"name": "vm-shared-storage-02", "type": "shared_disk", "shared_group": "multi_shared"},
    {"name": "vm-shared-storage-03", "type": "shared_disk", "shared_group": "multi_shared"},
    {"name": "vm-individual-shared-01", "type": "individual_shared"},
    {"name": "vm-individual-shared-02", "type": "individual_shared"},
    # --- Risky disks: RDM + independent persistent (blocking/warning) ---
    {
        "name": "vm-risky-disk-01",
        "type": "raw_disk",
        "disk_raw": True,
        "disk_raw_mode": "physicalMode",
    },
    {
        "name": "vm-risky-disk-02",
        "type": "raw_disk",
        "disk_raw": True,
        "disk_raw_mode": "virtualMode",
    },
    {
        "name": "vm-risky-disk-03",
        "type": "raw_disk",
        "disk_raw": True,
        "disk_raw_mode": "physicalMode",
    },
    {"name": "vm-risky-disk-04", "type": "independent_disk", "disk_mode": "independent_persistent"},
    # --- Standard / clean VMs ---
    {"name": "vm-web-server-01", "type": "web"},
    {"name": "vm-web-server-02", "type": "web", "memory": 16384, "provisioned": 204800},
    # --- Clear-text password exposure (emergency) ---
    {
        "name": "vm-password-exposed-01",
        "type": "web",
        "annotation": "Admin user password is admin123 - change after deployment",
    },
    {
        "name": "vm-password-exposed-02",
        "type": "web",
        "annotation": "Service account pwd: ServicePass456",
    },
    {
        "name": "vm-password-exposed-03",
        "type": "web",
        "annotation": "Contains secret key and credentials for DB access",
    },
    {
        "name": "vm-clean-annotation",
        "type": "web",
        "annotation": "Regular server configuration notes",
    },
    # --- VMkernel network VMs (warning) ---
    {"name": "vm-vmkernel-mgmt-01", "type": "vmkernel_risk", "vmkernel_network": "vMotion-Network"},
    {
        "name": "vm-vmkernel-mgmt-02",
        "type": "vmkernel_risk",
        "vmkernel_network": "Management-Network",
    },
    {
        "name": "vm-vmkernel-storage-01",
        "type": "vmkernel_risk",
        "vmkernel_network": "Storage-Network",
    },
    # --- Normal app VMs ---
    {"name": "vm-app-server-01", "type": "app", "os": "Ubuntu Linux 20.04"},
    {"name": "vm-app-server-02", "type": "app", "os": "Ubuntu Linux 22.04"},
    # --- Mixed issues VM (multiple risks on one VM) ---
    {
        "name": "vm-mixed-issues-01",
        "type": "mixed",
        "os": "Oracle Linux Server 7.9",
        "hw_version": 6,
        "cpus": 80,
        "memory": 1572864,
        "provisioned": 10737418240,
    },
    # --- Baseline clean VM ---
    {"name": "vm-baseline-good", "type": "baseline"},
    # --- Fault Tolerance enabled (warning) ---
    {
        "name": "vm-ft-enabled-01 (primary)",
        "type": "ft_enabled",
        "ft_state": "running",
        "ft_role": "1",
    },
    {
        "name": "vm-ft-enabled-01 (secondary)",
        "type": "ft_enabled",
        "ft_state": "running",
        "ft_role": "2",
    },
    {
        "name": "vm-ft-enabled-02 (primary)",
        "type": "ft_enabled",
        "ft_state": "needSecondary",
        "ft_role": "1",
    },
    {
        "name": "vm-ft-notenabled-01",
        "type": "ft_enabled",
        "ft_state": "notConfigured",
        "ft_role": "",
    },
]

HOSTS = [
    {
        "name": "esxi-host-01",
        "esx_version": "VMware ESXi 6.5.0",
        "cpu_model": "AMD EPYC 7402P",
        "datacenter": "DC-Primary",
        "cluster": "Cluster-01",
    },
    {
        "name": "esxi-host-02",
        "esx_version": "VMware ESXi 6.7.0",
        "cpu_model": "AMD EPYC 7543",
        "datacenter": "DC-Primary",
        "cluster": "Cluster-01",
    },
    {
        "name": "esxi-host-03",
        "esx_version": "VMware ESXi 7.0.3",
        "cpu_model": "Intel Xeon Gold 6254",
        "datacenter": "DC-Primary",
        "cluster": "Cluster-01",
    },
    {
        "name": "esxi-host-04",
        "esx_version": "VMware ESXi 7.0.3",
        "cpu_model": "Intel Xeon Gold 6348",
        "datacenter": "DC-Secondary",
        "cluster": "Cluster-02",
    },
    {
        "name": "esxi-host-05",
        "esx_version": "VMware ESXi 8.0.1",
        "cpu_model": "Intel Xeon Platinum 8380",
        "datacenter": "DC-Secondary",
        "cluster": "Cluster-02",
    },
    {
        "name": "esxi-host-06",
        "esx_version": "VMware ESXi 8.0.2",
        "cpu_model": "Intel Xeon Platinum 8480+",
        "datacenter": "DC-Tertiary",
        "cluster": "Cluster-03",
    },
]

USB_DEVICES = [
    {"vm": "vm-web-server-01", "device": "USB Controller", "connected": True},
    {"vm": "vm-app-server-01", "device": "USB Mass Storage", "connected": True},
    {"vm": "vm-db-oracle-01", "device": "USB Smart Card Reader", "connected": True},
    {"vm": "vm-app-server-02", "device": "USB Printer", "connected": False},
    {"vm": "vm-mixed-issues-01", "device": "USB Hub", "connected": True},
]

SNAPSHOTS = [
    {
        "vm": "vm-db-oracle-01",
        "name": "Pre-patch snapshot",
        "desc": "Created before monthly patching",
        "date": "2024-01-15 10:30:00",
        "size": 5120,
    },
    {
        "vm": "vm-db-oracle-02",
        "name": "Database backup point",
        "desc": "Before database schema upgrade",
        "date": "2024-01-20 14:15:00",
        "size": 8192,
    },
    {
        "vm": "vm-app-server-01",
        "name": "Before upgrade",
        "desc": "Before application upgrade",
        "date": "2024-01-25 02:00:00",
        "size": 2048,
    },
    {
        "vm": "vm-app-server-02",
        "name": "Performance baseline",
        "desc": "Baseline before performance tuning",
        "date": "2024-02-01 16:45:00",
        "size": 4096,
    },
    {
        "vm": "vm-web-server-01",
        "name": "Backup point",
        "desc": "Daily backup snapshot",
        "date": "2024-02-05 08:30:00",
        "size": 1024,
    },
    {
        "vm": "vm-web-server-02",
        "name": "Security update prep",
        "desc": "Before security patch installation",
        "date": "2024-02-10 12:15:00",
        "size": 3072,
    },
    {
        "vm": "vm-large-storage-01",
        "name": "Storage migration prep",
        "desc": "Before storage vMotion",
        "date": "2024-02-15 18:00:00",
        "size": 15360,
    },
    {
        "vm": "vm-mixed-issues-01",
        "name": "Multi-snapshot-vm",
        "desc": "Multiple snapshots for testing",
        "date": "2024-02-20 22:30:00",
        "size": 6144,
    },
    # Password exposure in snapshot descriptions (emergency)
    {
        "vm": "vm-password-exposed-01",
        "name": "Password reset point",
        "desc": "Before password change - old password was SecretPass123",
        "date": "2024-02-25 09:00:00",
        "size": 2048,
    },
    {
        "vm": "vm-password-exposed-02",
        "name": "Credential backup",
        "desc": "Service credentials updated - passphrase stored in config",
        "date": "2024-02-26 11:30:00",
        "size": 1536,
    },
    {
        "vm": "vm-clean-annotation",
        "name": "Clean snapshot",
        "desc": "Regular maintenance snapshot without sensitive data",
        "date": "2024-02-27 14:00:00",
        "size": 1024,
    },
]

CDROMS = [
    {
        "vm": "vm-app-server-01",
        "connected": "True",
        "starts": "True",
        "iso": "[datastore1] iso/windows-server-2019.iso",
    },
    {"vm": "vm-web-server-01", "connected": "False", "starts": "False", "iso": ""},
    {
        "vm": "vm-db-oracle-01",
        "connected": "True",
        "starts": "True",
        "iso": "[datastore2] iso/oracle-linux-8.5.iso",
    },
    {
        "vm": "vm-db-oracle-02",
        "connected": "True",
        "starts": "True",
        "iso": "[datastore1] iso/oracle-database-19c.iso",
    },
    {
        "vm": "vm-mixed-issues-01",
        "connected": "True",
        "starts": "True",
        "iso": "[datastore3] iso/mixed-tools.iso",
    },
    {"vm": "vm-baseline-good", "connected": "False", "starts": "False", "iso": ""},
]

STANDARD_SWITCH_VMS = [
    {"vm": "vm-standard-switch-01", "label": "VM Network", "switch": "vSwitch0"},
    {"vm": "vm-standard-switch-02", "label": "Management Network", "switch": "vSwitch1"},
    {"vm": "vm-standard-switch-03", "label": "Storage Network", "switch": "vSwitch2"},
    {"vm": "vm-mixed-issues-01", "label": "Legacy-Network", "switch": "vSwitch0"},
]

DVPORTS = [
    {
        "vm": "vm-web-server-01",
        "type": "earlyBinding",
        "vlan": 100,
        "promiscuous": "False",
        "mac": "False",
        "forge": "False",
    },
    {
        "vm": "vm-db-oracle-01",
        "type": "earlyBinding",
        "vlan": None,
        "promiscuous": "True",
        "mac": "False",
        "forge": "True",
    },
    {
        "vm": "vm-risky-port-01",
        "type": "ephemeral",
        "vlan": 200,
        "promiscuous": "False",
        "mac": "True",
        "forge": "False",
    },
    {
        "vm": "vm-risky-port-02",
        "type": "ephemeral",
        "vlan": None,
        "promiscuous": "False",
        "mac": "False",
        "forge": "True",
    },
    {
        "vm": "vm-app-server-01",
        "type": "earlyBinding",
        "vlan": 300,
        "promiscuous": "False",
        "mac": "False",
        "forge": "False",
    },
    {
        "vm": "vm-security-risk-01",
        "type": "earlyBinding",
        "vlan": 400,
        "promiscuous": "True",
        "mac": "True",
        "forge": "True",
    },
    {
        "vm": "vm-ephemeral-risk-01",
        "type": "ephemeral",
        "vlan": 500,
        "promiscuous": "False",
        "mac": "False",
        "forge": "False",
    },
    {
        "vm": "vm-ephemeral-risk-02",
        "type": "ephemeral",
        "vlan": 600,
        "promiscuous": "False",
        "mac": "False",
        "forge": "False",
    },
    {
        "vm": "vm-baseline-good",
        "type": "earlyBinding",
        "vlan": 700,
        "promiscuous": "False",
        "mac": "False",
        "forge": "False",
    },
]

VMKERNEL_INTERFACES = [
    {
        "host": "esxi-host-01",
        "device": "vmk0",
        "network": "Management-Network",
        "ip": "192.168.10.101",
        "netmask": "255.255.255.0",
        "mtu": 1500,
    },
    {
        "host": "esxi-host-01",
        "device": "vmk1",
        "network": "vMotion-Network",
        "ip": "192.168.20.101",
        "netmask": "255.255.255.0",
        "mtu": 9000,
    },
    {
        "host": "esxi-host-01",
        "device": "vmk2",
        "network": "Storage-Network",
        "ip": "192.168.30.101",
        "netmask": "255.255.255.0",
        "mtu": 9000,
    },
    {
        "host": "esxi-host-02",
        "device": "vmk0",
        "network": "Management-Network",
        "ip": "192.168.10.102",
        "netmask": "255.255.255.0",
        "mtu": 1500,
    },
    {
        "host": "esxi-host-02",
        "device": "vmk1",
        "network": "vMotion-Network",
        "ip": "192.168.20.102",
        "netmask": "255.255.255.0",
        "mtu": 9000,
    },
    {
        "host": "esxi-host-02",
        "device": "vmk2",
        "network": "Storage-Network",
        "ip": "192.168.30.102",
        "netmask": "255.255.255.0",
        "mtu": 9000,
    },
    {
        "host": "esxi-host-03",
        "device": "vmk0",
        "network": "Management-Network",
        "ip": "192.168.10.103",
        "netmask": "255.255.255.0",
        "mtu": 1500,
    },
    {
        "host": "esxi-host-03",
        "device": "vmk1",
        "network": "vMotion-Network",
        "ip": "192.168.20.103",
        "netmask": "255.255.255.0",
        "mtu": 9000,
    },
]

SHARED_DISK_GROUPS = {
    "cluster1": "[shared-datastore] cluster-shared-disk-01.vmdk",
    "cluster2": "[shared-datastore] cluster-shared-disk-02.vmdk",
    "multi_shared": "[shared-datastore] multi-shared-storage.vmdk",
}


# =============================================================================
# Sheet builders
# =============================================================================


def build_vhost() -> pd.DataFrame:
    data = []
    for host in HOSTS:
        vm_count = sum(1 for vm in VMS if vm.get("host", VM_DEFAULTS["host"]) == host["name"])
        data.append(
            {
                "Host": host["name"],
                "ESX Version": host["esx_version"],
                "CPU Model": host["cpu_model"],
                "Datacenter": host["datacenter"],
                "Cluster": host["cluster"],
                "# VMs": vm_count,
            }
        )
    return pd.DataFrame(data)


def build_vinfo() -> pd.DataFrame:
    data = []
    for vm in VMS:
        d = {**VM_DEFAULTS, **vm}
        in_use = int(d["provisioned"]) // 2  # type: ignore[arg-type]
        data.append(
            {
                "VM": d["name"],
                "Powerstate": d["powerstate"],
                "Guest state": d["guest_state"],
                "OS according to the VMware Tools": d["os"],
                "OS according to the configuration file": d["os_config"],
                "HW version": d["hw_version"],
                "CPUs": d["cpus"],
                "Memory": d["memory"],
                "Provisioned MiB": d["provisioned"],
                "In Use MiB": in_use,
                "Datacenter": d["datacenter"],
                "Cluster": d["cluster"],
                "Host": d["host"],
                "Annotation": d.get("annotation", ""),
                "FT State": d.get("ft_state", "notConfigured"),
                "FT Role": d.get("ft_role", ""),
            }
        )
    return pd.DataFrame(data)


def build_vdisk() -> pd.DataFrame:
    data = []
    for vm in VMS:
        d = {**VM_DEFAULTS, **vm}
        disk_path = f"[datastore1] {d['name']}/{d['name']}.vmdk"
        if d.get("shared_group"):
            disk_path = SHARED_DISK_GROUPS[d["shared_group"]]

        sharing_mode = "sharingNone"
        shared_bus = "noSharing"
        if d.get("type") in ("shared_disk", "individual_shared"):
            sharing_mode = "sharingMultiWriter"
            shared_bus = "physicalSharing"

        data.append(
            {
                "VM": d["name"],
                "Powerstate": d["powerstate"],
                "Disk": "Hard disk 1",
                "Capacity MiB": d["capacity"],
                "Raw": d.get("disk_raw", False),
                "Raw Com. Mode": d.get("disk_raw_mode", ""),
                "Disk Mode": d.get("disk_mode", "persistent"),
                "Path": disk_path,
                "Sharing mode": sharing_mode,
                "Shared Bus": shared_bus,
            }
        )
    return pd.DataFrame(data)


def build_vusb() -> pd.DataFrame:
    data = []
    for i, usb in enumerate(USB_DEVICES):
        data.append(
            {
                "VM": usb["vm"],
                "Powerstate": "poweredOn",
                "Device Type": usb["device"],
                "Connected": usb["connected"],
                "Path": f"/vmfs/devices/usb/{i + 1:03d}/001",
            }
        )
    return pd.DataFrame(data)


def build_vsnapshot() -> pd.DataFrame:
    data = []
    for snap in SNAPSHOTS:
        data.append(
            {
                "VM": snap["vm"],
                "Powerstate": "poweredOn",
                "Name": snap["name"],
                "Description": snap["desc"],
                "Date / time": snap["date"],
                "Size MiB (vmsn)": snap["size"],
            }
        )
    return pd.DataFrame(data)


def build_vcd() -> pd.DataFrame:
    data = []
    for cd in CDROMS:
        data.append(
            {
                "VM": cd["vm"],
                "Powerstate": "poweredOn",
                "Connected": cd["connected"],
                "Starts Connected": cd["starts"],
                "Device Type": "CD/DVD drive",
            }
        )
    return pd.DataFrame(data)


def build_vnetwork() -> pd.DataFrame:
    data = []
    # Standard switch VMs (risk: non-dvSwitch)
    for net in STANDARD_SWITCH_VMS:
        data.append(
            {
                "VM": net["vm"],
                "Powerstate": "poweredOn",
                "Network": net["label"],
                "Switch": net["switch"],
                "Connected": True,
                "IPv4 Address": "192.168.1.100",
            }
        )
    # dvSwitch VMs (good)
    for i, vm_name in enumerate(
        [
            "vm-web-server-01",
            "vm-web-server-02",
            "vm-db-oracle-01",
            "vm-app-server-01",
            "vm-baseline-good",
        ]
    ):
        data.append(
            {
                "VM": vm_name,
                "Powerstate": "poweredOn",
                "Network": f"Production-VLAN-{100 + i * 100}",
                "Switch": f"dvSwitch-{(i % 2) + 1:02d}",
                "Connected": True,
                "IPv4 Address": "192.168.1.100",
            }
        )
    # VMs on VMkernel networks (warning)
    for vmk_vm in [
        {"vm": "vm-vmkernel-mgmt-01", "network": "Management-Network"},
        {"vm": "vm-vmkernel-mgmt-02", "network": "Management-Network"},
        {"vm": "vm-vmkernel-storage-01", "network": "Storage-Network"},
    ]:
        data.append(
            {
                "VM": vmk_vm["vm"],
                "Powerstate": "poweredOn",
                "Network": vmk_vm["network"],
                "Switch": "vSwitch0",
                "Connected": True,
                "IPv4 Address": "192.168.1.100",
            }
        )
    return pd.DataFrame(data)


def build_vsc_vmk() -> pd.DataFrame:
    data = []
    for vmk in VMKERNEL_INTERFACES:
        data.append(
            {
                "Host": vmk["host"],
                "Device": vmk["device"],
                "Port Group": vmk["network"],
                "IP Address": vmk["ip"],
                "Subnet mask": vmk["netmask"],
                "MTU": vmk["mtu"],
                "Datacenter": "DC-Primary",
                "Cluster": "Cluster-01",
            }
        )
    return pd.DataFrame(data)


def build_dvport() -> pd.DataFrame:
    data = []
    for i, port in enumerate(DVPORTS):
        data.append(
            {
                "Port": str(50000001 + i),
                "Switch": "dvSwitch-01",
                "Object ID": str(1001 + i),
                "Type": port["type"],
                "VLAN": port["vlan"],
                "Allow Promiscuous": port["promiscuous"],
                "Mac Changes": port["mac"],
                "Forged Transmits": port["forge"],
            }
        )
    return pd.DataFrame(data)


def build_dvswitch() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Switch": "dvSwitch-01",
                "Name": "dvSwitch-01",
                "Type": "Distributed Virtual Switch",
                "Version": "7.0.3",
                "Datacenter": "DC-Primary",
            },
            {
                "Switch": "dvSwitch-02",
                "Name": "dvSwitch-02",
                "Type": "Distributed Virtual Switch",
                "Version": "8.0.1",
                "Datacenter": "DC-Secondary",
            },
        ]
    )


# =============================================================================
# Main
# =============================================================================


def create_test_data(output_path: Path | None = None) -> Path:
    """Create a comprehensive RVTools-like Excel file with all risk categories."""
    if output_path is None:
        output_path = Path("comprehensive_test_data.xlsx")

    sheets = {
        "vHost": build_vhost(),
        "vInfo": build_vinfo(),
        "vDisk": build_vdisk(),
        "vUSB": build_vusb(),
        "vSnapshot": build_vsnapshot(),
        "vCD": build_vcd(),
        "vNetwork": build_vnetwork(),
        "vSC_VMK": build_vsc_vmk(),
        "dvPort": build_dvport(),
        "dvSwitch": build_dvswitch(),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"Created: {output_path}")
    print(f"Sheets:  {len(sheets)}")
    for name, df in sheets.items():
        print(f"  {name}: {len(df)} rows")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a comprehensive RVTools test Excel file."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: comprehensive_test_data.xlsx)",
    )
    args = parser.parse_args()
    create_test_data(args.output)

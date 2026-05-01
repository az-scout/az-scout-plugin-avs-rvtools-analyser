"""RVTools statistics extraction engine.

Extracts infrastructure statistics from RVTools Excel exports:
VM counts, compute, storage, network, host, and OS distribution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

MIB_TO_GB = 1 / 1024


def gather_statistics(excel: pd.ExcelFile, exclude_powered_off: bool = False) -> dict[str, Any]:
    """Extract infrastructure statistics from an RVTools Excel file.

    Args:
        excel: Parsed RVTools Excel file.
        exclude_powered_off: If True, filter powered-off VMs before extracting statistics.

    Returns a dict with keys: vms, compute, storage, hosts, os_distribution.
    """
    if exclude_powered_off:
        from az_scout_avs_rvtools_analyser.risk_analysis import filter_powered_off

        filter_powered_off(excel)

    import pandas

    stats: dict[str, Any] = {
        "vms": _vm_stats(excel, pandas),
        "compute": _compute_stats(excel, pandas),
        "storage": _storage_stats(excel, pandas),
        "hosts": _host_stats(excel, pandas),
        "datastores": _datastore_stats(excel, pandas),
        "os_distribution": _os_distribution(excel),
    }
    return stats


def _safe_sheet(excel: pd.ExcelFile, name: str) -> pd.DataFrame | None:
    if name in excel.sheet_names:
        return excel.parse(name)
    return None


def _col_numeric(df: pd.DataFrame, col: str, pd: Any) -> Any:
    """Return a numeric Series for *col*, or a zero-filled Series if missing."""
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(0)
    return pd.Series(0, index=df.index)


def _vm_stats(excel: pd.ExcelFile, pd: Any) -> dict[str, Any]:
    """Count VMs by power state."""
    vinfo = _safe_sheet(excel, "vInfo")
    if vinfo is None:
        return {"total": 0, "powered_on": 0, "powered_off": 0, "suspended": 0}
    total = len(vinfo)
    powered_on = int((vinfo["Powerstate"] == "poweredOn").sum())
    powered_off = int((vinfo["Powerstate"] == "poweredOff").sum())
    suspended = total - powered_on - powered_off
    return {
        "total": total,
        "powered_on": powered_on,
        "powered_off": powered_off,
        "suspended": suspended,
    }


def _compute_stats(excel: pd.ExcelFile, pd: Any) -> dict[str, Any]:
    """Aggregate vCPU and memory from vInfo."""
    vinfo = _safe_sheet(excel, "vInfo")
    if vinfo is None:
        return {"total_vcpus": 0, "total_memory_gb": 0.0}
    cpus = _col_numeric(vinfo, "CPUs", pd)
    memory = _col_numeric(vinfo, "Memory", pd)
    return {
        "total_vcpus": int(cpus.sum()),
        "total_memory_gb": round(float(memory.sum()) * MIB_TO_GB, 2),
    }


def _storage_stats(excel: pd.ExcelFile, pd: Any) -> dict[str, Any]:
    """Aggregate provisioned and used storage from vInfo, disk count from vDisk."""
    vinfo = _safe_sheet(excel, "vInfo")
    provisioned_gb = 0.0
    in_use_gb = 0.0
    if vinfo is not None:
        prov = _col_numeric(vinfo, "Provisioned MiB", pd)
        used = _col_numeric(vinfo, "In Use MiB", pd)
        provisioned_gb = round(float(prov.sum()) * MIB_TO_GB, 2)
        in_use_gb = round(float(used.sum()) * MIB_TO_GB, 2)

    vdisk = _safe_sheet(excel, "vDisk")
    disk_count = len(vdisk) if vdisk is not None else 0

    return {
        "provisioned_gb": provisioned_gb,
        "in_use_gb": in_use_gb,
        "disk_count": disk_count,
    }


def _host_stats(excel: pd.ExcelFile, pd: Any) -> dict[str, Any]:
    """Count ESXi hosts and average resource usage."""
    vhost = _safe_sheet(excel, "vHost")
    if vhost is None:
        return {"count": 0, "avg_cpu_usage_pct": 0.0, "avg_memory_usage_pct": 0.0}
    count = len(vhost)
    cpu_usage = (
        pd.to_numeric(vhost["CPU usage %"], errors="coerce").dropna()
        if "CPU usage %" in vhost.columns
        else pd.Series(dtype=float)
    )
    mem_usage = (
        pd.to_numeric(vhost["Memory usage %"], errors="coerce").dropna()
        if "Memory usage %" in vhost.columns
        else pd.Series(dtype=float)
    )
    return {
        "count": count,
        "avg_cpu_usage_pct": round(float(cpu_usage.mean()), 1) if len(cpu_usage) > 0 else 0.0,
        "avg_memory_usage_pct": round(float(mem_usage.mean()), 1) if len(mem_usage) > 0 else 0.0,
    }


def _datastore_stats(excel: pd.ExcelFile, pd: Any) -> dict[str, Any]:
    """Aggregate datastore capacity and usage."""
    vds = _safe_sheet(excel, "vDatastore")
    if vds is None:
        return {"count": 0, "total_capacity_gb": 0.0, "total_in_use_gb": 0.0}
    capacity = _col_numeric(vds, "Capacity MiB", pd)
    in_use = _col_numeric(vds, "In Use MiB", pd)
    return {
        "count": len(vds),
        "total_capacity_gb": round(float(capacity.sum()) * MIB_TO_GB, 2),
        "total_in_use_gb": round(float(in_use.sum()) * MIB_TO_GB, 2),
    }


def _os_distribution(excel: pd.ExcelFile) -> list[dict[str, Any]]:
    """Count VMs per OS type from vInfo."""
    vinfo = _safe_sheet(excel, "vInfo")
    if vinfo is None:
        return []
    col = "OS according to the VMware Tools"
    if col not in vinfo.columns:
        return []
    counts = vinfo[col].fillna("Unknown").value_counts()
    return [{"os": str(os), "count": int(cnt)} for os, cnt in counts.items()]

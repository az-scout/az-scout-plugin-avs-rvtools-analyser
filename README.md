# az-scout-plugin-avs-rvtools-analyser

An [az-scout](https://github.com/az-scout/az-scout) plugin that analyses
[RVTools](https://www.robware.net/rvtools/) Excel exports to detect migration
risks for **Azure VMware Solution (AVS)**.

Ported from the standalone [avs-rvtools-analyzer](https://github.com/lrivallain/avs-rvtools-analyzer)
project — focused on migration risk analysis only.

## Features

- **19 risk detection checks** covering vUSB, risky disks, network switches,
  ESX versions, hardware versions, shared disks, clear-text passwords,
  Oracle VMs, Fault Tolerance, VMkernel networks, and more
- **File upload UI** with drag-and-drop, progress bar, risk summary cards,
  risk distribution gauge, and expandable risk detail cards with data tables
- **Option to exclude powered-off VMs** from analysis
- **Password redaction** — clear-text passwords in annotations/snapshots are
  automatically redacted from results
- **CSV export** of risk summary and **print / PDF** support
- **AI recommendations** — per-risk AI-powered guidance with remediation steps
  and references (requires AI to be enabled on the az-scout instance)
- **MCP tools** for programmatic analysis (`list_avs_migration_risks`,
  `analyze_rvtools_json`)

## Risk Levels

| Level | Meaning |
|-------|---------|
| **Emergency** | Critical security issue (e.g. clear-text passwords) |
| **Blocking** | Prevents migration entirely |
| **Warning** | Needs attention before migration |
| **Info** | Informational, no action required |

## Setup

```bash
# Install alongside az-scout
uv pip install az-scout-plugin-avs-rvtools-analyser

# Or install in dev mode from source
uv sync --group dev
uv pip install -e .

# Start az-scout — the plugin tab appears automatically
az-scout
```
## Generate Test Data

Create a comprehensive RVTools Excel file with all 19 risk categories represented:

```bash
uv run python tools/create_test_data.py                      # → comprehensive_test_data.xlsx
uv run python tools/create_test_data.py -o /tmp/rvtools.xlsx  # custom output path
```

The generated file contains 10 sheets (vHost, vInfo, vDisk, vUSB, vSnapshot, vCD,
vNetwork, vSC_VMK, dvPort, dvSwitch) with ~44 VMs covering every risk type:
emergency (clear-text passwords), blocking (RDM disks, shared disks, high vCPU/memory,
HW version, standard switches, vUSB), warning (snapshots, suspended VMs, CD-ROMs,
VMkernel networks, non-Intel hosts, VMware Tools, Fault Tolerance, large storage,
dvPort issues), and info (Oracle VMs, ESX versions).

## Quality Checks

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
uv run pytest
```

## License

[MIT](LICENSE.txt)

## Disclaimer

> **This tool is not affiliated with Microsoft.** Risk analysis results are
> informational and should be validated by VMware/Azure infrastructure experts
> before making migration decisions. The file is processed in memory only and
> never stored on disk.

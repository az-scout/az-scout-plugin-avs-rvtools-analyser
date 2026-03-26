// AVS RVTools Analyser — migration risk analysis tab
(function () {
    const PLUGIN = "avs-rvtools-analyser";
    const container = document.getElementById("plugin-tab-" + PLUGIN);
    if (!container) return;

    fetch(`/plugins/${PLUGIN}/static/html/avs-rvtools-analyser-tab.html`)
        .then(r => r.text())
        .then(html => { container.innerHTML = html; init(); })
        .catch(err => {
            container.innerHTML = `<div class="alert alert-danger">Failed to load plugin UI: ${err.message}</div>`;
        });

    function init() {
        const dropZone   = document.getElementById("rvtools-drop-zone");
        const fileInput  = document.getElementById("rvtools-file-input");
        const fileInfo   = document.getElementById("rvtools-file-info");
        const fileName   = document.getElementById("rvtools-file-name");
        const clearBtn   = document.getElementById("rvtools-clear-file");
        const analyzeBtn = document.getElementById("rvtools-analyze-btn");
        const excludeOff = document.getElementById("rvtools-exclude-off");
        const progress   = document.getElementById("rvtools-progress");
        const progBar    = document.getElementById("rvtools-progress-bar");
        const progLabel  = document.getElementById("rvtools-progress-label");
        const emptyState = document.getElementById("rvtools-empty");
        const errorDiv   = document.getElementById("rvtools-error");
        const errorMsg   = document.getElementById("rvtools-error-msg");
        const resultsDiv = document.getElementById("rvtools-results");

        let selectedFile = null;
        let analysisData = null;

        // --- File selection -------------------------------------------------
        dropZone.addEventListener("click", () => fileInput.click());
        dropZone.addEventListener("dragover", e => { e.preventDefault(); dropZone.classList.add("drag-over"); });
        dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
        dropZone.addEventListener("drop", e => {
            e.preventDefault();
            dropZone.classList.remove("drag-over");
            if (e.dataTransfer.files.length) selectFile(e.dataTransfer.files[0]);
        });
        fileInput.addEventListener("change", () => {
            if (fileInput.files.length) selectFile(fileInput.files[0]);
        });
        clearBtn.addEventListener("click", () => {
            selectedFile = null;
            fileInput.value = "";
            fileInfo.style.display = "none";
            dropZone.style.display = "";
            analyzeBtn.disabled = true;
        });

        function selectFile(file) {
            const ext = file.name.split(".").pop().toLowerCase();
            if (!["xlsx", "xls"].includes(ext)) {
                showError("Invalid file type. Please upload an .xlsx or .xls file.");
                return;
            }
            selectedFile = file;
            fileName.textContent = file.name + " (" + formatBytes(file.size) + ")";
            fileInfo.style.display = "";
            dropZone.style.display = "none";
            analyzeBtn.disabled = false;
            hideError();
        }

        // --- Analysis -------------------------------------------------------
        analyzeBtn.addEventListener("click", async () => {
            if (!selectedFile) return;
            hideError();
            resultsDiv.style.display = "none";
            emptyState.style.display = "none";
            progress.style.display = "";
            progBar.style.width = "20%";
            progLabel.textContent = "Uploading file…";
            analyzeBtn.disabled = true;

            const form = new FormData();
            form.append("file", selectedFile);

            const params = new URLSearchParams();
            if (excludeOff.checked) params.set("exclude_powered_off", "true");

            try {
                progBar.style.width = "50%";
                progLabel.textContent = "Analysing risks…";

                const url = `/plugins/${PLUGIN}/analyze-upload` + (params.toString() ? "?" + params : "");
                const resp = await fetch(url, { method: "POST", body: form });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({}));
                    throw new Error(err.detail || err.error || `HTTP ${resp.status}`);
                }

                progBar.style.width = "90%";
                progLabel.textContent = "Rendering results…";

                analysisData = await resp.json();
                renderResults(analysisData);

                progBar.style.width = "100%";
                setTimeout(() => { progress.style.display = "none"; }, 400);
            } catch (e) {
                progress.style.display = "none";
                showError(e.message);
            } finally {
                analyzeBtn.disabled = !selectedFile;
            }
        });

        // --- Render ---------------------------------------------------------
        function renderResults(data) {
            emptyState.style.display = "none";
            resultsDiv.style.display = "";

            // Meta
            const meta = document.getElementById("rvtools-result-meta");
            const sheets = (data.sheets || []).length;
            meta.innerHTML = `<i class="bi bi-file-earmark-check text-success"></i> ` +
                `Analysed <strong>${escHtml(data.filename || "file")}</strong> (${sheets} sheets). ` +
                `${excludeOff.checked ? "Powered-off VMs excluded." : ""}`;

            renderSummaryCards(data.summary);
            renderRiskBar(data.summary);
            renderRiskAccordion(data.risks);
        }

        // --- Summary cards --------------------------------------------------
        function renderSummaryCards(summary) {
            const el = document.getElementById("rvtools-summary-cards");
            const clean = Object.values(analysisData.risks || {}).filter(r => r.count === 0).length;
            const total = Object.keys(analysisData.risks || {}).length;
            const cards = [
                { label: "Risk Checks", value: total, cls: "card-total", icon: "bi-clipboard-check", jump: "" },
                { label: "Emergency", value: summary.emergency || 0, cls: "card-emergency", icon: "bi-exclamation-octagon-fill", jump: "emergency" },
                { label: "Blocking", value: summary.blocking || 0, cls: "card-blocking", icon: "bi-x-octagon-fill", jump: "blocking" },
                { label: "Warning", value: summary.warning || 0, cls: "card-warning", icon: "bi-exclamation-triangle-fill", jump: "warning" },
                { label: "Info", value: summary.info || 0, cls: "card-info", icon: "bi-info-circle-fill", jump: "info" },
                { label: "Clean", value: clean, cls: "card-clean", icon: "bi-check-circle-fill", jump: "clean" },
            ];
            el.innerHTML = cards.map(c => `
                <div class="col-6 col-sm-4 col-xl-2">
                    <div class="rvtools-summary-card ${c.cls}" ${c.jump ? `data-jump-level="${c.jump}" role="button" title="Jump to ${c.label} risks"` : ""}>
                        <div class="rvtools-card-value">${c.value}</div>
                        <div class="rvtools-card-label"><i class="bi ${c.icon}"></i> ${c.label}</div>
                    </div>
                </div>`).join("");
        }

        // --- Risk distribution bar ------------------------------------------
        function renderRiskBar(summary) {
            const bar = document.getElementById("rvtools-risk-bar");
            const legend = document.getElementById("rvtools-risk-legend");
            const total = (summary.emergency || 0) + (summary.blocking || 0) +
                          (summary.warning || 0) + (summary.info || 0);
            if (total === 0) {
                bar.innerHTML = '<div class="risk-segment risk-clean" style="flex:1">All clean</div>';
                legend.innerHTML = "";
                return;
            }
            const segments = [
                { key: "emergency", label: "Emergency", color: "#212529" },
                { key: "blocking", label: "Blocking", color: "#dc3545" },
                { key: "warning", label: "Warning", color: "#ffc107" },
                { key: "info", label: "Info", color: "#0dcaf0" },
            ];
            bar.innerHTML = segments.map(s => {
                const v = summary[s.key] || 0;
                if (!v) return "";
                const pct = (v / total * 100).toFixed(1);
                return `<div class="risk-segment risk-${s.key}" style="flex:${v}" title="${s.label}: ${v}">${pct > 8 ? v : ""}</div>`;
            }).join("");

            legend.innerHTML = segments.filter(s => summary[s.key]).map(s =>
                `<span class="legend-item"><span class="legend-dot" style="background:${s.color}"></span>${s.label}: ${summary[s.key]}</span>`
            ).join("");
        }

        // --- Risk accordion -------------------------------------------------
        function renderRiskAccordion(risks) {
            const acc = document.getElementById("rvtools-risk-accordion");
            // Sort: emergency > blocking > warning > info, then by count desc
            const order = { emergency: 0, blocking: 1, danger: 1, warning: 2, info: 3, clean: 4 };
            const entries = Object.entries(risks).sort((a, b) => {
                const la = a[1].count === 0 ? "clean" : a[1].risk_level;
                const lb = b[1].count === 0 ? "clean" : b[1].risk_level;
                const oa = order[la] ?? 9;
                const ob = order[lb] ?? 9;
                return oa !== ob ? oa - ob : (b[1].count || 0) - (a[1].count || 0);
            });

            acc.innerHTML = entries.map(([key, risk], idx) => {
                const rawLevel = normaliseLevel(risk.risk_level);
                const level = risk.count === 0 ? "clean" : rawLevel;
                const display = key.replace("detect_", "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
                const badge = badgeHtml(rawLevel, risk.count);
                const collapsed = idx > 0 ? "collapsed" : "";
                const show = idx === 0 ? "show" : "";
                const alertMsg = risk.risk_info?.alert_message || "";
                const dataHtml = risk.count > 0 ? renderDataTable(risk.data) : '<p class="text-body-secondary small mb-0">No issues detected.</p>';

                const aiBtn = (risk.count > 0 && typeof aiEnabled !== "undefined" && aiEnabled)
                    ? `<button class="btn btn-outline-primary btn-sm rvtools-ai-btn" data-risk-key="${escHtml(key)}" title="Get AI recommendation"><i class="bi bi-stars"></i> AI Recommendation</button>`
                    : "";

                return `
                <div class="accordion-item rvtools-risk-card risk-${level}" data-risk-level="${level}">
                    <h2 class="accordion-header">
                        <button class="accordion-button ${collapsed}" type="button"
                                data-bs-toggle="collapse" data-bs-target="#risk-${idx}">
                            ${badge}
                            <span class="ms-2">${escHtml(display)}</span>
                            <span class="ms-auto me-3 small text-body-secondary rvtools-issue-count">${risk.count} issue${risk.count !== 1 ? "s" : ""}</span>
                        </button>
                    </h2>
                    <div id="risk-${idx}" class="accordion-collapse collapse ${show}" data-bs-parent="#rvtools-risk-accordion">
                        <div class="accordion-body">
                            <div class="d-flex align-items-start justify-content-between mb-1">
                                <p class="small text-body-secondary mb-0">${escHtml(risk.risk_info?.description || "")}</p>
                                ${aiBtn}
                            </div>
                            ${alertMsg ? `<div class="rvtools-alert-message">${alertMsg}</div>` : ""}
                            ${dataHtml}
                        </div>
                    </div>
                </div>`;
            }).join("");
        }

        // --- Data table renderer --------------------------------------------
        function renderDataTable(data) {
            if (!data || !data.length) return "";
            const cols = Object.keys(data[0]);
            const head = cols.map(c => `<th>${escHtml(c)}</th>`).join("");
            const rows = data.slice(0, 500).map(row =>
                "<tr>" + cols.map(c => `<td title="${escHtml(String(row[c] ?? ""))}">${escHtml(String(row[c] ?? ""))}</td>`).join("") + "</tr>"
            ).join("");
            const note = data.length > 500 ? `<p class="small text-body-secondary mt-1">Showing 500 / ${data.length} rows.</p>` : "";
            return `<div class="rvtools-data-table-wrapper"><table class="rvtools-data-table"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>${note}`;
        }

        // --- Risk level toggles ---------------------------------------------
        document.getElementById("rvtools-summary-cards").addEventListener("click", (e) => {
            const card = e.target.closest("[data-jump-level]");
            if (!card) return;
            const level = card.dataset.jumpLevel;
            const first = document.querySelector(`#rvtools-risk-accordion .rvtools-risk-card[data-risk-level="${level}"]`);
            if (first) {
                first.scrollIntoView({ behavior: "smooth", block: "start" });
                // Open the first card of that level
                const collapse = first.querySelector(".accordion-collapse");
                if (collapse && !collapse.classList.contains("show")) {
                    const btn = first.querySelector(".accordion-button");
                    if (btn) btn.click();
                }
            }
        });

        // --- AI Recommendation ------------------------------------------------
        let currentAiRiskKey = null;

        document.getElementById("rvtools-risk-accordion").addEventListener("click", (e) => {
            const btn = e.target.closest(".rvtools-ai-btn");
            if (!btn || !analysisData) return;
            const riskKey = btn.dataset.riskKey;
            const risk = analysisData.risks[riskKey];
            if (!risk) return;
            currentAiRiskKey = riskKey;
            requestAiRecommendation(riskKey, risk, 1800);
        });

        document.getElementById("rvtools-ai-refresh-btn").addEventListener("click", () => {
            if (!currentAiRiskKey || !analysisData) return;
            const risk = analysisData.risks[currentAiRiskKey];
            if (!risk) return;
            requestAiRecommendation(currentAiRiskKey, risk, 0);
        });

        async function requestAiRecommendation(riskKey, risk, cacheTtl) {
            const modalEl = document.getElementById("rvtools-ai-modal");
            const loading = document.getElementById("rvtools-ai-loading");
            const content = document.getElementById("rvtools-ai-content");
            const errorDiv = document.getElementById("rvtools-ai-error");
            const errorMsg = document.getElementById("rvtools-ai-error-msg");
            const title = document.getElementById("rvtools-ai-modal-title");

            // Reset modal state
            const display = riskKey.replace("detect_", "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
            title.innerHTML = `<i class="bi bi-stars text-primary"></i> AI Recommendation — ${escHtml(display)}`;
            loading.style.display = "";
            content.style.display = "none";
            content.innerHTML = "";
            errorDiv.style.display = "none";

            // Show modal
            const modal = new bootstrap.Modal(modalEl);
            modal.show();

            // Check if aiComplete is available
            if (typeof aiComplete !== "function" || typeof aiEnabled === "undefined" || !aiEnabled) {
                loading.style.display = "none";
                errorDiv.style.display = "";
                errorMsg.textContent = "AI features are not enabled on this az-scout instance.";
                return;
            }

            // Build context: limit data to first 30 items to keep prompt manageable
            const items = (risk.data || []).slice(0, 30);
            const itemsSummary = items.length > 0
                ? "\n\nAffected items (" + risk.count + " total" + (items.length < risk.count ? ", showing first 30" : "") + "):\n" + JSON.stringify(items, null, 2)
                : "";

            const prompt = [
                `Analyse this AVS migration risk concisely.`,
                ``,
                `Risk: ${display}`,
                `Level: ${risk.risk_level}`,
                `Issues found: ${risk.count}`,
                `Description: ${risk.risk_info?.description || ""}`,
                `Context: ${(risk.risk_info?.alert_message || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim()}`,
                itemsSummary,
            ].join("\n");

            const systemPrompt = [
                "You are an Azure VMware Solution (AVS) migration expert with deep knowledge of",
                "VMware/Broadcom best practices and Microsoft AVS documentation.",
                "Provide a clear, actionable recommendation (around 300 words).",
                "Structure your answer with exactly these 4 sections using markdown ## headings:",
                "## Impact — What this risk means for AVS migration (2-3 sentences).",
                "## Remediation — Concrete steps to fix this, as a bullet list.",
                "Include VMware/vSphere or HCX specifics where relevant (e.g. vSphere Client paths, PowerCLI commands).",
                "## References — Only if you know a directly relevant page, include 1-2 links from",
                "Microsoft Learn (learn.microsoft.com/azure/azure-vmware),",
                "VMware/Broadcom docs (knowledge.broadcom.com), or HCX documentation.",
                "Format as a bullet list of markdown links. Omit this section entirely if no specific page applies.",
                "## Priority — One line: priority level (Critical/High/Medium/Low) and estimated effort (Low/Medium/High).",
                "Do NOT repeat the input data verbatim. Do NOT add extra sections or offers for more help.",
                "Use plain markdown. No emoji. No tables.",
            ].join(" ");

            try {
                const result = await aiComplete(prompt, {
                    systemPrompt,
                    tools: false,
                    cacheTtl: cacheTtl,
                });
                loading.style.display = "none";
                content.style.display = "";
                content.innerHTML = renderMarkdown(result.content || "No recommendation generated.");
            } catch (err) {
                loading.style.display = "none";
                errorDiv.style.display = "";
                errorMsg.textContent = err.message || "Failed to generate AI recommendation.";
            }
        }

        // --- Markdown rendering (uses marked.js from core app) -----------------
        function renderMarkdown(md) {
            const renderer = new marked.Renderer();
            // Open links in new tab
            renderer.link = function ({ href, text }) {
                return `<a href="${href}" target="_blank" rel="noopener">${text} <i class="bi bi-box-arrow-up-right small"></i></a>`;
            };
            const html = marked.parse(md, {
                renderer,
                gfm: true,
                breaks: false,
            });
            return `<div class="rvtools-ai-output">${html}</div>`;
        }

        // --- Print / PDF -------------------------------------------------------
        document.getElementById("rvtools-print-btn").addEventListener("click", () => {
            if (!analysisData) return;
            printResults();
        });

        function printResults() {
            const results = document.getElementById("rvtools-results");
            if (!results) return;

            // Clone results and force all accordion panels open
            const clone = results.cloneNode(true);
            clone.style.display = "";
            // Show all risk cards (override any active filter)
            clone.querySelectorAll(".rvtools-risk-card").forEach(c => { c.style.display = ""; });
            // Expand all accordion bodies
            clone.querySelectorAll(".accordion-collapse").forEach(el => {
                el.classList.add("show");
                el.style.display = "block";
                el.style.height = "auto";
                el.style.overflow = "visible";
            });
            // Remove accordion toggle arrows
            clone.querySelectorAll(".accordion-button::after, .accordion-button").forEach(btn => {
                btn.classList.remove("collapsed");
            });
            // Remove scrollable table constraints
            clone.querySelectorAll(".rvtools-data-table-wrapper").forEach(w => {
                w.style.maxHeight = "none";
                w.style.overflow = "visible";
            });

            const pluginCssUrl = `/plugins/${PLUGIN}/static/css/avs-rvtools-analyser.css`;
            // Collect Bootstrap CSS from main page
            const mainStyles = [...document.querySelectorAll('link[rel="stylesheet"]')]
                .map(l => l.href)
                .filter(h => h.includes("bootstrap"))
                .map(h => `<link rel="stylesheet" href="${h}">`)
                .join("\n");
            // Also grab Bootstrap Icons
            const iconStyles = [...document.querySelectorAll('link[rel="stylesheet"]')]
                .map(l => l.href)
                .filter(h => h.includes("bootstrap-icons"))
                .map(h => `<link rel="stylesheet" href="${h}">`)
                .join("\n");

            const filename = analysisData.filename || "RVTools export";
            const now = new Date().toLocaleString();

            const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AVS Migration Risk Analysis</title>
${mainStyles}
${iconStyles}
<link rel="stylesheet" href="${pluginCssUrl}">
<style>
  body { padding: 1.5rem; font-family: system-ui, -apple-system, sans-serif; }
  .print-header { margin-bottom: 1rem; }
  .print-header h1 { font-size: 1.3rem; font-weight: 700; margin: 0; }
  .print-header p { font-size: 0.8rem; color: #6c757d; margin: 0.25rem 0 0; }
  .accordion-button::after { display: none !important; }
  .rvtools-data-table-wrapper { max-height: none !important; overflow: visible !important; }
  @media print {
    body { padding: 0; }
    .rvtools-risk-card { break-inside: avoid; page-break-inside: avoid; }
  }
</style>
</head>
<body>
<div class="print-header">
  <h1><i class="bi bi-shield-exclamation"></i> AVS Migration Risk Analysis</h1>
  <p>File: ${escHtml(filename)} &mdash; Generated: ${escHtml(now)}</p>
</div>
${clone.outerHTML}
<script>window.onload = function() { window.print(); }<\/script>
</body>
</html>`;

            const printWin = window.open("", "_blank");
            if (!printWin) {
                showError("Pop-up blocked. Please allow pop-ups for this site to print.");
                return;
            }
            printWin.document.write(html);
            printWin.document.close();
        }

        // --- CSV export -----------------------------------------------------
        document.getElementById("rvtools-export-csv").addEventListener("click", () => {
            if (!analysisData) return;
            const rows = [["Risk Check", "Level", "Count", "Description"]];
            for (const [key, risk] of Object.entries(analysisData.risks)) {
                const display = key.replace("detect_", "").replace(/_/g, " ");
                rows.push([display, risk.risk_level, risk.count, risk.risk_info?.description || ""]);
            }
            const csv = rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
            const blob = new Blob([csv], { type: "text/csv" });
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = "avs-migration-risks.csv";
            a.click();
            URL.revokeObjectURL(a.href);
        });

        // --- Helpers --------------------------------------------------------
        function normaliseLevel(level) {
            if (level === "danger") return "blocking";
            return ["emergency", "blocking", "warning", "info"].includes(level) ? level : "info";
        }

        function badgeHtml(level, count) {
            const icons = {
                emergency: "bi-exclamation-octagon-fill",
                blocking: "bi-x-octagon-fill",
                warning: "bi-exclamation-triangle-fill",
                info: "bi-info-circle-fill",
            };
            if (count === 0) return `<span class="rvtools-badge rvtools-badge-clean"><i class="bi bi-check-circle-fill"></i> clean</span>`;
            return `<span class="rvtools-badge rvtools-badge-${level}"><i class="bi ${icons[level] || icons.info}"></i> ${level}</span>`;
        }

        function escHtml(s) {
            const d = document.createElement("div");
            d.textContent = s;
            return d.innerHTML;
        }

        function formatBytes(b) {
            if (b < 1024) return b + " B";
            if (b < 1024 * 1024) return (b / 1024).toFixed(1) + " KB";
            return (b / (1024 * 1024)).toFixed(1) + " MB";
        }

        function showError(msg) {
            errorMsg.textContent = msg;
            errorDiv.style.display = "";
            emptyState.style.display = "none";
        }

        function hideError() {
            errorDiv.style.display = "none";
        }
    }
})();

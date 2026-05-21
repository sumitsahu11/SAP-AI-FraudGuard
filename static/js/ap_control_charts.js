/**
 * ap_control_charts.js  — FIXED VERSION
 *
 * Bugs fixed:
 *  1. Function exposed as window.loadAPControlCharts (uppercase AP)
 *     to match the call in main.js and the Refresh Charts button.
 *  2. All div IDs corrected to match index.html:
 *       chart-risk-donut        (was chart-risk-distribution)
 *       chart-monthly-trend     ✓
 *       chart-monthly-amount    (was chart-monthly-amount-split)
 *       chart-risk-histogram    (was chart-risk-score-hist)
 *       chart-top-vendors       ✓
 *       chart-invoice-type      ✓
 *       chart-cost-center       ✓
 *       chart-vendor-state      ✓
 */

"use strict";

/* ─────────────────────────────────────────────────────────────────────
   Actual div IDs that exist in index.html
───────────────────────────────────────────────────────────────────── */
const AP_CHART_IDS = [
  "chart-monthly-trend",
  "chart-risk-donut",
  "chart-monthly-amount",
  "chart-risk-histogram",
  "chart-top-vendors",
  "chart-invoice-type",
  "chart-cost-center",
  "chart-vendor-state",
];

/* ─────────────────────────────────────────────────────────────────────
   Helpers
───────────────────────────────────────────────────────────────────── */
function _apSetLoading(divId) {
  const el = document.getElementById(divId);
  if (!el) return;
  el.innerHTML =
    '<div style="display:flex;align-items:center;justify-content:center;' +
    'height:260px;color:#94a3b8;font-size:13px;gap:8px;">' +
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="2" style="animation:_ap_spin 1s linear infinite">' +
    '<path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83' +
    'M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>' +
    'Loading chart\u2026</div>' +
    '<style>@keyframes _ap_spin{to{transform:rotate(360deg)}}</style>';
}

function _apRenderChart(divId, traces, layout, config) {
  const el = document.getElementById(divId);
  if (!el) {
    console.warn("[AP Charts] div not found:", divId);
    return;
  }
  el.innerHTML = "";

  const finalLayout = Object.assign(
    {
      paper_bgcolor: "transparent",
      plot_bgcolor:  "transparent",
      font:   { family: "'Inter','Segoe UI',sans-serif", size: 12, color: "#334155" },
      margin: { t: 44, r: 16, b: 56, l: 56 },
      legend: { orientation: "h", y: -0.28, font: { size: 11 } },
    },
    layout
  );

  Plotly.newPlot(
    el,
    traces,
    finalLayout,
    Object.assign({ responsive: true, displayModeBar: false }, config || {})
  );
}

function _apShowError(divId, msg) {
  const el = document.getElementById(divId);
  if (!el) return;
  el.innerHTML =
    '<div style="display:flex;align-items:center;justify-content:center;' +
    'height:200px;color:#94a3b8;font-size:12px;text-align:center;padding:16px;">' +
    "\u26A0 " + msg + "</div>";
}

/* ─────────────────────────────────────────────────────────────────────
   Main loader
   Name MUST be loadAPControlCharts (uppercase AP) —
   matches main.js line 125 and the Refresh Charts button onclick.
───────────────────────────────────────────────────────────────────── */
async function loadAPControlCharts() {
  /* 1. Show spinners */
  AP_CHART_IDS.forEach(_apSetLoading);

  /* 2. Fetch both endpoints in parallel */
  let overview, charts;
  try {
    const [r1, r2] = await Promise.all([
      fetch("/api/ap_control_overview"),
      fetch("/api/ap_control_charts"),
    ]);

    if (!r1.ok || !r2.ok) {
      let errMsg = "Server error";
      try { errMsg = (await (!r1.ok ? r1 : r2).json()).error || errMsg; } catch (_) {}
      AP_CHART_IDS.forEach((id) => _apShowError(id, errMsg));
      return;
    }

    overview = await r1.json();
    charts   = await r2.json();

    /* Backend sends {error:...} with HTTP 200 when no file uploaded */
    if (overview.error) { AP_CHART_IDS.forEach((id) => _apShowError(id, overview.error)); return; }
    if (charts.error)   { AP_CHART_IDS.forEach((id) => _apShowError(id, charts.error));   return; }

  } catch (err) {
    console.error("[AP Charts] fetch error:", err);
    AP_CHART_IDS.forEach((id) => _apShowError(id, "Cannot reach server. Is Flask running?"));
    return;
  }

  const RC = { HIGH: "#ef4444", MEDIUM: "#f97316", LOW: "#22c55e", UNKNOWN: "#94a3b8" };

  /* ──────────────────────────────────────────────────────────
     1. chart-monthly-trend  — Line chart
        Source: overview.monthly_trend
  ────────────────────────────────────────────────────────── */
  try {
    const mt = overview.monthly_trend || [];
    if (!mt.length) throw new Error("No monthly trend data");
    const months = mt.map((r) => r.month);
    _apRenderChart("chart-monthly-trend", [
      { x: months, y: mt.map((r) => r.invoices),           name: "Total",     type: "scatter", mode: "lines+markers", line: { color: "#3b82f6", width: 2 }, marker: { size: 5 } },
      { x: months, y: mt.map((r) => r.risky_invoices),     name: "Risky",     type: "scatter", mode: "lines+markers", line: { color: "#f97316", width: 2 }, marker: { size: 5 } },
      { x: months, y: mt.map((r) => r.high_risk_invoices), name: "High Risk", type: "scatter", mode: "lines+markers", line: { color: "#ef4444", width: 2 }, marker: { size: 5 } },
    ], {
      title: { text: "Monthly Invoice Trend", font: { size: 13, color: "#1e293b" } },
      xaxis: { title: { text: "Month",    font: { size: 11 } }, tickangle: -30, gridcolor: "#f1f5f9" },
      yaxis: { title: { text: "Invoices", font: { size: 11 } }, gridcolor: "#f1f5f9" },
    });
  } catch (e) { _apShowError("chart-monthly-trend", e.message); }

  /* ──────────────────────────────────────────────────────────
     2. chart-risk-donut  — Donut chart
        Source: overview.risk_distribution
  ────────────────────────────────────────────────────────── */
  try {
    const rd = overview.risk_distribution || {};
    const labels = Object.keys(rd);
    const values = Object.values(rd);
    if (!labels.length) throw new Error("No risk distribution data");
    _apRenderChart("chart-risk-donut", [{
      type: "pie", hole: 0.48,
      labels, values,
      marker:   { colors: labels.map((l) => RC[l] || "#64748b") },
      textinfo: "label+percent",
      textfont: { size: 11 },
      hovertemplate: "<b>%{label}</b><br>Count: %{value}<br>%{percent}<extra></extra>",
    }], {
      title:      { text: "Risk Distribution", font: { size: 13, color: "#1e293b" } },
      showlegend: true,
      margin:     { t: 44, r: 16, b: 20, l: 16 },
    });
  } catch (e) { _apShowError("chart-risk-donut", e.message); }

  /* ──────────────────────────────────────────────────────────
     3. chart-monthly-amount  — Stacked area
        Source: charts.monthly_amount_split
  ────────────────────────────────────────────────────────── */
  try {
    const mas = charts.monthly_amount_split || [];
    if (!mas.length) throw new Error("No monthly amount data");
    const months = mas.map((r) => r.month);
    _apRenderChart("chart-monthly-amount", [
      {
        x: months, y: mas.map((r) => r.safe_amount || 0),
        name: "Safe", type: "scatter", mode: "lines",
        stackgroup: "one",
        fillcolor: "rgba(34,197,94,0.55)", line: { color: "#16a34a", width: 1.5 },
        hovertemplate: "%{x}<br>Safe: \u20B9%{y:,.0f}<extra></extra>",
      },
      {
        x: months, y: mas.map((r) => Math.max(0, (r.risky_amount || 0) - (r.high_amount || 0))),
        name: "Medium Risk", type: "scatter", mode: "lines",
        stackgroup: "one",
        fillcolor: "rgba(249,115,22,0.55)", line: { color: "#ea580c", width: 1.5 },
        hovertemplate: "%{x}<br>Medium: \u20B9%{y:,.0f}<extra></extra>",
      },
      {
        x: months, y: mas.map((r) => r.high_amount || 0),
        name: "High Risk", type: "scatter", mode: "lines",
        stackgroup: "one",
        fillcolor: "rgba(239,68,68,0.55)", line: { color: "#dc2626", width: 1.5 },
        hovertemplate: "%{x}<br>High Risk: \u20B9%{y:,.0f}<extra></extra>",
      },
    ], {
      title: { text: "Monthly Amount Split (\u20B9)", font: { size: 13, color: "#1e293b" } },
      xaxis: { title: { text: "Month",        font: { size: 11 } }, tickangle: -30, gridcolor: "#f1f5f9" },
      yaxis: { title: { text: "Amount (\u20B9)", font: { size: 11 } }, gridcolor: "#f1f5f9" },
    });
  } catch (e) { _apShowError("chart-monthly-amount", e.message); }

  /* ──────────────────────────────────────────────────────────
     4. chart-risk-histogram  — Histogram
        Source: charts.risk_scores
  ────────────────────────────────────────────────────────── */
  try {
    const rs = charts.risk_scores || [];
    if (!rs.length) throw new Error("No risk score data");
    _apRenderChart("chart-risk-histogram", [{
      x: rs, type: "histogram", nbinsx: 20,
      marker: { color: "#6366f1", opacity: 0.85 },
      hovertemplate: "Score: %{x:.2f}<br>Count: %{y}<extra></extra>",
    }], {
      title: { text: "Risk Score Distribution", font: { size: 13, color: "#1e293b" } },
      xaxis: { title: { text: "Risk Score",  font: { size: 11 } }, range: [0, 1], gridcolor: "#f1f5f9" },
      yaxis: { title: { text: "# Invoices", font: { size: 11 } }, gridcolor: "#f1f5f9" },
      shapes: [
        { type: "line", x0: 0.4, x1: 0.4, y0: 0, y1: 1, yref: "paper", line: { color: "#f97316", dash: "dash", width: 1.5 } },
        { type: "line", x0: 0.7, x1: 0.7, y0: 0, y1: 1, yref: "paper", line: { color: "#ef4444", dash: "dash", width: 1.5 } },
      ],
      annotations: [
        { x: 0.41, y: 0.97, yref: "paper", text: "Medium", showarrow: false, font: { color: "#f97316", size: 10 }, xanchor: "left" },
        { x: 0.71, y: 0.97, yref: "paper", text: "High",   showarrow: false, font: { color: "#ef4444", size: 10 }, xanchor: "left" },
      ],
    });
  } catch (e) { _apShowError("chart-risk-histogram", e.message); }

  /* ──────────────────────────────────────────────────────────
     5. chart-top-vendors  — Horizontal bar
        Source: overview.top_risky_vendors
  ────────────────────────────────────────────────────────── */
  try {
    const tv = overview.top_risky_vendors || [];
    if (!tv.length) throw new Error("No risky vendor data");
    const sorted = [...tv].sort((a, b) => a.risky_amount - b.risky_amount);
    _apRenderChart("chart-top-vendors", [{
      x: sorted.map((r) => r.risky_amount),
      y: sorted.map((r) => r.vendor),
      type: "bar", orientation: "h",
      marker: {
        color: sorted.map((r) =>
          r.risky_amount > 500000 ? "#ef4444" :
          r.risky_amount > 100000 ? "#f97316" : "#6366f1"
        ),
      },
      hovertemplate: "<b>%{y}</b><br>Risky: \u20B9%{x:,.0f}<extra></extra>",
    }], {
      title:  { text: "Top Risky Vendors by Amount", font: { size: 13, color: "#1e293b" } },
      xaxis:  { title: { text: "Risky Amount (\u20B9)", font: { size: 11 } }, gridcolor: "#f1f5f9" },
      yaxis:  { automargin: true },
      margin: { t: 44, r: 16, b: 56, l: 150 },
    });
  } catch (e) { _apShowError("chart-top-vendors", e.message); }

  /* ──────────────────────────────────────────────────────────
     6. chart-invoice-type  — Grouped bar
        Source: charts.invoice_type_breakdown
  ────────────────────────────────────────────────────────── */
  try {
    const itb = charts.invoice_type_breakdown || [];
    if (!itb.length) throw new Error("No InvoiceType column in your dataset");
    const riskLevels = [...new Set(itb.map((r) => r.RiskLevel))];
    const invTypes   = [...new Set(itb.map((r) => r.InvoiceType))];
    _apRenderChart("chart-invoice-type",
      riskLevels.map((rl) => ({
        x: invTypes,
        y: invTypes.map((it) => { const row = itb.find((r) => r.InvoiceType === it && r.RiskLevel === rl); return row ? row.count : 0; }),
        name: rl, type: "bar",
        marker: { color: RC[rl] || "#64748b" },
      })),
      {
        title:   { text: "Invoice Type \u00D7 Risk Level", font: { size: 13, color: "#1e293b" } },
        barmode: "group",
        xaxis:   { title: { text: "Invoice Type", font: { size: 11 } }, tickangle: -20, gridcolor: "#f1f5f9" },
        yaxis:   { title: { text: "Count",        font: { size: 11 } }, gridcolor: "#f1f5f9" },
      }
    );
  } catch (e) { _apShowError("chart-invoice-type", e.message); }

  /* ──────────────────────────────────────────────────────────
     7. chart-cost-center  — Stacked bar
        Source: charts.cost_center_breakdown
  ────────────────────────────────────────────────────────── */
  try {
    const ccb = charts.cost_center_breakdown || [];
    if (!ccb.length) throw new Error("No CostCenter column in your dataset");
    const riskLevels  = [...new Set(ccb.map((r) => r.RiskLevel))];
    const costCenters = [...new Set(ccb.map((r) => r.CostCenter))];
    _apRenderChart("chart-cost-center",
      riskLevels.map((rl) => ({
        x: costCenters,
        y: costCenters.map((cc) => { const row = ccb.find((r) => r.CostCenter === cc && r.RiskLevel === rl); return row ? row.count : 0; }),
        name: rl, type: "bar",
        marker: { color: RC[rl] || "#64748b" },
      })),
      {
        title:   { text: "Cost Center \u00D7 Risk Level", font: { size: 13, color: "#1e293b" } },
        barmode: "stack",
        xaxis:   { title: { text: "Cost Center", font: { size: 11 } }, tickangle: -30, gridcolor: "#f1f5f9" },
        yaxis:   { title: { text: "Count",       font: { size: 11 } }, gridcolor: "#f1f5f9" },
      }
    );
  } catch (e) { _apShowError("chart-cost-center", e.message); }

  /* ──────────────────────────────────────────────────────────
     8. chart-vendor-state  — Stacked horizontal bar
        Source: charts.vendor_state_breakdown
  ────────────────────────────────────────────────────────── */
  try {
    const vsb = charts.vendor_state_breakdown || [];
    if (!vsb.length) throw new Error("No VendorState column in your dataset");
    const sorted = [...vsb].sort((a, b) => a.risky - b.risky).slice(-15);
    _apRenderChart("chart-vendor-state", [
      {
        x: sorted.map((r) => Math.max(0, (r.total || 0) - (r.risky || 0))),
        y: sorted.map((r) => r.VendorState),
        name: "Low Risk", type: "bar", orientation: "h",
        marker: { color: "#22c55e" },
      },
      {
        x: sorted.map((r) => Math.max(0, (r.risky || 0) - (r.high_risk || 0))),
        y: sorted.map((r) => r.VendorState),
        name: "Medium Risk", type: "bar", orientation: "h",
        marker: { color: "#f97316" },
      },
      {
        x: sorted.map((r) => r.high_risk || 0),
        y: sorted.map((r) => r.VendorState),
        name: "High Risk", type: "bar", orientation: "h",
        marker: { color: "#ef4444" },
      },
    ], {
      title:   { text: "Vendor State Risk Summary", font: { size: 13, color: "#1e293b" } },
      barmode: "stack",
      xaxis:   { title: { text: "Invoice Count", font: { size: 11 } }, gridcolor: "#f1f5f9" },
      yaxis:   { automargin: true },
      margin:  { t: 44, r: 16, b: 56, l: 130 },
    });
  } catch (e) { _apShowError("chart-vendor-state", e.message); }
}

/* ─────────────────────────────────────────────────────────────────────
   Global export — uppercase AP to match main.js + HTML button
───────────────────────────────────────────────────────────────────── */
window.loadAPControlCharts = loadAPControlCharts;
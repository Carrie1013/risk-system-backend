const form = document.getElementById("analysis-form");
const summaryStrip = document.getElementById("summary-strip");
const triggerTable = document.getElementById("trigger-table");
const windowInput = document.getElementById("window_value");
const frequencySelect = document.getElementById("frequency");

const palette = {
  bg: "#0d1222",
  grid: "rgba(255,255,255,0.08)",
  text: "#f5f7ff",
  muted: "#adb8db",
  blue: "#4ea1ff",
  violet: "#8f7cff",
  soft: "#c7bcff"
};

frequencySelect.addEventListener("change", () => {
  windowInput.value = frequencySelect.value === "monthly" ? 12 : 52;
});

function parseTickers(text) {
  return text
    .split(/[\s,]+/)
    .map((x) => x.trim().toUpperCase())
    .filter(Boolean);
}

function lineChart(target, series, title, threshold = null, color = palette.blue) {
  const x = series.map((d) => d.date);
  const y = series.map((d) => d.value);
  const traces = [{
    x, y,
    type: "scatter",
    mode: "lines",
    line: { color, width: 2.4 },
    fill: "tozeroy",
    fillcolor: color === palette.blue ? "rgba(78,161,255,0.14)" : "rgba(143,124,255,0.16)",
    name: title
  }];

  if (threshold !== null && threshold !== undefined) {
    traces.push({
      x,
      y: x.map(() => threshold),
      type: "scatter",
      mode: "lines",
      line: { color: palette.soft, width: 1.4, dash: "dash" },
      name: "Trigger threshold"
    });
  }

  Plotly.newPlot(target, traces, {
    margin: { l: 44, r: 18, t: 18, b: 36 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: palette.text },
    xaxis: { gridcolor: palette.grid, zerolinecolor: palette.grid },
    yaxis: { gridcolor: palette.grid, zerolinecolor: palette.grid },
    showlegend: threshold !== null
  }, { displayModeBar: false, responsive: true });
}

function dualChart(target, leftSeries, rightSeries, leftName, rightName) {
  Plotly.newPlot(target, [
    {
      x: leftSeries.map((d) => d.date),
      y: leftSeries.map((d) => d.value),
      type: "scatter",
      mode: "lines",
      line: { color: palette.violet, width: 2.2 },
      name: leftName
    },
    {
      x: rightSeries.map((d) => d.date),
      y: rightSeries.map((d) => d.value),
      type: "scatter",
      mode: "lines",
      line: { color: palette.blue, width: 2.0 },
      name: rightName,
      yaxis: "y2"
    }
  ], {
    margin: { l: 44, r: 44, t: 18, b: 36 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: palette.text },
    xaxis: { gridcolor: palette.grid, zerolinecolor: palette.grid },
    yaxis: { gridcolor: palette.grid, zerolinecolor: palette.grid },
    yaxis2: { overlaying: "y", side: "right" },
    showlegend: true
  }, { displayModeBar: false, responsive: true });
}

function renderSummary(data) {
  const cards = [
    ["Assets", data.etf_count, `${data.sample_start} to ${data.sample_end}`],
    ["Risk %ile", data.metrics.risk_percentile.value, `Recent ${data.metrics.risk_percentile.recent.toFixed(4)}`],
    ["Corr %ile", data.metrics.correlation_percentile.value, `Recent ${data.metrics.correlation_percentile.recent.toFixed(4)}`],
    ["Cov Drift", data.metrics.cov_matrix_drift.value, `Threshold ${data.metrics.cov_matrix_drift.threshold}`],
    ["F-Distance", data.metrics.f_distance.value, `Threshold ${data.metrics.f_distance.threshold}`],
    ["GARCH Drift", data.metrics.garch_conditional_drift.value, `Threshold ${data.metrics.garch_conditional_drift.threshold}`]
  ];

  summaryStrip.innerHTML = cards.map(([label, value, sub]) => `
    <article class="summary-card">
      <div class="label">${label}</div>
      <div class="value">${value}</div>
      <div class="sub">${sub}</div>
    </article>
  `).join("");
}

function renderTriggers(rows) {
  triggerTable.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Metric</th>
          <th>Latest</th>
          <th>Threshold</th>
          <th>Trigger</th>
        </tr>
      </thead>
      <tbody>
        ${rows.map((row) => `
          <tr>
            <td>${row.label}</td>
            <td>${row.value}</td>
            <td>${row.threshold}</td>
            <td><span class="pill ${row.triggered ? "on" : "off"}">${row.triggered ? "Triggered" : "Calm"}</span></td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

async function runAnalysis(evt = null) {
  if (evt) evt.preventDefault();
  const button = document.getElementById("run-btn");
  button.disabled = true;
  button.textContent = "Loading...";

  try {
    const payload = {
      tickers: parseTickers(document.getElementById("tickers").value),
      frequency: frequencySelect.value,
      window_value: Number(windowInput.value)
    };

    const resp = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Request failed");

    renderSummary(data);
    renderTriggers(data.triggers);

    lineChart("chart-ew", data.supporting.equal_weight_return, "Equal-weight return", null, palette.blue);
    lineChart("chart-risk", data.metrics.risk_percentile.series, "Rolling volatility", data.metrics.risk_percentile.threshold, palette.violet);
    lineChart("chart-corr", data.metrics.correlation_percentile.series, "Average pairwise correlation", data.metrics.correlation_percentile.threshold, palette.blue);
    lineChart("chart-cov", data.metrics.cov_matrix_drift.series, "Covariance drift", data.metrics.cov_matrix_drift.threshold, palette.violet);
    dualChart("chart-eig", data.supporting.eig_concentration, data.supporting.effective_rank, "Eigen concentration", "Effective rank");
    lineChart("chart-fdist", data.metrics.f_distance.series, "Frobenius distance", data.metrics.f_distance.threshold, palette.blue);
    lineChart("chart-garch", data.metrics.garch_conditional_drift.series, "GARCH conditional drift", data.metrics.garch_conditional_drift.threshold, palette.violet);
  } catch (err) {
    summaryStrip.innerHTML = `<article class="summary-card"><div class="label">Error</div><div class="value" style="font-size:1rem;">${err.message}</div></article>`;
    triggerTable.innerHTML = "";
  } finally {
    button.disabled = false;
    button.textContent = "Run Dashboard";
  }
}

form.addEventListener("submit", runAnalysis);
runAnalysis();

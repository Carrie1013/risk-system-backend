(function () {
  let exogenousPeriodWeeks = "all";
  const qs = (sel) => document.querySelector(sel);
  const qsa = (sel) => Array.from(document.querySelectorAll(sel));

  function byDate(rows) {
    return (rows || []).map((d) => d.value == null ? null : d.value);
  }

  function clipSeries(rows, periods) {
    return (rows || []).slice(-Math.max(1, periods));
  }

  function fetchJson(url, options = {}) {
    return fetch(url, options).then(async (resp) => {
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Request failed");
      return data;
    });
  }

  function dateLabels(series) {
    return (series || []).map((d) => d.date);
  }

  function setText(id, value, cls = null) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = value;
    if (cls) el.className = cls;
  }

  function fmtPct(v) {
    return v == null || Number.isNaN(v) ? "—" : (v * 100).toFixed(1) + "%";
  }

  function fmtNum(v, digits = 1, suffix = "") {
    return v == null || Number.isNaN(v) ? "—" : Number(v).toFixed(digits) + suffix;
  }

  function liveLineChart(id, dates, datasets, plugins = [], yFmt = v => v?.toFixed?.(2) ?? v) {
    dc(id);
    const pointRadius = dates.length <= 2 ? 3 : 0;
    CH[id] = new Chart(document.getElementById(id), {
      type: "line",
      plugins,
      data: {
        labels: dates,
        datasets: datasets.map(ds => ({ ...ds, pointRadius: ds.pointRadius ?? pointRadius }))
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: items => items[0]?.label || "",
              label: item => item.dataset.label ? `${item.dataset.label}: ${yFmt(item.raw)}` : yFmt(item.raw)
            }
          }
        },
        scales: {
          x: {
            ticks: {
              color: "#404660",
              font: { size: 9 },
              callback: (v, i, arr) => i % (Math.max(1, Math.floor(arr.length / 8))) === 0 ? dates[i]?.slice(0, 7) : "",
              autoSkip: false,
              maxRotation: 0
            },
            grid: gridCfg
          },
          y: { ticks: { color: "#404660", font: { size: 9 } }, grid: gridCfg }
        }
      }
    });
  }

  async function p0Run() {
    setPageStatus("page0", "loading", "Running trigger monitor with live market data...");
    const payload = {
      etfs: p0etfs,
      params: {
        sw: +document.getElementById("sw").value,
        lw: +document.getElementById("lw").value,
        cw: +document.getElementById("cw").value,
        tq: +document.getElementById("tq").value,
        mv: +document.getElementById("mv").value
      }
    };
    const data = await fetchJson("/api/risk-system/page0", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    DATES = data.dates;
    setText("p0-s0", data.stats.risk_state, "s-val " + (data.stats.risk_state === "TRIGGERED" ? "red" : "green"));
    setText("p0-s0b", `${data.stats.last_vote} methods active`);
    setText("p0-s1", String(data.stats.combined_triggers), "s-val amber");
    setText("p0-s2", fmtPct(data.stats.current_fwd_vol));
    setText("p0-s2b", `median ${fmtPct(data.stats.median_fwd_vol)}`);
    setText("p0-s3", data.stats.last_trigger, "s-val accent");
    setText("p0-s3b", data.stats.last_trigger_detail);

    const L = Array.from({ length: data.dates.length }, (_, i) => i);
    const cols = { m1: "#f87171", m2: "#b07ef7", m3: "#2ecfc0", m4: "#f5a623" };

    const lp = document.getElementById("p0-legend");
    lp.innerHTML = `<span class="leg-item"><span class="leg-dash" style="background:#dde1ea"></span>Fwd vol</span>` +
      ["m1", "m2", "m3", "m4"].filter(k => p0methods[k]).map(k =>
        `<span class="leg-item"><span class="leg-dot" style="background:${cols[k]}"></span>${k.toUpperCase()}</span>`
      ).join("") +
      `<span class="leg-item"><span class="leg-dot" style="background:#6c7ef7"></span>Combined</span>`;

    const plugins = [];
    if (p0methods.m1) plugins.push(bandPlugin(data.triggers.m1, "rgba(248,113,113,0.10)"));
    if (p0methods.m2) plugins.push(bandPlugin(data.triggers.m2, "rgba(176,126,247,0.10)"));
    if (p0methods.m3) plugins.push(bandPlugin(data.triggers.m3, "rgba(46,207,192,0.10)"));
    if (p0methods.m4) plugins.push(bandPlugin(data.triggers.m4, "rgba(245,166,35,0.10)"));
    plugins.push(bandPlugin(data.triggers.combined, "rgba(108,126,247,0.18)"));

    liveLineChart("p0-main", data.dates, [
      { ...lineDefaults, data: byDate(data.series.forward_vol).map(v => v == null ? null : +(v * 100).toFixed(2)), borderColor: "#dde1ea", label: "Fwd vol" }
    ], plugins, v => v?.toFixed(1) + "%");

    liveLineChart("p0-c1", data.dates, [
      { ...lineDefaults, data: byDate(data.series.vol_ratio), borderColor: cols.m1, label: "Vol ratio" },
      { ...lineDefaults, data: new Array(L.length).fill(data.thresholds.m1), borderColor: "#555", borderDash: [4, 3], borderWidth: 1 }
    ], [bandPlugin(data.triggers.m1, "rgba(248,113,113,0.15)")]);

    liveLineChart("p0-c2", data.dates, [
      { ...lineDefaults, data: byDate(data.series.garch_vol).map(v => v == null ? null : +(v * 100).toFixed(2)), borderColor: cols.m2, label: "GARCH vol" },
      { ...lineDefaults, data: new Array(L.length).fill(+(data.thresholds.m2 * 100).toFixed(2)), borderColor: "#555", borderDash: [4, 3], borderWidth: 1 }
    ], [bandPlugin(data.triggers.m2, "rgba(176,126,247,0.15)")], v => v?.toFixed(1) + "%");

    liveLineChart("p0-c3", data.dates, [
      { ...lineDefaults, data: byDate(data.series.frobenius), borderColor: cols.m3, label: "Frobenius" },
      { ...lineDefaults, data: new Array(L.length).fill(data.thresholds.m3), borderColor: "#555", borderDash: [4, 3], borderWidth: 1 }
    ], [bandPlugin(data.triggers.m3, "rgba(46,207,192,0.15)")], v => v?.toExponential?.(2) || v);

    liveLineChart("p0-c4", data.dates, [
      { ...lineDefaults, data: byDate(data.series.concentration), borderColor: cols.m4, label: "Eigen concentration" },
      { ...lineDefaults, data: new Array(L.length).fill(data.thresholds.m4), borderColor: "#555", borderDash: [4, 3], borderWidth: 1 }
    ], [bandPlugin(data.triggers.m4, "rgba(245,166,35,0.15)")]);

    const log = document.getElementById("p0-log");
    log.innerHTML = data.events.length ? `
      <table class="tbl"><thead><tr><th>Date</th><th>Methods fired</th><th>Votes</th><th>8w fwd vol</th></tr></thead>
      <tbody>${data.events.map(e => `<tr>
        <td style="font-family:var(--font)">${e.date}</td>
        <td>${e.fired.map(m => `<span class="badge" style="background:rgba(108,126,247,.15);color:var(--accent);margin-right:3px">${m}</span>`).join("")}</td>
        <td style="font-family:var(--font);text-align:center">${e.votes}</td>
        <td style="font-family:var(--font)">${e.fwd_vol == null ? "—" : (e.fwd_vol * 100).toFixed(1) + "%"}</td>
      </tr>`).join("")}</tbody></table>`
      : `<div style="color:var(--text3);padding:16px 0;text-align:center;font-size:12px">No combined triggers with current settings</div>`;

    updateNavDots(data.stats.nav_state);
    clearPageStatus("page0");
  }

  function p0Demo() {
    p0etfs = [{ t: "VTI", w: 40 }, { t: "BND", w: 30 }, { t: "GLD", w: 15 }, { t: "VNQ", w: 15 }];
    p0RenderList();
    p0Run().catch((err) => { setPageStatus("page0", "error", err.message); });
  }

  async function initExogenous() {
    setPageStatus("page1", "loading", "Loading VIX, MOVE, spreads, and dollar data...");
    const detailWeeks = exogenousPeriodWeeks === "all" ? 4 : exogenousPeriodWeeks;
    const data = await fetchJson(`/api/risk-system/page1?period_weeks=${detailWeeks}`);
    DATES = data.dates;
    setText("x-vix", fmtNum(data.stats.vix, 1));
    setText("x-vvix", fmtNum(data.stats.vvix, 1));
    setText("x-move", fmtNum(data.stats.move, 1));
    setText("x-hy", fmtNum(data.stats.hy, 1, " bp"));
    setText("x-ted", fmtNum(data.stats.ted, 1, " bp"));
    setText("x-dxy", fmtNum(data.stats.dxy, 2));
    setText(
      "x-ts",
      data.stats.term_structure == null || Number.isNaN(data.stats.term_structure)
        ? "—"
        : `${data.stats.term_structure > 0 ? "+" : ""}${Number(data.stats.term_structure).toFixed(2)}`,
      "s-val " + ((data.stats.term_structure ?? 0) < 0 ? "red" : "green")
    );
    setText(
      "x-ivr",
      data.stats.impl_real == null || Number.isNaN(data.stats.impl_real)
        ? "—"
        : `${data.stats.impl_real > 0 ? "+" : ""}${Number(data.stats.impl_real).toFixed(1)}`,
      "s-val accent"
    );

    const chartPeriods = exogenousPeriodWeeks === "all" ? data.dates.length : exogenousPeriodWeeks;
    const dates = data.dates.slice(-chartPeriods);
    const vixRows = clipSeries(data.series.vix, chartPeriods);
    const vvixRows = clipSeries(data.series.vvix, chartPeriods);
    const termRows = clipSeries(data.series.term_structure, chartPeriods);
    const implRows = clipSeries(data.series.impl_real, chartPeriods);
    const moveRows = clipSeries(data.series.move, chartPeriods);
    const hyRows = clipSeries(data.series.hy, chartPeriods);
    const tedRows = clipSeries(data.series.ted, chartPeriods);
    const garchRows = clipSeries(data.series.garch_scaled, chartPeriods);
    const vixScaledRows = clipSeries(data.series.vix_scaled, chartPeriods);
    const divRows = clipSeries(data.series.divergence, chartPeriods);
    const compRows = clipSeries(data.series.composite, chartPeriods);
    const riskOff = data.risk_off.slice(-chartPeriods);

    liveLineChart("x-c1", dates, [
      { ...lineDefaults, data: byDate(vixRows), borderColor: "#f5a623", label: "VIX" },
      { ...lineDefaults, data: byDate(vvixRows).map(v => v == null ? null : +(v / 10).toFixed(1)), borderColor: "#b07ef7", label: "VVIX/10" },
      { ...lineDefaults, data: new Array(dates.length).fill(data.thresholds.vix_q90), borderColor: "#f06060", borderDash: [5, 3], borderWidth: 1, label: "VIX 90th" }
    ], [bandPlugin(byDate(vixRows).map(v => v > data.thresholds.vix_q90), "rgba(240,96,96,0.10)")], v => v?.toFixed(1));

    liveLineChart("x-c2", dates, [
      { ...lineDefaults, data: byDate(termRows), borderColor: "#2ecfc0", label: "Term str" },
      { ...lineDefaults, data: byDate(implRows), borderColor: "#6c7ef7", label: "Impl−Real" },
      { ...lineDefaults, data: new Array(dates.length).fill(0), borderColor: "#404660", borderDash: [3, 3], borderWidth: 1 }
    ], [bandPlugin(byDate(termRows).map(v => v < 0), "rgba(240,96,96,0.12)")], v => v?.toFixed(1));

    liveLineChart("x-c3", dates, [
      { ...lineDefaults, data: byDate(moveRows).map(v => v == null ? null : +(v / 10).toFixed(1)), borderColor: "#f06060", label: "MOVE/10" },
      { ...lineDefaults, data: byDate(hyRows).map(v => v == null ? null : +(v / 100).toFixed(2)), borderColor: "#f5a623", label: "HY/100" },
      { ...lineDefaults, data: byDate(tedRows).map(v => v == null ? null : +(v * 5).toFixed(1)), borderColor: "#3edfa0", label: "TED×5" }
    ], [], v => v?.toFixed(1));

    liveLineChart("x-c4", dates, [
      { ...lineDefaults, data: byDate(garchRows), borderColor: "#6c7ef7", label: "GARCH" },
      { ...lineDefaults, data: byDate(vixScaledRows), borderColor: "#f5a623", label: "VIX" },
      { ...lineDefaults, data: byDate(divRows), borderColor: "#f06060", label: "Divergence" }
    ], [], v => v?.toFixed(1));

    liveLineChart("x-c5", dates, [
      { ...lineDefaults, data: byDate(compRows), borderColor: "#6c7ef7", label: "Composite Z" },
      { ...lineDefaults, data: new Array(dates.length).fill(data.thresholds.composite_q80), borderColor: "#f06060", borderDash: [5, 3], borderWidth: 1 }
    ], [bandPlugin(riskOff, "rgba(240,96,96,0.13)")], v => v?.toFixed(2));

    document.getElementById("x-signal-table").innerHTML = data.signals.map(s => `<tr>
      <td style="font-weight:500">${s.name}</td>
      <td style="font-family:var(--font);color:var(--text2)">${s.cond}</td>
      <td style="font-family:var(--font)">${s.val}</td>
      <td><span class="badge ${s.fire ? 'badge-crisis' : 'badge-low'}">${s.fire ? 'FIRING' : 'OK'}</span></td>
    </tr>`).join("");

    const head = document.getElementById("x-focus-period-head");
    const sub = document.getElementById("x-focus-sub");
    head.textContent = `Δ ${data.period_weeks}W`;
    sub.textContent = `Latest date ${data.latest_date} · compare against the last ${data.period_weeks} week${data.period_weeks > 1 ? "s" : ""}`;
    const tedLabelEl = document.querySelector(".s-label");
    document.getElementById("x-focus-table").innerHTML = data.recent_focus.map(r => `<tr>
      <td style="font-weight:500">${r.name}</td>
      <td style="font-family:var(--font)">${fmtNum(r.current, 2)}</td>
      <td style="font-family:var(--font);color:${r.delta_1w > 0 ? 'var(--danger)' : r.delta_1w < 0 ? 'var(--accent2)' : 'var(--text2)'}">${r.delta_1w == null || Number.isNaN(r.delta_1w) ? '—' : `${r.delta_1w > 0 ? '+' : ''}${Number(r.delta_1w).toFixed(2)}`}</td>
      <td style="font-family:var(--font);color:${r.delta_period > 0 ? 'var(--danger)' : r.delta_period < 0 ? 'var(--accent2)' : 'var(--text2)'}">${r.delta_period == null || Number.isNaN(r.delta_period) ? '—' : `${r.delta_period > 0 ? '+' : ''}${Number(r.delta_period).toFixed(2)}`}</td>
      <td style="font-family:var(--font)">${r.percentile == null || Number.isNaN(r.percentile) ? '—' : `${Number(r.percentile).toFixed(1)}%`}</td>
    </tr>`).join("");
    clearPageStatus("page1");
  }

  function setExogenousPeriod(period, btn) {
    exogenousPeriodWeeks = period;
    ["x-btn-all", "x-btn-1w", "x-btn-4w", "x-btn-12w"].forEach(id => document.getElementById(id)?.classList.remove("active-btn"));
    btn.classList.add("active-btn");
    initExogenous().catch(err => { setPageStatus("page1", "error", err.message); });
  }

  async function renderStructural() {
    setPageStatus("page2", "loading", "Computing covariance structure and eigenvalue diagnostics...");
    const assets = [...srActive];
    const windowVal = Number(document.getElementById("sr-window")?.value || 52);
    const data = await fetchJson(`/api/risk-system/page2?assets=${encodeURIComponent(assets.join(","))}&window=${windowVal}`);
    DATES = data.series.sri.map(d => d.date);
    setText("sr-sri", data.stats.sri.toFixed(3), "s-val " + (data.stats.sri > 0.5 ? "red" : data.stats.sri > 0.35 ? "amber" : "green"));
    setText("sr-er", data.stats.effective_rank.toFixed(1));
    setText("sr-pr", data.stats.participation_ratio.toFixed(3));
    setText("sr-ac", data.stats.avg_corr.toFixed(3), "s-val " + (data.stats.avg_corr > 0.55 ? "red" : data.stats.avg_corr > 0.35 ? "amber" : "green"));

    const idx = Array.from({ length: DATES.length }, (_, i) => i);
    const maxEr = data.assets_active.length;
    liveLineChart("sr-c1", DATES, [
      { ...lineDefaults, data: byDate(data.series.sri), borderColor: "#f5a623", label: "SRI" },
      { ...lineDefaults, data: byDate(data.series.effective_rank).map(v => v == null ? null : +(v / maxEr).toFixed(3)), borderColor: "#6c7ef7", label: "Eff rank/max" }
    ], [], v => v?.toFixed(3));

    liveLineChart("sr-c2", DATES, [
      { ...lineDefaults, data: byDate(data.series.avg_corr), borderColor: "#f06060", label: "Avg ρ" },
      { ...lineDefaults, data: byDate(data.series.disp_corr), borderColor: "#2ecfc0", label: "Dispersion" }
    ], [], v => v?.toFixed(3));

    dc("sr-c3");
    CH["sr-c3"] = new Chart(document.getElementById("sr-c3"), {
      type: "bar",
      data: {
        labels: data.pcs,
        datasets: [
          { data: data.cum_variance, backgroundColor: "rgba(108,126,247,0.6)", borderColor: "#6c7ef7", borderWidth: 1, label: "Cum var" },
          { type: "line", ...lineDefaults, data: new Array(data.pcs.length).fill(0.80), borderColor: "#f5a623", borderDash: [4, 3], label: "80% line" }
        ]
      },
      options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } },
        scales: { x: { ticks: { color: "#404660", font: { size: 9 } }, grid: gridCfg }, y: { min: 0, max: 1, ticks: { color: "#404660", font: { size: 9 }, callback: v => (v * 100 | 0) + "%" }, grid: gridCfg } } }
    });

    liveLineChart("sr-c4", DATES, [
      { ...lineDefaults, data: byDate(data.series.participation_ratio), borderColor: "#b07ef7", label: "PR" },
      { ...lineDefaults, data: new Array(idx.length).fill(0.4), borderColor: "#f06060", borderDash: [4, 3], borderWidth: 1 }
    ], [], v => v?.toFixed(3));

    const hm = document.getElementById("sr-heatmap");
    const labels = data.heatmap.labels;
    hm.innerHTML = `<tr><th></th>${labels.map(a => `<th style="font-size:9px;color:var(--text2)">${a}</th>`).join("")}</tr>` +
      labels.map((r, i) => `<tr><th style="font-size:9px;color:var(--text2);white-space:nowrap">${r}</th>` +
        labels.map((_, j) => {
          const v = data.heatmap.matrix[i][j];
          const bg = corrColor(i === j ? 1 : v);
          const txt = i === j ? "—" : v.toFixed(2);
          const tc = Math.abs(i === j ? 1 : v) > 0.5 ? "#fff" : "var(--text)";
          return `<td style="background:${bg};color:${tc};font-family:var(--font);font-size:9px">${txt}</td>`;
        }).join("") + `</tr>`).join("");
    clearPageStatus("page2");
  }

  async function initStructural() {
    setPageStatus("page2", "loading", "Loading structural-risk universe...");
    const data = await fetchJson("/api/risk-system/page2");
    window.SR_ASSETS = data.assets_all;
    if (!window.srActive || !(window.srActive instanceof Set)) window.srActive = new Set(data.assets_active);
    const tgl = document.getElementById("sr-asset-toggles");
    tgl.innerHTML = data.assets_all.map(t => `<span class="tgl ${srActive.has(t) ? "on" : ""}" onclick="srToggleAsset('${t}',this)">${t}</span>`).join("");
    const winEl = document.getElementById("sr-window");
    if (winEl) winEl.value = data.window;
    await renderStructural();
  }

  function srToggleAsset(t, el) {
    if (srActive.has(t)) { if (srActive.size <= 2) return; srActive.delete(t); el.classList.remove("on"); }
    else { srActive.add(t); el.classList.add("on"); }
    renderStructural().catch(err => alert(err.message));
  }

  async function initRegime() {
    setPageStatus("page3", "loading", "Scoring current regime and position map...");
    const garch = Number(document.getElementById("rg-w-garch")?.value || 0.25);
    const eigen = Number(document.getElementById("rg-w-eigen")?.value || 0.25);
    const corr = Number(document.getElementById("rg-w-corr")?.value || 0.25);
    const exo = Number(document.getElementById("rg-w-exo")?.value || 0.25);
    const data = await fetchJson(`/api/risk-system/page3?garch=${garch}&eigen=${eigen}&corr=${corr}&exo=${exo}`);
    const dates = data.series.risk_score.map(d => d.date);
    DATES = dates;
    const cur = data.stats.current_regime;
    qsa(".regime-seg").forEach(el => el.classList.remove("active-seg"));
    ["low", "rising", "crisis", "recovery"].forEach(k => {
      document.getElementById(`reg-${k}-pct`).textContent = data.stats.regime_pcts[k];
      if (k === cur) document.getElementById(`reg-${k}`).classList.add("active-seg");
    });
    setText("rg-cur", cur.charAt(0).toUpperCase() + cur.slice(1) + " risk", "s-val " + (cur === "crisis" ? "red" : cur === "rising" ? "amber" : cur === "recovery" ? "accent" : "green"));
    setText("rg-drisk", (data.stats.delta_risk > 0 ? "+" : "") + data.stats.delta_risk.toFixed(3), "s-val " + (data.stats.delta_risk > 0.01 ? "red" : data.stats.delta_risk < -0.01 ? "green" : "amber"));
    setText("rg-lev", data.stats.leverage);
    setText("rg-exp", data.stats.exposure);

    const idx = Array.from({ length: dates.length }, (_, i) => i);
    liveLineChart("rg-c1", dates, [
      { ...lineDefaults, data: byDate(data.series.risk_score), borderColor: "#6c7ef7", label: "Risk score" }
    ], [
      bandPlugin(data.regimes.map(r => r === "crisis"), "rgba(240,96,96,0.15)"),
      bandPlugin(data.regimes.map(r => r === "rising"), "rgba(245,166,35,0.10)"),
      bandPlugin(data.regimes.map(r => r === "low"), "rgba(62,223,160,0.08)")
    ], v => v?.toFixed(3));

    liveLineChart("rg-c2", dates, [
      { ...lineDefaults, data: byDate(data.series.risk_score), borderColor: "#f5a623", label: "Risk level" },
      { ...lineDefaults, data: byDate(data.series.delta_risk), borderColor: "#f06060", label: "ΔRisk" }
    ], [], v => v?.toFixed(3));

    dc("rg-c3");
    CH["rg-c3"] = new Chart(document.getElementById("rg-c3"), {
      type: "bar",
      data: {
        labels: Object.keys(data.factor_contrib),
        datasets: [{ data: Object.values(data.factor_contrib), backgroundColor: ["rgba(108,126,247,.7)", "rgba(245,166,35,.7)", "rgba(240,96,96,.7)", "rgba(176,126,247,.7)"], borderWidth: 0 }]
      },
      options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } },
        scales: { x: { min: 0, max: 1, ticks: { color: "#404660", font: { size: 9 } }, grid: gridCfg }, y: { ticks: { color: "#7a8099", font: { size: 11 } }, grid: { display: false } } } }
    });

    document.getElementById("rg-rules").innerHTML = data.rules.map(r => `<tr>
      <td style="font-weight:500">${r.name}</td>
      <td style="font-family:var(--font);color:var(--text2)">${r.weight}</td>
      <td style="font-family:var(--font)">${r.val}</td>
      <td style="font-family:var(--font);color:var(--accent)">${r.contrib}</td>
    </tr>`).join("");
    clearPageStatus("page3");
  }

  async function renderMarketSentiment() {
    setPageStatus("page4", "loading", "Refreshing cross-market data and CNN Fear & Greed...");
    const data = await fetchJson(`/api/risk-system/page4?assets=${encodeURIComponent([...msSelectedAssets].join(","))}&window=${msWindow}`);
    setText("fg-val", fmtNum(data.fear_greed.value, 2), "s-val " + (data.fear_greed.value < 25 ? "red" : data.fear_greed.value < 45 ? "amber" : data.fear_greed.value > 75 ? "green" : "accent"));
    setText("fg-sub", `${data.fear_greed.rating} · ${data.fear_greed.last_update}`);
    setText("fg-close", fmtNum(data.fear_greed.previous_close, 2));
    setText("fg-1w", fmtNum(data.fear_greed.previous_1_week, 2));
    setText("fg-1m", fmtNum(data.fear_greed.previous_1_month, 2));

    mkLineChart("fg-c1", data.fear_greed.series.map(d => d.date), [
      { ...lineDefaults, data: data.fear_greed.series.map(d => d.value), borderColor: "#f5a623", label: "CNN Fear & Greed", pointRadius: 0 },
      { ...lineDefaults, data: new Array(data.fear_greed.series.length).fill(25), borderColor: "#f06060", borderDash: [4, 3], borderWidth: 1, label: "Extreme fear" },
      { ...lineDefaults, data: new Array(data.fear_greed.series.length).fill(75), borderColor: "#3edfa0", borderDash: [4, 3], borderWidth: 1, label: "Extreme greed" }
    ], [], v => v?.toFixed(1));

    data.global_cards.forEach(m => {
      document.getElementById("mv-" + m.id).textContent = m.price.toFixed(2);
      const chgEl = document.getElementById("mc2-" + m.id);
      chgEl.textContent = (m.change >= 0 ? "+" : "") + m.change.toFixed(2) + `% (${msWindow}w)`;
      chgEl.className = "mkt-chg " + (m.change > 1 ? "mkt-up" : m.change < -1 ? "mkt-dn" : "mkt-flat");
      document.getElementById("mv-" + m.id).className = "mkt-val " + (m.change > 1 ? "mkt-up" : m.change < -1 ? "mkt-dn" : "mkt-flat");
    });

    const assets = data.selected_assets;
    const seriesMap = data.us_chart;
    const some = seriesMap[assets[0]] || [];
    DATES = some.map(d => d.date);
    dc("ms-c1");
    CH["ms-c1"] = new Chart(document.getElementById("ms-c1"), {
      type: "line",
      data: {
        labels: Array.from({ length: DATES.length }, (_, i) => i),
        datasets: assets.map((a, i) => ({
          ...lineDefaults,
          data: byDate(seriesMap[a]),
          borderColor: ["#6c7ef7", "#f5a623", "#3edfa0", "#f06060", "#b07ef7", "#2ecfc0"][i % 6],
          label: a.toUpperCase()
        }))
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: { legend: { display: false }, tooltip: { mode: "index", intersect: false } },
        scales: {
          x: { ticks: xTickCfg(DATES.length, DATES), grid: gridCfg },
          y: { ticks: { color: "#404660", font: { size: 9 } }, grid: gridCfg }
        }
      }
    });

    const M = msMatrixMode === "corr" ? data.heatmap.corr : data.heatmap.cov;
    const labels = data.heatmap.labels;
    const maxCov = Math.max(...data.heatmap.cov.flat().map(v => Math.abs(v))) || 1;
    const hmEl = document.getElementById("ms-heatmap");
    hmEl.innerHTML = `<tr><th></th>${labels.map(l => `<th>${l}</th>`).join("")}</tr>` +
      labels.map((r, i) => `<tr><th style="white-space:nowrap">${r}</th>` +
        labels.map((_, j) => {
          const v = M[i][j];
          const bg = msMatrixMode === "corr" ? corrColor(i === j ? 1 : v) : covColor(v, maxCov);
          const txt = msMatrixMode === "corr" ? (i === j ? "1.00" : v.toFixed(2)) : (Math.abs(v) < 0.0001 ? v.toExponential(1) : v.toFixed(4));
          const tc = Math.abs(msMatrixMode === "corr" ? v : v / maxCov) > 0.5 ? "#fff" : "var(--text)";
          return `<td style="background:${bg};color:${tc};font-family:var(--font);font-size:9px">${txt}</td>`;
        }).join("") + `</tr>`).join("");
    clearPageStatus("page4");
  }

  async function initSentiment() {
    const data = await fetchJson(`/api/risk-system/page4?assets=${encodeURIComponent([...msSelectedAssets].join(","))}&window=${msWindow}`);
    const grid = document.getElementById("ms-grid");
    grid.innerHTML = data.global_meta.map(m => `
      <div class="market-card" id="mc-${m.id}" onclick="msSelectMarket('${m.id}')">
        <div class="mkt-name">${m.name}</div>
        <div class="mkt-val" id="mv-${m.id}">—</div>
        <div class="mkt-chg" id="mc2-${m.id}">—</div>
      </div>`).join("");
    const tgl = document.getElementById("ms-asset-toggles");
    tgl.innerHTML = data.us_meta.map(a => `<span class="tgl ${msSelectedAssets.has(a.id) ? "on" : ""}" onclick="msToggleAsset('${a.id}',this)">${a.id.toUpperCase()}</span>`).join("");
    await renderMarketSentiment();
  }

  function msSwitchWindow(w, btn) {
    msWindow = w;
    qsa('[id^="ms-btn-"]').forEach(b => b.classList.remove("active-btn"));
    btn.classList.add("active-btn");
    renderMarketSentiment().catch(err => alert(err.message));
  }

  function msSwitchMatrix(mode, btn) {
    msMatrixMode = mode;
    document.getElementById("ms-cov-btn").classList.toggle("active-btn", mode === "cov");
    document.getElementById("ms-cor-btn").classList.toggle("active-btn", mode === "corr");
    renderMarketSentiment().catch(err => alert(err.message));
  }

  function msToggleAsset(id, el) {
    if (msSelectedAssets.has(id)) { if (msSelectedAssets.size <= 2) return; msSelectedAssets.delete(id); el.classList.remove("on"); }
    else { msSelectedAssets.add(id); el.classList.add("on"); }
    renderMarketSentiment().catch(err => alert(err.message));
  }

  function msSelectMarket(id) {
    qsa(".market-card").forEach(c => c.classList.remove("selected-mkt"));
    document.getElementById("mc-" + id)?.classList.add("selected-mkt");
  }

  window.p0Run = p0Run;
  window.p0Demo = p0Demo;
  const wrap = (pageId, fn) => () => fn().catch(err => { setPageStatus(pageId, "error", err.message); });
  window.initExogenous = wrap("page1", initExogenous);
  window.setExogenousPeriod = setExogenousPeriod;
  window.initStructural = wrap("page2", initStructural);
  window.renderStructural = wrap("page2", renderStructural);
  window.srToggleAsset = srToggleAsset;
  window.initRegime = wrap("page3", initRegime);
  window.initSentiment = wrap("page4", initSentiment);
  window.msSwitchWindow = msSwitchWindow;
  window.msSwitchMatrix = msSwitchMatrix;
  window.msToggleAsset = msToggleAsset;
  window.msSelectMarket = msSelectMarket;
  window.renderMarketSentiment = wrap("page4", renderMarketSentiment);

  window.p0Run = () => p0Run().catch(err => { setPageStatus("page0", "error", err.message); });
  window.p0Demo = p0Demo;
  p0Demo();
})();

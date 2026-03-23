const CH = {};
function dc(id) { if (CH[id]) { CH[id].destroy(); delete CH[id]; } }

let DATES = [];
const SCALE = Math.sqrt(52);

function quantile(arr, q) {
  const s = arr.filter(x => isFinite(x) && !isNaN(x)).sort((a, b) => a - b);
  if (!s.length) return NaN;
  const i = q * (s.length - 1);
  return s[Math.floor(i)] + (s[Math.ceil(i)] - s[Math.floor(i)]) * (i % 1);
}

function xTickCfg(n, dates) {
  const skip = Math.max(1, Math.floor(n / 8));
  return {
    color: "#404660",
    font: { size: 9 },
    callback: (v, i) => i % skip === 0 ? dates[i]?.slice(0, 7) : "",
    autoSkip: false,
    maxRotation: 0
  };
}

const gridCfg = { color: "rgba(255,255,255,0.035)" };
const lineDefaults = { pointRadius: 0, tension: 0.3, fill: false, spanGaps: true, borderWidth: 1.3 };

function bandPlugin(triggers, color) {
  return {
    id: "bp" + Math.random(),
    afterDraw(ch) {
      const { ctx, scales, chartArea } = ch;
      ctx.save();
      ctx.fillStyle = color;
      triggers.forEach((t, i) => {
        if (!t) return;
        const x0 = scales.x.getPixelForValue(i);
        const x1 = scales.x.getPixelForValue(i + 1);
        ctx.fillRect(x0, chartArea.top, x1 - x0, chartArea.bottom - chartArea.top);
      });
      ctx.restore();
    }
  };
}

function mkLineChart(id, labels, datasets, plugins = [], yFmt = v => v?.toFixed?.(2) ?? v) {
  dc(id);
  CH[id] = new Chart(document.getElementById(id), {
    type: "line",
    plugins,
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: items => labels[items[0].dataIndex] || "",
            label: item => item.dataset.label ? `${item.dataset.label}: ${yFmt(item.raw)}` : yFmt(item.raw)
          }
        }
      },
      scales: {
        x: { ticks: xTickCfg(labels.length, labels), grid: gridCfg },
        y: { ticks: { color: "#404660", font: { size: 9 } }, grid: gridCfg }
      }
    }
  });
}

function corrColor(v) {
  if (isNaN(v)) return "#1e2229";
  const a = Math.min(1, Math.abs(v));
  return v > 0 ? `rgba(108,126,247,${0.15 + a * 0.75})` : `rgba(240,96,96,${0.15 + a * 0.75})`;
}

function covColor(v, max) {
  if (isNaN(v) || max === 0) return "#1e2229";
  const a = Math.min(1, Math.abs(v) / max);
  return v >= 0 ? `rgba(108,126,247,${0.1 + a * 0.8})` : `rgba(240,96,96,${0.1 + a * 0.8})`;
}

let p0etfs = [];
const p0methods = { m1: true, m2: true, m3: true, m4: true };
let srActive = new Set(["VTI", "BND", "GLD", "VNQ", "EWC", "EWL"]);
let msWindow = 4;
let msMatrixMode = "cov";
let msSelectedAssets = new Set(["spy", "qqq", "tlt", "gld", "hyg"]);

function toggleM(m) {
  p0methods[m] = !p0methods[m];
  document.getElementById("mt-" + m + "-dot").style.background = p0methods[m] ? "var(--accent)" : "var(--text3)";
}

function p0RenderList() {
  const el = document.getElementById("p0-etf-list");
  el.innerHTML = "";
  p0etfs.forEach((e, i) => {
    const row = document.createElement("div");
    row.style.cssText = "display:grid;grid-template-columns:1fr 52px 22px;gap:6px;align-items:center;background:var(--bg3);border:1px solid var(--border);border-radius:6px;padding:6px 8px";
    row.innerHTML = `<span style="font-family:var(--font);font-size:12px;font-weight:600">${e.t}</span>
      <input class="input-sm" type="number" value="${e.w}" min="0" max="100" step="1" style="text-align:right;padding:3px 6px"
        onchange="p0etfs[${i}].w=+this.value;p0UpdateTotal()">
      <button onclick="p0etfs.splice(${i},1);p0RenderList()" style="background:none;border:none;cursor:pointer;color:var(--text3);font-size:13px">✕</button>`;
    el.appendChild(row);
  });
  p0UpdateTotal();
}

function p0UpdateTotal() {
  const t = p0etfs.reduce((s, e) => s + e.w, 0);
  const el = document.getElementById("p0-wtotal");
  el.textContent = `Total: ${t.toFixed(0)}%`;
  el.style.color = Math.abs(t - 100) < 1 ? "var(--accent2)" : "var(--danger)";
}

function p0AddEtf() {
  const t = document.getElementById("p0-ticker").value.trim().toUpperCase();
  const w = +document.getElementById("p0-weight").value || 0;
  if (!t) return;
  p0etfs.push({ t, w });
  p0RenderList();
  document.getElementById("p0-ticker").value = "";
  document.getElementById("p0-weight").value = "";
}

function setPageStatus(pageId, kind, text) {
  const box = document.getElementById(`status-${pageId}`);
  const label = document.getElementById(`status-${pageId}-text`);
  if (!box || !label) return;
  label.textContent = text;
  box.classList.add("show");
  box.classList.remove("loading", "error");
  if (kind) box.classList.add(kind);
}

function clearPageStatus(pageId) {
  const box = document.getElementById(`status-${pageId}`);
  if (!box) return;
  box.classList.remove("show", "loading", "error");
}

let initialized = [false, false, false, false, false];
const pages = document.querySelectorAll(".page");
const tabs = document.querySelectorAll(".nav-tab");

function goPage(i) {
  pages.forEach((p, j) => {
    p.classList.toggle("active", j === i);
    tabs[j].classList.toggle("active", j === i);
  });
  if (!initialized[i]) {
    initialized[i] = true;
    if (i === 1) initExogenous();
    else if (i === 2) initStructural();
    else if (i === 3) initRegime();
    else if (i === 4) initSentiment();
  }
}

function updateNavDots(state) {
  document.getElementById("nd0").className = "nav-dot " + (state === "red" ? "red" : state === "amber" ? "amber" : "green");
}

window.dc = dc;
window.DATES = DATES;
window.SCALE = SCALE;
window.quantile = quantile;
window.xTickCfg = xTickCfg;
window.gridCfg = gridCfg;
window.lineDefaults = lineDefaults;
window.bandPlugin = bandPlugin;
window.mkLineChart = mkLineChart;
window.corrColor = corrColor;
window.covColor = covColor;
window.p0etfs = p0etfs;
window.p0methods = p0methods;
window.srActive = srActive;
window.msSelectedAssets = msSelectedAssets;
window.msWindow = msWindow;
window.msMatrixMode = msMatrixMode;
window.toggleM = toggleM;
window.p0RenderList = p0RenderList;
window.p0UpdateTotal = p0UpdateTotal;
window.p0AddEtf = p0AddEtf;
window.setPageStatus = setPageStatus;
window.clearPageStatus = clearPageStatus;
window.goPage = goPage;
window.updateNavDots = updateNavDots;

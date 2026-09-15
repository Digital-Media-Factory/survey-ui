const PALETTE = ["#7C6BFF", "#2BC4A8", "#F5B942", "#FF6B8B", "#54A6F5", "#A177FF", "#43D8B6", "#FF9A5B", "#6E8BFF", "#C46BFF"];
const MOTION = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const state = { filters: {}, page: 1, search: "", charts: new Map(), meta: null };
const $ = (id) => document.getElementById(id);

const qs = () => {
  const keys = Object.keys(state.filters);
  return keys.length ? `?filters=${encodeURIComponent(JSON.stringify(state.filters))}` : "";
};

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `تعذّر تنفيذ الطلب (${res.status})`);
  }
  return res.json();
}

function toast(message, isError = false) {
  const el = $("toast");
  el.textContent = message;
  el.classList.toggle("error", isError);
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => (el.hidden = true), 4200);
}

/* ------------------------------------------------------------ animation -- */

function countUp(el, target, suffix = "") {
  const value = Number(target) || 0;
  if (!MOTION) return (el.textContent = value + suffix);
  const duration = 1100;
  const start = performance.now();
  const step = (now) => {
    const p = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(value * eased) + suffix;
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/** Reveals cards and starts their chart only once they scroll into view. */
const revealer = new IntersectionObserver(
  (entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      e.target.classList.add("is-in");
      e.target._draw?.();
      e.target._draw = null;
      revealer.unobserve(e.target);
    });
  },
  { rootMargin: "0px 0px -60px 0px", threshold: 0.15 }
);

/* ----------------------------------------------------------------- boot -- */

async function boot() {
  try {
    const meta = await api("/api/meta");
    state.meta = meta;
    $("sourceTag").textContent = `${meta.source} · ${meta.responses} رد`;
    if (meta.dateRange) $("heroRange").textContent = `${meta.dateRange[0]} — ${meta.dateRange[1]}`;
    renderFilters(meta.filters);
    await refresh();
  } catch (err) {
    $("sourceTag").textContent = "لا توجد بيانات";
    $("highlightGrid").innerHTML = `<p class="empty">${err.message}<br />ارفع ملفاً من الأعلى للبدء.</p>`;
  }
}

async function refresh() {
  showSkeletons();
  const [kpis, stats, highlights] = await Promise.all([
    api(`/api/kpis${qs()}`),
    api(`/api/stats${qs()}`),
    api(`/api/highlights${qs()}`),
  ]);

  const closed = stats.blocks.filter((b) => b.type !== "open");
  const open = stats.blocks.filter((b) => b.type === "open");

  renderTotals(stats, closed, open);
  renderKpis(kpis.kpis);
  renderHighlights(highlights.highlights);
  renderCharts($("overviewCharts"), closed.slice(0, 6));
  renderCharts($("chartGrid"), closed);
  renderOpen(open);
  $("matchNote").textContent = `تُعرض ${stats.matched} استجابة من أصل ${stats.total}.`;
  $("exportCsv").href = `/api/export/summary.csv${qs()}`;
  state.page = 1;
  await loadRows();
}

function showSkeletons() {
  const sk = '<div class="skeleton"></div>'.repeat(4);
  if (!$("chartGrid").children.length) {
    $("overviewCharts").innerHTML = sk;
    $("chartGrid").innerHTML = sk;
  }
}

/* --------------------------------------------------------------- totals -- */

function renderTotals(stats, closed, open) {
  countUp($("totalCount"), stats.matched);

  const countries = closed.find((b) => b.title.includes("دولة"));
  const written = open.reduce((sum, b) => sum + b.answered, 0);
  const side = [
    { value: state.meta.questions, label: "سؤالاً في الاستبيان" },
    { value: countries ? countries.data.length : closed.length, label: countries ? "دولة مشاركة" : "سؤالاً مغلقاً" },
    { value: written, label: "إجابة مكتوبة" },
  ];
  $("totalSide").innerHTML = side.map((s) => `<li><b data-v="${s.value}">0</b><span>${s.label}</span></li>`).join("");
  $("totalSide").querySelectorAll("b").forEach((b) => countUp(b, b.dataset.v));
}

/* ----------------------------------------------------------------- kpis -- */

function renderKpis(items) {
  $("kpis").innerHTML = items
    .map((k) => {
      const pct = typeof k.value === "string" && k.value.endsWith("%") ? parseInt(k.value) : null;
      const ring = pct === null ? "" : `
        <svg class="kpi-ring" viewBox="0 0 64 64" aria-hidden="true">
          <circle class="track" cx="32" cy="32" r="26" />
          <circle class="value" cx="32" cy="32" r="26" stroke-dasharray="163" stroke-dashoffset="163" data-pct="${pct}" />
        </svg>`;
      return `<article class="kpi">${ring}
        <div><b data-v="${pct === null ? k.value : pct}" data-suffix="${pct === null ? "" : "%"}">0</b>
        <span>${k.label}</span><small>${k.hint || ""}</small></div></article>`;
    })
    .join("");

  $("kpis").querySelectorAll("b").forEach((b) => countUp(b, b.dataset.v, b.dataset.suffix || ""));
  requestAnimationFrame(() => {
    $("kpis").querySelectorAll(".value").forEach((c) => {
      c.style.strokeDashoffset = 163 - (163 * Number(c.dataset.pct)) / 100;
    });
  });
}

/* ----------------------------------------------------------- highlights -- */

function renderHighlights(items) {
  $("highlightGrid").innerHTML = items
    .map(
      (h) => `<article class="highlight">
        <p class="q">${h.question}</p>
        <p class="a">${h.label}</p>
        <div class="bar"><i data-w="${h.percent}"></i></div>
        <p class="pct"><b>${h.percent}%</b> · ${h.count} مشارك</p>
      </article>`
    )
    .join("");
  requestAnimationFrame(() => {
    $("highlightGrid").querySelectorAll(".bar i").forEach((i) => (i.style.width = `${i.dataset.w}%`));
  });
}

/* --------------------------------------------------------------- charts -- */

const centerTotal = {
  id: "centerTotal",
  afterDraw(chart, _args, opts) {
    if (chart.config.type !== "doughnut") return;
    const { ctx, chartArea } = chart;
    const total = chart.data.datasets[0].data.reduce((a, b) => a + b, 0);
    const x = (chartArea.left + chartArea.right) / 2;
    const y = (chartArea.top + chartArea.bottom) / 2;
    ctx.save();
    ctx.textAlign = "center";
    ctx.fillStyle = opts.color || "#EEF1FB";
    ctx.font = "800 26px Almarai, sans-serif";
    ctx.fillText(total, x, y + 4);
    ctx.font = "400 12px Tajawal, sans-serif";
    ctx.fillStyle = "#98A2C8";
    ctx.fillText("إجابة", x, y + 24);
    ctx.restore();
  },
};
Chart.register(centerTotal);

function renderCharts(container, blocks) {
  [...container.children].forEach((c) => state.charts.get(c.dataset.chart)?.destroy());
  container.innerHTML = blocks
    .map(
      (b) => `<article class="card" data-chart="${container.id}-${b.id}">
        <h3>${b.title}</h3>
        <p class="meta">${b.answered} إجابة · ${b.options} خيار${b.type === "multi" ? " · اختيار متعدد" : ""}</p>
        <div class="chart-box"><canvas id="cv-${container.id}-${b.id}"></canvas></div>
        <ul class="legend">${b.data
          .slice(0, 7)
          .map((d, i) => `<li><i style="background:${PALETTE[i % PALETTE.length]}"></i>${d.label}<b>${d.count} · ${d.percent}%</b></li>`)
          .join("")}</ul>
      </article>`
    )
    .join("");

  blocks.forEach((b) => {
    const key = `${container.id}-${b.id}`;
    const card = container.querySelector(`[data-chart="${key}"]`);
    card._draw = () => state.charts.set(key, buildChart(`cv-${key}`, b));
    revealer.observe(card);
  });
}

function buildChart(canvasId, block) {
  const labels = block.data.map((d) => d.label);
  const values = block.data.map((d) => d.count);
  const colors = labels.map((_, i) => PALETTE[i % PALETTE.length]);
  const isDoughnut = block.chart === "doughnut";

  return new Chart(document.getElementById(canvasId), {
    type: isDoughnut ? "doughnut" : "bar",
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: colors.map((c) => (isDoughnut ? c : c + "D9")),
          hoverBackgroundColor: colors,
          borderWidth: isDoughnut ? 3 : 0,
          borderColor: "#0B1024",
          borderRadius: isDoughnut ? 0 : 7,
          barThickness: 18,
        },
      ],
    },
    options: {
      indexAxis: isDoughnut ? "x" : "y",
      responsive: true,
      maintainAspectRatio: false,
      cutout: isDoughnut ? "62%" : undefined,
      animation: MOTION ? { duration: 900, easing: "easeOutQuart" } : false,
      plugins: {
        legend: { display: false },
        centerTotal: {},
        tooltip: {
          rtl: true,
          backgroundColor: "#161B36",
          borderColor: "rgba(255,255,255,.12)",
          borderWidth: 1,
          padding: 12,
          titleFont: { family: "Tajawal" },
          bodyFont: { family: "Tajawal" },
          callbacks: { label: (i) => ` ${block.data[i.dataIndex].count} (${block.data[i.dataIndex].percent}%)` },
        },
      },
      scales: isDoughnut
        ? {}
        : {
            x: { beginAtZero: true, ticks: { precision: 0, color: "#98A2C8" }, grid: { color: "rgba(255,255,255,.06)" } },
            y: {
              grid: { display: false },
              ticks: { color: "#98A2C8", font: { family: "Tajawal", size: 12 }, callback: (v) => trim(labels[v], 24) },
            },
          },
    },
  });
}

const trim = (s = "", n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

/* ------------------------------------------------------------ open text -- */

function renderOpen(blocks) {
  $("openGrid").innerHTML = blocks
    .map(
      (b) => `<article class="card is-in">
        <h3>${b.title}</h3>
        <p class="meta">${b.answered} إجابة مكتوبة</p>
        <p class="words">${b.keywords.map((k) => `<span class="word">${k.word}<em>${k.count}</em></span>`).join("")}</p>
        <div class="answers">${
          b.answers.map((a) => `<p class="answer">${escapeHtml(a)}</p>`).join("") ||
          '<p class="empty">لا توجد إجابات ضمن هذه التصفية</p>'
        }</div>
      </article>`
    )
    .join("");

  const pool = blocks.flatMap((b) => b.answers).filter((a) => a.length > 60);
  if (pool.length) {
    $("heroQuoteText").textContent = `«${pool[Math.floor(Math.random() * pool.length)]}»`;
    $("heroQuote").hidden = false;
  }
}

/* --------------------------------------------------------------- filters -- */

function renderFilters(groups) {
  $("filterGroups").innerHTML = groups
    .map(
      (g) => `<div class="filter-group"><h3>${g.column}</h3><div class="chips">${g.options
        .map((o) => `<button class="chip" aria-pressed="false" data-col="${escapeHtml(g.column)}" data-val="${escapeHtml(o)}">${o}</button>`)
        .join("")}</div></div>`
    )
    .join("");
}

$("filterGroups").addEventListener("click", async (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  const { col, val } = chip.dataset;
  const on = chip.getAttribute("aria-pressed") === "true";
  chip.setAttribute("aria-pressed", String(!on));
  const list = state.filters[col] || [];
  state.filters[col] = on ? list.filter((v) => v !== val) : [...list, val];
  if (!state.filters[col].length) delete state.filters[col];
  await refresh();
});

$("clearFilters").addEventListener("click", async () => {
  state.filters = {};
  document.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", "false"));
  await refresh();
});

/* ------------------------------------------------------------------ tabs -- */

function moveInk(tab) {
  // offsetLeft is measured from the container's left edge in both directions,
  // so positioning with `left` works unchanged under RTL.
  const ink = $("tabInk");
  ink.style.width = `${tab.offsetWidth}px`;
  ink.style.left = `${tab.offsetLeft}px`;
}

$("tabs").addEventListener("click", (e) => {
  const tab = e.target.closest(".tab");
  if (!tab) return;
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("is-active", t === tab));
  document.querySelectorAll(".tabpane").forEach((p) => {
    const on = p.id === `pane-${tab.dataset.tab}`;
    p.classList.toggle("is-active", on);
    p.hidden = !on;
  });
  moveInk(tab);
  state.charts.forEach((c) => c.resize());
});
window.addEventListener("load", () => moveInk(document.querySelector(".tab.is-active")));
window.addEventListener("resize", () => moveInk(document.querySelector(".tab.is-active")));

/* ----------------------------------------------------------------- table -- */

async function loadRows() {
  const params = new URLSearchParams({ page: state.page, size: 25 });
  if (Object.keys(state.filters).length) params.set("filters", JSON.stringify(state.filters));
  if (state.search) params.set("search", state.search);

  const data = await api(`/api/responses?${params}`);
  const table = $("responsesTable");
  if (!data.rows.length) {
    table.innerHTML = `<tbody><tr><td class="empty">لا توجد ردود مطابقة</td></tr></tbody>`;
  } else {
    const cols = Object.keys(data.rows[0]);
    table.innerHTML =
      `<thead><tr>${cols.map((c) => `<th title="${escapeHtml(c)}">${trim(c, 26)}</th>`).join("")}</tr></thead>` +
      `<tbody>${data.rows
        .map((r) => `<tr>${cols.map((c) => `<td title="${escapeHtml(r[c])}">${escapeHtml(r[c])}</td>`).join("")}</tr>`)
        .join("")}</tbody>`;
  }
  const pages = Math.max(1, Math.ceil(data.total / data.size));
  $("pageInfo").textContent = `صفحة ${data.page} من ${pages} · ${data.total} رد`;
  $("prevPage").disabled = data.page <= 1;
  $("nextPage").disabled = data.page >= pages;
}

$("prevPage").addEventListener("click", () => { state.page--; loadRows(); });
$("nextPage").addEventListener("click", () => { state.page++; loadRows(); });
$("tableSearch").addEventListener("input", debounce((e) => { state.search = e.target.value; state.page = 1; loadRows(); }, 300));

/* --------------------------------------------------------------- sources -- */

$("openSource").addEventListener("click", (e) => {
  const panel = $("sourcePanel");
  panel.hidden = !panel.hidden;
  e.currentTarget.setAttribute("aria-expanded", String(!panel.hidden));
});

async function loadFile(file) {
  const form = new FormData();
  form.append("file", file);
  try {
    await api("/api/source/upload", { method: "POST", body: form });
    toast(`تم تحميل ${file.name}`);
    state.filters = {};
    $("sourcePanel").hidden = true;
    await boot();
  } catch (err) {
    toast(err.message, true);
  }
}

$("fileInput").addEventListener("change", (e) => e.target.files[0] && loadFile(e.target.files[0]));

const drop = $("drop");
["dragenter", "dragover"].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("is-over"); })
);
["dragleave", "drop"].forEach((ev) =>
  drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("is-over"); })
);
drop.addEventListener("drop", (e) => e.dataTransfer.files[0] && loadFile(e.dataTransfer.files[0]));

$("driveBtn").addEventListener("click", async () => {
  const link = $("driveInput").value.trim();
  if (!link) return toast("الصق رابط الملف أولاً", true);
  try {
    await api("/api/source/drive", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ link }),
    });
    toast("تم التحميل من الرابط");
    state.filters = {};
    $("sourcePanel").hidden = true;
    await boot();
  } catch (err) {
    toast(err.message, true);
  }
});

/* ----------------------------------------------------------------- utils -- */

function escapeHtml(s = "") {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

boot();

/**
 * JEE Main Cutoffs 2025 — JoSAA + CSAB
 * Loads OR-CR data, converts percentile → rank, filters results.
 */

"use strict";

// ── Constants ──────────────────────────────────────────────────────────────
// JEE Main 2024 total appeared candidates (~13.4 lakh); used as proxy until
// official 2025 figures are published.
const TOTAL_CANDIDATES = 1338704;
const PAGE_SIZE = 50;
const MAX_CHOICES_DISPLAY = 200; // cap choices table to avoid DOM overload

// ── State ──────────────────────────────────────────────────────────────────
let josaaRows = [];
let csabRows = [];
let activeRows = [];   // current dataset (josaa or csab)
let filtered = [];     // after filters applied
let displayed = [];    // after sort
let page = 1;
let sortKey = null;
let sortAsc = true;
let userRank = null;
let choicesRows = [];

// ── Helpers ────────────────────────────────────────────────────────────────
function percentileToRank(p) {
  if (p == null || p === "" || isNaN(+p)) return null;
  const pct = parseFloat(p);
  if (pct < 0 || pct > 100) return null;
  return Math.max(1, Math.ceil((1 - pct / 100) * TOTAL_CANDIDATES));
}

function parseBranchPreferences(raw) {
  return raw
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

function uniq(arr) {
  return [...new Set(arr)].filter(Boolean).sort();
}

function escCsv(v) {
  const s = String(v ?? "");
  return s.includes(",") || s.includes('"') || s.includes("\n")
    ? `"${s.replace(/"/g, '""')}"`
    : s;
}

function setOptions(selectEl, values, allLabel) {
  const prev = selectEl.value;
  selectEl.innerHTML = `<option value="">${allLabel ?? "All"}</option>`;
  values.forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    selectEl.appendChild(opt);
  });
  if ([...selectEl.options].some((o) => o.value === prev)) selectEl.value = prev;
}

// ── Data loading ───────────────────────────────────────────────────────────
async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.json();
}

async function loadData() {
  const statusEl = document.getElementById("statusBody");
  statusEl.textContent = "Loading JoSAA data…";

  try {
    const josaa = await fetchJson("data/josaa-2025.json");
    josaaRows = josaa.rows ?? [];
    statusEl.textContent = `JoSAA: ${josaaRows.length.toLocaleString()} rows loaded. Loading CSAB…`;
  } catch (e) {
    josaaRows = [];
    statusEl.textContent = `JoSAA data unavailable (${e.message}). Loading CSAB…`;
  }

  try {
    const csab = await fetchJson("data/csab-2025.json");
    csabRows = csab.rows ?? [];
  } catch (e) {
    csabRows = [];
  }

  const total = josaaRows.length + csabRows.length;
  statusEl.innerHTML =
    `JoSAA: <strong>${josaaRows.length.toLocaleString()}</strong> rows &nbsp;|&nbsp; ` +
    `CSAB: <strong>${csabRows.length.toLocaleString()}</strong> rows &nbsp;|&nbsp; ` +
    `Total: <strong>${total.toLocaleString()}</strong>`;

  // Default to josaa dataset
  activeRows = josaaRows;
  buildFilters();
  applyFilters();
  populateProfileDropdowns();
}

// ── Filter dropdowns ───────────────────────────────────────────────────────
function buildFilters() {
  setOptions(
    document.getElementById("filter-round"),
    uniq(activeRows.map((r) => r.round)),
    "All Rounds"
  );
  setOptions(
    document.getElementById("filter-inst-type"),
    uniq(activeRows.map((r) => r.institute_type)),
    "All Types"
  );
  setOptions(
    document.getElementById("filter-inst"),
    uniq(activeRows.map((r) => r.institute)),
    "All Institutes"
  );
  setOptions(
    document.getElementById("filter-program"),
    uniq(activeRows.map((r) => r.program)),
    "All Programs"
  );
  setOptions(
    document.getElementById("filter-seat"),
    uniq(activeRows.map((r) => r.seat_type)),
    "All Seat Types"
  );
  setOptions(
    document.getElementById("filter-quota"),
    uniq(activeRows.map((r) => r.quota)),
    "All Quotas"
  );
  setOptions(
    document.getElementById("filter-gender"),
    uniq(activeRows.map((r) => r.gender)),
    "All Genders"
  );
}

function populateProfileDropdowns() {
  const allSeatTypes = uniq(
    [...josaaRows, ...csabRows].map((r) => r.seat_type)
  );
  setOptions(document.getElementById("profile-category"), allSeatTypes, "Select Category");

  const allQuotas = uniq(
    [...josaaRows, ...csabRows].map((r) => r.quota)
  );
  setOptions(document.getElementById("profile-quota"), allQuotas, "Select Quota");

  const allGenders = uniq(
    [...josaaRows, ...csabRows].map((r) => r.gender)
  );
  setOptions(document.getElementById("profile-gender"), allGenders, "Select Gender");
}

// ── Filtering logic ────────────────────────────────────────────────────────
function applyFilters() {
  const round = document.getElementById("filter-round").value;
  const instType = document.getElementById("filter-inst-type").value;
  const inst = document.getElementById("filter-inst").value;
  const program = document.getElementById("filter-program").value;
  const seat = document.getElementById("filter-seat").value;
  const quota = document.getElementById("filter-quota").value;
  const gender = document.getElementById("filter-gender").value;
  const search = document.getElementById("search").value.trim().toLowerCase();

  filtered = activeRows.filter((r) => {
    if (round && r.round !== round) return false;
    if (instType && r.institute_type !== instType) return false;
    if (inst && r.institute !== inst) return false;
    if (program && r.program !== program) return false;
    if (seat && r.seat_type !== seat) return false;
    if (quota && r.quota !== quota) return false;
    if (gender && r.gender !== gender) return false;
    if (search) {
      const hay = `${r.institute} ${r.program}`.toLowerCase();
      if (!hay.includes(search)) return false;
    }
    return true;
  });

  sortData();
}

function sortData() {
  if (sortKey) {
    const numericKeys = ["opening_rank", "closing_rank"];
    displayed = [...filtered].sort((a, b) => {
      let va = a[sortKey] ?? "";
      let vb = b[sortKey] ?? "";
      if (numericKeys.includes(sortKey)) {
        // Non-numeric / missing values sort to the end regardless of direction
        const na = +va;
        const nb = +vb;
        va = isNaN(na) ? Infinity : na;
        vb = isNaN(nb) ? Infinity : nb;
        return sortAsc ? va - vb : vb - va;
      }
      return sortAsc
        ? String(va).localeCompare(String(vb))
        : String(vb).localeCompare(String(va));
    });
  } else {
    displayed = filtered;
  }
  page = 1;
  renderResults();
}

// ── Profile / Choices ──────────────────────────────────────────────────────
function applyProfile() {
  const cat = document.getElementById("profile-category").value;
  const quota = document.getElementById("profile-quota").value;
  const gender = document.getElementById("profile-gender").value;
  const pct = document.getElementById("profile-percentile").value;
  const branchPref = parseBranchPreferences(
    document.getElementById("profile-branches").value
  );

  userRank = percentileToRank(pct);
  const rankEl = document.getElementById("profile-rank");
  if (userRank) {
    rankEl.textContent = `Estimated CRL Rank: ${userRank.toLocaleString()}`;
  } else {
    rankEl.textContent = "Estimated Rank: —";
  }

  if (!userRank) {
    choicesRows = [];
    renderChoices();
    return;
  }

  // Search across both datasets
  const pool = [...josaaRows, ...csabRows];
  choicesRows = pool.filter((r) => {
    if (cat && r.seat_type !== cat) return false;
    if (quota && r.quota !== quota) return false;
    if (gender && r.gender !== gender) return false;
    const closeRank = +r.closing_rank;
    if (!closeRank || userRank > closeRank) return false;
    if (branchPref.length) {
      const prog = r.program.toLowerCase();
      if (!branchPref.some((b) => prog.includes(b))) return false;
    }
    return true;
  });

  // Sort choices by closing rank ascending so best fits show first
  choicesRows.sort((a, b) => +a.closing_rank - +b.closing_rank);
  renderChoices();
}

function renderChoices() {
  const panel = document.getElementById("choicesPanel");
  const countEl = document.getElementById("choicesCount");
  const tbody = document.getElementById("choicesBody");

  if (!choicesRows.length) {
    countEl.textContent =
      userRank
        ? "No matching choices found. Try adjusting your profile filters."
        : "Enter your percentile to see choices.";
    tbody.innerHTML = "";
    return;
  }

  countEl.textContent = `${choicesRows.length.toLocaleString()} choice${choicesRows.length !== 1 ? "s" : ""} found (rank ≤ closing rank)`;
  tbody.innerHTML = "";
  const capped = choicesRows.length > MAX_CHOICES_DISPLAY;
  choicesRows.slice(0, MAX_CHOICES_DISPLAY).forEach((r) => {
    tbody.appendChild(buildRow(r, true));
  });
  if (capped) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 9;
    td.className = "choices-cap-note";
    td.textContent = `Showing top ${MAX_CHOICES_DISPLAY} of ${choicesRows.length.toLocaleString()} choices. Use filters to narrow results.`;
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
}

// ── Render results table ───────────────────────────────────────────────────
function renderResults() {
  const tbody = document.getElementById("resultsBody");
  const countEl = document.getElementById("count");
  const pageInfoEl = document.getElementById("pageInfo");
  const totalPages = Math.max(1, Math.ceil(displayed.length / PAGE_SIZE));

  countEl.textContent = `${displayed.length.toLocaleString()} result${displayed.length !== 1 ? "s" : ""}`;
  pageInfoEl.textContent = `Page ${page} of ${totalPages}`;
  document.getElementById("prev").disabled = page <= 1;
  document.getElementById("next").disabled = page >= totalPages;

  const start = (page - 1) * PAGE_SIZE;
  const slice = displayed.slice(start, start + PAGE_SIZE);

  tbody.innerHTML = "";
  slice.forEach((r) => tbody.appendChild(buildRow(r, false)));
}

function buildRow(r, highlight) {
  const tr = document.createElement("tr");
  if (highlight && userRank) {
    const close = +r.closing_rank;
    if (userRank <= close) tr.classList.add("eligible");
  }
  [
    r.round,
    r.institute_type,
    r.institute,
    r.program,
    r.seat_type,
    r.quota,
    r.gender,
    r.opening_rank,
    r.closing_rank,
  ].forEach((val) => {
    const td = document.createElement("td");
    td.textContent = val ?? "";
    tr.appendChild(td);
  });
  return tr;
}

// ── Sort ───────────────────────────────────────────────────────────────────
function handleSort(key) {
  if (sortKey === key) {
    sortAsc = !sortAsc;
  } else {
    sortKey = key;
    sortAsc = true;
  }
  // Update header indicators
  document.querySelectorAll("#results th[data-key], #choices th[data-key]").forEach((th) => {
    th.classList.remove("sort-asc", "sort-desc");
    th.removeAttribute("aria-sort");
    if (th.dataset.key === sortKey) {
      th.classList.add(sortAsc ? "sort-asc" : "sort-desc");
      th.setAttribute("aria-sort", sortAsc ? "ascending" : "descending");
    }
  });
  sortData();
}

// ── CSV Export ─────────────────────────────────────────────────────────────
function exportCsv() {
  const headers = [
    "Round","Institute Type","Institute","Program",
    "Seat Type","Quota","Gender","Opening Rank","Closing Rank",
  ];
  const lines = [headers.map(escCsv).join(",")];
  displayed.forEach((r) => {
    lines.push(
      [
        r.round, r.institute_type, r.institute, r.program,
        r.seat_type, r.quota, r.gender, r.opening_rank, r.closing_rank,
      ].map(escCsv).join(",")
    );
  });
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "jee-cutoffs-2025.csv";
  a.click();
}

// ── Reset filters ──────────────────────────────────────────────────────────
function resetFilters() {
  ["filter-round","filter-inst-type","filter-inst","filter-program",
   "filter-seat","filter-quota","filter-gender"].forEach((id) => {
    document.getElementById(id).value = "";
  });
  document.getElementById("search").value = "";
  sortKey = null;
  sortAsc = true;
  document.querySelectorAll("#results th[data-key], #choices th[data-key]").forEach((th) =>
    th.classList.remove("sort-asc", "sort-desc")
  );
  applyFilters();
}

// ── Dataset toggle ─────────────────────────────────────────────────────────
function switchDataset(val) {
  activeRows = val === "csab" ? csabRows : josaaRows;
  buildFilters();
  applyFilters();
}

// ── Boot ───────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Dataset radio
  document.querySelectorAll('input[name="dataset"]').forEach((radio) => {
    radio.addEventListener("change", () => switchDataset(radio.value));
  });

  // Filters
  ["filter-round","filter-inst-type","filter-inst","filter-program",
   "filter-seat","filter-quota","filter-gender"].forEach((id) => {
    document.getElementById(id).addEventListener("change", applyFilters);
  });
  document.getElementById("search").addEventListener("input", applyFilters);

  // Sort headers
  document.querySelectorAll("#results th[data-key], #choices th[data-key]").forEach((th) => {
    th.addEventListener("click", () => handleSort(th.dataset.key));
  });

  // Pagination
  document.getElementById("prev").addEventListener("click", () => {
    if (page > 1) { page--; renderResults(); }
  });
  document.getElementById("next").addEventListener("click", () => {
    const totalPages = Math.ceil(displayed.length / PAGE_SIZE);
    if (page < totalPages) { page++; renderResults(); }
  });

  // Profile
  document.getElementById("profile-apply").addEventListener("click", applyProfile);
  document.getElementById("profile-percentile").addEventListener("keydown", (e) => {
    if (e.key === "Enter") applyProfile();
  });

  // Actions
  document.getElementById("reset").addEventListener("click", resetFilters);
  document.getElementById("export").addEventListener("click", exportCsv);

  loadData();
});

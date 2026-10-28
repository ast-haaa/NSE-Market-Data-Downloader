/**
 * NSE Market Pulse — Frontend Client Logic
 */

document.addEventListener("DOMContentLoaded", () => {
  // ── State ──────────────────────────────────────────────────────────
  let activeDataset = "top-gainers-losers";
  let datasetCache = {};
  let currentRecords = [];
  let filteredRecords = [];
  let statusData = null;

  // ── DOM References ─────────────────────────────────────────────────
  const datasetTabs = document.querySelectorAll(".tab-btn");
  const tableHead = document.getElementById("tableHead");
  const tableBody = document.getElementById("tableBody");
  const tableLoading = document.getElementById("tableLoading");
  const tableEmpty = document.getElementById("tableEmpty");
  const searchInput = document.getElementById("searchInput");
  const clearSearchBtn = document.getElementById("clearSearchBtn");
  const recordsPill = document.getElementById("recordsPill");
  const btnDownloadCSV = document.getElementById("btnDownloadCSV");
  const btnTriggerIngestion = document.getElementById("btnTriggerIngestion");
  const btnTriggerText = document.getElementById("btnTriggerText");
  const toastContainer = document.getElementById("toastContainer");
  const themeToggleBtn = document.getElementById("themeToggleBtn");
  const themeToggleText = document.getElementById("themeToggleText");
  const themeIcon = document.getElementById("themeIcon");

  // KPI elements
  const kpiTotalCount = document.getElementById("kpiTotalCount");
  const kpiTopGainer = document.getElementById("kpiTopGainer");
  const kpiTopGainerSub = document.getElementById("kpiTopGainerSub");
  const kpiUpperBandCount = document.getElementById("kpiUpperBandCount");
  const kpi52WeekCount = document.getElementById("kpi52WeekCount");
  const footerFilename = document.getElementById("footerFilename");
  const footerUpdatedAt = document.getElementById("footerUpdatedAt");

  // ── Theme Switcher (Default: Light Mode) ───────────────────────────
  let currentTheme = localStorage.getItem("nse_theme") || "light";
  applyTheme(currentTheme);

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("nse_theme", theme);
    if (!themeToggleText || !themeIcon) return;
    if (theme === "light") {
      themeToggleText.textContent = "Light";
      themeIcon.innerHTML = `
        <circle cx="12" cy="12" r="5"></circle>
        <line x1="12" y1="1" x2="12" y2="3"></line>
        <line x1="12" y1="21" x2="12" y2="23"></line>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
        <line x1="1" y1="12" x2="3" y2="12"></line>
        <line x1="21" y1="12" x2="23" y2="12"></line>
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
      `;
    } else {
      themeToggleText.textContent = "Dark";
      themeIcon.innerHTML = `
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
      `;
    }
  }

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener("click", () => {
      const active = document.documentElement.getAttribute("data-theme") || "light";
      const nextTheme = active === "light" ? "dark" : "light";
      applyTheme(nextTheme);
      showToast(`Switched to ${nextTheme === "light" ? "Light" : "Dark"} Mode`, "info");
    });
  }

  // ── Column Definitions per Dataset ─────────────────────────────────
  const COLUMN_CONFIGS = {
    "top-gainers-losers": [
      { key: "symbol", label: "Symbol", type: "symbol" },
      { key: "series", label: "Series", type: "series" },
      { key: "ltp", label: "LTP (₹)", type: "price" },
      { key: "perChange", label: "% Change", type: "change" },
      { key: "open_price", label: "Open (₹)", type: "price" },
      { key: "high_price", label: "High (₹)", type: "price" },
      { key: "low_price", label: "Low (₹)", type: "price" },
      { key: "prev_price", label: "Prev Close", type: "price" },
      { key: "trade_quantity", label: "Volume", type: "number" }
    ],
    "upper-band-hitters": [
      { key: "symbol", label: "Symbol", type: "symbol" },
      { key: "series", label: "Series", type: "series" },
      { key: "ltp", label: "LTP (₹)", type: "price" },
      { key: "pChange", label: "% Change", type: "change" },
      { key: "priceBand", label: "Band %", type: "badge" },
      { key: "highPrice", label: "High (₹)", type: "price" },
      { key: "lowPrice", label: "Low (₹)", type: "price" },
      { key: "yearHigh", label: "52W High", type: "price" },
      { key: "totalTradedVol", label: "Vol (Lakhs)", type: "number" },
      { key: "bandHitDate", label: "Date", type: "text" }
    ],
    "volume-gainers-spurts": [
      { key: "symbol", label: "Symbol", type: "symbol" },
      { key: "companyName", label: "Company Name", type: "text" },
      { key: "ltp", label: "LTP (₹)", type: "price" },
      { key: "pChange", label: "% Change", type: "change" },
      { key: "volume", label: "Volume (Shares)", type: "number" },
      { key: "week1AvgVolume", label: "1W Avg Vol", type: "number" },
      { key: "week1volChange", label: "1W Volume Spurt", type: "spurt" },
      { key: "turnover", label: "Turnover (₹L)", type: "number" }
    ],
    "52-week-high": [
      { key: "symbol", label: "Symbol", type: "symbol" },
      { key: "series", label: "Series", type: "series" },
      { key: "comapnyName", label: "Company Name", type: "text" },
      { key: "ltp", label: "LTP (₹)", type: "price" },
      { key: "pChange", label: "% Change", type: "change" },
      { key: "new52WHL", label: "New 52W High (₹)", type: "highlight-price" },
      { key: "prev52WHL", label: "Prev 52W High", type: "price" },
      { key: "prevHLDate", label: "Prev High Date", type: "text" }
    ]
  };

  // ── Formatters ─────────────────────────────────────────────────────
  function formatNumber(num) {
    if (num === null || num === undefined || isNaN(num)) return "—";
    return Number(num).toLocaleString("en-IN");
  }

  function formatPrice(num) {
    if (num === null || num === undefined || isNaN(num)) return "—";
    return Number(num).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  }

  function formatChange(val) {
    if (val === null || val === undefined) return "—";
    const num = parseFloat(String(val).trim());
    if (isNaN(num)) return "—";
    const sign = num > 0 ? "+" : "";
    const isPositive = num >= 0;
    const cls = isPositive ? "positive" : "negative";
    return `<span class="change-pill ${cls}">${sign}${num.toFixed(2)}%</span>`;
  }

  // ── Fetch Global Status & KPIs ─────────────────────────────────────
  async function loadStatus() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) throw new Error("Failed to load status");
      statusData = await res.json();

      // Update KPI Cards
      kpiTotalCount.textContent = formatNumber(statusData.total_records);

      if (statusData.datasets["upper-band-hitters"]) {
        kpiUpperBandCount.textContent = formatNumber(
          statusData.datasets["upper-band-hitters"].record_count
        );
      }
      if (statusData.datasets["52-week-high"]) {
        kpi52WeekCount.textContent = formatNumber(
          statusData.datasets["52-week-high"].record_count
        );
      }

      // Update tab counts
      for (const [key, ds] of Object.entries(statusData.datasets)) {
        const countEl = document.getElementById(`count-${key}`);
        if (countEl) countEl.textContent = ds.record_count;
      }
    } catch (err) {
      console.error("Status error:", err);
    }
  }

  // ── Fetch Single Dataset ───────────────────────────────────────────
  async function loadDataset(datasetKey) {
    tableLoading.classList.remove("hidden");
    tableEmpty.classList.add("hidden");

    try {
      const res = await fetch(`/api/data/${datasetKey}`);
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();

      datasetCache[datasetKey] = data;
      currentRecords = data.records || [];

      // Update Top Gainer KPI if this is gainers
      if (datasetKey === "top-gainers-losers" && currentRecords.length > 0) {
        const top = currentRecords[0];
        kpiTopGainer.textContent = `${top.symbol} +${Number(top.perChange).toFixed(2)}%`;
        kpiTopGainerSub.textContent = `LTP: ₹${formatPrice(top.ltp)}`;
      }

      // Update footer metadata
      footerFilename.textContent = data.filename || "—";
      if (statusData && statusData.datasets[datasetKey]) {
        footerUpdatedAt.textContent =
          statusData.datasets[datasetKey].updated_at || "Just now";
      }

      // Apply current search filter
      applyFilter();
    } catch (err) {
      console.error("Dataset fetch error:", err);
      tableBody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: #f43f5e; padding: 40px;">Failed to load dataset: ${err.message}. Please click "Run Ingestion" above.</td></tr>`;
      recordsPill.textContent = "Showing 0 records";
    } finally {
      tableLoading.classList.add("hidden");
    }
  }

  // ── Render Table ───────────────────────────────────────────────────
  function renderTable(records) {
    const config = COLUMN_CONFIGS[activeDataset] || [];

    // 1. Build Headers
    tableHead.innerHTML = `<tr>${config
      .map(col => `<th>${col.label}</th>`)
      .join("")}</tr>`;

    // 2. Build Rows
    if (!records || records.length === 0) {
      tableBody.innerHTML = "";
      tableEmpty.classList.remove("hidden");
      recordsPill.textContent = "Showing 0 records";
      return;
    }

    tableEmpty.classList.add("hidden");
    recordsPill.textContent = `Showing ${records.length} of ${currentRecords.length} records`;

    const rowsHtml = records
      .map(row => {
        const cellsHtml = config
          .map(col => {
            const rawVal = row[col.key];

            switch (col.type) {
              case "symbol":
                return `<td><span class="symbol-cell">${rawVal || "—"}</span></td>`;
              case "series":
                return `<td><span class="series-badge">${rawVal || "EQ"}</span></td>`;
              case "price":
                return `<td class="numeric-cell">₹${formatPrice(rawVal)}</td>`;
              case "highlight-price":
                return `<td class="numeric-cell" style="color: #fde047; font-weight: 700;">₹${formatPrice(rawVal)}</td>`;
              case "change":
                return `<td>${formatChange(rawVal)}</td>`;
              case "badge":
                return `<td><span class="kpi-badge accent-cyan">${rawVal || "—"}%</span></td>`;
              case "spurt":
                const spurtVal = parseFloat(rawVal) || 0;
                return `<td><span class="change-pill positive">+${spurtVal.toFixed(1)}x</span></td>`;
              case "number":
                return `<td class="numeric-cell">${formatNumber(rawVal)}</td>`;
              default:
                return `<td>${rawVal !== null && rawVal !== undefined ? rawVal : "—"}</td>`;
            }
          })
          .join("");

        return `<tr>${cellsHtml}</tr>`;
      })
      .join("");

    tableBody.innerHTML = rowsHtml;
  }

  // ── Search & Filter ────────────────────────────────────────────────
  function applyFilter() {
    const query = (searchInput.value || "").trim().toLowerCase();
    if (!query) {
      filteredRecords = currentRecords;
      clearSearchBtn.classList.remove("visible");
    } else {
      clearSearchBtn.classList.add("visible");
      filteredRecords = currentRecords.filter(row => {
        const symbol = String(row.symbol || "").toLowerCase();
        const company = String(row.companyName || row.comapnyName || "").toLowerCase();
        const series = String(row.series || "").toLowerCase();
        return symbol.includes(query) || company.includes(query) || series.includes(query);
      });
    }
    renderTable(filteredRecords);
  }

  searchInput.addEventListener("input", applyFilter);
  clearSearchBtn.addEventListener("click", () => {
    searchInput.value = "";
    applyFilter();
    searchInput.focus();
  });

  // ── Tab Switching ──────────────────────────────────────────────────
  datasetTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const targetDataset = tab.getAttribute("data-dataset");
      if (targetDataset === activeDataset) return;

      datasetTabs.forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      activeDataset = targetDataset;

      searchInput.value = "";
      clearSearchBtn.classList.remove("visible");
      loadDataset(activeDataset);
    });
  });

  // ── CSV Download ───────────────────────────────────────────────────
  btnDownloadCSV.addEventListener("click", () => {
    window.location.href = `/api/download/${activeDataset}`;
    showToast(`Downloading CSV for ${activeDataset}...`, "success");
  });

  // ── Ingestion Trigger ──────────────────────────────────────────────
  btnTriggerIngestion.addEventListener("click", async () => {
    btnTriggerIngestion.classList.add("loading");
    btnTriggerText.textContent = "Ingesting Data...";
    btnTriggerIngestion.disabled = true;

    showToast("Triggering full market ingestion across all 4 datasets...", "info");

    try {
      const res = await fetch("/api/trigger", { method: "POST" });
      const result = await res.json();

      if (result.success) {
        showToast(
          `✓ Successfully ingested all 4 datasets (${result.results.reduce((a, b) => a + b.records, 0)} records total)!`,
          "success"
        );
      } else {
        showToast(
          `Ingested with warnings: ${result.succeeded} OK, ${result.failed} Failed.`,
          "error"
        );
      }

      // Refresh status and active view
      await loadStatus();
      await loadDataset(activeDataset);
    } catch (err) {
      showToast(`Ingestion error: ${err.message}`, "error");
    } finally {
      btnTriggerIngestion.classList.remove("loading");
      btnTriggerText.textContent = "Run Ingestion";
      btnTriggerIngestion.disabled = false;
    }
  });

  // ── Toast System ───────────────────────────────────────────────────
  function showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${message}</span>`;
    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 4500);
  }

  // ── Initial Boot ───────────────────────────────────────────────────
  async function init() {
    await loadStatus();
    await loadDataset(activeDataset);
  }

  init();
});

const API_BASE = window.BRODY_API_BASE || "http://localhost:8787/api";

const state = {
  token: localStorage.getItem("brody_token") || "",
  currentView: "dashboard",
  me: null,
  market: null,
  lastError: "",
  pollId: null,
};

const els = {
  loginView: document.getElementById("login-view"),
  appView: document.getElementById("app-view"),
  loginForm: document.getElementById("login-form"),
  loginError: document.getElementById("login-error"),
  username: document.getElementById("username"),
  password: document.getElementById("password"),
  currentUser: document.getElementById("current-user"),
  marketStatus: document.getElementById("market-status"),
  connectionState: document.getElementById("connection-state"),
  adminLink: document.getElementById("admin-link"),
  announcement: document.getElementById("announcement-banner"),
  tickerTape: document.getElementById("ticker-tape"),
  logoutBtn: document.getElementById("logout-btn"),
  navLinks: Array.from(document.querySelectorAll(".nav-link[data-view]")),
  views: {
    dashboard: document.getElementById("dashboard-view"),
    markets: document.getElementById("markets-view"),
    portfolio: document.getElementById("portfolio-view"),
    trade: document.getElementById("trade-view"),
    leaderboard: document.getElementById("leaderboard-view"),
    history: document.getElementById("history-view"),
    admin: document.getElementById("admin-view"),
  },
};

els.loginForm.addEventListener("submit", handleLogin);
els.logoutBtn.addEventListener("click", logout);
els.navLinks.forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.view));
});

boot();

async function boot() {
  if (!state.token) {
    showLogin();
    return;
  }
  const ok = await refreshState();
  if (!ok) {
    showLogin();
    return;
  }
  startPolling();
}

async function handleLogin(event) {
  event.preventDefault();
  setLoginError("");
  try {
    const response = await request("/login", {
      method: "POST",
      body: JSON.stringify({
        username: els.username.value.trim(),
        password: els.password.value,
      }),
    }, false);

    state.token = response.token;
    localStorage.setItem("brody_token", state.token);
    await refreshState();
    showApp();
    startPolling();
  } catch (error) {
    setLoginError(error.message);
  }
}

function logout() {
  state.token = "";
  state.me = null;
  state.market = null;
  localStorage.removeItem("brody_token");
  stopPolling();
  showLogin();
}

function showLogin() {
  els.loginView.classList.remove("hidden");
  els.appView.classList.add("hidden");
}

function showApp() {
  els.loginView.classList.add("hidden");
  els.appView.classList.remove("hidden");
  renderAll();
}

function setLoginError(message) {
  els.loginError.textContent = message;
  els.loginError.classList.toggle("hidden", !message);
}

function setView(viewName) {
  state.currentView = viewName;
  els.navLinks.forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  Object.entries(els.views).forEach(([key, node]) => {
    node.classList.toggle("hidden", key !== viewName);
  });
}

function startPolling() {
  stopPolling();
  state.pollId = setInterval(refreshState, 2500);
}

function stopPolling() {
  if (state.pollId) {
    clearInterval(state.pollId);
    state.pollId = null;
  }
}

async function refreshState() {
  try {
    const payload = await request("/state");
    state.me = payload.me;
    state.market = payload.market;
    els.connectionState.textContent = "Live";
    showApp();
    renderAll();
    return true;
  } catch (error) {
    els.connectionState.textContent = "Offline";
    if (error.message === "Unauthorized") {
      logout();
    }
    return false;
  }
}

async function request(path, options = {}, withAuth = true) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (withAuth && state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function renderAll() {
  if (!state.market || !state.me) {
    return;
  }

  els.currentUser.textContent = state.me.username;
  els.marketStatus.textContent = state.market.market_open ? "Market Open" : "Market Closed";
  els.adminLink.classList.toggle("hidden", !state.me.is_admin);
  els.announcement.textContent = state.market.announcement || "";
  els.announcement.classList.toggle("hidden", !state.market.announcement);

  renderTicker();
  renderDashboard();
  renderMarkets();
  renderPortfolio();
  renderTrade();
  renderLeaderboard();
  renderHistory();
  renderAdmin();
}

function renderTicker() {
  els.tickerTape.innerHTML = state.market.stocks.slice(0, 20).map((stock) => `
    <div class="ticker-item">
      <div class="mono">${stock.symbol}</div>
      <strong>$${stock.price.toFixed(2)}</strong>
      <div class="${stock.change_pct >= 0 ? "up" : "down"}">${formatSigned(stock.change_pct)}%</div>
    </div>
  `).join("");
}

function renderDashboard() {
  const page = els.views.dashboard;
  const summary = state.market.summary;
  page.innerHTML = `
    <div class="stats-grid">
      ${statCard("Portfolio Value", money(summary.portfolio_value), `Cash ${money(summary.cash)}`)}
      ${statCard("Buying Power", money(summary.cash), `${summary.holdings_count} active holdings`)}
      ${statCard("Unrealized P/L", signedMoney(summary.unrealized_pl), `${formatSigned(summary.unrealized_pct)}% today`)}
      ${statCard("Rank", `#${summary.rank}`, `${state.market.leaderboard.length} players live`)}
    </div>
    <div class="charts-grid">
      <section class="chart-card">
        <div class="section-head">
          <div>
            <h3>Net Worth Trend</h3>
            <p>Shared market ticks update this chart from server-side history.</p>
          </div>
          <span class="pill">${summary.history.length} points</span>
        </div>
        ${lineChart(summary.history)}
      </section>
      <section class="chart-card">
        <div class="section-head">
          <div>
            <h3>Allocation Mix</h3>
            <p>Current exposure across your live holdings.</p>
          </div>
        </div>
        ${donutChart(summary.allocations)}
      </section>
    </div>
    <div class="page-card">
      <div class="section-head">
        <div>
          <h3>Market Movers</h3>
          <p>Fastest climbers and biggest drops on the shared tape.</p>
        </div>
      </div>
      <div class="leaderboard-list">
        ${state.market.movers.map((stock) => `
          <div class="leader-row">
            <div>
              <strong>${stock.symbol}</strong>
              <div class="metric-delta">${stock.name}</div>
            </div>
            <div class="${stock.change_pct >= 0 ? "positive" : "negative"}">${formatSigned(stock.change_pct)}%</div>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

function renderMarkets() {
  const page = els.views.markets;
  page.innerHTML = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Name</th>
            <th>Sector</th>
            <th>Price</th>
            <th>Change</th>
          </tr>
        </thead>
        <tbody>
          ${state.market.stocks.map((stock) => `
            <tr>
              <td class="mono">${stock.symbol}</td>
              <td>${stock.name}</td>
              <td>${stock.sector}</td>
              <td class="mono">$${stock.price.toFixed(2)}</td>
              <td class="${stock.change_pct >= 0 ? "positive" : "negative"}">${formatSigned(stock.change_pct)}%</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderPortfolio() {
  const page = els.views.portfolio;
  const holdings = state.market.portfolio.holdings;
  page.innerHTML = `
    <div class="portfolio-layout">
      <section class="page-card">
        <div class="section-head">
          <div>
            <h3>Open Positions</h3>
            <p>Holdings are priced from the shared market, not local simulation.</p>
          </div>
        </div>
        <div class="holdings-list">
          ${holdings.length ? holdings.map((holding) => `
            <div class="holding-row">
              <div>
                <strong>${holding.symbol}</strong>
                <div class="metric-delta">${holding.shares.toFixed(2)} shares at avg ${money(holding.avg_cost)}</div>
              </div>
              <div>
                <div>${money(holding.market_value)}</div>
                <div class="${holding.unrealized_pl >= 0 ? "positive" : "negative"}">${signedMoney(holding.unrealized_pl)}</div>
              </div>
            </div>
          `).join("") : '<div class="empty-state">No holdings yet. Head to Trade to place your first order.</div>'}
        </div>
      </section>
      <section class="chart-card">
        <div class="section-head">
          <div>
            <h3>Allocation</h3>
            <p>Your portfolio concentration by position size.</p>
          </div>
        </div>
        ${donutChart(state.market.summary.allocations)}
      </section>
    </div>
  `;
}

function renderTrade() {
  const page = els.views.trade;
  const options = state.market.stocks.map((stock) => `
    <option value="${stock.symbol}">${stock.symbol} - ${stock.name}</option>
  `).join("");
  page.innerHTML = `
    <div class="trade-layout">
      <section class="trade-panel">
        <div class="section-head">
          <div>
            <h3>Place Trade</h3>
            <p>${state.market.market_open ? "Orders execute immediately at the current shared price." : "Market is currently closed. Admin can force-open it."}</p>
          </div>
        </div>
        <form id="trade-form" class="form-row">
          <label>
            Symbol
            <select name="symbol">${options}</select>
          </label>
          <label>
            Shares
            <input type="number" name="shares" min="1" step="1" value="1">
          </label>
          <div class="button-row dual">
            <button type="submit" name="side" value="buy" class="primary-btn">Buy</button>
            <button type="submit" name="side" value="sell" class="danger-btn">Sell</button>
          </div>
        </form>
        <p id="trade-result" class="metric-delta"></p>
      </section>
      <section class="page-card">
        <div class="section-head">
          <div>
            <h3>Quick Snapshot</h3>
            <p>Buying power and open positions for this account.</p>
          </div>
        </div>
        <div class="event-feed">
          <div class="event-row"><span>Cash</span><strong>${money(state.market.summary.cash)}</strong></div>
          <div class="event-row"><span>Portfolio Value</span><strong>${money(state.market.summary.portfolio_value)}</strong></div>
          <div class="event-row"><span>Positions</span><strong>${state.market.summary.holdings_count}</strong></div>
          <div class="event-row"><span>Rank</span><strong>#${state.market.summary.rank}</strong></div>
        </div>
      </section>
    </div>
  `;

  const form = document.getElementById("trade-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    const formData = new FormData(form);
    const result = document.getElementById("trade-result");
    try {
      await request("/trade", {
        method: "POST",
        body: JSON.stringify({
          symbol: formData.get("symbol"),
          side: submitter.value,
          shares: Number(formData.get("shares")),
        }),
      });
      result.textContent = `Order filled: ${submitter.value.toUpperCase()} ${formData.get("shares")} ${formData.get("symbol")}`;
      await refreshState();
    } catch (error) {
      result.textContent = error.message;
    }
  });
}

function renderLeaderboard() {
  const page = els.views.leaderboard;
  page.innerHTML = `
    <div class="leaderboard-layout">
      <section class="page-card">
        <div class="section-head">
          <div>
            <h3>Leaderboard</h3>
            <p>Ranked by total portfolio value across all live accounts.</p>
          </div>
        </div>
        <div class="leaderboard-list">
          ${state.market.leaderboard.map((entry, index) => `
            <div class="leader-row">
              <div>
                <strong>#${index + 1} ${entry.username}</strong>
                <div class="metric-delta">${entry.holdings_count} holdings</div>
              </div>
              <strong>${money(entry.portfolio_value)}</strong>
            </div>
          `).join("")}
        </div>
      </section>
      <section class="chart-card">
        <div class="section-head">
          <div>
            <h3>Top Podium</h3>
            <p>Live top three on the shared market.</p>
          </div>
        </div>
        <div class="leaderboard-list">
          ${state.market.leaderboard.slice(0, 3).map((entry, index) => `
            <div class="leader-row">
              <div>
                <strong>${["Gold", "Silver", "Bronze"][index]}</strong>
                <div class="metric-delta">${entry.username}</div>
              </div>
              <strong>${money(entry.portfolio_value)}</strong>
            </div>
          `).join("")}
        </div>
      </section>
    </div>
  `;
}

function renderHistory() {
  const page = els.views.history;
  const trades = state.market.trade_history;
  page.innerHTML = `
    <div class="page-card">
      <div class="section-head">
        <div>
          <h3>Trade History</h3>
          <p>Your fills, stored server-side and shared across devices after login.</p>
        </div>
      </div>
      <div class="history-list">
        ${trades.length ? trades.map((trade) => `
          <div class="history-row">
            <div>
              <strong>${trade.side.toUpperCase()} ${trade.symbol}</strong>
              <div class="metric-delta">${trade.created_at}</div>
            </div>
            <div>
              <div>${trade.shares} shares</div>
              <div class="mono">${money(trade.price)}</div>
            </div>
          </div>
        `).join("") : '<div class="empty-state">No trades yet.</div>'}
      </div>
    </div>
  `;
}

function renderAdmin() {
  const page = els.views.admin;
  if (!state.me.is_admin) {
    page.innerHTML = '<div class="page-card"><div class="empty-state">Admin access only.</div></div>';
    return;
  }

  page.innerHTML = `
    <div class="admin-grid">
      <section class="admin-card">
        <div class="section-head">
          <div>
            <h3>Announcements</h3>
            <p>Broadcast a site-wide banner instantly.</p>
          </div>
        </div>
        <form id="announce-form" class="admin-form form-row">
          <label>
            Message
            <textarea name="message" placeholder="Market opens early today."></textarea>
          </label>
          <button class="primary-btn" type="submit">Send Announcement</button>
        </form>
      </section>

      <section class="admin-card">
        <div class="section-head">
          <div>
            <h3>Market Override</h3>
            <p>Force the market open for a chosen number of minutes.</p>
          </div>
        </div>
        <form id="market-form" class="admin-form form-row">
          <label>
            Minutes
            <input type="number" name="minutes" min="1" value="15">
          </label>
          <button class="action-btn" type="submit">Force Open Market</button>
        </form>
      </section>

      <section class="admin-card">
        <div class="section-head">
          <div>
            <h3>Bulk Cash Actions</h3>
            <p>Operate on all users at once.</p>
          </div>
        </div>
        <div class="button-row">
          <button class="ghost-btn" data-admin-action="give_500k_all">Give all 500K</button>
          <button class="ghost-btn" data-admin-action="give_10m_all">Give all 10M</button>
          <button class="ghost-btn" data-admin-action="double_cash_all">Double everyone cash</button>
          <button class="ghost-btn" data-admin-action="halve_cash_all">Halve everyone cash</button>
          <button class="ghost-btn" data-admin-action="tax_all_20">Tax everyone 20%</button>
          <button class="danger-btn" data-admin-action="take_all_cash">Take all cash</button>
        </div>
      </section>

      <section class="admin-card">
        <div class="section-head">
          <div>
            <h3>Player Reset</h3>
            <p>Portfolio cleanup tools for all users.</p>
          </div>
        </div>
        <div class="button-row">
          <button class="ghost-btn" data-admin-action="wipe_all_holdings">Wipe all holdings</button>
          <button class="danger-btn" data-admin-action="reset_all_players">Reset all players</button>
          <button class="ghost-btn" data-admin-action="steal_from_richest">Steal from richest non-admin</button>
        </div>
      </section>
    </div>

    <section class="page-card">
      <div class="section-head">
        <div>
          <h3>Users</h3>
          <p>Account list with current balances and status.</p>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>User</th>
              <th>Cash</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${state.market.admin.users.map((user) => `
              <tr>
                <td>${user.username}</td>
                <td>${money(user.cash)}</td>
                <td>${user.banned ? "Banned" : user.is_admin ? "Admin" : "Active"}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </section>
  `;

  const announceForm = document.getElementById("announce-form");
  announceForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(announceForm);
    await request("/admin/announcement", {
      method: "POST",
      body: JSON.stringify({ message: formData.get("message") }),
    });
    await refreshState();
    announceForm.reset();
  });

  const marketForm = document.getElementById("market-form");
  marketForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(marketForm);
    await request("/admin/market-override", {
      method: "POST",
      body: JSON.stringify({ minutes: Number(formData.get("minutes")) }),
    });
    await refreshState();
  });

  page.querySelectorAll("[data-admin-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      await request("/admin/bulk-action", {
        method: "POST",
        body: JSON.stringify({ action: button.dataset.adminAction }),
      });
      await refreshState();
    });
  });
}

function statCard(label, value, detail) {
  return `
    <section class="stat-card">
      <div class="metric-label">${label}</div>
      <div class="metric-value">${value}</div>
      <div class="metric-delta">${detail}</div>
    </section>
  `;
}

function lineChart(points) {
  if (!points.length) {
    return '<div class="empty-state">No chart points yet.</div>';
  }
  const max = Math.max(...points);
  const min = Math.min(...points);
  const range = Math.max(max - min, 1);
  const width = 640;
  const height = 240;
  const coords = points.map((point, index) => {
    const x = (index / Math.max(points.length - 1, 1)) * width;
    const y = height - ((point - min) / range) * (height - 20) - 10;
    return `${x},${y}`;
  }).join(" ");
  return `
    <svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
      <defs>
        <linearGradient id="line-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="rgba(115,167,255,0.45)"></stop>
          <stop offset="100%" stop-color="rgba(115,167,255,0.02)"></stop>
        </linearGradient>
      </defs>
      <polyline fill="none" stroke="#7aa9ff" stroke-width="4" points="${coords}"></polyline>
    </svg>
  `;
}

function donutChart(items) {
  if (!items.length) {
    return '<div class="empty-state">No allocation data yet.</div>';
  }
  const total = items.reduce((sum, item) => sum + item.value, 0) || 1;
  let offset = 0;
  const colors = ["#7aa9ff", "#35d59a", "#ffcf69", "#ff8c72", "#ab8bff", "#59d4ff"];
  const circles = items.map((item, index) => {
    const length = (item.value / total) * 282.743;
    const circle = `
      <circle
        cx="60"
        cy="60"
        r="45"
        fill="transparent"
        stroke="${colors[index % colors.length]}"
        stroke-width="12"
        stroke-dasharray="${length} 282.743"
        stroke-dashoffset="${-offset}"
        transform="rotate(-90 60 60)"
      ></circle>
    `;
    offset += length;
    return circle;
  }).join("");
  const legend = items.map((item, index) => `
    <div class="leader-row">
      <div><strong>${item.label}</strong></div>
      <div style="color:${colors[index % colors.length]}">${money(item.value)}</div>
    </div>
  `).join("");
  return `
    <div class="portfolio-layout">
      <svg viewBox="0 0 120 120" class="chart-svg" style="height:220px">
        ${circles}
        <text x="60" y="58" text-anchor="middle" fill="#eef4ff" font-size="10" font-family="IBM Plex Mono">LIVE</text>
        <text x="60" y="73" text-anchor="middle" fill="#eef4ff" font-size="12" font-family="IBM Plex Mono">ALLOC</text>
      </svg>
      <div class="leaderboard-list">${legend}</div>
    </div>
  `;
}

function money(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value || 0);
}

function signedMoney(value) {
  const prefix = value >= 0 ? "+" : "-";
  return `${prefix}${money(Math.abs(value || 0))}`;
}

function formatSigned(value) {
  const number = Number(value || 0);
  return `${number >= 0 ? "+" : ""}${number.toFixed(2)}`;
}

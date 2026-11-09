/**
 * BANDI Dashboard Client Application v2.0.
 * Zero external JS dependencies. High efficiency, low memory footprint.
 */

let nextEventSeconds = 0;
let isKillSwitchActive = false;

// Clock updates
function updateClocks() {
  const now = new Date();
  const utcStr = now.toISOString().substring(11, 19);
  document.getElementById('utc-clock').textContent = utcStr;

  const sastDate = new Date(now.getTime() + (2 * 3600 * 1000));
  const sastStr = sastDate.toISOString().substring(11, 19);
  document.getElementById('sast-clock').textContent = sastStr;

  if (nextEventSeconds > 0) {
    nextEventSeconds--;
    formatCountdown(nextEventSeconds);
  } else if (nextEventSeconds === 0) {
    document.getElementById('countdown-display').textContent = 'EVENT IMMINENT';
  }
}

function formatCountdown(totalSecs) {
  const d = Math.floor(totalSecs / 86400);
  const h = Math.floor((totalSecs % 86400) / 3600);
  const m = Math.floor((totalSecs % 3600) / 60);
  const s = totalSecs % 60;

  let text = '';
  if (d > 0) {
    text = `${d}d ${String(h).padStart(2, '0')}h ${String(m).padStart(2, '0')}m`;
  } else {
    text = `${String(h).padStart(2, '0')}h ${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`;
  }
  document.getElementById('countdown-display').textContent = text;
}

// -----------------------------------------------------------------------------
// Data Fetching
// -----------------------------------------------------------------------------
async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();

    // Trading Mode KPI
    const modeEl = document.getElementById('trading-mode-val');
    modeEl.textContent = data.trading_mode;
    document.getElementById('select-trading-mode').value = data.trading_mode;

    if (data.trading_mode === 'AUTO') modeEl.className = 'kpi-val text-success';
    else if (data.trading_mode === 'APPROVAL') modeEl.className = 'kpi-val text-info';
    else if (data.trading_mode === 'SIGNALS_ONLY') modeEl.className = 'kpi-val text-warning';
    else modeEl.className = 'kpi-val text-danger';

    // Risk Gate KPI
    const riskEl = document.getElementById('risk-gate-val');
    riskEl.textContent = data.trading_locked ? 'LOCKED (Read-Only)' : 'UNLOCKED';
    riskEl.className = data.trading_locked ? 'kpi-val text-info' : 'kpi-val text-warning';

    // Kill switch button
    isKillSwitchActive = data.kill_switch_active;
    const ksBtn = document.getElementById('btn-kill-switch');
    if (isKillSwitchActive) {
      ksBtn.className = 'btn btn-danger';
      ksBtn.innerHTML = '<span>🚨</span> Kill Switch: ACTIVE (Click to Resume)';
    } else {
      ksBtn.className = 'btn btn-outline';
      ksBtn.innerHTML = '<span>🛡️</span> Kill Switch: OFF';
    }

    // MT5 KPI
    const mt5El = document.getElementById('mt5-status-val');
    const mt5Sub = document.getElementById('mt5-status-sub');
    if (data.mt5.connected) {
      mt5El.textContent = 'CONNECTED';
      mt5El.className = 'kpi-val text-success';
      const acct = data.mt5.account;
      mt5Sub.textContent = `Acct #${acct.login} [${acct.trade_mode}] (${acct.broker})`;
    } else {
      mt5El.textContent = 'MONITORING';
      mt5El.className = 'kpi-val text-warning';
      mt5Sub.textContent = 'Bandi.ex5 Compiled & Ready';
    }
  } catch (err) {
    console.error('Failed to fetch status:', err);
  }
}

async function fetchSignalsAndDecisions() {
  try {
    // Signals
    const sigRes = await fetch('/api/signals');
    const sigData = await sigRes.json();
    const sigTbody = document.getElementById('signals-tbody');

    if (sigData.signals.length === 0) {
      sigTbody.innerHTML = '<tr><td colspan="11" class="text-center">No active signals waiting for approval.</td></tr>';
    } else {
      sigTbody.innerHTML = sigData.signals.map(s => `
        <tr>
          <td><code>${s.signal_id}</code></td>
          <td><strong>${s.symbol}</strong></td>
          <td>${s.timeframe}</td>
          <td><span class="badge ${s.direction === 'BUY' ? 'badge-currency' : 'badge-alert'}">${s.direction}</span></td>
          <td>${s.entry_price.toFixed(5)}</td>
          <td>${s.sl.toFixed(5)}</td>
          <td>${s.tp.toFixed(5)}</td>
          <td>1:${s.rr.toFixed(1)}</td>
          <td>${s.confidence.toFixed(0)}%</td>
          <td><span class="text-warning">${s.status}</span></td>
          <td>
            <button class="btn btn-primary" style="padding:4px 8px; font-size:11px;" onclick="approveSignal('${s.signal_id}')">Approve</button>
            <button class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="skipSignal('${s.signal_id}')">Skip</button>
          </td>
        </tr>
      `).join('');
    }

    // Decisions
    const decRes = await fetch('/api/decisions?limit=30');
    const decData = await decRes.json();
    const decTbody = document.getElementById('decisions-tbody');

    if (decData.decisions.length === 0) {
      decTbody.innerHTML = '<tr><td colspan="6" class="text-center">No decisions recorded yet.</td></tr>';
    } else {
      decTbody.innerHTML = decData.decisions.map(d => {
        const cls = d.action === 'TRADE' ? 'text-success' : (d.action === 'WATCH' ? 'text-info' : 'text-danger');
        return `
          <tr>
            <td><code>${d.decision_id}</code></td>
            <td><strong>${d.symbol}</strong></td>
            <td><strong class="${cls}">[${d.action}]</strong></td>
            <td>${d.risk_checks_passed ? '✅ Pass' : '❌ Reject'}</td>
            <td>${d.lot_size ? d.lot_size.toFixed(2) : '--'}</td>
            <td>${d.reasons.join(' | ')}</td>
          </tr>
        `;
      }).join('');
    }
  } catch (err) {
    console.error('Failed to fetch signals/decisions:', err);
  }
}

async function fetchPositionsAndPerformance() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    const tbody = document.getElementById('positions-tbody');

    const positions = data.mt5.open_positions || [];
    if (positions.length === 0) {
      tbody.innerHTML = '<tr><td colspan="9" class="text-center">No open positions currently in MT5.</td></tr>';
    } else {
      tbody.innerHTML = positions.map(p => `
        <tr>
          <td><code>#${p.ticket}</code></td>
          <td><strong>${p.symbol}</strong></td>
          <td><span class="badge ${p.type === 'BUY' ? 'badge-currency' : 'badge-alert'}">${p.type}</span></td>
          <td>${p.volume}</td>
          <td>${p.price_open}</td>
          <td>${p.price_current}</td>
          <td>${p.sl}</td>
          <td>${p.tp}</td>
          <td class="${p.profit >= 0 ? 'text-success' : 'text-danger'}"><strong>$${p.profit.toFixed(2)}</strong></td>
        </tr>
      `).join('');
    }

    // Performance
    const perfRes = await fetch('/api/performance');
    const perf = await perfRes.json();

    document.getElementById('stat-winrate').textContent = `${perf.win_rate_pct}%`;
    document.getElementById('stat-pf').textContent = perf.profit_factor;
    document.getElementById('stat-avgr').textContent = `${perf.average_r}R`;
    document.getElementById('stat-total').textContent = perf.total_trades;
    document.getElementById('perf-winrate-val').textContent = `${perf.win_rate_pct}% Win Rate`;
    document.getElementById('perf-metrics-sub').textContent = `PF: ${perf.profit_factor} | Avg R: ${perf.average_r}R | Net: $${perf.net_pnl}`;
  } catch (err) {
    console.error('Failed to fetch positions/perf:', err);
  }
}

async function fetchFundamentalBias() {
  try {
    const res = await fetch('/api/research/overview');
    const data = await res.json();
    const tbody = document.getElementById('bias-tbody');

    const biases = data.fundamental_biases || {};
    const keys = Object.keys(biases);

    if (keys.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center">No fundamental biases loaded.</td></tr>';
      return;
    }

    tbody.innerHTML = keys.map(sym => {
      const b = biases[sym];
      const isBull = b.bias_value > 0;
      const cls = isBull ? 'badge-currency' : 'badge-alert';
      return `
        <tr>
          <td><strong>${sym}</strong></td>
          <td><span class="badge ${cls}">${b.bias_label}</span></td>
          <td><strong>${b.bias_value > 0 ? '+' : ''}${b.bias_value}</strong></td>
          <td>${b.central_bank_score > 0 ? '+' : ''}${b.central_bank_score}</td>
          <td>${b.contributing_events.map(e => e.title).join(', ') || 'Central bank baseline'}</td>
          <td><code>${b.updated_at_utc.substring(11, 19)} UTC</code></td>
        </tr>
      `;
    }).join('');

    // Strength Matrix
    const strEl = document.getElementById('strength-container');
    const strength = data.currency_strength;
    if (strength && strength.ranking) {
      strEl.innerHTML = strength.ranking.map(item => {
        const pct = (item.score / 10.0) * 100.0;
        return `
          <div class="strength-card">
            <div style="font-weight: 700; font-size: 14px;">${item.currency}</div>
            <div class="strength-score text-info">${item.score.toFixed(1)}</div>
            <div class="strength-bar">
              <div class="strength-fill" style="width: ${pct}%;"></div>
            </div>
          </div>
        `;
      }).join('');
    }
  } catch (err) {
    console.error('Failed to fetch fundamental bias:', err);
  }
}

async function fetchNextEvent() {
  try {
    const res = await fetch('/api/calendar/next');
    const data = await res.json();

    if (data.has_event && data.event) {
      const ev = data.event;
      nextEventSeconds = data.seconds_remaining;
      document.getElementById('next-release-title').textContent = ev.title;
      document.getElementById('next-release-currency').textContent = ev.currency;
      document.getElementById('next-release-time').textContent = ev.release_time_sast;
      document.getElementById('next-release-why').textContent = ev.why_it_matters || 'High impact macroeconomic indicator.';

      const insts = ev.affected_instruments;
      document.getElementById('next-release-instruments').textContent = Array.isArray(insts) ? insts.join(', ') : insts;
      formatCountdown(nextEventSeconds);
    } else {
      document.getElementById('next-release-title').textContent = 'No high-impact events in next 7 days.';
      document.getElementById('countdown-display').textContent = 'ALL CLEAR';
      nextEventSeconds = 0;
    }
  } catch (err) {
    console.error('Failed to fetch next event:', err);
  }
}

async function fetchCalendar() {
  try {
    const highImpactOnly = document.getElementById('filter-high-impact').checked;
    const url = `/api/calendar/events?impact=${highImpactOnly ? 'high' : ''}&limit=100`;
    const res = await fetch(url);
    const data = await res.json();

    const tbody = document.getElementById('calendar-tbody');
    if (data.events.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center">No scheduled events found for this filter.</td></tr>';
      return;
    }

    const search = document.getElementById('search-events').value.toLowerCase();
    const filtered = data.events.filter(e => {
      if (!search) return true;
      return e.title.toLowerCase().includes(search) || e.currency.toLowerCase().includes(search);
    });

    tbody.innerHTML = filtered.map(ev => {
      const isHigh = ev.impact.toLowerCase() === 'high';
      const badgeCls = isHigh ? 'badge-alert' : 'badge-currency';
      const remMins = ev.minutes_remaining;
      const remText = remMins > 0 ? `In ~${Math.round(remMins / 60)}h ${Math.round(remMins % 60)}m` : 'Completed';

      return `
        <tr>
          <td><code>${ev.release_time_sast}</code></td>
          <td><strong>${ev.currency}</strong></td>
          <td><span class="badge ${badgeCls}">${ev.impact.toUpperCase()}</span></td>
          <td>
            <strong>${ev.title}</strong>
            <div style="font-size: 11px; color: var(--text-dim);">${ev.why_it_matters || ''}</div>
          </td>
          <td>${ev.forecast || '--'}</td>
          <td>${ev.previous || '--'}</td>
          <td><code>${Array.isArray(ev.affected_instruments) ? ev.affected_instruments.join(', ') : ''}</code></td>
          <td>${remText}</td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to fetch calendar:', err);
  }
}

async function fetchNotifications() {
  try {
    const res = await fetch('/api/notifications');
    const data = await res.json();
    const tbody = document.getElementById('alerts-tbody');

    if (data.notifications.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center">No notifications dispatched yet.</td></tr>';
      return;
    }

    tbody.innerHTML = data.notifications.map(n => {
      const isLate = n.status === 'late';
      const statusCls = n.status === 'sent' ? 'text-success' : (isLate ? 'text-warning' : 'text-danger');
      return `
        <tr>
          <td>#${n.id}</td>
          <td><code>${n.sent_time_sast}</code></td>
          <td><span class="${statusCls}"><strong>${n.status.toUpperCase()}</strong></span></td>
          <td>${n.event_title}</td>
          <td>~${n.minutes_before} min prior</td>
          <td>${n.channel} (${n.recipient || 'N/A'})</td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to fetch notifications:', err);
  }
}

async function fetchWatchlist() {
  try {
    const res = await fetch('/api/watchlist');
    const data = await res.json();
    const cardsEl = document.getElementById('watchlist-cards');

    cardsEl.innerHTML = data.symbols.map(s => {
      const hasQuote = s.bid > 0;
      return `
        <div class="symbol-card">
          <div class="symbol-header">
            <span class="symbol-title">${s.symbol}</span>
            <span class="badge ${s.bias_value >= 0 ? 'badge-currency' : 'badge-alert'}">${s.bias_label}</span>
          </div>
          <div style="font-size: 12px; color: var(--text-muted);">${s.name}</div>
          <div class="symbol-prices">
            <span>Bid: <strong>${hasQuote ? s.bid.toFixed(5) : '--'}</strong></span>
            <span>Ask: <strong>${hasQuote ? s.ask.toFixed(5) : '--'}</strong></span>
          </div>
          <div class="symbol-spread">
            Spread: <strong>${hasQuote ? s.spread_points + ' pts' : 'Awaiting tick'}</strong>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to fetch watchlist:', err);
  }
}

async function fetchLogs() {
  try {
    const res = await fetch('/api/logs?limit=30');
    const data = await res.json();
    const tbody = document.getElementById('logs-tbody');

    if (data.logs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center">No logs recorded.</td></tr>';
      return;
    }

    tbody.innerHTML = data.logs.map(l => {
      const cls = l.level === 'ERROR' ? 'text-danger' : (l.level === 'WARNING' ? 'text-warning' : 'text-info');
      return `
        <tr>
          <td>#${l.id}</td>
          <td><code>${l.created_at_utc.substring(11, 19)}</code></td>
          <td><span class="${cls}"><strong>${l.level}</strong></span></td>
          <td><code>${l.component}</code></td>
          <td>${l.message}</td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to fetch logs:', err);
  }
}

// -----------------------------------------------------------------------------
// Interactive Action Handlers
// -----------------------------------------------------------------------------
async function approveSignal(sigId) {
  try {
    const res = await fetch(`/api/signals/${sigId}/approve`, { method: 'POST' });
    const data = await res.json();
    alert(`✅ Signal approved! Queued order #${data.order_id} for MT5 EA.`);
    fetchSignalsAndDecisions();
  } catch (e) {
    alert('Error approving signal: ' + e);
  }
}

async function skipSignal(sigId) {
  try {
    await fetch(`/api/signals/${sigId}/skip`, { method: 'POST' });
    alert(`❌ Signal #${sigId} marked as skipped.`);
    fetchSignalsAndDecisions();
  } catch (e) {
    alert('Error skipping signal: ' + e);
  }
}

function setupActions() {
  // Kill switch
  document.getElementById('btn-kill-switch').addEventListener('click', async () => {
    const newState = !isKillSwitchActive;
    try {
      const res = await fetch('/api/kill-switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: newState })
      });
      const data = await res.json();
      isKillSwitchActive = data.kill_switch_active;
      fetchStatus();
      alert(`Kill Switch is now: ${isKillSwitchActive ? 'ACTIVE (Trading Halted)' : 'OFF (Normal Operation)'}`);
    } catch (e) {
      alert('Error updating kill switch: ' + e);
    }
  });

  // Trading mode selector
  document.getElementById('select-trading-mode').addEventListener('change', async (e) => {
    const mode = e.target.value;
    try {
      const res = await fetch('/api/trading-mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: mode, confirmed: true })
      });
      if (res.ok) {
        alert(`Trading mode updated to [${mode}]`);
      } else {
        const err = await res.json();
        alert('Cannot change mode: ' + err.detail);
      }
      fetchStatus();
    } catch (err) {
      alert('Error updating mode: ' + err);
    }
  });

  // Telegram Test
  document.getElementById('btn-test-tg').addEventListener('click', async () => {
    const btn = document.getElementById('btn-test-tg');
    btn.disabled = true;
    btn.textContent = 'Sending...';
    try {
      const res = await fetch('/api/telegram/test', { method: 'POST' });
      const data = await res.json();
      if (data.ok) alert('✅ Telegram Alert Test Delivered Successfully!');
      else alert('❌ Telegram Alert Failed: ' + (data.error || 'Unknown error'));
    } catch (e) {
      alert('Network error connecting to backend: ' + e);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>🔔</span> Test Telegram';
      fetchNotifications();
    }
  });

  // Calendar Sync
  document.getElementById('btn-sync-cal').addEventListener('click', async () => {
    const btn = document.getElementById('btn-sync-cal');
    btn.disabled = true;
    btn.textContent = 'Syncing...';
    try {
      const res = await fetch('/api/calendar/sync', { method: 'POST' });
      const data = await res.json();
      alert(`🔄 Calendar Sync: ${data.status.toUpperCase()} (Synced ${data.count} events)`);
      fetchCalendar();
      fetchNextEvent();
    } catch (e) {
      alert('Error syncing calendar: ' + e);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>🔄</span> Sync Calendar';
    }
  });

  // Compile EA
  document.getElementById('btn-compile-ea').addEventListener('click', async () => {
    const btn = document.getElementById('btn-compile-ea');
    btn.disabled = true;
    btn.textContent = 'Compiling...';
    try {
      const res = await fetch('/api/mt5/compile', { method: 'POST' });
      const data = await res.json();
      if (data.ok) alert(`⚡ Compilation Complete! Bandi.ex5 generated across ${data.terminals_processed} MT5 terminals.`);
      else alert('Compilation Notice: ' + (data.error || 'Check MT5 directory settings'));
    } catch (e) {
      alert('Error triggering compiler: ' + e);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>⚡</span> Compile MT5 EA';
    }
  });

  // Filters
  document.getElementById('filter-high-impact').addEventListener('change', fetchCalendar);
  document.getElementById('search-events').addEventListener('input', fetchCalendar);

  // Tabs
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const tabId = btn.getAttribute('data-tab');
      document.getElementById(`tab-${tabId}`).classList.add('active');

      if (tabId === 'signals') fetchSignalsAndDecisions();
      if (tabId === 'positions') fetchPositionsAndPerformance();
      if (tabId === 'bias') fetchFundamentalBias();
      if (tabId === 'calendar') fetchCalendar();
      if (tabId === 'alerts') fetchNotifications();
      if (tabId === 'watchlist') fetchWatchlist();
      if (tabId === 'logs') fetchLogs();
    });
  });
}

// Initial Boot
document.addEventListener('DOMContentLoaded', () => {
  setInterval(updateClocks, 1000);
  updateClocks();
  setupActions();

  // Load active tab data
  fetchStatus();
  fetchSignalsAndDecisions();
  fetchPositionsAndPerformance();
  fetchFundamentalBias();
  fetchCalendar();
  fetchNotifications();
  fetchWatchlist();
  fetchLogs();

  // Background polling every 8 seconds
  setInterval(() => {
    fetchStatus();
    fetchNextEvent();
    fetchPositionsAndPerformance();
  }, 8000);
});

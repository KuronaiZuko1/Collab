/**
 * BANDI Dashboard Client Application.
 * Zero external JS dependencies. High efficiency, low memory footprint.
 */

let nextEventSeconds = 0;
let nextEventTimerInterval = null;

// Clock updates
function updateClocks() {
  const now = new Date();
  // UTC Time
  const utcStr = now.toISOString().substring(11, 19);
  document.getElementById('utc-clock').textContent = utcStr;

  // SAST Time is UTC + 2
  const sastDate = new Date(now.getTime() + (2 * 3600 * 1000));
  const sastStr = sastDate.toISOString().substring(11, 19);
  document.getElementById('sast-clock').textContent = sastStr;

  // Tick countdown timer
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

    // Telegram KPI
    const tgEl = document.getElementById('tg-status-val');
    const tgSub = document.getElementById('tg-status-sub');
    if (data.telegram.connected) {
      tgEl.textContent = 'ONLINE';
      tgEl.className = 'kpi-val text-success';
      tgSub.textContent = `@${data.telegram.username} (${data.telegram.chat_id})`;
    } else {
      tgEl.textContent = 'OFFLINE';
      tgEl.className = 'kpi-val text-danger';
      tgSub.textContent = data.telegram.details.error || 'Token unverified';
    }

    // MT5 KPI
    const mt5El = document.getElementById('mt5-status-val');
    const mt5Sub = document.getElementById('mt5-status-sub');
    if (data.mt5.connected) {
      mt5El.textContent = 'CONNECTED';
      mt5El.className = 'kpi-val text-success';
      mt5Sub.textContent = `Acct #${data.mt5.account.login} (${data.mt5.account.broker})`;
    } else {
      mt5El.textContent = 'MONITORING';
      mt5El.className = 'kpi-val text-warning';
      mt5Sub.textContent = 'Bandi.ex5 Compiled & Ready';
    }
  } catch (err) {
    console.error('Failed to fetch status:', err);
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

    document.getElementById('total-events-val').textContent = data.count;

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
            <span class="badge badge-currency">${s.asset_class}</span>
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

async function fetchResearch() {
  try {
    const res = await fetch('/api/research/overview');
    const data = await res.json();

    // Theses
    document.getElementById('thesis-gold').textContent = data.macro.gold_macro_thesis;
    document.getElementById('thesis-equities').textContent = data.macro.equities_macro_thesis;

    // Macro Cards
    const macroEl = document.getElementById('macro-cards');
    macroEl.innerHTML = data.macro.regions.map(r => `
      <div class="macro-card">
        <h4>${r.currency} — ${r.region}</h4>
        <div class="macro-facts">
          <strong>Confirmed Empirical Facts:</strong><br>
          ${r.confirmed_facts}
        </div>
        <div class="macro-interp">
          <strong>Deterministic Assessment:</strong><br>
          ${r.interpretation}
        </div>
      </div>
    `).join('');

    // Strength Matrix
    const strEl = document.getElementById('strength-container');
    const strength = data.currency_strength;
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
  } catch (err) {
    console.error('Failed to fetch research:', err);
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

async function fetchJournal() {
  try {
    const res = await fetch('/api/journal');
    const data = await res.json();
    const listEl = document.getElementById('journal-list');

    if (data.journal.length === 0) {
      listEl.innerHTML = '<div style="color: var(--text-dim); font-size: 13px;">No journal entries recorded yet.</div>';
      return;
    }

    listEl.innerHTML = data.journal.map(j => `
      <div class="journal-item">
        <div class="journal-item-header">
          <strong>${j.symbol} — ${j.action}</strong>
          <span style="font-size: 11px; color: var(--text-dim);">${j.created_at_utc.substring(0, 19)} UTC</span>
        </div>
        <div style="font-size: 12px; color: var(--amber);">${j.economic_context || ''}</div>
        <div style="font-size: 13px; margin-top: 4px;">${j.strategy_reason || ''}</div>
      </div>
    `).join('');
  } catch (err) {
    console.error('Failed to fetch journal:', err);
  }
}

// -----------------------------------------------------------------------------
// Action Handlers
// -----------------------------------------------------------------------------
function setupActions() {
  // Telegram Test
  document.getElementById('btn-test-tg').addEventListener('click', async () => {
    const btn = document.getElementById('btn-test-tg');
    btn.disabled = true;
    btn.textContent = 'Sending...';
    try {
      const res = await fetch('/api/telegram/test', { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        alert('✅ Telegram Alert Test Delivered Successfully! Check your Telegram chat.');
      } else {
        alert('❌ Telegram Alert Failed: ' + (data.error || 'Unknown error'));
      }
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
      if (data.ok) {
        alert(`⚡ Compilation Complete! Bandi.ex5 generated across ${data.terminals_processed} MT5 terminals.`);
      } else {
        alert('Compilation Notice: ' + (data.error || 'Check MT5 directory settings'));
      }
    } catch (e) {
      alert('Error triggering compiler: ' + e);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>⚡</span> Compile MT5 EA';
    }
  });

  // Filter events
  document.getElementById('filter-high-impact').addEventListener('change', fetchCalendar);
  document.getElementById('search-events').addEventListener('input', fetchCalendar);

  // Journal form
  document.getElementById('journal-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      symbol: document.getElementById('j-symbol').value,
      action: document.getElementById('j-action').value,
      economic_context: document.getElementById('j-context').value,
      strategy_reason: document.getElementById('j-reason').value
    };
    try {
      await fetch('/api/journal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      document.getElementById('j-context').value = '';
      document.getElementById('j-reason').value = '';
      fetchJournal();
    } catch (err) {
      alert('Failed to save journal note: ' + err);
    }
  });

  // Tab switching
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const tabId = btn.getAttribute('data-tab');
      document.getElementById(`tab-${tabId}`).classList.add('active');

      if (tabId === 'calendar') fetchCalendar();
      if (tabId === 'alerts') fetchNotifications();
      if (tabId === 'watchlist') fetchWatchlist();
      if (tabId === 'research') fetchResearch();
      if (tabId === 'journal') fetchJournal();
      if (tabId === 'logs') fetchLogs();
    });
  });
}

// Initial Boot
document.addEventListener('DOMContentLoaded', () => {
  setInterval(updateClocks, 1000);
  updateClocks();
  setupActions();

  // Load all tabs
  fetchStatus();
  fetchNextEvent();
  fetchCalendar();
  fetchNotifications();
  fetchWatchlist();
  fetchResearch();
  fetchJournal();
  fetchLogs();

  // Background refresh every 15 seconds
  setInterval(() => {
    fetchStatus();
    fetchNextEvent();
    fetchWatchlist();
  }, 15000);
});

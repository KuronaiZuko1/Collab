"""
SQLite Database Schema and Versioning for BANDI.
Defines all tables for economic events, notifications, research, journal, snapshots,
logs, candles, event scores, fundamental bias, signals, decisions, orders, and trade results.
"""

SCHEMA_VERSION = 2

CREATE_TABLES_SQL = """
-- Version Tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at_utc TEXT NOT NULL
);

-- 1. Economic Events
CREATE TABLE IF NOT EXISTS economic_events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    country TEXT,
    currency TEXT NOT NULL,
    impact TEXT NOT NULL,
    event_time_utc TEXT NOT NULL,
    event_ts INTEGER NOT NULL,
    forecast TEXT,
    previous TEXT,
    actual TEXT,
    status TEXT NOT NULL DEFAULT 'scheduled',
    moved_from TEXT,
    period TEXT,
    source TEXT NOT NULL,
    retrieval_time_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    affected_instruments TEXT,
    why_it_matters TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON economic_events(event_ts);
CREATE INDEX IF NOT EXISTS idx_events_impact ON economic_events(impact);
CREATE INDEX IF NOT EXISTS idx_events_currency ON economic_events(currency);

-- 2. Notification History (with duplicate prevention constraint)
CREATE TABLE IF NOT EXISTS notification_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    event_title TEXT NOT NULL,
    event_time_utc TEXT NOT NULL,
    channel TEXT NOT NULL,
    recipient TEXT,
    status TEXT NOT NULL,
    message_content TEXT,
    sent_at_utc TEXT NOT NULL,
    sent_ts INTEGER NOT NULL,
    minutes_before REAL,
    error_message TEXT,
    UNIQUE(event_id, channel)
);
CREATE INDEX IF NOT EXISTS idx_notifications_event ON notification_history(event_id);
CREATE INDEX IF NOT EXISTS idx_notifications_sent_ts ON notification_history(sent_ts);

-- 3. News Articles
CREATE TABLE IF NOT EXISTS news_articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    url TEXT,
    source TEXT NOT NULL,
    summary TEXT,
    published_at_utc TEXT,
    sentiment TEXT,
    related_symbols TEXT,
    created_at_utc TEXT NOT NULL
);

-- 4. Fundamental Market Research
CREATE TABLE IF NOT EXISTS market_research (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    subject TEXT NOT NULL,
    analysis_text TEXT NOT NULL,
    confirmed_facts TEXT,
    interpretation TEXT,
    confidence_score REAL DEFAULT 1.0,
    is_data_sufficient INTEGER DEFAULT 1,
    created_at_utc TEXT NOT NULL
);

-- 5. Market Snapshots & Broker Quotes
CREATE TABLE IF NOT EXISTS market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    bid REAL NOT NULL,
    ask REAL NOT NULL,
    spread_points REAL NOT NULL,
    snapshot_time_utc TEXT NOT NULL,
    snapshot_ts INTEGER NOT NULL,
    source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_sym_ts ON market_snapshots(symbol, snapshot_ts);

-- 6. Trading Journal
CREATE TABLE IF NOT EXISTS trading_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket INTEGER,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    volume REAL,
    price REAL,
    sl REAL,
    tp REAL,
    pnl REAL,
    strategy_reason TEXT,
    economic_context TEXT,
    risk_assessment TEXT,
    created_at_utc TEXT NOT NULL
);

-- 7. Application Settings
CREATE TABLE IF NOT EXISTS application_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

-- 8. System Logs
CREATE TABLE IF NOT EXISTS system_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    component TEXT NOT NULL,
    message TEXT NOT NULL,
    details TEXT,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_created ON system_logs(id DESC);

-- ============================================================================
-- V2 TRADING ENGINE TABLES
-- ============================================================================

-- 9. Candle Historical & Streaming Data
CREATE TABLE IF NOT EXISTS candles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    candle_time_utc TEXT NOT NULL,
    candle_ts INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL DEFAULT 0.0,
    UNIQUE(symbol, timeframe, candle_ts)
);
CREATE INDEX IF NOT EXISTS idx_candles_lookup ON candles(symbol, timeframe, candle_ts DESC);

-- 10. Economic Event Surprise Scores
CREATE TABLE IF NOT EXISTS event_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    currency TEXT NOT NULL,
    actual REAL,
    forecast REAL,
    previous REAL,
    raw_surprise REAL,
    normalized_surprise REAL,
    direction_score REAL,
    event_time_utc TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_event_scores_ccy ON event_scores(currency, event_time_utc);

-- 11. Fundamental Bias per Symbol
CREATE TABLE IF NOT EXISTS fundamental_bias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    bias_value REAL NOT NULL,
    bias_label TEXT NOT NULL,
    contributing_events TEXT,
    central_bank_score REAL DEFAULT 0.0,
    updated_at_utc TEXT NOT NULL
);

-- 12. Trade Signals Generated by Strategy
CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    sl REAL NOT NULL,
    tp REAL NOT NULL,
    rr REAL NOT NULL,
    confidence REAL NOT NULL,
    reasons TEXT NOT NULL,
    fundamental_bias TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    expiry_ts INTEGER NOT NULL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status, expiry_ts);

-- 13. Decision Audit Log (Every trade, watch, or skip decision)
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL UNIQUE,
    signal_id TEXT,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    reasons TEXT NOT NULL,
    risk_checks_passed INTEGER NOT NULL,
    lot_size REAL,
    equity REAL,
    created_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_created ON decisions(id DESC);

-- 14. Order Management Records
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    signal_id TEXT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    volume REAL NOT NULL,
    entry_price REAL,
    sl REAL NOT NULL,
    tp REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    ticket INTEGER,
    error_message TEXT,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

-- 15. Live Open Positions
CREATE TABLE IF NOT EXISTS positions (
    ticket INTEGER PRIMARY KEY,
    order_id TEXT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    volume REAL NOT NULL,
    open_price REAL NOT NULL,
    sl REAL NOT NULL,
    tp REAL NOT NULL,
    current_price REAL,
    profit REAL,
    be_moved INTEGER DEFAULT 0,
    open_time_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

-- 16. Closed Trade Results & Performance Audit
CREATE TABLE IF NOT EXISTS trade_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    volume REAL NOT NULL,
    open_price REAL NOT NULL,
    close_price REAL NOT NULL,
    sl REAL,
    tp REAL,
    pnl REAL NOT NULL,
    r_multiple REAL NOT NULL,
    close_reason TEXT NOT NULL,
    open_time_utc TEXT NOT NULL,
    close_time_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trade_results_sym ON trade_results(symbol, close_time_utc);
"""

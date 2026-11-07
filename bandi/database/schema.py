"""
SQLite Database Schema and Versioning for BANDI.
Defines all tables for economic events, notifications, research, journal, snapshots, and logs.
"""

SCHEMA_VERSION = 1

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
"""

"""
Configuration management for BANDI.
Loads environment variables from .env with fallback defaults.
Ensures directories exist and exposes timezone-aware time utilities.
"""

from __future__ import annotations
import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List
from dotenv import load_dotenv

logger = logging.getLogger("bandi.config")

# Safe timezone import
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore

# Resolve root workspace path
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env if present
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, override=True)


def get_display_timezone(name: str):
    """Safely obtain timezone with SAST (UTC+2) fallback."""
    if ZoneInfo:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    # Fallback to standard fixed offset SAST (+02:00)
    return timezone(timedelta(hours=2), name="SAST")


class Settings:
    # -------------------------------------------------------------------------
    # Application details
    # -------------------------------------------------------------------------
    APP_NAME: str = os.getenv("APP_NAME", "BANDI")
    APP_ENV: str = os.getenv("APP_ENV", "production")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    # File paths
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    LOGS_DIR: Path = BASE_DIR / "logs"
    DATABASE_PATH: Path = BASE_DIR / os.getenv("DATABASE_PATH", "data/bandi.db")
    KILL_SWITCH_FILE: Path = BASE_DIR / "data" / "kill_switch.flag"

    # Timezone settings (SAST Africa/Johannesburg UTC+2)
    DISPLAY_TIMEZONE_NAME: str = os.getenv("DISPLAY_TIMEZONE", "Africa/Johannesburg")
    DISPLAY_TIMEZONE = get_display_timezone(DISPLAY_TIMEZONE_NAME)

    # -------------------------------------------------------------------------
    # Telegram
    # -------------------------------------------------------------------------
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    TELEGRAM_ENABLED: bool = os.getenv("TELEGRAM_ENABLED", "true").lower() in ("true", "1", "yes")

    # -------------------------------------------------------------------------
    # Economic Calendar Engine
    # -------------------------------------------------------------------------
    CALENDAR_API_URL: str = os.getenv(
        "CALENDAR_API_URL", "https://showmytrades.com/api/public/calendar/v1"
    ).strip()
    CALENDAR_POLL_INTERVAL_MINUTES: int = max(15, int(os.getenv("CALENDAR_POLL_INTERVAL_MINUTES", "15")))
    CALENDAR_RANGE_DAYS: int = int(os.getenv("CALENDAR_RANGE_DAYS", "7"))

    # Alert Timing
    ALERT_MINUTES_BEFORE: int = int(os.getenv("ALERT_MINUTES_BEFORE", "30"))
    LATE_ALERT_WINDOW_MINUTES: int = int(os.getenv("LATE_ALERT_WINDOW_MINUTES", "25"))
    SCHEDULER_CHECK_INTERVAL_SECONDS: int = int(os.getenv("SCHEDULER_CHECK_INTERVAL_SECONDS", "15"))

    # -------------------------------------------------------------------------
    # MetaTrader 5 Integration
    # -------------------------------------------------------------------------
    MT5_ENABLED: bool = os.getenv("MT5_ENABLED", "true").lower() in ("true", "1", "yes")
    MT5_TERMINAL_PATH: str = os.getenv(
        "MT5_TERMINAL_PATH", r"C:\Program Files\JustMarkets MetaTrader 5\terminal64.exe"
    )
    MT5_METAEDITOR_PATH: str = os.getenv(
        "MT5_METAEDITOR_PATH", r"C:\Program Files\JustMarkets MetaTrader 5\MetaEditor64.exe"
    )
    MT5_DEMO_MODE: bool = os.getenv("MT5_DEMO_MODE", "true").lower() in ("true", "1", "yes")

    # -------------------------------------------------------------------------
    # Trading Mode & Safety Control
    # Modes: OFF | SIGNALS_ONLY | APPROVAL | AUTO
    # -------------------------------------------------------------------------
    TRADING_MODE: str = os.getenv("TRADING_MODE", "OFF").upper().strip()
    LIVE_TRADING_CONFIRMED: bool = os.getenv("LIVE_TRADING_CONFIRMED", "false").lower() in ("true", "1", "yes")
    RISK_TRADING_LOCKED: bool = os.getenv("RISK_TRADING_LOCKED", "true").lower() in ("true", "1", "yes")

    # -------------------------------------------------------------------------
    # Risk Management Parameters
    # -------------------------------------------------------------------------
    RISK_PER_TRADE_PCT: float = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
    MAX_LOT: float = float(os.getenv("MAX_LOT", "1.0"))
    MIN_RR: float = float(os.getenv("MIN_RR", "1.5"))
    RISK_MAX_DAILY_DRAWDOWN_PCT: float = float(os.getenv("RISK_MAX_DAILY_DRAWDOWN_PCT", "3.0"))
    WEEKLY_LOSS_LIMIT_PCT: float = float(os.getenv("WEEKLY_LOSS_LIMIT_PCT", "6.0"))
    MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
    RISK_MAX_OPEN_POSITIONS: int = int(os.getenv("RISK_MAX_OPEN_POSITIONS", "5"))
    RISK_MAX_SPREAD_POINTS: int = int(os.getenv("RISK_MAX_SPREAD_POINTS", "30"))
    MAX_TRADES_PER_DAY: int = int(os.getenv("MAX_TRADES_PER_DAY", "3"))
    MAX_CORRELATED_USD_POSITIONS: int = int(os.getenv("MAX_CORRELATED_USD_POSITIONS", "2"))

    # -------------------------------------------------------------------------
    # Strategy & Filters
    # -------------------------------------------------------------------------
    NEWS_BLACKOUT_BEFORE_MIN: int = int(os.getenv("NEWS_BLACKOUT_BEFORE_MIN", "30"))
    NEWS_BLACKOUT_AFTER_MIN: int = int(os.getenv("NEWS_BLACKOUT_AFTER_MIN", "15"))
    ALLOWED_SESSIONS: str = os.getenv("ALLOWED_SESSIONS", "London,New York")
    SIGNAL_EXPIRY_MIN: int = int(os.getenv("SIGNAL_EXPIRY_MIN", "120"))
    MAGIC_NUMBER: int = int(os.getenv("MAGIC_NUMBER", "202611"))
    ATR_PERIOD: int = int(os.getenv("ATR_PERIOD", "14"))
    STRATEGY_TIMEFRAMES: str = os.getenv("STRATEGY_TIMEFRAMES", "M15,H1,H4,D1")

    # -------------------------------------------------------------------------
    # GitHub Integration
    # -------------------------------------------------------------------------
    GITHUB_REPO: str = os.getenv("GITHUB_REPO", "https://github.com/KuronaiZuko1/Collab.git")
    GITHUB_ACCESS_TOKEN: str = os.getenv("GITHUB_ACCESS_TOKEN", "").strip()

    @classmethod
    def initialize(cls) -> None:
        """Create necessary data and log directories."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        cls.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        cls.validate_configuration()

    @classmethod
    def validate_configuration(cls) -> None:
        """Validate critical trading and risk settings."""
        valid_modes = {"OFF", "SIGNALS_ONLY", "APPROVAL", "AUTO"}
        if cls.TRADING_MODE not in valid_modes:
            logger.warning("Invalid TRADING_MODE '%s', resetting to OFF.", cls.TRADING_MODE)
            cls.TRADING_MODE = "OFF"

        if cls.TRADING_MODE == "AUTO":
            if cls.RISK_TRADING_LOCKED:
                logger.warning("TRADING_MODE is AUTO but RISK_TRADING_LOCKED is true. Live order execution remains guarded.")
            if not cls.MT5_DEMO_MODE and not cls.LIVE_TRADING_CONFIRMED:
                raise RuntimeError(
                    "SECURITY REFUSAL: Cannot start in AUTO mode on a LIVE account without LIVE_TRADING_CONFIRMED=true."
                )

        if cls.RISK_PER_TRADE_PCT <= 0 or cls.RISK_PER_TRADE_PCT > 5.0:
            logger.warning("RISK_PER_TRADE_PCT (%s) out of safe bounds (0-5%%). Clamping to 1.0%%.", cls.RISK_PER_TRADE_PCT)
            cls.RISK_PER_TRADE_PCT = 1.0

        if cls.MAX_LOT <= 0 or cls.MAX_LOT > 10.0:
            logger.warning("MAX_LOT (%s) out of bounds. Clamping to 1.0.", cls.MAX_LOT)
            cls.MAX_LOT = 1.0

    @classmethod
    def is_kill_switch_active(cls) -> bool:
        """Check if emergency kill switch is activated."""
        return cls.KILL_SWITCH_FILE.exists()

    @classmethod
    def set_kill_switch(cls, active: bool) -> None:
        """Activate or deactivate emergency kill switch."""
        if active:
            cls.KILL_SWITCH_FILE.touch()
        else:
            if cls.KILL_SWITCH_FILE.exists():
                cls.KILL_SWITCH_FILE.unlink(missing_ok=True)

    @classmethod
    def now_utc(cls) -> datetime:
        """Return current datetime in UTC."""
        return datetime.now(timezone.utc)

    @classmethod
    def now_sast(cls) -> datetime:
        """Return current datetime in Africa/Johannesburg (SAST)."""
        return datetime.now(cls.DISPLAY_TIMEZONE)

    @classmethod
    def utc_to_sast(cls, dt_utc: datetime) -> datetime:
        """Convert a UTC datetime to Africa/Johannesburg timezone."""
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        return dt_utc.astimezone(cls.DISPLAY_TIMEZONE)

    @classmethod
    def ts_to_sast_str(cls, ts: int | float) -> str:
        """Convert a Unix timestamp to human-readable SAST string."""
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(cls.DISPLAY_TIMEZONE)
        return dt.strftime("%Y-%m-%d %H:%M:%S SAST")


# Initialize directories on import
Settings.initialize()
settings = Settings()

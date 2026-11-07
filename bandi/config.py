"""
Configuration management for BANDI.
Loads environment variables from .env with fallback defaults.
Ensures directories exist and exposes timezone-aware time utilities.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

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
    # Application details
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

    # Timezone settings (SAST Africa/Johannesburg UTC+2)
    DISPLAY_TIMEZONE_NAME: str = os.getenv("DISPLAY_TIMEZONE", "Africa/Johannesburg")
    DISPLAY_TIMEZONE = get_display_timezone(DISPLAY_TIMEZONE_NAME)

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    TELEGRAM_ENABLED: bool = os.getenv("TELEGRAM_ENABLED", "true").lower() in ("true", "1", "yes")

    # Economic Calendar Engine
    CALENDAR_API_URL: str = os.getenv(
        "CALENDAR_API_URL", "https://showmytrades.com/api/public/calendar/v1"
    ).strip()
    CALENDAR_POLL_INTERVAL_MINUTES: int = max(15, int(os.getenv("CALENDAR_POLL_INTERVAL_MINUTES", "15")))
    CALENDAR_RANGE_DAYS: int = int(os.getenv("CALENDAR_RANGE_DAYS", "7"))

    # Alert Timing
    ALERT_MINUTES_BEFORE: int = int(os.getenv("ALERT_MINUTES_BEFORE", "30"))
    LATE_ALERT_WINDOW_MINUTES: int = int(os.getenv("LATE_ALERT_WINDOW_MINUTES", "25"))
    SCHEDULER_CHECK_INTERVAL_SECONDS: int = int(os.getenv("SCHEDULER_CHECK_INTERVAL_SECONDS", "15"))

    # MetaTrader 5
    MT5_ENABLED: bool = os.getenv("MT5_ENABLED", "true").lower() in ("true", "1", "yes")
    MT5_TERMINAL_PATH: str = os.getenv(
        "MT5_TERMINAL_PATH", r"C:\Program Files\JustMarkets MetaTrader 5\terminal64.exe"
    )
    MT5_METAEDITOR_PATH: str = os.getenv(
        "MT5_METAEDITOR_PATH", r"C:\Program Files\JustMarkets MetaTrader 5\MetaEditor64.exe"
    )
    MT5_SERVER_PORT: int = int(os.getenv("MT5_SERVER_PORT", "8000"))
    MT5_DEMO_MODE: bool = os.getenv("MT5_DEMO_MODE", "true").lower() in ("true", "1", "yes")

    # Deterministic Risk Limits
    RISK_MAX_DAILY_DRAWDOWN_PCT: float = float(os.getenv("RISK_MAX_DAILY_DRAWDOWN_PCT", "3.0"))
    RISK_MAX_OPEN_POSITIONS: int = int(os.getenv("RISK_MAX_OPEN_POSITIONS", "5"))
    RISK_MAX_SPREAD_POINTS: int = int(os.getenv("RISK_MAX_SPREAD_POINTS", "30"))
    RISK_TRADING_LOCKED: bool = os.getenv("RISK_TRADING_LOCKED", "true").lower() in ("true", "1", "yes")

    # GitHub
    GITHUB_REPO: str = os.getenv("GITHUB_REPO", "https://github.com/KuronaiZuko1/Collab.git")
    GITHUB_ACCESS_TOKEN: str = os.getenv("GITHUB_ACCESS_TOKEN", "").strip()

    @classmethod
    def initialize(cls) -> None:
        """Create necessary data and log directories."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        cls.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

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

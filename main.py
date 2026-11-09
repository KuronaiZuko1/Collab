"""
BANDI — Automated Trading Intelligence & Economic Alert Platform.
Master Execution Entry Point.
"""

from __future__ import annotations
import sys
import time
import signal
import logging
import argparse
import uvicorn

from bandi.config import settings
from bandi.database.db import db
from bandi.calendar.client import calendar_client
from bandi.alert.scheduler import precision_scheduler
from bandi.telegram.bot import telegram_notifier
from bandi.mt5.compiler import mql5_compiler
from bandi.dashboard.server import app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.LOGS_DIR / "bandi.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("bandi.main")


def start_server():
    """Start all BANDI services: Database, Calendar, Scheduler, Compiler, Telegram Poller, and Server."""
    print("=" * 65)
    print("   BANDI — AUTOMATED TRADING INTELLIGENCE & ALERT PLATFORM")
    print(f"   Version: 2.0.0 | Environment: {settings.APP_ENV.upper()}")
    print(f"   Trading Mode: [{settings.TRADING_MODE}] | Lock: {'LOCKED' if settings.RISK_TRADING_LOCKED else 'UNLOCKED'}")
    print(f"   Display Timezone: {settings.DISPLAY_TIMEZONE_NAME} (SAST)")
    print(f"   Storage: SQLite WAL Mode ({settings.DATABASE_PATH})")
    print("=" * 65)

    # 1. Initialize SQLite Database Schema
    logger.info("Initializing database schema...")
    db.init_db()

    # 2. Automated MetaTrader 5 EA Compilation
    logger.info("Checking MetaTrader 5 installations and compiling Bandi.ex5...")
    compile_res = mql5_compiler.compile_ea()
    if compile_res.get("ok"):
        logger.info("MQL5 Expert Advisor compiled successfully across %d terminal(s).", compile_res.get("terminals_processed", 0))
    else:
        logger.warning("MT5 compilation note: %s", compile_res.get("error", "No action needed"))

    # 3. Synchronize Economic Calendar (initial fetch)
    logger.info("Synchronizing economic calendar from provider...")
    sync_res = calendar_client.fetch_and_sync(force=False)
    logger.info("Calendar sync status: %s (events: %s)", sync_res.get("status"), sync_res.get("count"))

    # 4. Start Precision 30-Minute Alert Scheduler
    logger.info("Starting precision 30-minute alert scheduler...")
    precision_scheduler.start()

    # 5. Start Telegram Command Poller
    logger.info("Starting Telegram command poller...")
    telegram_notifier.start_polling()

    # 6. Signal Handling for Graceful Shutdown
    def handle_shutdown(signum, frame):
        print("\nStopping BANDI platform...")
        precision_scheduler.stop()
        telegram_notifier.stop_polling()
        db.log("INFO", "SYSTEM", "BANDI platform shut down cleanly.")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # 7. Launch Web Dashboard Server
    dashboard_url = f"http://{settings.HOST}:{settings.PORT}"
    print("\n" + "*" * 65)
    print(f"   BANDI DASHBOARD RUNNING AT: {dashboard_url}")
    print("   Open this link in your browser to view the live dashboard.")
    print("*" * 65 + "\n")

    db.log("INFO", "SYSTEM", f"BANDI platform started on {dashboard_url}")

    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level="info",
        access_log=False
    )


def run_backtest_cli(symbol: str = "EURUSD", split: float = 0.70):
    """Run historical backtest simulation and output metrics."""
    print("=" * 65)
    print(f"   BANDI BACKTEST SIMULATION: {symbol.upper()}")
    print(f"   Split Ratio: {int(split*100)}% In-Sample / {int((1-split)*100)}% Out-of-Sample")
    print("=" * 65)

    from bandi.backtest import backtest_engine, generate_benchmark_candles, load_candles_from_db

    # Try loading from DB first, otherwise use benchmark candles
    h1 = load_candles_from_db(symbol, "H1", limit=1000)
    h4 = load_candles_from_db(symbol, "H4", limit=500)

    if len(h1) < 50:
        print("Note: Limited local DB candles found. Utilizing calibrated benchmark candle sequence.")
        h1 = generate_benchmark_candles(symbol, "H1", count=800, seed=42)
        h4 = generate_benchmark_candles(symbol, "H4", count=250, seed=42)

    res = backtest_engine.run(h1, h4, split_ratio=split)

    if "error" in res:
        print("Backtest Error:", res["error"])
        return

    full = res["overall"]
    in_s = res["in_sample"]
    out_s = res["out_of_sample"]

    print("\n--- OVERALL PERFORMANCE ---")
    print(f"Total Closed Trades: {full['total_trades']}")
    print(f"Win Rate:            {full['win_rate_pct']}% (Wins: {full['winning_trades']}, Losses: {full['losing_trades']})")
    print(f"Average R:           {full['average_r']:+.2f}R")
    print(f"Expectancy:          {full['expectancy_r']:+.2f}R per trade")
    print(f"Profit Factor:       {full['profit_factor']}")
    print(f"Net PnL:             ${full['net_pnl']:+,.2f} (Final: ${full['final_balance']:,.2f})")
    print(f"Max Drawdown:        {full['max_drawdown_pct']}% (${full['max_drawdown_amount']:,.2f})")

    print("\n--- IN-SAMPLE (70%) vs OUT-OF-SAMPLE (30%) ---")
    print(f"In-Sample Trades:    {in_s['total_trades']} | Win Rate: {in_s['win_rate_pct']}% | Net: ${in_s['net_pnl']:+,.2f}")
    print(f"Out-of-Sample Trades: {out_s['total_trades']} | Win Rate: {out_s['win_rate_pct']}% | Net: ${out_s['net_pnl']:+,.2f}")
    print("=" * 65)


def test_telegram_cmd():
    print("Testing Telegram Bot connectivity...")
    res = telegram_notifier.send_test_alert()
    if res.get("ok"):
        print("SUCCESS: Telegram alert delivered to your chat!")
    else:
        print(f"FAILED: {res.get('error')}")


def sync_calendar_cmd():
    db.init_db()
    res = calendar_client.fetch_and_sync(force=True)
    print("Calendar sync completed:", res)


def compile_ea_cmd():
    res = mql5_compiler.compile_ea()
    print("Compilation result:", res)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BANDI Trading Platform")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "test-telegram", "sync-calendar", "compile-ea", "backtest"])
    parser.add_argument("--symbol", default="EURUSD", help="Symbol for backtest")
    parser.add_argument("--split", type=float, default=0.70, help="Train/test split ratio (default 0.70)")

    args = parser.parse_args()

    if args.command == "run":
        start_server()
    elif args.command == "backtest":
        run_backtest_cli(symbol=args.symbol, split=args.split)
    elif args.command == "test-telegram":
        test_telegram_cmd()
    elif args.command == "sync-calendar":
        sync_calendar_cmd()
    elif args.command == "compile-ea":
        compile_ea_cmd()

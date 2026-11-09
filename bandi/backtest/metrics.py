"""
Performance and Risk Metrics for BANDI Backtesting Engine.
Calculates win rate, average R, expectancy, profit factor, max drawdown, and equity curves.
"""

from __future__ import annotations
import math
from typing import List, Dict, Any


def calculate_backtest_metrics(
    trades: List[Dict[str, Any]],
    initial_balance: float = 10000.0
) -> Dict[str, Any]:
    """Calculate comprehensive performance metrics from closed trade simulations."""
    if not trades:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate_pct": 0.0,
            "average_r": 0.0,
            "expectancy_r": 0.0,
            "profit_factor": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "net_pnl": 0.0,
            "final_balance": initial_balance,
            "max_drawdown_pct": 0.0,
            "max_drawdown_amount": 0.0,
            "equity_curve": [initial_balance]
        }

    total_trades = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]

    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    net_pnl = gross_profit - gross_loss

    win_rate = (len(wins) / total_trades) * 100.0
    r_multiples = [t.get("r_multiple", 0.0) for t in trades]
    average_r = sum(r_multiples) / total_trades if total_trades > 0 else 0.0

    # Expectancy in R: (Win_Rate * Avg_Win_R) - (Loss_Rate * Avg_Loss_R)
    win_rs = [t["r_multiple"] for t in wins]
    loss_rs = [abs(t["r_multiple"]) for t in losses]
    avg_win_r = sum(win_rs) / len(win_rs) if win_rs else 0.0
    avg_loss_r = sum(loss_rs) / len(loss_rs) if loss_rs else 0.0
    expectancy_r = ((len(wins) / total_trades) * avg_win_r) - ((len(losses) / total_trades) * avg_loss_r)

    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    # Compute equity curve and maximum drawdown
    balance = initial_balance
    peak = initial_balance
    max_dd_amount = 0.0
    max_dd_pct = 0.0
    equity_curve = [balance]

    for t in trades:
        balance += t["pnl"]
        equity_curve.append(round(balance, 2))
        if balance > peak:
            peak = balance
        dd_amt = peak - balance
        dd_pct = (dd_amt / peak) * 100.0 if peak > 0 else 0.0
        if dd_amt > max_dd_amount:
            max_dd_amount = dd_amt
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct

    return {
        "total_trades": total_trades,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate_pct": round(win_rate, 1),
        "average_r": round(average_r, 2),
        "expectancy_r": round(expectancy_r, 2),
        "profit_factor": profit_factor,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "net_pnl": round(net_pnl, 2),
        "final_balance": round(balance, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_drawdown_amount": round(max_dd_amount, 2),
        "equity_curve": equity_curve
    }

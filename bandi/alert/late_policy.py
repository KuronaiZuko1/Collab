"""
Late-Alert Policy for BANDI.
Defines deterministic handling for events when BANDI starts or recovers
after the nominal 30-minute alert boundary.
"""

from __future__ import annotations
from enum import Enum
from typing import Tuple


class AlertDecision(str, Enum):
    ON_TIME = "on_time"        # Within ~30 min window (28.5m - 31.0m)
    LATE = "late"              # Started late but event is still 1 to 28.5 mins in future
    TOO_LATE = "too_late"      # Event occurs in < 1 min or already passed (suppress)
    TOO_EARLY = "too_early"    # More than 31.0 mins away (wait)


def evaluate_event_timing(
    event_ts: int,
    current_ts: float,
    nominal_minutes: float = 30.0,
    tolerance_window_minutes: float = 1.5,
    late_cutoff_minutes: float = 1.0
) -> Tuple[AlertDecision, float]:
    """
    Evaluate whether an event should trigger an immediate on-time alert, a late alert,
    or be held / suppressed.

    Returns:
        (AlertDecision, minutes_remaining)
    """
    seconds_remaining = event_ts - current_ts
    minutes_remaining = seconds_remaining / 60.0

    # Upper and lower thresholds for on-time window
    on_time_min = nominal_minutes - tolerance_window_minutes  # 28.5
    on_time_max = nominal_minutes + tolerance_window_minutes  # 31.5

    if minutes_remaining > on_time_max:
        return AlertDecision.TOO_EARLY, minutes_remaining

    if on_time_min <= minutes_remaining <= on_time_max:
        return AlertDecision.ON_TIME, minutes_remaining

    if late_cutoff_minutes <= minutes_remaining < on_time_min:
        return AlertDecision.LATE, minutes_remaining

    return AlertDecision.TOO_LATE, minutes_remaining

"""
Unit tests for precision 30-minute scheduler and late alert policy.
"""

import time
from bandi.alert.late_policy import evaluate_event_timing, AlertDecision


def test_evaluate_timing_on_time():
    current_ts = 1000000.0
    # Exactly 30 minutes in future (1800 seconds)
    event_ts = int(current_ts + 1800)
    decision, rem = evaluate_event_timing(event_ts, current_ts)

    assert decision == AlertDecision.ON_TIME
    assert abs(rem - 30.0) < 0.1


def test_evaluate_timing_too_early():
    current_ts = 1000000.0
    # 45 minutes in future (2700 seconds)
    event_ts = int(current_ts + 2700)
    decision, rem = evaluate_event_timing(event_ts, current_ts)

    assert decision == AlertDecision.TOO_EARLY
    assert rem > 31.5


def test_evaluate_timing_late_policy():
    current_ts = 1000000.0
    # System restarted with event 15 minutes away
    event_ts = int(current_ts + 900)
    decision, rem = evaluate_event_timing(event_ts, current_ts)

    assert decision == AlertDecision.LATE
    assert abs(rem - 15.0) < 0.1


def test_evaluate_timing_too_late_suppress():
    current_ts = 1000000.0
    # Event is in 30 seconds (0.5 mins) or in past
    event_ts = int(current_ts + 30)
    decision, rem = evaluate_event_timing(event_ts, current_ts)

    assert decision == AlertDecision.TOO_LATE

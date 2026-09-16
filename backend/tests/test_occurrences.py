"""Schedule occurrence computation (pure, no DB)."""
from __future__ import annotations

from datetime import date

from app.scheduling.occurrences import compute_occurrences


def test_fixed_weekday_window():
    # 2026-09-14 is a Monday
    definition = {"days": {"mon": ["09:00", "18:00"]}}
    occ = compute_occurrences("fixed", definition, date(2026, 9, 14), "UTC")
    assert len(occ) == 1
    assert occ[0].scheduled_start.hour == 9
    assert occ[0].scheduled_end.hour == 18


def test_fixed_no_window_on_unlisted_day():
    definition = {"days": {"mon": ["09:00", "18:00"]}}
    # 2026-09-15 is Tuesday, not listed
    occ = compute_occurrences("fixed", definition, date(2026, 9, 15), "UTC")
    assert occ == []


def test_multiple_windows_per_day():
    definition = {"days": {"mon": [["08:00", "12:00"], ["14:00", "18:00"]]}}
    occ = compute_occurrences("fixed", definition, date(2026, 9, 14), "UTC")
    assert len(occ) == 2


def test_overnight_shift_rolls_to_next_day():
    definition = {"days": {"mon": ["22:00", "06:00"]}}
    occ = compute_occurrences("fixed", definition, date(2026, 9, 14), "UTC")
    assert occ[0].scheduled_end > occ[0].scheduled_start
    # end is on the 15th
    assert occ[0].scheduled_end.day == 15


def test_timezone_conversion_to_utc():
    definition = {"days": {"mon": ["09:00", "18:00"]}}
    occ = compute_occurrences("fixed", definition, date(2026, 9, 14), "Asia/Karachi")
    # Karachi is UTC+5, so 09:00 local == 04:00 UTC
    assert occ[0].scheduled_start.hour == 4


def test_rotating_cycle():
    definition = {
        "cycle_weeks": 2,
        "anchor": "2026-09-14",  # Monday, week index 0
        "weeks": [
            {"days": {"mon": ["09:00", "18:00"]}},
            {"days": {"mon": ["14:00", "23:00"]}},
        ],
    }
    wk0 = compute_occurrences("rotating", definition, date(2026, 9, 14), "UTC")
    wk1 = compute_occurrences("rotating", definition, date(2026, 9, 21), "UTC")
    assert wk0[0].scheduled_start.hour == 9
    assert wk1[0].scheduled_start.hour == 14


def test_custom_dates():
    definition = {"dates": {"2026-09-14": ["10:00", "16:00"]}}
    occ = compute_occurrences("custom", definition, date(2026, 9, 14), "UTC")
    assert occ[0].scheduled_start.hour == 10
    assert compute_occurrences("custom", definition, date(2026, 9, 15), "UTC") == []

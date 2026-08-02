from datetime import datetime

import pytest

from app.orchestration.cron import cron_matches


def test_every_minute():
    assert cron_matches("* * * * *", datetime(2026, 6, 13, 9, 30))


def test_specific_minute_hour():
    assert cron_matches("30 9 * * *", datetime(2026, 6, 13, 9, 30))
    assert not cron_matches("30 9 * * *", datetime(2026, 6, 13, 9, 31))


def test_step_and_range():
    assert cron_matches("*/15 * * * *", datetime(2026, 6, 13, 9, 45))
    assert not cron_matches("*/15 * * * *", datetime(2026, 6, 13, 9, 46))
    assert cron_matches("0 9-17 * * *", datetime(2026, 6, 13, 14, 0))
    assert not cron_matches("0 9-17 * * *", datetime(2026, 6, 13, 18, 0))


def test_day_of_week_saturday():
    # 2026-06-13 is a Saturday → cron dow 6.
    assert cron_matches("0 0 * * 6", datetime(2026, 6, 13, 0, 0))
    assert not cron_matches("0 0 * * 1", datetime(2026, 6, 13, 0, 0))


def test_invalid_expression():
    with pytest.raises(ValueError):
        cron_matches("* * *", datetime(2026, 6, 13, 9, 30))

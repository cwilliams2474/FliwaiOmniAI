"""Pure-Python tests for the cron parser (no database needed)."""

from datetime import datetime, timezone

import pytest

from app.cron import CronError, describe, next_after, parse

UTC = timezone.utc


def at(*a):
    return datetime(*a, tzinfo=UTC)


def test_basic_fields():
    c = parse("*/15 8-18/2 * jan,jul mon-fri")
    assert c.minutes == {0, 15, 30, 45}
    assert c.hours == {8, 10, 12, 14, 16, 18}
    assert c.months == {1, 7}
    assert c.weekdays == {1, 2, 3, 4, 5}
    assert parse("0 0 * * 7").weekdays == {0}
    assert parse("@daily") == parse("0 0 * * *")


@pytest.mark.parametrize("bad", ["", "* * * *", "61 * * * *", "* 24 * * *", "*/0 * * * *", "5-1 * * * *", "x * * * *", "* * 0 * *"])
def test_rejects_bad(bad):
    with pytest.raises(CronError):
        parse(bad)


def test_next_simple():
    assert next_after("0 2 * * *", at(2026, 10, 18, 1, 59)) == at(2026, 10, 18, 2, 0)
    assert next_after("0 2 * * *", at(2026, 10, 18, 2, 0)) == at(2026, 10, 19, 2, 0)  # strictly after
    assert next_after("*/15 * * * *", at(2026, 10, 18, 10, 7, 30)) == at(2026, 10, 18, 10, 15)


def test_weekdays_and_month_rollover():
    # 2026-10-17 is a Saturday -> next weekday 07:00 is Monday the 19th
    assert next_after("0 7 * * 1-5", at(2026, 10, 17, 12, 0)) == at(2026, 10, 19, 7, 0)
    assert next_after("0 0 1 * *", at(2026, 12, 15)) == at(2027, 1, 1)
    assert next_after("0 0 29 2 *", at(2026, 3, 1)) == at(2028, 2, 29)


def test_dom_or_dow():
    # 1st of month OR Monday
    assert next_after("0 9 1 * mon", at(2026, 10, 20, 10)) == at(2026, 10, 26, 9)
    assert next_after("0 9 1 * mon", at(2026, 10, 27, 10)) == at(2026, 11, 1, 9)


def test_timezone_and_dst():
    tz = "America/New_York"
    # 02:00 local in October (EDT, UTC-4) = 06:00 UTC; in December (EST, UTC-5) = 07:00 UTC
    assert next_after("0 2 * * *", at(2026, 10, 18, 0), tz) == at(2026, 10, 18, 6)
    assert next_after("0 2 * * *", at(2026, 12, 1, 0), tz) == at(2026, 12, 1, 7)
    # 2027-03-14 02:30 doesn't exist in New York (spring forward): skipped to the next day
    assert next_after("30 2 * * *", at(2027, 3, 14, 5), tz) == at(2027, 3, 15, 6, 30)


def test_never_matches():
    with pytest.raises(CronError):
        next_after("0 0 30 2 *", at(2026, 1, 1))


def test_describe():
    assert describe("0 7 * * 1-5") == "Weekdays at 07:00"
    assert describe("30 2 * * *") == "Daily at 02:30"
    assert describe("0 9 * * mon") == "Mon at 09:00"
    assert describe("15 * * * *") == "Hourly at :15"

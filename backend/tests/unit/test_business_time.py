from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.shared.business_time import add_business_hours

HK = ZoneInfo("Asia/Hong_Kong")


def hk(month: int, day: int, hour: int) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=HK)


def test_two_business_days_end_at_the_same_time_two_working_days_later():
    assert add_business_hours(hk(10, 27, 10), 18) == hk(10, 29, 10)  # Tuesday 10:00 -> Thursday 10:00


def test_hours_carry_over_the_weekend():
    assert add_business_hours(hk(10, 30, 17), 2) == hk(11, 2, 10)  # Friday 17:00 + 2 h -> Monday 10:00


def test_the_clock_starts_at_opening_time():
    assert add_business_hours(hk(11, 2, 7), 1) == hk(11, 2, 10)  # Monday 07:00 + 1 h -> 10:00


def test_a_saturday_start_counts_from_monday():
    assert add_business_hours(hk(10, 31, 12), 4) == hk(11, 2, 13)


def test_the_result_is_in_utc():
    assert add_business_hours(hk(10, 27, 10), 1).tzinfo == UTC

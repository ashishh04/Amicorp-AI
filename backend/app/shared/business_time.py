"""Business-time arithmetic for SLAs (LLD, Card type registry: SLAs run on the owner's calendar).

Working hours are 09:00-18:00 local time, Monday to Friday, so one business day is 9 working hours.
Public holidays will come from ref.calendar; until then every weekday is a working day.
"""
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class BusinessCalendar:
    zone: ZoneInfo
    opens: time
    closes: time

    @property
    def hours_per_day(self) -> float:
        return (self.closes.hour * 60 + self.closes.minute - self.opens.hour * 60 - self.opens.minute) / 60


CALENDARS: dict[str, BusinessCalendar] = {
    "HK": BusinessCalendar(ZoneInfo("Asia/Hong_Kong"), time(9), time(18)),
    "EU": BusinessCalendar(ZoneInfo("Europe/Amsterdam"), time(9), time(18)),
}
BUSINESS_DAY_HOURS = CALENDARS["HK"].hours_per_day


def add_business_hours(start: datetime, hours: float, calendar: str = "HK") -> datetime:
    """The moment `hours` working hours after `start`, returned in UTC."""
    cal = CALENDARS[calendar]
    remaining = timedelta(hours=hours)
    moment = start.astimezone(cal.zone)
    while True:
        opens, closes = _at(moment, cal.opens), _at(moment, cal.closes)
        if moment.weekday() >= 5 or moment >= closes:
            moment = _next_opening(moment, cal)
            continue
        moment = max(moment, opens)
        available = closes - moment
        if remaining <= available:
            return (moment + remaining).astimezone(UTC)
        remaining -= available
        moment = _next_opening(moment, cal)


def _at(day: datetime, clock: time) -> datetime:
    return day.replace(hour=clock.hour, minute=clock.minute, second=0, microsecond=0)


def _next_opening(moment: datetime, cal: BusinessCalendar) -> datetime:
    following = _at(moment + timedelta(days=1), cal.opens)
    while following.weekday() >= 5:
        following += timedelta(days=1)
    return following

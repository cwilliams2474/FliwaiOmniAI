"""Five-field cron expressions (minute hour day-of-month month day-of-week), stdlib only.

Supports *, lists (1,15), ranges (1-5), steps (*/15, 8-18/2), month and weekday names
(jan, mon), and the shortcuts @hourly @daily @weekly @monthly. Day-of-week 0 and 7 are Sunday.
As in standard cron, when both day-of-month and day-of-week are restricted, a day matches if
either matches. Times are evaluated in the given time zone (so 02:00 stays 02:00 across DST).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
DAYS = {d: i for i, d in enumerate("sun mon tue wed thu fri sat".split())}
SHORTCUTS = {"@hourly": "0 * * * *", "@daily": "0 0 * * *", "@midnight": "0 0 * * *", "@weekly": "0 0 * * 0", "@monthly": "0 0 1 * *", "@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *"}
FIELDS = [("minute", 0, 59, {}), ("hour", 0, 23, {}), ("day of month", 1, 31, {}), ("month", 1, 12, MONTHS), ("day of week", 0, 7, DAYS)]


class CronError(ValueError):
    pass


def _num(tok: str, names: dict, name: str) -> int:
    t = tok.lower()
    if t in names:
        return names[t]
    if not t.isdigit():
        raise CronError(f"'{tok}' isn't a valid {name}.")
    return int(t)


def _field(text: str, name: str, lo: int, hi: int, names: dict) -> set[int]:
    out: set[int] = set()
    for part in text.split(","):
        if not part:
            raise CronError(f"Empty value in the {name} field.")
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            if not s.isdigit() or int(s) == 0:
                raise CronError(f"Step '/{s}' in the {name} field must be a positive number.")
            step = int(s)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            x, y = part.split("-", 1)
            a, b = _num(x, names, name), _num(y, names, name)
        else:
            a = _num(part, names, name)
            b = hi if step > 1 else a
        if not (lo <= a <= hi and lo <= b <= hi) or a > b:
            raise CronError(f"{part} is out of range for {name} ({lo}-{hi}).")
        out.update(range(a, b + 1, step))
    return out


@dataclass(frozen=True)
class Cron:
    minutes: frozenset
    hours: frozenset
    days: frozenset
    months: frozenset
    weekdays: frozenset  # 0 = Sunday
    dom_any: bool
    dow_any: bool

    def day_matches(self, d: datetime) -> bool:
        dom = d.day in self.days
        dow = ((d.weekday() + 1) % 7) in self.weekdays
        if self.dom_any and self.dow_any:
            return True
        if self.dom_any:
            return dow
        if self.dow_any:
            return dom
        return dom or dow


def parse(expr: str) -> Cron:
    e = SHORTCUTS.get(expr.strip().lower(), expr.strip())
    parts = e.split()
    if len(parts) != 5:
        raise CronError("Use five fields: minute hour day-of-month month day-of-week, e.g. '0 7 * * 1-5'.")
    sets = [_field(p, n, lo, hi, names) for p, (n, lo, hi, names) in zip(parts, FIELDS)]
    wd = {0 if d == 7 else d for d in sets[4]}
    return Cron(frozenset(sets[0]), frozenset(sets[1]), frozenset(sets[2]), frozenset(sets[3]), frozenset(wd), parts[2] == "*", parts[4] == "*")


def next_after(expr: str | Cron, after: datetime, tz: str = "UTC") -> datetime:
    """First matching time strictly after `after` (aware datetime). Returns an aware UTC datetime."""
    c = parse(expr) if isinstance(expr, str) else expr
    zone = ZoneInfo(tz)
    t = after.astimezone(zone).replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = t + timedelta(days=366 * 5)
    while t < limit:
        if t.month not in c.months:
            # jump to the first day of next month
            t = (t.replace(day=1, hour=0, minute=0) + timedelta(days=32)).replace(day=1)
            continue
        if not c.day_matches(t):
            t = (t + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        if t.hour not in c.hours:
            t = (t + timedelta(hours=1)).replace(minute=0)
            continue
        if t.minute not in c.minutes:
            t += timedelta(minutes=1)
            continue
        # Wall-clock times that don't exist (DST spring-forward) are skipped.
        roundtrip = t.astimezone(timezone.utc).astimezone(zone)
        if roundtrip.replace(tzinfo=None) != t.replace(tzinfo=None):
            t += timedelta(minutes=1)
            continue
        return t.astimezone(timezone.utc)
    raise CronError("This schedule never matches (for example, 30 February).")


def describe(expr: str) -> str:
    """Short human hint for common patterns; falls back to the expression itself."""
    try:
        c = parse(expr)
    except CronError:
        return expr
    if len(c.minutes) == 1 and len(c.hours) == 1 and c.dom_any and len(c.months) == 12:
        hh, mm = next(iter(c.hours)), next(iter(c.minutes))
        at = f"{hh:02d}:{mm:02d}"
        if c.dow_any:
            return f"Daily at {at}"
        if c.weekdays == frozenset({1, 2, 3, 4, 5}):
            return f"Weekdays at {at}"
        names = [n.capitalize() for n, i in sorted(DAYS.items(), key=lambda x: x[1]) if i in c.weekdays]
        return f"{', '.join(names)} at {at}"
    if len(c.hours) == 24 and c.dom_any and c.dow_any and len(c.minutes) == 1:
        return f"Hourly at :{next(iter(c.minutes)):02d}"
    return expr

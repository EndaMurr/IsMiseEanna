"""Runna-style plan week/block progress, parsed from calendar session names.

Runna-generated Garmin calendar sessions follow a "W<week> <Day> <Type> -
<detail>" naming convention (e.g. "W6 Tue Tempo - 2km Repeats"). Non-Runna
activities on the same calendar (manual runs, other apps) don't match this
pattern and are simply ignored - there's no reliable way to distinguish "not
on a Runna plan this week" from "rest week with no Runna session" from
calendar data alone, so both surface identically as ``currentWeek: None``.
"""

import math
import re
from datetime import date

_SESSION_NAME_RE = re.compile(
    r"^W(\d+)\s+(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+.+", re.IGNORECASE
)


def _parse_week_number(name: str | None) -> int | None:
    """Parse the leading "W<n>" out of a Runna-style session name, or None if
    ``name`` doesn't match the convention (rest week, non-Runna activity, or
    no name at all).
    """
    if not name:
        return None
    match = _SESSION_NAME_RE.match(name.strip())
    return int(match.group(1)) if match else None


def build_plan_progress(scheduled: list[dict], race_date: str, today: date | None = None) -> dict:
    """Determine which week of a Runna-style plan ``today`` falls in, and how
    many weeks remain until ``race_date``.

    - ``scheduled``: this week's calendar items, normalized exactly like
      build_weekly_check_in's ``scheduled`` argument
      (``{"date": "YYYY-MM-DD", "name": str, ...}``) - callers should reuse
      the same weekly-scoped calendar fetch, not scan the whole plan.
    - ``race_date``: "YYYY-MM-DD" - raises ValueError if it doesn't parse,
      since this is client-supplied input, not something to silently ignore.

    ``currentWeek`` is read from the first scheduled item this week whose
    name matches the "W<n> <Day> <Type>" convention - it's None if nothing
    this week matches. A rest week, a non-Runna plan, or no plan at all all
    look the same from calendar data alone, so this degrades to None rather
    than guessing or raising.

    ``totalWeeks`` is only computed when both ``currentWeek`` is known and
    the race is still in the future - it's ``currentWeek + weeksRemaining``,
    not derived by scanning the calendar for a plan's actual last week.

    Returns ``{raceDate, daysUntilRace, currentWeek, weeksRemaining,
    totalWeeks, matchedSessionName}``.
    """
    today = today or date.today()
    race = date.fromisoformat(race_date)
    days_until_race = (race - today).days

    weeks_remaining = math.ceil(days_until_race / 7) if days_until_race >= 0 else None

    current_week = None
    matched_name = None
    for item in scheduled:
        week = _parse_week_number(item.get("name"))
        if week is not None:
            current_week = week
            matched_name = item.get("name")
            break

    total_weeks = (
        current_week + weeks_remaining
        if current_week is not None and weeks_remaining is not None
        else None
    )

    return {
        "raceDate": race_date,
        "daysUntilRace": days_until_race,
        "currentWeek": current_week,
        "weeksRemaining": weeks_remaining,
        "totalWeeks": total_weeks,
        "matchedSessionName": matched_name,
    }

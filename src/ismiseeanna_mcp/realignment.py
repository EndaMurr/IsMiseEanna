"""Weekly plan-vs-actual + recovery check-in.

Compares whatever's on the Garmin calendar for the current week — regardless
of which app scheduled it (Runna, ismiseeanna, or by hand) — against
completed activities, plus the recent training-readiness/HRV trend, so you
can decide whether to ease off or push on. Read-only: this module has no
write access to the calendar, unlike create_running_workout/schedule_workout.
That's deliberate, not a missing feature — a plan this project didn't create
(e.g. Runna's) can get re-synced by its own app at any time, so an automated
write here could conflict with or silently get overwritten by that sync.
"""

from datetime import date, timedelta


def _week_range(today: date | None = None) -> tuple[date, date]:
    """Monday-Sunday range containing ``today`` (default: today)."""
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def _is_suppressed(values: list[float | None], recent_n: int = 3, threshold: float = 0.90) -> bool:
    """True if the most recent ``recent_n`` readings are all below ``threshold``
    of the average of the readings before them — a sustained dip, not one bad day.
    """
    if len(values) <= recent_n:
        return False
    baseline_values = [v for v in values[:-recent_n] if v is not None]
    recent_values = values[-recent_n:]
    if not baseline_values or any(v is None for v in recent_values):
        return False
    baseline = sum(baseline_values) / len(baseline_values)
    return all(v < baseline * threshold for v in recent_values)


def build_weekly_check_in(
    scheduled: list[dict],
    completed: list[dict],
    recovery_trend: dict,
    today: date | None = None,
    match_tolerance_days: int = 1,
) -> dict:
    """Compare this week's scheduled Garmin-calendar items against completed activities.

    - ``scheduled``: calendar items already normalized to ``{"date": "YYYY-MM-DD", "name": str}``
    - ``completed``: activity summaries as returned by search_activities_by_date /
      list_activities (each has a ``startTimeLocal`` field)
    - ``recovery_trend``: ``{"trainingReadiness": [...], "hrv": [...]}``, oldest first,
      as returned by garmin_client._n_day_trend

    A scheduled item counts as completed if any activity's date falls within
    ``match_tolerance_days`` of it — this is a date-proximity match, not a
    same-workout match, since a plan generated elsewhere (e.g. Runna) has no
    workoutId this project can compare against directly.

    A non-completed item only counts as "missed" if its date has already
    passed (today's own session, and anything later in the week, is
    "upcoming" instead — it hasn't happened yet, so it can't be missed).

    Returns ``{weekStart, weekEnd, sessionsScheduled, sessionsCompleted,
    sessionsMissed, sessionsUpcoming, recoveryTrend, readinessSuppressed,
    hrvSuppressed}``. Deliberately returns data, not a canned recommendation
    - the narrative (what to actually do about it) is for whoever calls this
    to write, conversationally, from this data.
    """
    today = today or date.today()
    week_start, week_end = _week_range(today)

    scheduled_in_week = [
        item
        for item in scheduled
        if item.get("date") and week_start.isoformat() <= item["date"] <= week_end.isoformat()
    ]

    completed_dates = []
    for activity in completed:
        start = activity.get("startTimeLocal")
        if start:
            completed_dates.append(date.fromisoformat(start[:10]))

    completed_items = []
    missed_items = []
    upcoming_items = []
    for item in scheduled_in_week:
        item_date = date.fromisoformat(item["date"])
        is_done = any(abs((d - item_date).days) <= match_tolerance_days for d in completed_dates)
        if is_done:
            completed_items.append(item)
        elif item_date < today:
            missed_items.append(item)
        else:
            upcoming_items.append(item)

    readiness_trend = recovery_trend.get("trainingReadiness") or []
    hrv_trend = recovery_trend.get("hrv") or []

    return {
        "weekStart": week_start.isoformat(),
        "weekEnd": week_end.isoformat(),
        "sessionsScheduled": len(scheduled_in_week),
        "sessionsCompleted": completed_items,
        "sessionsMissed": missed_items,
        "sessionsUpcoming": upcoming_items,
        "recoveryTrend": recovery_trend,
        "readinessSuppressed": _is_suppressed(readiness_trend),
        "hrvSuppressed": _is_suppressed(hrv_trend),
    }

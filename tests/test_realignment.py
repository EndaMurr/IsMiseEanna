from datetime import date

from ismiseeanna_mcp.realignment import _is_suppressed, _week_range, build_weekly_check_in

# Wednesday, so the week runs Mon 2026-08-10 .. Sun 2026-08-16
TODAY = date(2026, 8, 12)


def test_week_range_is_monday_to_sunday_containing_today():
    start, end = _week_range(TODAY)
    assert start == date(2026, 8, 10)
    assert end == date(2026, 8, 16)


def test_week_range_defaults_to_real_today():
    start, end = _week_range()
    assert start.weekday() == 0  # Monday
    assert (end - start).days == 6
    assert start <= date.today() <= end


def test_is_suppressed_true_for_sustained_dip_below_baseline():
    # baseline (first 4) avg = 70; last 3 all well under 90% of that
    values = [70, 70, 70, 70, 50, 48, 45]
    assert _is_suppressed(values) is True


def test_is_suppressed_false_for_one_bad_day():
    values = [70, 70, 70, 70, 50, 72, 71]
    assert _is_suppressed(values) is False


def test_is_suppressed_false_when_recent_values_missing():
    values = [70, 70, 70, 70, None, 50, 45]
    assert _is_suppressed(values) is False


def test_is_suppressed_false_with_too_few_values():
    assert _is_suppressed([70, 60, 55]) is False


def test_is_suppressed_false_when_no_baseline_data():
    values = [None, None, None, None, 50, 48, 45]
    assert _is_suppressed(values) is False


def _scheduled(day: str, name: str = "Long Run") -> dict:
    return {"date": day, "name": name}


def _activity(day: str) -> dict:
    return {"activityId": 1, "name": "Run", "startTimeLocal": f"{day} 07:00:00"}


def test_build_weekly_check_in_filters_to_current_week():
    scheduled = [
        _scheduled("2026-08-09"),  # previous week — excluded
        _scheduled("2026-08-11"),
        _scheduled("2026-08-17"),  # next week — excluded
    ]
    result = build_weekly_check_in(scheduled, [], {}, today=TODAY)
    assert result["weekStart"] == "2026-08-10"
    assert result["weekEnd"] == "2026-08-16"
    assert result["sessionsScheduled"] == 1


def test_build_weekly_check_in_matches_completed_within_tolerance():
    scheduled = [_scheduled("2026-08-12", "Tempo Run")]
    completed = [_activity("2026-08-13")]  # 1 day off, within default tolerance

    result = build_weekly_check_in(scheduled, completed, {}, today=TODAY)

    assert result["sessionsCompleted"] == [{"date": "2026-08-12", "name": "Tempo Run"}]
    assert result["sessionsMissed"] == []


def test_build_weekly_check_in_flags_missed_session_outside_tolerance():
    scheduled = [_scheduled("2026-08-11", "Tempo Run")]  # yesterday relative to TODAY
    completed = [_activity("2026-08-15")]  # 4 days off, well outside tolerance

    result = build_weekly_check_in(scheduled, completed, {}, today=TODAY)

    assert result["sessionsMissed"] == [{"date": "2026-08-11", "name": "Tempo Run"}]
    assert result["sessionsCompleted"] == []
    assert result["sessionsUpcoming"] == []


def test_build_weekly_check_in_does_not_flag_future_sessions_as_missed():
    scheduled = [
        _scheduled("2026-08-11", "Yesterday's Run"),  # past, uncompleted -> missed
        _scheduled("2026-08-12", "Today's Run"),  # today, uncompleted -> upcoming
        _scheduled("2026-08-14", "Friday's Run"),  # future -> upcoming
    ]

    result = build_weekly_check_in(scheduled, [], {}, today=TODAY)

    assert [s["name"] for s in result["sessionsMissed"]] == ["Yesterday's Run"]
    assert [s["name"] for s in result["sessionsUpcoming"]] == ["Today's Run", "Friday's Run"]


def test_build_weekly_check_in_surfaces_recovery_suppression_flags():
    recovery_trend = {
        "trainingReadiness": [70, 70, 70, 70, 50, 48, 45],
        "hrv": [60, 60, 60, 60, 60, 60, 60],
    }
    result = build_weekly_check_in([], [], recovery_trend, today=TODAY)
    assert result["readinessSuppressed"] is True
    assert result["hrvSuppressed"] is False
    assert result["recoveryTrend"] == recovery_trend

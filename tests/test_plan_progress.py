from datetime import date

import pytest

from ismiseeanna_mcp.plan_progress import _parse_week_number, build_plan_progress

# Wednesday, so the week runs Mon 2026-08-10 .. Sun 2026-08-16
TODAY = date(2026, 8, 12)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("W6 Tue Tempo - 2km Repeats", 6),
        ("W6 Sun Easy Run - 11km", 6),
        ("W4 Tue Tempo - Progressive Run", 4),
        ("W3 Fri Long Run - 26km Progressive", 3),
        ("W3 Mon Easy Run - 9km", 3),
        ("W2 Sat Long Run - 24km", 2),
        ("w12 Sun Easy Run - 11km", 12),  # case-insensitive
    ],
)
def test_parse_week_number_matches_runna_convention(name, expected):
    assert _parse_week_number(name) == expected


@pytest.mark.parametrize(
    "name",
    ["28km Run", "Easy 10K", "County Galway Running", "", None, "Week 6 Tempo"],
)
def test_parse_week_number_ignores_non_matching_names(name):
    assert _parse_week_number(name) is None


def _scheduled(name: str) -> dict:
    return {"date": "2026-08-11", "name": name}


def test_build_plan_progress_finds_current_week_from_scheduled_sessions():
    scheduled = [_scheduled("28km Run"), _scheduled("W6 Tue Tempo - 2km Repeats")]
    result = build_plan_progress(scheduled, "2026-10-03", today=TODAY)

    assert result["currentWeek"] == 6
    assert result["matchedSessionName"] == "W6 Tue Tempo - 2km Repeats"
    assert result["daysUntilRace"] == (date(2026, 10, 3) - TODAY).days
    assert result["weeksRemaining"] == 8  # ceil(52 / 7)
    assert result["totalWeeks"] == 14


def test_build_plan_progress_degrades_gracefully_with_no_matching_session():
    scheduled = [_scheduled("28km Run"), _scheduled("Easy 10K")]
    result = build_plan_progress(scheduled, "2026-10-03", today=TODAY)

    assert result["currentWeek"] is None
    assert result["matchedSessionName"] is None
    assert result["totalWeeks"] is None
    assert result["weeksRemaining"] == 8  # still computable without a current week


def test_build_plan_progress_handles_past_race_date():
    scheduled = [_scheduled("W6 Tue Tempo - 2km Repeats")]
    result = build_plan_progress(scheduled, "2026-01-01", today=TODAY)

    assert result["daysUntilRace"] < 0
    assert result["weeksRemaining"] is None
    assert result["totalWeeks"] is None
    assert result["currentWeek"] == 6


def test_build_plan_progress_rejects_malformed_race_date():
    with pytest.raises(ValueError):
        build_plan_progress([], "not-a-date", today=TODAY)

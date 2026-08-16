from datetime import date, timedelta

import pytest

from ismiseeanna_mcp import plan_generator
from ismiseeanna_mcp.garmin_client import GarminClientError
from ismiseeanna_mcp.plan_generator import MARATHON_KM, generate_marathon_plan

RACE_PREDICTIONS = {
    "time5K": 1215,
    "time10K": 2560,
    "timeHalfMarathon": 5619,
    "timeMarathon": 12399,
}

TODAY = date(2026, 8, 16)  # Sunday
RACE_DATE = "2026-10-03"  # Saturday, 7 weeks out


def _plan(**kwargs):
    return generate_marathon_plan(
        RACE_DATE, 55.0, RACE_PREDICTIONS, today=TODAY, **kwargs
    )


def test_rejects_race_date_in_the_past():
    with pytest.raises(GarminClientError, match="future"):
        generate_marathon_plan("2020-01-01", 50.0, RACE_PREDICTIONS, today=TODAY)


def test_rejects_malformed_race_date():
    with pytest.raises(GarminClientError, match="ISO date"):
        generate_marathon_plan("not-a-date", 50.0, RACE_PREDICTIONS, today=TODAY)


def test_rejects_unknown_strategy():
    with pytest.raises(GarminClientError, match="strategy"):
        _plan(strategy="yolo")


def test_rejects_incomplete_race_predictions():
    incomplete = dict(RACE_PREDICTIONS, timeMarathon=None)
    with pytest.raises(GarminClientError, match="timeMarathon"):
        generate_marathon_plan(RACE_DATE, 50.0, incomplete, today=TODAY)


def test_plan_spans_from_next_monday_through_race_week():
    plan = _plan()
    assert plan[0]["weekStart"] == "2026-08-17"
    assert plan[-1]["weekStart"] == "2026-09-28"
    assert len(plan) == 7


def test_last_week_is_race_phase_and_includes_race_day():
    plan = _plan()
    race_week = plan[-1]
    assert race_week["phase"] == "race"
    race_day = race_week["sessions"][-1]
    assert race_day["date"] == RACE_DATE
    assert race_day["name"] == "Marathon (Race Day)"
    assert race_day["steps"] is None


def test_second_to_last_week_is_taper_with_reduced_volume():
    plan = _plan()
    taper_week, peak_week = plan[-2], plan[-3]
    assert taper_week["phase"] == "taper"
    assert peak_week["phase"] == "peak"
    assert taper_week["targetWeeklyKm"] < peak_week["targetWeeklyKm"]


def test_build_phase_ramps_without_exceeding_ten_percent_weekly_growth():
    plan = _plan()
    build_weeks = [w for w in plan if w["phase"] == "build"]
    assert build_weeks  # sanity: this plan has at least one build week
    prev = 55.0
    for week in build_weeks:
        assert week["targetWeeklyKm"] <= round(prev * 1.10 + 0.05, 1)
        prev = week["targetWeeklyKm"]


def test_aggressive_strategy_peaks_higher_than_conservative():
    aggressive_peak = max(w["targetWeeklyKm"] for w in _plan(strategy="aggressive"))
    conservative_peak = max(w["targetWeeklyKm"] for w in _plan(strategy="conservative"))
    assert aggressive_peak > conservative_peak


def test_non_race_weeks_have_three_sessions_on_tue_thu_sat():
    plan = _plan()
    for week in plan[:-1]:
        names = [s["name"] for s in week["sessions"]]
        assert names == ["Intervals", "Tempo Run", "Long Run"]
        for session, offset in zip(week["sessions"], (1, 3, 5)):
            expected_date = date.fromisoformat(week["weekStart"])
            assert session["date"] == (expected_date + timedelta(days=offset)).isoformat()


def test_long_run_distance_never_exceeds_cap():
    plan = _plan(strategy="aggressive")
    for week in plan[:-1]:
        long_run = next(s for s in week["sessions"] if s["name"] == "Long Run")
        total_meters = sum(
            step["distance_meters"] for step in long_run["steps"] if "distance_meters" in step
        )
        assert total_meters <= plan_generator._LONG_RUN_CAP_KM * 1000 + 1


def test_peak_week_long_run_finishes_at_marathon_pace():
    plan = _plan()
    peak_week = next(w for w in plan if w["phase"] == "peak")
    long_run = next(s for s in peak_week["sessions"] if s["name"] == "Long Run")
    marathon_pace = RACE_PREDICTIONS["timeMarathon"] / MARATHON_KM
    finish_step = long_run["steps"][1]
    assert finish_step["kind"] == "interval"
    assert finish_step["target_pace_min_per_km"] == round(marathon_pace - 5)
    assert finish_step["target_pace_max_per_km"] == round(marathon_pace + 5)


def test_interval_session_uses_repeat_block_at_interval_pace():
    plan = _plan()
    week = plan[0]
    intervals = next(s for s in week["sessions"] if s["name"] == "Intervals")
    repeat = intervals["steps"][1]["repeat"]
    assert repeat["count"] == 6
    rep_step = repeat["steps"][0]
    interval_pace = RACE_PREDICTIONS["time10K"] / 10
    assert rep_step["target_pace_min_per_km"] == round(interval_pace - 5)
    assert rep_step["target_pace_max_per_km"] == round(interval_pace + 5)


@pytest.mark.parametrize("race_date", ["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"])
def test_race_week_shakeout_and_sharpener_always_precede_race_day(race_date):
    # 2026-10-05..08 are Mon/Tue/Wed/Thu — the days the old fixed Tue/Thu
    # offsets could land on or after race day instead of before it.
    plan = generate_marathon_plan(race_date, 50.0, RACE_PREDICTIONS, today=TODAY)
    race_week = plan[-1]
    shakeout, sharpener, race_day = race_week["sessions"]
    assert shakeout["date"] < sharpener["date"] < race_day["date"]


def test_warmup_and_cooldown_legs_carry_an_easy_pace_target():
    plan = _plan()
    easy_pace = RACE_PREDICTIONS["timeMarathon"] / MARATHON_KM + 60
    for week in plan:
        for session in week["sessions"]:
            if session["steps"] is None:
                continue
            for step in session["steps"]:
                if step.get("kind") not in ("warmup", "cooldown"):
                    continue
                assert step["target_pace_min_per_km"] == round(easy_pace - 5)
                assert step["target_pace_max_per_km"] == round(easy_pace + 5)


def test_all_generated_steps_are_accepted_by_build_structured_running_workout():
    from ismiseeanna_mcp.garmin_client import build_structured_running_workout

    plan = _plan()
    for week in plan:
        for session in week["sessions"]:
            if session["steps"] is None:
                continue
            workout = build_structured_running_workout(session["name"], session["steps"])
            assert workout["workoutName"] == session["name"]

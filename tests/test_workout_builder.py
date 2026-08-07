import pytest

from ismiseeanna_mcp.workout_builder import (
    WorkoutBuilderError,
    build_running_workout,
    pace_to_speed_mps,
)


def test_pace_to_speed_mps_converts_correctly():
    # 5:00/km == 300s/km == 1000m / 300s
    assert pace_to_speed_mps(5.0) == pytest.approx(1000.0 / 300.0)


def test_pace_to_speed_mps_rejects_non_positive():
    with pytest.raises(WorkoutBuilderError):
        pace_to_speed_mps(0)


def test_build_running_workout_requires_name():
    with pytest.raises(WorkoutBuilderError):
        build_running_workout("", [{"kind": "warmup", "duration_seconds": 600}])


def test_build_running_workout_requires_steps():
    with pytest.raises(WorkoutBuilderError):
        build_running_workout("Easy Run", [])


def test_build_running_workout_simple_time_based_steps():
    workout = build_running_workout(
        "Easy Run",
        [
            {"kind": "warmup", "duration_seconds": 600},
            {"kind": "cooldown", "duration_seconds": 300},
        ],
    )

    assert workout["workoutName"] == "Easy Run"
    assert workout["sportType"] == {
        "sportTypeId": 1,
        "sportTypeKey": "running",
        "displayOrder": 1,
    }
    assert workout["estimatedDurationInSecs"] == 900

    segment = workout["workoutSegments"][0]
    assert segment["segmentOrder"] == 1
    steps = segment["workoutSteps"]
    assert len(steps) == 2

    warmup, cooldown = steps
    assert warmup["stepOrder"] == 1
    assert warmup["stepType"]["stepTypeKey"] == "warmup"
    assert warmup["endCondition"]["conditionTypeKey"] == "time"
    assert warmup["endConditionValue"] == 600
    assert warmup["targetType"]["workoutTargetTypeKey"] == "no.target"
    assert "targetValueOne" not in warmup

    assert cooldown["stepOrder"] == 2
    assert cooldown["stepType"]["stepTypeKey"] == "cooldown"
    assert cooldown["endConditionValue"] == 300


def test_build_running_workout_includes_description_when_given():
    workout = build_running_workout(
        "Easy Run",
        [{"kind": "warmup", "duration_seconds": 600}],
        description="Keep it conversational.",
    )
    assert workout["description"] == "Keep it conversational."


def test_build_running_workout_omits_description_when_not_given():
    workout = build_running_workout(
        "Easy Run", [{"kind": "warmup", "duration_seconds": 600}]
    )
    assert "description" not in workout


def test_step_requires_exactly_one_of_duration_or_distance():
    with pytest.raises(WorkoutBuilderError):
        build_running_workout("Run", [{"kind": "warmup"}])
    with pytest.raises(WorkoutBuilderError):
        build_running_workout(
            "Run",
            [
                {
                    "kind": "warmup",
                    "duration_seconds": 600,
                    "distance_meters": 1000,
                }
            ],
        )


def test_step_rejects_both_pace_and_heart_rate_targets():
    with pytest.raises(WorkoutBuilderError):
        build_running_workout(
            "Run",
            [
                {
                    "kind": "interval",
                    "duration_seconds": 300,
                    "target_pace_min_per_km": [4.0, 4.2],
                    "target_heart_rate_bpm": [150, 160],
                }
            ],
        )


def test_pace_target_step_uses_speed_zone_with_sorted_values():
    workout = build_running_workout(
        "Intervals",
        [
            {
                "kind": "interval",
                "distance_meters": 400,
                # low pace number (faster) listed first
                "target_pace_min_per_km": [3.9, 4.1],
            }
        ],
    )
    step = workout["workoutSegments"][0]["workoutSteps"][0]
    assert step["endCondition"]["conditionTypeKey"] == "distance"
    assert step["endConditionValue"] == 400
    assert step["targetType"]["workoutTargetTypeKey"] == "speed.zone"
    # slower pace (4.1) -> lower speed -> targetValueOne (low)
    assert step["targetValueOne"] == pytest.approx(pace_to_speed_mps(4.1))
    assert step["targetValueTwo"] == pytest.approx(pace_to_speed_mps(3.9))


def test_heart_rate_target_step_sorts_low_and_high():
    workout = build_running_workout(
        "Easy Run",
        [
            {
                "kind": "interval",
                "duration_seconds": 1800,
                "target_heart_rate_bpm": [160, 140],
            }
        ],
    )
    step = workout["workoutSegments"][0]["workoutSteps"][0]
    assert step["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert step["targetValueOne"] == 140
    assert step["targetValueTwo"] == 160


def test_repeat_block_builds_nested_group_with_continuing_step_order():
    workout = build_running_workout(
        "5x400m",
        [
            {"kind": "warmup", "duration_seconds": 600},
            {
                "kind": "repeat",
                "iterations": 5,
                "steps": [
                    {
                        "kind": "interval",
                        "distance_meters": 400,
                        "target_pace_min_per_km": [3.9, 4.1],
                    },
                    {"kind": "recovery", "duration_seconds": 90},
                ],
            },
            {"kind": "cooldown", "duration_seconds": 600},
        ],
    )

    steps = workout["workoutSegments"][0]["workoutSteps"]
    assert len(steps) == 3

    warmup, repeat_group, cooldown = steps
    assert warmup["stepOrder"] == 1
    assert repeat_group["type"] == "RepeatGroupDTO"
    assert repeat_group["stepOrder"] == 2
    assert repeat_group["numberOfIterations"] == 5
    assert repeat_group["endCondition"]["conditionTypeKey"] == "iterations"
    assert repeat_group["endConditionValue"] == 5

    interval, recovery = repeat_group["workoutSteps"]
    assert interval["stepOrder"] == 3
    assert recovery["stepOrder"] == 4
    assert cooldown["stepOrder"] == 5

    # estimated duration: warmup(600) + 5*(interval estimate + 90) + cooldown(600)
    interval_seconds = 400 * ((3.9 + 4.1) / 2) * 60.0 / 1000.0
    expected = 600 + 5 * (interval_seconds + 90) + 600
    assert workout["estimatedDurationInSecs"] == round(expected)


def test_repeat_block_requires_nonempty_steps():
    with pytest.raises(WorkoutBuilderError):
        build_running_workout(
            "Run", [{"kind": "repeat", "iterations": 5, "steps": []}]
        )


def test_repeat_block_requires_at_least_one_iteration():
    with pytest.raises(WorkoutBuilderError):
        build_running_workout(
            "Run",
            [
                {
                    "kind": "repeat",
                    "iterations": 0,
                    "steps": [{"kind": "interval", "duration_seconds": 60}],
                }
            ],
        )


def test_unknown_step_kind_rejected():
    with pytest.raises(WorkoutBuilderError):
        build_running_workout("Run", [{"kind": "sprint", "duration_seconds": 60}])

"""Build Garmin Connect workout JSON payloads from simple structured steps.

This targets the same undocumented workout-service schema the Garmin Connect
web/mobile apps use to save workouts, which is also what
``Garmin.upload_workout`` posts as-is. The step/target/condition ids come
from ``garminconnect.workout`` (bundled with the pinned ``garminconnect``
dependency). Two key strings are confirmed straight from that module's own
helpers: ``"time"`` (``create_warmup_step``) and ``"iterations"``
(``create_repeat_group``). The others (notably ``"distance"`` and
``"heart.rate.zone"``) aren't documented anywhere reachable from this
sandbox, so they're inferred from Garmin's own naming pattern (e.g.
``"speed.zone"``, ``"power.zone"`` are spelled out in that module's
comments). Sanity-check a workout in the Garmin Connect app after the first
real upload, and adjust here if a step doesn't render as expected.
"""

from __future__ import annotations

from typing import Any

SPORT_TYPE_RUNNING = {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1}

_STEP_TYPES = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4},
    "rest": {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5},
    "repeat": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
}

_NO_TARGET = {
    "workoutTargetTypeId": 1,
    "workoutTargetTypeKey": "no.target",
    "displayOrder": 1,
}
_HR_TARGET = {
    "workoutTargetTypeId": 4,
    "workoutTargetTypeKey": "heart.rate.zone",
    "displayOrder": 4,
}
_SPEED_TARGET = {
    "workoutTargetTypeId": 5,
    "workoutTargetTypeKey": "speed.zone",
    "displayOrder": 5,
}

_TIME_CONDITION = {
    "conditionTypeId": 2,
    "conditionTypeKey": "time",
    "displayOrder": 2,
    "displayable": True,
}
_DISTANCE_CONDITION = {
    "conditionTypeId": 1,
    "conditionTypeKey": "distance",
    "displayOrder": 1,
    "displayable": True,
}
_ITERATIONS_CONDITION = {
    "conditionTypeId": 7,
    "conditionTypeKey": "iterations",
    "displayOrder": 7,
    "displayable": False,
}

_EASY_PACE_MIN_PER_KM = 6.0  # fallback effort used only to estimate duration


class WorkoutBuilderError(ValueError):
    """Raised when the requested workout steps can't be turned into a payload."""


def pace_to_speed_mps(pace_min_per_km: float) -> float:
    """Convert a running pace (decimal minutes per km, e.g. 4.5 == 4:30/km)
    to speed in meters/second, the unit Garmin's speed-zone target uses."""
    if pace_min_per_km <= 0:
        raise WorkoutBuilderError("pace_min_per_km must be positive")
    return 1000.0 / (pace_min_per_km * 60.0)


def _step_type(kind: str) -> dict:
    try:
        return _STEP_TYPES[kind]
    except KeyError:
        raise WorkoutBuilderError(
            f"Unknown step kind {kind!r}; expected one of {sorted(_STEP_TYPES)}"
        ) from None


def _end_condition(step: dict) -> tuple[dict, float]:
    has_duration = "duration_seconds" in step
    has_distance = "distance_meters" in step
    if has_duration == has_distance:
        raise WorkoutBuilderError(
            "Each step needs exactly one of duration_seconds or distance_meters "
            f"(got: {step!r})"
        )
    if has_duration:
        return _TIME_CONDITION, float(step["duration_seconds"])
    return _DISTANCE_CONDITION, float(step["distance_meters"])


def _target(step: dict) -> tuple[dict, float | None, float | None]:
    pace_range = step.get("target_pace_min_per_km")
    hr_range = step.get("target_heart_rate_bpm")
    if pace_range and hr_range:
        raise WorkoutBuilderError("A step can't target both pace and heart rate")
    if pace_range:
        if len(pace_range) != 2:
            raise WorkoutBuilderError("target_pace_min_per_km needs exactly 2 values")
        low, high = sorted(pace_to_speed_mps(p) for p in pace_range)
        return _SPEED_TARGET, low, high
    if hr_range:
        if len(hr_range) != 2:
            raise WorkoutBuilderError("target_heart_rate_bpm needs exactly 2 values")
        low, high = sorted(float(b) for b in hr_range)
        return _HR_TARGET, low, high
    return _NO_TARGET, None, None


def _build_executable_step(step: dict, step_order: int) -> dict:
    end_condition, end_value = _end_condition(step)
    target_type, target_low, target_high = _target(step)
    result: dict[str, Any] = {
        "type": "ExecutableStepDTO",
        "stepOrder": step_order,
        "stepType": _step_type(step.get("kind", "")),
        "endCondition": end_condition,
        "endConditionValue": end_value,
        "targetType": target_type,
    }
    if target_low is not None:
        result["targetValueOne"] = target_low
        result["targetValueTwo"] = target_high
    if step.get("description"):
        result["description"] = step["description"]
    return result


def _estimate_step_seconds(step: dict) -> float:
    """Best-effort duration estimate, used only for estimatedDurationInSecs."""
    if "duration_seconds" in step:
        return float(step["duration_seconds"])
    distance = float(step.get("distance_meters", 0.0))
    pace_range = step.get("target_pace_min_per_km")
    pace = sum(pace_range) / len(pace_range) if pace_range else _EASY_PACE_MIN_PER_KM
    return distance * pace * 60.0 / 1000.0


class _StepOrder:
    """Sequential stepOrder counter, shared across a workout's full step tree
    (repeat groups consume one slot; their children keep counting after it)."""

    def __init__(self) -> None:
        self._next = 1

    def take(self) -> int:
        value = self._next
        self._next += 1
        return value


def _build_steps(steps: list[dict], order: _StepOrder) -> tuple[list[dict], float]:
    built: list[dict] = []
    total_seconds = 0.0
    for step in steps:
        if step.get("kind") == "repeat":
            repeat_order = order.take()
            child_steps, child_seconds = _build_steps(step.get("steps") or [], order)
            if not child_steps:
                raise WorkoutBuilderError("A repeat step needs a non-empty 'steps' list")
            iterations = int(step.get("iterations", 0))
            if iterations < 1:
                raise WorkoutBuilderError("A repeat step needs iterations >= 1")
            built.append(
                {
                    "type": "RepeatGroupDTO",
                    "stepOrder": repeat_order,
                    "stepType": _step_type("repeat"),
                    "numberOfIterations": iterations,
                    "workoutSteps": child_steps,
                    "endCondition": _ITERATIONS_CONDITION,
                    "endConditionValue": float(iterations),
                }
            )
            total_seconds += child_seconds * iterations
        else:
            built.append(_build_executable_step(step, order.take()))
            total_seconds += _estimate_step_seconds(step)
    return built, total_seconds


def build_running_workout(
    name: str, steps: list[dict], description: str | None = None
) -> dict:
    """Build a Garmin Connect running-workout JSON payload from simple steps.

    ``steps`` is a list where each item is either:
      - a plain step: ``{"kind": "warmup"|"cooldown"|"recovery"|"rest"|
        "interval", "duration_seconds": <float>}`` (or ``"distance_meters"``
        instead of ``"duration_seconds"``), optionally with
        ``"target_pace_min_per_km": [low, high]`` (decimal minutes per km,
        e.g. 4.5 == 4:30/km) or ``"target_heart_rate_bpm": [low, high]``.
      - a repeat block: ``{"kind": "repeat", "iterations": <int>,
        "steps": [...]}`` wrapping a list of plain steps to repeat.

    Raises ``WorkoutBuilderError`` on malformed input.
    """
    if not name or not name.strip():
        raise WorkoutBuilderError("Workout name is required")
    if not steps:
        raise WorkoutBuilderError("At least one step is required")

    built_steps, total_seconds = _build_steps(steps, _StepOrder())

    workout: dict[str, Any] = {
        "workoutName": name,
        "sportType": SPORT_TYPE_RUNNING,
        "estimatedDurationInSecs": round(total_seconds),
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": SPORT_TYPE_RUNNING,
                "workoutSteps": built_steps,
            }
        ],
    }
    if description:
        workout["description"] = description
    return workout

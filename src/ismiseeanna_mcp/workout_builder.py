"""Build Garmin Connect workout JSON payloads from simple structured steps.

This targets the same undocumented workout-service schema the Garmin Connect
web/mobile apps use to save workouts, which is also what
``Garmin.upload_workout`` posts as-is. The step/target/condition ids come
from ``garminconnect.workout`` (bundled with the pinned ``garminconnect``
dependency). Two key strings are confirmed straight from that module's own
helpers: ``"time"`` (``create_warmup_step``) and ``"iterations"``
(``create_repeat_group``). The others (notably ``"distance"`` and
``"heart.rate.zone"``) aren't documented anywhere reachable from this
sandbox, so they're inferred from Garmin's own naming pattern.

The pace target type is a confirmed exception, not an inference:
``garminconnect.workout``'s own ``TargetType`` constants list 5 as
``SPEED``/``speed.zone`` and (confusingly) 6 as ``OPEN``, but a real
pace-targeted step saved through the Garmin Connect web UI and read back via
``get_workout`` came back as ``workoutTargetTypeId: 6, workoutTargetTypeKey:
"pace.zone"`` - using id 5/"speed.zone" instead silently renders as "No
Target" in the UI despite the values being present. That same real example
also confirmed value order: ``targetValueOne`` holds the *faster* pace's
converted speed (the higher of the two, since speed and pace are inversely
related) and ``targetValueTwo`` the slower pace's - reversed from what
sorting the converted speeds ascending would give you.

Sanity-check a workout in the Garmin Connect app after any change here that
touches target values, and adjust if a step doesn't render as expected.
"""

from __future__ import annotations

import math
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
_PACE_TARGET = {
    "workoutTargetTypeId": 6,
    "workoutTargetTypeKey": "pace.zone",
    "displayOrder": 6,
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

# Sanity bounds on user/LLM-supplied step values. These aren't Garmin API
# limits (which aren't documented) - they exist so a malformed or malicious
# tool call fails with a clear WorkoutBuilderError instead of an uncaught
# RecursionError/OverflowError/TypeError, or a nonsensical payload silently
# reaching the real account.
_MAX_DURATION_SECONDS = 24 * 60 * 60  # 24 hours
_MAX_DISTANCE_METERS = 200_000  # 200 km
_MAX_ITERATIONS = 100
_MIN_PACE_MIN_PER_KM = 1.0
_MAX_PACE_MIN_PER_KM = 60.0
_MIN_HEART_RATE_BPM = 30
_MAX_HEART_RATE_BPM = 250


class WorkoutBuilderError(ValueError):
    """Raised when the requested workout steps can't be turned into a payload."""


def _finite_number(value: object, field_name: str) -> float:
    """Coerce ``value`` to a finite float, or raise WorkoutBuilderError."""
    if isinstance(value, bool):  # bool is a subclass of int; reject explicitly
        raise WorkoutBuilderError(f"{field_name} must be a number (got {value!r})")
    try:
        number = float(value)
    except (TypeError, ValueError) as e:
        raise WorkoutBuilderError(f"{field_name} must be a number (got {value!r})") from e
    if not math.isfinite(number):
        raise WorkoutBuilderError(f"{field_name} must be a finite number (got {value!r})")
    return number


def _bounded(value: object, field_name: str, min_value: float, max_value: float) -> float:
    """Validate ``value`` is a finite number within [min_value, max_value]."""
    number = _finite_number(value, field_name)
    if not (min_value <= number <= max_value):
        raise WorkoutBuilderError(
            f"{field_name} must be between {min_value} and {max_value} (got {number})"
        )
    return number


def _bounded_int(value: object, field_name: str, min_value: int, max_value: int) -> int:
    """Validate ``value`` is an integer (or integer-valued float, since JSON
    has no separate int type) within [min_value, max_value]."""
    if isinstance(value, bool):
        raise WorkoutBuilderError(f"{field_name} must be an integer (got {value!r})")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and value.is_integer():
        number = int(value)
    else:
        raise WorkoutBuilderError(f"{field_name} must be an integer (got {value!r})")
    if not (min_value <= number <= max_value):
        raise WorkoutBuilderError(
            f"{field_name} must be between {min_value} and {max_value} (got {number})"
        )
    return number


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
        value = _bounded(
            step["duration_seconds"], "duration_seconds", 1, _MAX_DURATION_SECONDS
        )
        return _TIME_CONDITION, value
    value = _bounded(step["distance_meters"], "distance_meters", 1, _MAX_DISTANCE_METERS)
    return _DISTANCE_CONDITION, value


def _target(step: dict) -> tuple[dict, float | None, float | None]:
    pace_range = step.get("target_pace_min_per_km")
    hr_range = step.get("target_heart_rate_bpm")
    if pace_range and hr_range:
        raise WorkoutBuilderError("A step can't target both pace and heart rate")
    if pace_range:
        if len(pace_range) != 2:
            raise WorkoutBuilderError("target_pace_min_per_km needs exactly 2 values")
        paces = [
            _bounded(p, "target_pace_min_per_km", _MIN_PACE_MIN_PER_KM, _MAX_PACE_MIN_PER_KM)
            for p in pace_range
        ]
        # Sort by pace (fast, then slow), *then* convert to speed - not the
        # other way around. Speed is inversely related to pace, so sorting
        # the converted speeds would put the slow pace's (lower) speed in
        # targetValueOne, which is backwards from what Garmin expects (see
        # module docstring).
        fast_pace, slow_pace = sorted(paces)
        return _PACE_TARGET, pace_to_speed_mps(fast_pace), pace_to_speed_mps(slow_pace)
    if hr_range:
        if len(hr_range) != 2:
            raise WorkoutBuilderError("target_heart_rate_bpm needs exactly 2 values")
        bpms = [
            _bounded(b, "target_heart_rate_bpm", _MIN_HEART_RATE_BPM, _MAX_HEART_RATE_BPM)
            for b in hr_range
        ]
        low, high = sorted(bpms)
        return _HR_TARGET, low, high
    return _NO_TARGET, None, None


def _build_executable_step(step: dict, step_order: int) -> dict:
    end_condition, end_value = _end_condition(step)
    target_type, target_value_one, target_value_two = _target(step)
    result: dict[str, Any] = {
        "type": "ExecutableStepDTO",
        "stepOrder": step_order,
        "stepType": _step_type(step.get("kind", "")),
        "endCondition": end_condition,
        "endConditionValue": end_value,
        "targetType": target_type,
    }
    if target_value_one is not None:
        result["targetValueOne"] = target_value_one
        result["targetValueTwo"] = target_value_two
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


def _build_steps(
    steps: list[dict], order: _StepOrder, in_repeat: bool = False
) -> tuple[list[dict], float]:
    if not isinstance(steps, list):
        raise WorkoutBuilderError(f"'steps' must be a list (got {steps!r})")

    built: list[dict] = []
    total_seconds = 0.0
    for step in steps:
        if not isinstance(step, dict):
            raise WorkoutBuilderError(f"Each step must be an object (got {step!r})")
        if step.get("kind") == "repeat":
            if in_repeat:
                raise WorkoutBuilderError(
                    "Repeat blocks can't be nested inside another repeat block"
                )
            repeat_order = order.take()
            child_steps, child_seconds = _build_steps(
                step.get("steps") or [], order, in_repeat=True
            )
            if not child_steps:
                raise WorkoutBuilderError("A repeat step needs a non-empty 'steps' list")
            iterations = _bounded_int(
                step.get("iterations", 0), "iterations", 1, _MAX_ITERATIONS
            )
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
    if not isinstance(steps, list) or not steps:
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

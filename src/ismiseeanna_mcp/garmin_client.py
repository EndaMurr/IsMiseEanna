"""Authenticated Garmin Connect client, shared across MCP tool calls."""

import os
import stat

from garminconnect import Garmin, GarminConnectAuthenticationError


class GarminClientError(RuntimeError):
    pass


def _resolve_token_store() -> str:
    """Resolve GARMINTOKENS to a real path, rejecting anything outside $HOME."""
    raw = os.environ.get("GARMINTOKENS", "~/.garminconnect")
    resolved = os.path.realpath(os.path.expanduser(raw))
    home = os.path.realpath(os.path.expanduser("~"))
    if os.path.commonpath([resolved, home]) != home:
        raise GarminClientError(
            f"GARMINTOKENS ({raw!r}) must resolve to a path under the home "
            "directory."
        )
    return resolved


TOKEN_STORE = _resolve_token_store()

_client: Garmin | None = None


def _secure_token_store() -> None:
    """Restrict the token cache to owner-only access."""
    if os.path.isdir(TOKEN_STORE):
        os.chmod(TOKEN_STORE, stat.S_IRWXU)
        for root, dirs, files in os.walk(TOKEN_STORE):
            for name in dirs:
                os.chmod(os.path.join(root, name), stat.S_IRWXU)
            for name in files:
                os.chmod(os.path.join(root, name), stat.S_IRUSR | stat.S_IWUSR)
    elif os.path.isfile(TOKEN_STORE):
        os.chmod(TOKEN_STORE, stat.S_IRUSR | stat.S_IWUSR)


def get_client() -> Garmin:
    """Return a logged-in Garmin client, resuming a cached session when possible.

    ``Garmin.login(tokenstore)`` handles both paths itself: it resumes from a
    cached token at ``tokenstore`` if one exists, and otherwise logs in with
    the constructor's email/password and saves the resulting token there.
    """
    global _client
    if _client is not None:
        return _client

    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not (email and password) and not os.path.exists(TOKEN_STORE):
        raise GarminClientError(
            "No cached Garmin session found and GARMIN_EMAIL/GARMIN_PASSWORD "
            "are not set. Set both env vars for the first login; the session "
            f"is then cached at {TOKEN_STORE} so future calls don't need the "
            "password."
        )

    client = Garmin(email=email, password=password)
    try:
        client.login(TOKEN_STORE)
    except GarminConnectAuthenticationError as e:
        raise GarminClientError(
            "Garmin login failed: invalid credentials or authentication was "
            "rejected. If this is the first run, set GARMIN_EMAIL and "
            "GARMIN_PASSWORD; the session is then cached at "
            f"{TOKEN_STORE} so future calls don't need the password."
        ) from e
    except Exception as e:
        raise GarminClientError(
            f"Garmin login failed unexpectedly ({type(e).__name__})."
        ) from e

    _secure_token_store()
    _client = client
    return _client


_STEP_KIND_TO_TYPE = {
    "warmup": (1, "warmup", 1),  # StepType.WARMUP
    "cooldown": (2, "cooldown", 2),  # StepType.COOLDOWN
    "interval": (3, "interval", 3),  # StepType.INTERVAL
    "recovery": (4, "recovery", 4),  # StepType.RECOVERY
}


def _build_step_target(step: dict) -> tuple[dict, float | None, float | None]:
    """Resolve a step's optional pace/heart-rate target into Garmin's target shape.

    Pace targets are converted to speed (m/s), since Garmin has no distinct
    "pace" target type — it uses the same speed-zone type watches show pace
    from. targetValueOne/targetValueTwo are undocumented by Garmin but are
    the field names every reverse-engineered workout-JSON writer (including
    this library's own wire format) uses for a target's lower/upper bound.
    """
    from garminconnect.workout import TargetType

    has_pace = "target_pace_min_per_km" in step or "target_pace_max_per_km" in step
    has_hr = "target_hr_min" in step or "target_hr_max" in step
    if has_pace and has_hr:
        raise GarminClientError(
            "Specify at most one of a pace target or a heart-rate target per step."
        )

    if has_pace:
        pace_min = step.get("target_pace_min_per_km")
        pace_max = step.get("target_pace_max_per_km")
        if pace_min is None or pace_max is None:
            raise GarminClientError(
                "Pace targets need both target_pace_min_per_km and "
                "target_pace_max_per_km (seconds per km)."
            )
        if pace_min <= 0 or pace_max <= 0:
            raise GarminClientError("target_pace_min_per_km/target_pace_max_per_km must be positive.")
        speeds = sorted([1000 / pace_min, 1000 / pace_max])
        return (
            {
                "workoutTargetTypeId": TargetType.SPEED,
                "workoutTargetTypeKey": "speed.zone",
                "displayOrder": 1,
            },
            speeds[0],
            speeds[1],
        )

    if has_hr:
        hr_min = step.get("target_hr_min")
        hr_max = step.get("target_hr_max")
        if hr_min is None or hr_max is None:
            raise GarminClientError(
                "Heart-rate targets need both target_hr_min and target_hr_max (bpm)."
            )
        return (
            {
                "workoutTargetTypeId": TargetType.HEART_RATE,
                "workoutTargetTypeKey": "heart.rate.zone",
                "displayOrder": 1,
            },
            min(hr_min, hr_max),
            max(hr_min, hr_max),
        )

    return (
        {
            "workoutTargetTypeId": TargetType.NO_TARGET,
            "workoutTargetTypeKey": "no.target",
            "displayOrder": 1,
        },
        None,
        None,
    )


def _estimate_step_seconds(step: dict) -> float:
    """Ballpark a step's duration for the workout's display total only — never gates the step."""
    duration = step.get("duration_seconds")
    if duration is not None:
        return duration
    distance = step.get("distance_meters")
    if distance is not None:
        return distance / 1000 * 360  # easy 6:00/km assumption, display only
    return 0.0


def _build_step(step: dict, order: int):
    from garminconnect.workout import ConditionType, ExecutableStep

    kind = step.get("kind")
    if kind not in _STEP_KIND_TO_TYPE:
        raise GarminClientError(
            f"Unknown step kind {kind!r}; expected one of {sorted(_STEP_KIND_TO_TYPE)}."
        )
    step_type_id, step_type_key, display_order = _STEP_KIND_TO_TYPE[kind]

    distance = step.get("distance_meters")
    duration = step.get("duration_seconds")
    if (distance is None) == (duration is None):
        raise GarminClientError(
            f"Step {order} ({kind}): specify exactly one of distance_meters or duration_seconds."
        )

    if distance is not None:
        end_condition = {
            "conditionTypeId": ConditionType.DISTANCE,
            "conditionTypeKey": "distance",
            "displayOrder": 2,
            "displayable": True,
        }
        end_condition_value = distance
    else:
        end_condition = {
            "conditionTypeId": ConditionType.TIME,
            "conditionTypeKey": "time",
            "displayOrder": 2,
            "displayable": True,
        }
        end_condition_value = duration

    target_type, target_value_one, target_value_two = _build_step_target(step)

    kwargs = dict(
        stepOrder=order,
        stepType={"stepTypeId": step_type_id, "stepTypeKey": step_type_key, "displayOrder": display_order},
        endCondition=end_condition,
        endConditionValue=end_condition_value,
        targetType=target_type,
    )
    if target_value_one is not None:
        kwargs["targetValueOne"] = target_value_one
        kwargs["targetValueTwo"] = target_value_two
    return ExecutableStep(**kwargs)


def build_structured_running_workout(name: str, steps: list[dict]) -> dict:
    """Build a multi-step running workout: warmup/interval/recovery/cooldown
    steps, each with its own end condition and an optional pace or
    heart-rate target, with one level of repeated interval blocks.

    Each entry in ``steps`` is either a plain step or a repeat block:

    Plain step (dict):
      - ``kind``: one of "warmup", "interval", "recovery", "cooldown" (required)
      - exactly one of ``distance_meters`` or ``duration_seconds`` (required)
      - at most one target, both bounds required together:
          ``target_pace_min_per_km`` / ``target_pace_max_per_km`` (seconds per km), or
          ``target_hr_min`` / ``target_hr_max`` (bpm)
        omit both for no target.

    Repeat block (dict): ``{"repeat": {"count": int, "steps": [plain step, ...]}}``
      — repeats the nested plain steps ``count`` times (e.g. 6x 400m @ pace
      with 200m recovery jog between reps). Nested repeats are not supported.

    NOTE: targetValueOne/targetValueTwo and the speed-zone target type are
    Garmin's undocumented internal wire format, reverse-engineered rather
    than officially specified — create one test workout and check it renders
    with the right pace/HR range in the Garmin Connect app before relying on
    it for real training.
    """
    if not steps:
        raise GarminClientError("Provide at least one step.")

    from garminconnect.workout import RunningWorkout, WorkoutSegment, create_repeat_group

    order = 1
    workout_steps: list = []
    total_seconds = 0.0

    for entry in steps:
        repeat_spec = entry.get("repeat")
        if repeat_spec is not None:
            count = repeat_spec.get("count")
            child_specs = repeat_spec.get("steps") or []
            if not isinstance(count, int) or count < 1:
                raise GarminClientError("repeat.count must be a positive integer.")
            if not child_specs:
                raise GarminClientError("repeat.steps must be a non-empty list.")

            child_steps = []
            block_seconds = 0.0
            for i, child in enumerate(child_specs, start=1):
                child_steps.append(_build_step(child, i))
                block_seconds += _estimate_step_seconds(child)

            workout_steps.append(
                create_repeat_group(iterations=count, workout_steps=child_steps, step_order=order)
            )
            total_seconds += block_seconds * count
        else:
            workout_steps.append(_build_step(entry, order))
            total_seconds += _estimate_step_seconds(entry)
        order += 1

    segment = WorkoutSegment(
        segmentOrder=1,
        sportType={"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
        workoutSteps=workout_steps,
    )
    workout = RunningWorkout(
        workoutName=name,
        estimatedDurationInSecs=round(total_seconds),
        workoutSegments=[segment],
    )
    return workout.to_dict()

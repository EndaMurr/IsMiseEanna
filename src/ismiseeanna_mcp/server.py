"""MCP server exposing Garmin Connect activity data as tools."""

import logging
import os
from collections.abc import Callable
from typing import TypeVar
from urllib.parse import urlparse

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl

from .garmin_client import get_client
from .workout_builder import WorkoutBuilderError, build_running_workout


def _build_mcp() -> FastMCP:
    """Build the FastMCP instance, wiring in WorkOS AuthKit as the OAuth
    authorization server when configured.

    Local stdio use is unaffected: with WORKOS_AUTHKIT_DOMAIN and
    MCP_RESOURCE_URL unset (the default), this returns a plain, unauthenticated
    FastMCP instance exactly as before. Both must be set to opt into running
    as an OAuth-protected resource server (see README's "Hosted deployment"
    section) - that's the mode a public streamable-http deployment should use.
    """
    authkit_domain = os.environ.get("WORKOS_AUTHKIT_DOMAIN")
    resource_url = os.environ.get("MCP_RESOURCE_URL")
    if not authkit_domain or not resource_url:
        return FastMCP("ismiseeanna-garmin")

    from .auth import WorkOSTokenVerifier

    # The mcp SDK's DNS-rebinding protection rejects any Host/Origin header
    # not on an explicit allowlist - which, left unset, means it rejects
    # *everything* once a reverse proxy (Caddy/Fly's edge) forwards the real
    # public hostname through. Derive the allowlist from MCP_RESOURCE_URL so
    # this doesn't need yet another env var kept in sync with it.
    resource_host = urlparse(resource_url).netloc
    resource_origin = f"{urlparse(resource_url).scheme}://{resource_host}"

    return FastMCP(
        "ismiseeanna-garmin",
        token_verifier=WorkOSTokenVerifier(authkit_domain, resource_url),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(authkit_domain),
            resource_server_url=AnyHttpUrl(resource_url),
            required_scopes=[],
        ),
        transport_security=TransportSecuritySettings(
            allowed_hosts=[resource_host, f"{resource_host}:*"],
            allowed_origins=[resource_origin],
        ),
        host=os.environ.get("MCP_HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
    )


mcp = _build_mcp()

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _call_client(fn: Callable[[], T]) -> T:
    """Call a Garmin Connect client method, sanitizing any exception before
    it reaches the MCP client - the same discipline garmin_client.get_client()
    already applies to login failures. garminconnect's own exceptions often
    embed request URLs/response bodies, which shouldn't be echoed back
    verbatim. The full exception is still logged server-side (e.g. to
    journalctl under systemd) - MCP tool errors return in a normal 200
    JSON-RPC response, not an HTTP error, so without this there'd be no
    server-side record of what actually failed.
    """
    try:
        return fn()
    except Exception as e:
        logger.exception("Garmin Connect request failed")
        raise RuntimeError(f"Garmin Connect request failed ({type(e).__name__}).") from e


def _summarize(activity: dict) -> dict:
    return {
        "activityId": activity.get("activityId"),
        "name": activity.get("activityName"),
        "type": (activity.get("activityType") or {}).get("typeKey"),
        "startTimeLocal": activity.get("startTimeLocal"),
        "distanceMeters": activity.get("distance"),
        "durationSeconds": activity.get("duration"),
        "calories": activity.get("calories"),
        "averageHR": activity.get("averageHR"),
    }


def _estimate_recovery_pace_min_per_km() -> tuple[float, float] | None:
    """Estimate an easy/recovery pace range from recent running history.

    Recovery days are naturally an athlete's slowest runs, so this takes the
    slowest third (by pace) of their last 20 running activities and returns a
    modest range around that average. Best-effort: returns None (rather than
    raising) if the history lookup fails or there isn't enough running
    history to estimate from, since this is a fallback default, not something
    that should ever block workout creation.
    """
    try:
        activities = get_client().get_activities(0, 20)
    except Exception:
        return None

    paces = []
    for activity in activities:
        type_key = (activity.get("activityType") or {}).get("typeKey") or ""
        if "running" not in type_key:
            continue
        distance = activity.get("distance")
        duration = activity.get("duration")
        if not distance or not duration:
            continue
        pace = (duration / 60) / (distance / 1000)
        if pace > 0:
            paces.append(pace)

    if len(paces) < 3:
        return None

    paces.sort()
    slowest_third = paces[-max(1, len(paces) // 3) :]
    avg = sum(slowest_third) / len(slowest_third)
    return (round(avg - 0.15, 2), round(avg + 0.15, 2))


def _normalize_standalone_recovery_steps(steps: list[dict]) -> list[dict]:
    """Reinterpret a top-level "recovery" step as a plain easy "interval"
    step instead - Garmin Connect's "Run" step type, not "Recover".

    "recovery" only makes sense as the jog/rest portion *between* hard
    efforts inside a repeat block; a step at the top level (outside any
    repeat) can't be "recovering" from anything, so "recovery" there is
    always a mismodeled standalone easy/recovery run. This is a structural
    rule, not a judgment call for the LLM to get right each time - confirmed
    against a real "Run" step (stepTypeId 3 / "interval") saved through
    Garmin Connect's own UI and read back via get_workout.

    Only rewrites top-level steps. A "recovery" step nested inside a repeat
    block is left untouched, since that's exactly the context where the
    kind is meaningful.
    """

    def normalize(step: dict) -> dict:
        if step.get("kind") == "recovery":
            return {**step, "kind": "interval", "effort": step.get("effort", "easy")}
        return step

    return [normalize(step) for step in steps]


def _fill_easy_pace_defaults(steps: list[dict]) -> list[dict]:
    """Fill in a target_pace_min_per_km, estimated from recent running
    history, for any step that needs an easy/recovery pace but has neither a
    pace nor an HR target of its own.

    This applies to "recovery"-kind steps (the jog/rest portions between hard
    efforts) and to any step explicitly marked "effort": "easy" regardless of
    kind - the latter covers a whole easy/recovery run, which is a standalone
    "interval" step, not a "recovery" one (see create_running_workout's
    docstring). It deliberately does *not* apply to untagged "interval" steps
    in general, since those are also used for hard efforts (e.g. 5x400m at
    race pace) that must never get an easy-pace default.

    The estimate is computed at most once per call (even across multiple
    qualifying steps/repeat blocks) and only when actually needed.
    """
    state = {"estimate": None, "computed": False}

    def needs_easy_pace(step: dict) -> bool:
        if "target_pace_min_per_km" in step or "target_heart_rate_bpm" in step:
            return False
        return step.get("kind") == "recovery" or step.get("effort") == "easy"

    def fill(step: dict) -> dict:
        if step.get("kind") == "repeat":
            return {**step, "steps": [fill(s) for s in step.get("steps", [])]}
        if needs_easy_pace(step):
            if not state["computed"]:
                state["estimate"] = _estimate_recovery_pace_min_per_km()
                state["computed"] = True
            if state["estimate"] is not None:
                return {**step, "target_pace_min_per_km": list(state["estimate"])}
        return step

    return [fill(step) for step in steps]


@mcp.tool()
def list_activities(limit: int = 20, start: int = 0) -> list[dict]:
    """List recent Garmin activities, most recent first, with basic summary info."""
    activities = _call_client(lambda: get_client().get_activities(start, limit))
    return [_summarize(a) for a in activities]


@mcp.tool()
def search_activities_by_date(
    start_date: str, end_date: str, activity_type: str | None = None
) -> list[dict]:
    """Find activities between two dates (YYYY-MM-DD), optionally filtered by activity type."""
    activities = _call_client(
        lambda: get_client().get_activities_by_date(start_date, end_date, activity_type)
    )
    return [_summarize(a) for a in activities]


@mcp.tool()
def get_activity_details(activity_id: int) -> dict:
    """Get full details (metrics, splits summary, etc.) for one activity by its Garmin activity ID."""
    return _call_client(lambda: get_client().get_activity_details(activity_id))


@mcp.tool()
def get_activity_splits(activity_id: int) -> dict:
    """Get lap/split data for one activity by its Garmin activity ID."""
    return _call_client(lambda: get_client().get_activity_splits(activity_id))


@mcp.tool()
def get_activity_weather(activity_id: int) -> dict:
    """Get recorded weather conditions for one activity by its Garmin activity ID."""
    return _call_client(lambda: get_client().get_activity_weather(activity_id))


@mcp.tool()
def get_activity_gear(activity_id: int) -> dict:
    """Get the gear (shoes, bike, etc.) logged against one activity by its Garmin activity ID."""
    return _call_client(lambda: get_client().get_activity_gear(activity_id))


@mcp.tool()
def get_activity_hr_zones(activity_id: int) -> dict:
    """Get time spent in each heart rate zone for one activity by its Garmin activity ID."""
    return _call_client(lambda: get_client().get_activity_hr_in_timezones(activity_id))


@mcp.tool()
def get_personal_records() -> dict:
    """Get the current user's personal records (e.g. fastest 5K, longest run)."""
    return _call_client(lambda: get_client().get_personal_record())


@mcp.tool()
def get_sleep_data(date: str) -> dict:
    """Get sleep data for one date (YYYY-MM-DD)."""
    return _call_client(lambda: get_client().get_sleep_data(date))


@mcp.tool()
def get_stress_data(date: str) -> dict:
    """Get stress level data for one date (YYYY-MM-DD)."""
    return _call_client(lambda: get_client().get_stress_data(date))


@mcp.tool()
def get_body_battery(date: str) -> list[dict]:
    """Get Body Battery (energy level) data for one date (YYYY-MM-DD)."""
    return _call_client(lambda: get_client().get_body_battery(date))


@mcp.tool()
def get_hrv_data(date: str) -> dict | None:
    """Get heart rate variability (HRV) data for one date (YYYY-MM-DD)."""
    return _call_client(lambda: get_client().get_hrv_data(date))


@mcp.tool()
def get_resting_heart_rate(date: str) -> dict:
    """Get resting heart rate for one date (YYYY-MM-DD)."""
    return _call_client(lambda: get_client().get_rhr_day(date))


@mcp.tool()
def get_training_readiness(date: str) -> dict:
    """Get training readiness score and its contributing factors for one date (YYYY-MM-DD)."""
    return _call_client(lambda: get_client().get_training_readiness(date))


@mcp.tool()
def get_training_status(date: str) -> dict:
    """Get training status (e.g. productive, peaking, detraining) for one date (YYYY-MM-DD)."""
    return _call_client(lambda: get_client().get_training_status(date))


@mcp.tool()
def get_max_metrics(date: str) -> dict:
    """Get fitness age and VO2 max metrics for one date (YYYY-MM-DD)."""
    return _call_client(lambda: get_client().get_max_metrics(date))


@mcp.tool()
def get_race_predictions() -> dict:
    """Get predicted race times for the 5K, 10K, half marathon, and marathon, as of today."""
    return _call_client(lambda: get_client().get_race_predictions())


@mcp.tool()
def get_endurance_score(date: str) -> dict:
    """Get endurance score for one date (YYYY-MM-DD)."""
    return _call_client(lambda: get_client().get_endurance_score(date))


def _summarize_workout(workout: dict) -> dict:
    return {
        "workoutId": workout.get("workoutId"),
        "name": workout.get("workoutName"),
        "sportType": (workout.get("sportType") or {}).get("sportTypeKey"),
        "estimatedDurationInSecs": workout.get("estimatedDurationInSecs"),
        "updatedDate": workout.get("updatedDate"),
    }


@mcp.tool()
def list_workouts(limit: int = 20, start: int = 0) -> list[dict]:
    """List saved Garmin workouts, most recently updated first."""
    workouts = _call_client(lambda: get_client().get_workouts(start, limit))
    return [_summarize_workout(w) for w in workouts]


@mcp.tool()
def get_workout(workout_id: int) -> dict:
    """Get the full step-by-step definition of one saved workout by its Garmin workout ID."""
    return _call_client(lambda: get_client().get_workout_by_id(workout_id))


@mcp.tool()
def delete_workout(workout_id: int) -> str:
    """Delete a saved workout from the Garmin workout library by its Garmin workout ID.

    Looks the workout up first, so the deletion is tied to a real, currently
    saved workout (and its name) rather than an arbitrary, unverified ID.
    """
    workout = _call_client(lambda: get_client().get_workout_by_id(workout_id))
    name = workout.get("workoutName") or "workout"
    _call_client(lambda: get_client().delete_workout(workout_id))
    return f"Deleted workout {workout_id} ({name!r})"


@mcp.tool()
def create_running_workout(
    name: str,
    steps: list[dict],
    description: str | None = None,
    date: str | None = None,
) -> dict:
    """Create and save a structured running workout on Garmin Connect.

    Translate the user's natural-language workout description into a list
    of `steps` yourself, then call this tool - there is no separate parsing
    step. Each item in `steps` is one of:

      - A plain step: {"kind": "warmup"|"cooldown"|"recovery"|"rest"|
        "interval", "duration_seconds": <float>} (or "distance_meters"
        instead of "duration_seconds"), optionally with
        "target_pace_min_per_km": [low, high] (decimal minutes per km, e.g.
        4.5 == 4:30/km) or "target_heart_rate_bpm": [low, high]. Prefer
        pace over heart rate by default - only use target_heart_rate_bpm
        if the user specifically asks for a heart-rate-based target. Use
        "recovery" for a whole standalone easy/recovery run as well as for
        the jog/rest portion between hard efforts inside a repeat block -
        both read equally naturally in plain English, and this tool
        reinterprets a top-level "recovery" step as Garmin's "Run" step type
        automatically (only "recovery" steps *inside* a repeat block render
        as Garmin's "Recover" type, which is what that's actually for).
      - A repeat block: {"kind": "repeat", "iterations": <int>,
        "steps": [...]} wrapping a list of plain steps (e.g. an interval
        plus its recovery) to repeat. Repeat blocks can't be nested.

    Example - "10 min warmup, 5x400m at 5k pace (~4:00/km) with 90s jog
    recovery, 10 min cooldown":
        steps=[
            {"kind": "warmup", "duration_seconds": 600},
            {"kind": "repeat", "iterations": 5, "steps": [
                {"kind": "interval", "distance_meters": 400,
                 "target_pace_min_per_km": [3.9, 4.1]},
                {"kind": "recovery", "duration_seconds": 90},
            ]},
            {"kind": "cooldown", "duration_seconds": 600},
        ]

    Example - "an easy recovery 5k tomorrow", with no pace given:
        steps=[{"kind": "recovery", "distance_meters": 5000}]

    Pass `date` (YYYY-MM-DD) to also schedule the new workout onto the
    Garmin Connect calendar for that date in the same call - equivalent to
    calling schedule_workout afterwards with the returned workoutId.

    A "recovery"-kind step given without an explicit pace or HR target
    automatically gets a pace estimated from the user's recent running
    history (the slowest third of their last 20 runs) - you don't need to
    look this up yourself for those. It's worth a one-line mention in your
    reply so the user can sanity-check the pace it picked. Skip this if the
    user already gave a pace/HR target, asked for no target at all (e.g. a
    plain rest step), or has told you in this conversation that they prefer
    HR-based targets generally.

    Before declining to create/schedule something because you believe it
    already exists (e.g. "already scheduled for that date"), re-check with
    a fresh call to list_scheduled_workouts/list_workouts rather than
    relying on an earlier turn's result - the user may have changed or
    deleted things directly in Garmin Connect since then, outside this
    conversation.
    """
    steps = _normalize_standalone_recovery_steps(steps)
    steps = _fill_easy_pace_defaults(steps)
    try:
        workout_json = build_running_workout(name, steps, description)
    except WorkoutBuilderError as e:
        raise ValueError(str(e)) from e
    created = _call_client(lambda: get_client().upload_workout(workout_json))
    if date:
        workout_id = created.get("workoutId")
        if workout_id is None:
            raise RuntimeError(
                "Workout was created but Garmin didn't return a workoutId, so "
                "it couldn't be scheduled. Use schedule_workout once you know "
                "the workout's ID (e.g. from list_workouts)."
            )
        scheduled = _call_client(lambda: get_client().schedule_workout(workout_id, date))
        created = {**created, "scheduled": scheduled}
    return created


@mcp.tool()
def schedule_workout(workout_id: int, date: str) -> dict:
    """Schedule a saved workout onto a specific date (YYYY-MM-DD) on the
    Garmin Connect calendar. `workout_id` is the workout template's own ID
    (e.g. from create_running_workout's result or list_workouts), not a
    scheduled-workout ID."""
    return _call_client(lambda: get_client().schedule_workout(workout_id, date))


@mcp.tool()
def unschedule_workout(scheduled_workout_id: int) -> str:
    """Remove a scheduled workout from the Garmin Connect calendar without
    deleting the underlying workout template. `scheduled_workout_id` is the
    ID of the calendar entry (e.g. from schedule_workout's or
    list_scheduled_workouts' result), not the workout template's own ID."""
    _call_client(lambda: get_client().unschedule_workout(scheduled_workout_id))
    return f"Removed scheduled workout {scheduled_workout_id} from the calendar"


@mcp.tool()
def list_scheduled_workouts(year: int, month: int) -> dict:
    """List workouts scheduled on the Garmin Connect calendar for one month
    (month: 1-12)."""
    return _call_client(lambda: get_client().get_scheduled_workouts(year, month))


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()

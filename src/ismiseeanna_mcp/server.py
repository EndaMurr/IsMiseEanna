"""MCP server exposing Garmin Connect activity data as tools."""

import logging
import os
from collections.abc import Callable
from datetime import date
from typing import TypeVar
from urllib.parse import urlparse

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse

from . import onboarding
from .garmin_client import (
    GarminClientError,
    _extract_hrv,
    _extract_training_readiness,
    _n_day_trend,
    disconnect_user,
    get_client,
    summarize_activity,
)
from .plan_generator import generate_marathon_plan as _generate_marathon_plan
from .plan_progress import build_plan_progress as _build_plan_progress
from .realignment import _week_range, build_weekly_check_in
from .workout_builder import (
    WorkoutBuilderError,
    build_indoor_cycling_workout,
    build_running_workout,
)


# Sent to any connecting MCP client as server-level guidance (part of the
# initialize response) - this is what lets Claude walk a brand-new hosted
# user through connecting their own Garmin account on its own, without
# needing a separately-maintained set of human instructions kept in sync.
_HOSTED_INSTRUCTIONS = (
    "This server gives access to the connected user's own Garmin Connect "
    "data (activities, sleep, recovery, training plans, workout scheduling). "
    "Each person who added this connector has their own separate Garmin "
    "account, fully isolated from everyone else's.\n\n"
    "If any tool call fails with a message about the Garmin account not "
    "being connected yet, that means this specific user hasn't linked their "
    "own Garmin account to this server - it's not an error to work around. "
    "In that case, call start_garmin_connection and tell the user to open "
    "the link it returns in their own browser. Make clear they should never "
    "type their Garmin email or password directly into this chat - the link "
    "takes them to this server's own page instead, specifically so their "
    "password never sits in claude.ai's conversation history. If their "
    "Garmin account has MFA enabled, that page will ask for the code as a "
    "second step.\n\n"
    "If a user wants to revoke access, call disconnect_garmin_account."
)


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
        instructions=_HOSTED_INSTRUCTIONS,
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

# Multi-tenant onboarding (start_garmin_connection, disconnect_garmin_account,
# the /connect routes) only makes sense once WorkOS auth is actually wired up
# - local stdio mode keeps today's exact single-account tool list and route
# table, unchanged. Mirrors _build_mcp()'s own check rather than threading a
# value out of it, so _build_mcp()'s tested return-a-FastMCP-instance
# contract doesn't change.
_HOSTED = bool(os.environ.get("WORKOS_AUTHKIT_DOMAIN")) and bool(
    os.environ.get("MCP_RESOURCE_URL")
)
_RESOURCE_ORIGIN = None
if _HOSTED:
    _resource_url = os.environ["MCP_RESOURCE_URL"]
    _RESOURCE_ORIGIN = f"{urlparse(_resource_url).scheme}://{urlparse(_resource_url).netloc}"


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
    except GarminClientError:
        # Already a safe, actionable message (e.g. GarminNotConnectedError's
        # "call start_garmin_connection") - don't flatten it into a generic
        # RuntimeError below. get_client() is called *inside* fn() at every
        # call site, so this needs to be checked before the catch-all.
        raise
    except Exception as e:
        logger.exception("Garmin Connect request failed")
        raise RuntimeError(f"Garmin Connect request failed ({type(e).__name__}).") from e


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
    return [summarize_activity(a) for a in activities]


@mcp.tool()
def search_activities_by_date(
    start_date: str, end_date: str, activity_type: str | None = None
) -> list[dict]:
    """Find activities between two dates (YYYY-MM-DD), optionally filtered by activity type."""
    activities = _call_client(
        lambda: get_client().get_activities_by_date(start_date, end_date, activity_type)
    )
    return [summarize_activity(a) for a in activities]


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


@mcp.tool()
def generate_marathon_plan(
    race_date: str, current_weekly_km: float, strategy: str = "aggressive"
) -> list[dict]:
    """Generate a periodized marathon training plan from today through race day.

    Uses the user's own Garmin race-time predictions to set training paces
    (no guessed numbers). Returns a preview only — nothing is created or
    scheduled on the Garmin calendar; each session's "steps" can be passed
    to create_running_workout and the result's workoutId to schedule_workout
    once the plan has been reviewed.

    - "race_date": YYYY-MM-DD, must be in the future
    - "current_weekly_km": recent typical (not peak) weekly running volume
    - "strategy": "aggressive" (ramp toward ~120% of current volume) or
      "conservative" (hold near current volume); weekly growth during the
      build phase is capped at +10%/week either way
    """
    race_predictions = _call_client(lambda: get_client().get_race_predictions())
    return _generate_marathon_plan(race_date, current_weekly_km, race_predictions, strategy)


def _fetch_scheduled_for_week(week_start: date, week_end: date) -> list[dict]:
    """Fetch and normalize Garmin calendar items for the given Mon-Sun week,
    for reuse by get_weekly_check_in and get_plan_progress.
    """
    months = {(week_start.year, week_start.month), (week_end.year, week_end.month)}
    calendar_items = []
    for year, month in months:
        response = _call_client(
            lambda year=year, month=month: get_client().get_scheduled_workouts(year, month)
        )
        calendar_items.extend((response or {}).get("calendarItems") or [])

    return [
        {
            "date": item.get("date"),
            "name": item.get("title") or item.get("workoutName"),
            "scheduledWorkoutId": item.get("id"),
            "workoutId": item.get("workoutId"),
        }
        for item in calendar_items
        if item.get("date")
    ]


@mcp.tool()
def get_weekly_check_in() -> dict:
    """Compare this week's scheduled Garmin-calendar sessions against what you
    actually completed, plus the recent training-readiness/HRV trend.

    Read-only: this never touches the calendar, so it's safe to run alongside
    any plan already scheduled there (Runna's or otherwise) — it doesn't
    matter which app put a session on the calendar, only whether an activity
    shows up near that date. Returns data to interpret, not a canned
    recommendation: sessionsMissed, and whether readiness or HRV has been
    sustained-suppressed for the last few days, are worth reading together
    with what's actually on the plan for the coming week.

    Each scheduled item also carries its scheduledWorkoutId/workoutId, so if
    a missed or upcoming session is worth moving (e.g. easing a hard day
    back given suppressed readiness), pass those straight to
    move_scheduled_workout rather than looking them up again.

    NOTE: calendar-item field names ("date"/"title") are a best-effort
    reading of Garmin's undocumented calendar response; if scheduled-session
    names or dates look wrong, verify against the real Garmin Connect app.
    """
    week_start, week_end = _week_range()
    scheduled = _fetch_scheduled_for_week(week_start, week_end)

    # No activity-type filter: the calendar this compares against can (and
    # regularly does) schedule non-running sessions too - a "Strength" day
    # would never be found as completed if this only fetched running
    # activities, showing a real completed session as missed instead.
    activities = _call_client(
        lambda: get_client().get_activities_by_date(
            week_start.isoformat(), week_end.isoformat(), None
        )
    )
    completed = [summarize_activity(a) for a in activities]

    recovery_trend = {
        "trainingReadiness": _n_day_trend(
            get_client().get_training_readiness, _extract_training_readiness
        ),
        "hrv": _n_day_trend(get_client().get_hrv_data, _extract_hrv),
    }

    return build_weekly_check_in(scheduled, completed, recovery_trend)


@mcp.tool()
def get_plan_progress(race_date: str) -> dict:
    """Figure out which week of your Runna-style training plan you're in,
    and how many weeks remain until race day.

    Reads this week's Garmin-calendar session names for a "W<n> <Day>
    <Type> - <detail>" convention (Runna's naming pattern, e.g. "W6 Tue
    Tempo - 2km Repeats") to determine the current week, then combines that
    with `race_date` (YYYY-MM-DD) to compute weeksRemaining and totalWeeks.

    currentWeek/totalWeeks come back null (not an error) if this week has
    no session matching that convention — a rest week, a non-Runna plan, or
    no plan at all all look identical from calendar data alone.

    Raises a ValueError if race_date isn't a valid YYYY-MM-DD date.
    """
    week_start, week_end = _week_range()
    scheduled = _fetch_scheduled_for_week(week_start, week_end)
    return _build_plan_progress(scheduled, race_date)


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
def create_indoor_cycling_workout(
    name: str,
    steps: list[dict],
    description: str | None = None,
    date: str | None = None,
) -> dict:
    """Create and save a structured indoor cycling workout on Garmin Connect.

    Same step schema as create_running_workout, except there's no pace
    target for cycling - use "target_heart_rate_bpm": [low, high] instead,
    or omit a target entirely. Each item in `steps` is one of:

      - A plain step: {"kind": "warmup"|"cooldown"|"recovery"|"rest"|
        "interval", "duration_seconds": <float>} (or "distance_meters"
        instead of "duration_seconds"), optionally with
        "target_heart_rate_bpm": [low, high]. Use "recovery" for a whole
        standalone easy/recovery ride as well as for the easy portion
        between hard efforts inside a repeat block - see
        create_running_workout's docstring for why that's the same
        underlying Garmin step type either way.
      - A repeat block: {"kind": "repeat", "iterations": <int>,
        "steps": [...]} wrapping a list of plain steps (e.g. an interval
        plus its recovery) to repeat. Repeat blocks can't be nested.

    Example - "10 min warmup, 4x5min hard with 3min easy recovery, 10 min
    cooldown":
        steps=[
            {"kind": "warmup", "duration_seconds": 600},
            {"kind": "repeat", "iterations": 4, "steps": [
                {"kind": "interval", "duration_seconds": 300,
                 "target_heart_rate_bpm": [155, 165]},
                {"kind": "recovery", "duration_seconds": 180},
            ]},
            {"kind": "cooldown", "duration_seconds": 600},
        ]

    Pass `date` (YYYY-MM-DD) to also schedule the new workout onto the
    Garmin Connect calendar for that date in the same call.

    Before declining to create/schedule something because you believe it
    already exists, re-check with a fresh call to
    list_scheduled_workouts/list_workouts rather than relying on an
    earlier turn's result - the user may have changed or deleted things
    directly in Garmin Connect since then, outside this conversation.
    """
    steps = _normalize_standalone_recovery_steps(steps)
    try:
        workout_json = build_indoor_cycling_workout(name, steps, description)
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
def move_scheduled_workout(scheduled_workout_id: int, workout_id: int, new_date: str) -> dict:
    """Move a scheduled workout to a new date, keeping its exact original
    definition (pace targets, structure, etc.) unchanged - only the date
    moves. This works regardless of which app scheduled the session
    originally (Runna, ismiseeanna, or manual) - Garmin's calendar has no
    concept of which app a workout came from.

    Use this instead of unschedule_workout + create_running_workout/
    schedule_workout whenever the request is to shift an *existing* session
    to a different day (e.g. "move Friday's long run to Saturday") - it
    guarantees the moved session still asks for exactly what it did before,
    rather than risking a rebuilt approximation of it. Only fall back to
    creating a new workout if the user actually wants the session's content
    to change too (different distance, pace, structure), not just its date.

    `scheduled_workout_id` is the calendar entry's own ID and `workout_id`
    is the underlying saved workout template's ID - both are on the same
    item in list_scheduled_workouts'/get_weekly_check_in's results (as
    `scheduledWorkoutId` and `workoutId` respectively).

    A session pushed by another app (Runna's own sync, for example) can get
    re-created by that app later - mention this to the user the first time
    they move one of those, since it's not something this project controls.
    """
    _call_client(lambda: get_client().unschedule_workout(scheduled_workout_id))
    return _call_client(lambda: get_client().schedule_workout(workout_id, new_date))


@mcp.tool()
def list_scheduled_workouts(year: int, month: int) -> dict:
    """List workouts scheduled on the Garmin Connect calendar for one month
    (month: 1-12)."""
    return _call_client(lambda: get_client().get_scheduled_workouts(year, month))


def _connect_result_response(token: str, result: dict) -> HTMLResponse:
    headers = {"Cache-Control": "no-store"}
    status = result["status"]
    if status == "connected":
        return HTMLResponse(
            onboarding.render_result(
                True, "Garmin account connected. You can close this page and return to Claude."
            ),
            headers=headers,
        )
    if status == "mfa_required":
        return HTMLResponse(onboarding.render_mfa_form(token), headers=headers)
    if status == "invalid_token":
        return HTMLResponse(onboarding.render_invalid_token(), status_code=404, headers=headers)
    if status == "too_many_attempts":
        return HTMLResponse(
            onboarding.render_result(
                False, "Too many incorrect codes. Ask Claude to run start_garmin_connection again."
            ),
            headers=headers,
        )
    # "error" - re-render whichever form the session is still waiting on
    message = result.get("message", "Something went wrong.")
    if onboarding.get_session_state(token) == "awaiting_mfa":
        return HTMLResponse(onboarding.render_mfa_form(token, error=message), headers=headers)
    return HTMLResponse(onboarding.render_credentials_form(token, error=message), headers=headers)


if _HOSTED:
    from .garmin_client import _user_token_path

    @mcp.tool()
    def start_garmin_connection() -> dict:
        """Link your own Garmin Connect account to this server.

        Returns a one-time link to open in your own browser - open it there,
        never paste your Garmin email/password directly into this chat. The
        link expires in 15 minutes and can only be used once.

        Safe to call again if you're not sure whether you're already
        connected; returns {"status": "already_connected"} instead of a new
        link in that case.
        """
        access_token = get_access_token()
        if access_token is None or not access_token.subject:
            raise GarminClientError("No authenticated identity on this request.")
        user_id = access_token.subject

        if os.path.exists(_user_token_path(user_id)):
            return {"status": "already_connected"}

        token = onboarding.create_session(user_id)
        return {
            "status": "action_required",
            "connect_url": f"{_RESOURCE_ORIGIN}/connect?token={token}",
            "expires_in_minutes": 15,
            "instructions": (
                "Open this link in your own browser to connect your Garmin "
                "account - never paste your Garmin password into this chat."
            ),
        }

    @mcp.tool()
    def disconnect_garmin_account() -> str:
        """Disconnect your Garmin account from this server, deleting your
        stored session. Any tool call afterward will ask you to reconnect
        via start_garmin_connection."""
        access_token = get_access_token()
        if access_token is None or not access_token.subject:
            raise GarminClientError("No authenticated identity on this request.")
        disconnect_user(access_token.subject)
        return "Garmin account disconnected."

    @mcp.custom_route("/connect", methods=["GET"])
    async def connect_page(request: Request) -> HTMLResponse:
        token = request.query_params.get("token", "")
        state = onboarding.get_session_state(token)
        headers = {"Cache-Control": "no-store"}
        if state == "awaiting_credentials":
            return HTMLResponse(onboarding.render_credentials_form(token), headers=headers)
        if state == "awaiting_mfa":
            return HTMLResponse(onboarding.render_mfa_form(token), headers=headers)
        return HTMLResponse(onboarding.render_invalid_token(), status_code=404, headers=headers)

    @mcp.custom_route("/connect/submit", methods=["POST"])
    async def connect_submit(request: Request) -> HTMLResponse:
        form = await request.form()
        token = str(form.get("token", ""))
        email = str(form.get("email", ""))
        password = str(form.get("password", ""))
        result = onboarding.submit_credentials(token, email, password)
        return _connect_result_response(token, result)

    @mcp.custom_route("/connect/mfa", methods=["POST"])
    async def connect_mfa(request: Request) -> HTMLResponse:
        form = await request.form()
        token = str(form.get("token", ""))
        mfa_code = str(form.get("mfa_code", ""))
        result = onboarding.submit_mfa(token, mfa_code)
        return _connect_result_response(token, result)


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()

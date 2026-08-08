"""MCP server exposing Garmin Connect activity data as tools."""

from collections.abc import Callable
from typing import TypeVar

from mcp.server.fastmcp import FastMCP

from .garmin_client import get_client
from .workout_builder import WorkoutBuilderError, build_running_workout

mcp = FastMCP("ismiseeanna-garmin")

T = TypeVar("T")


def _call_client(fn: Callable[[], T]) -> T:
    """Call a Garmin Connect client method, sanitizing any exception before
    it reaches the MCP client - the same discipline garmin_client.get_client()
    already applies to login failures. garminconnect's own exceptions often
    embed request URLs/response bodies, which shouldn't be echoed back
    verbatim."""
    try:
        return fn()
    except Exception as e:
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
    name: str, steps: list[dict], description: str | None = None
) -> dict:
    """Create and save a structured running workout on Garmin Connect.

    Translate the user's natural-language workout description into a list
    of `steps` yourself, then call this tool - there is no separate parsing
    step. Each item in `steps` is one of:

      - A plain step: {"kind": "warmup"|"cooldown"|"recovery"|"rest"|
        "interval", "duration_seconds": <float>} (or "distance_meters"
        instead of "duration_seconds"), optionally with
        "target_pace_min_per_km": [low, high] (decimal minutes per km, e.g.
        4.5 == 4:30/km) or "target_heart_rate_bpm": [low, high].
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
    """
    try:
        workout_json = build_running_workout(name, steps, description)
    except WorkoutBuilderError as e:
        raise ValueError(str(e)) from e
    return _call_client(lambda: get_client().upload_workout(workout_json))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

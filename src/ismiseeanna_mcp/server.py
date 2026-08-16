"""MCP server exposing Garmin Connect activity data as tools."""

from mcp.server.fastmcp import FastMCP

from .garmin_client import build_structured_running_workout, get_client

mcp = FastMCP("ismiseeanna-garmin")


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
    activities = get_client().get_activities(start, limit)
    return [_summarize(a) for a in activities]


@mcp.tool()
def search_activities_by_date(
    start_date: str, end_date: str, activity_type: str | None = None
) -> list[dict]:
    """Find activities between two dates (YYYY-MM-DD), optionally filtered by activity type."""
    activities = get_client().get_activities_by_date(start_date, end_date, activity_type)
    return [_summarize(a) for a in activities]


@mcp.tool()
def get_activity_details(activity_id: int) -> dict:
    """Get full details (metrics, splits summary, etc.) for one activity by its Garmin activity ID."""
    return get_client().get_activity_details(activity_id)


@mcp.tool()
def get_activity_splits(activity_id: int) -> dict:
    """Get lap/split data for one activity by its Garmin activity ID."""
    return get_client().get_activity_splits(activity_id)


@mcp.tool()
def get_activity_weather(activity_id: int) -> dict:
    """Get recorded weather conditions for one activity by its Garmin activity ID."""
    return get_client().get_activity_weather(activity_id)


@mcp.tool()
def get_activity_gear(activity_id: int) -> dict:
    """Get the gear (shoes, bike, etc.) logged against one activity by its Garmin activity ID."""
    return get_client().get_activity_gear(activity_id)


@mcp.tool()
def get_activity_hr_zones(activity_id: int) -> dict:
    """Get time spent in each heart rate zone for one activity by its Garmin activity ID."""
    return get_client().get_activity_hr_in_timezones(activity_id)


@mcp.tool()
def get_personal_records() -> dict:
    """Get the current user's personal records (e.g. fastest 5K, longest run)."""
    return get_client().get_personal_record()


@mcp.tool()
def get_sleep_data(date: str) -> dict:
    """Get sleep data for one date (YYYY-MM-DD)."""
    return get_client().get_sleep_data(date)


@mcp.tool()
def get_stress_data(date: str) -> dict:
    """Get stress level data for one date (YYYY-MM-DD)."""
    return get_client().get_stress_data(date)


@mcp.tool()
def get_body_battery(date: str) -> list[dict]:
    """Get Body Battery (energy level) data for one date (YYYY-MM-DD)."""
    return get_client().get_body_battery(date)


@mcp.tool()
def get_hrv_data(date: str) -> dict | None:
    """Get heart rate variability (HRV) data for one date (YYYY-MM-DD)."""
    return get_client().get_hrv_data(date)


@mcp.tool()
def get_resting_heart_rate(date: str) -> dict:
    """Get resting heart rate for one date (YYYY-MM-DD)."""
    return get_client().get_rhr_day(date)


@mcp.tool()
def get_training_readiness(date: str) -> dict:
    """Get training readiness score and its contributing factors for one date (YYYY-MM-DD)."""
    return get_client().get_training_readiness(date)


@mcp.tool()
def get_training_status(date: str) -> dict:
    """Get training status (e.g. productive, peaking, detraining) for one date (YYYY-MM-DD)."""
    return get_client().get_training_status(date)


@mcp.tool()
def get_max_metrics(date: str) -> dict:
    """Get fitness age and VO2 max metrics for one date (YYYY-MM-DD)."""
    return get_client().get_max_metrics(date)


@mcp.tool()
def get_race_predictions() -> dict:
    """Get predicted race times for the 5K, 10K, half marathon, and marathon, as of today."""
    return get_client().get_race_predictions()


@mcp.tool()
def get_endurance_score(date: str) -> dict:
    """Get endurance score for one date (YYYY-MM-DD)."""
    return get_client().get_endurance_score(date)


@mcp.tool()
def list_workouts(start: int = 0, limit: int = 100) -> list[dict]:
    """List saved workouts."""
    return get_client().get_workouts(start, limit)


@mcp.tool()
def get_workout(workout_id: int) -> dict:
    """Get one saved workout's full step-by-step definition by its Garmin workout ID."""
    return get_client().get_workout_by_id(workout_id)


@mcp.tool()
def create_running_workout(name: str, steps: list[dict]) -> dict:
    """Create and save a multi-step running workout: warmup/interval/recovery/cooldown
    steps, each with an end condition and an optional pace or heart-rate target.

    Each entry in `steps` is either a plain step or a repeat block:

    Plain step:
      - "kind": one of "warmup", "interval", "recovery", "cooldown" (required)
      - exactly one of "distance_meters" or "duration_seconds" (required)
      - at most one target, both bounds required together:
          "target_pace_min_per_km" / "target_pace_max_per_km" (seconds per km), or
          "target_hr_min" / "target_hr_max" (bpm)
        omit both for no target.

    Repeat block: {"repeat": {"count": int, "steps": [plain step, ...]}}
      — repeats the nested plain steps `count` times, e.g. 6x 400m @ pace with
      200m recovery jog between reps. Nested repeats are not supported.

    Example — an easy warmup, 4x(3min hard / 2min easy), and a cooldown:
      [
        {"kind": "warmup", "distance_meters": 1000},
        {"repeat": {"count": 4, "steps": [
          {"kind": "interval", "duration_seconds": 180,
           "target_pace_min_per_km": 240, "target_pace_max_per_km": 255},
          {"kind": "recovery", "duration_seconds": 120}
        ]}},
        {"kind": "cooldown", "distance_meters": 1000}
      ]

    Returns the saved workout, including its workoutId for use with
    schedule_workout.
    """
    workout_json = build_structured_running_workout(name, steps)
    return get_client().upload_workout(workout_json)


@mcp.tool()
def schedule_workout(workout_id: int, date: str) -> dict:
    """Schedule a saved workout on the Garmin calendar for one date (YYYY-MM-DD)."""
    return get_client().schedule_workout(workout_id, date)


@mcp.tool()
def list_scheduled_workouts(year: int, month: int) -> dict:
    """List workouts scheduled on the Garmin calendar for one month."""
    return get_client().get_scheduled_workouts(year, month)


@mcp.tool()
def unschedule_workout(scheduled_workout_id: int) -> dict:
    """Remove a scheduled workout from the Garmin calendar."""
    return get_client().unschedule_workout(scheduled_workout_id)


@mcp.tool()
def delete_workout(workout_id: int) -> dict:
    """Delete a saved workout."""
    return get_client().delete_workout(workout_id)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

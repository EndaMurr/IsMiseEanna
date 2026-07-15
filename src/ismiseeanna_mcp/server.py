"""MCP server exposing Garmin Connect activity data as tools."""

from mcp.server.fastmcp import FastMCP

from .garmin_client import get_client

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
def get_daily_snapshot(date: str) -> dict:
    """Get a combined daily health snapshot (sleep, stress, body battery,
    resting heart rate, steps) for one date (YYYY-MM-DD), in a single call."""
    client = get_client()
    return {
        "date": date,
        "sleep": client.get_sleep_data(date),
        "stress": client.get_stress_data(date),
        "bodyBattery": client.get_body_battery(date),
        "restingHeartRate": client.get_rhr_day(date),
        "steps": client.get_steps_data(date),
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

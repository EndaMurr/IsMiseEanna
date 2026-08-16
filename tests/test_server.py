from unittest.mock import MagicMock

import pytest

from ismiseeanna_mcp import server
from ismiseeanna_mcp.server import _summarize


@pytest.fixture
def fake_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(server, "get_client", lambda: client)
    return client


def test_summarize_full_activity():
    activity = {
        "activityId": 123,
        "activityName": "Morning Run",
        "activityType": {"typeKey": "running"},
        "startTimeLocal": "2026-07-15 07:00:00",
        "distance": 5000.0,
        "duration": 1800.0,
        "calories": 350,
        "averageHR": 145,
    }
    assert _summarize(activity) == {
        "activityId": 123,
        "name": "Morning Run",
        "type": "running",
        "startTimeLocal": "2026-07-15 07:00:00",
        "distanceMeters": 5000.0,
        "durationSeconds": 1800.0,
        "calories": 350,
        "averageHR": 145,
    }


def test_summarize_handles_missing_fields():
    assert _summarize({}) == {
        "activityId": None,
        "name": None,
        "type": None,
        "startTimeLocal": None,
        "distanceMeters": None,
        "durationSeconds": None,
        "calories": None,
        "averageHR": None,
    }


def test_list_activities_summarizes_and_passes_pagination(fake_client):
    fake_client.get_activities.return_value = [
        {"activityId": 1, "activityName": "Run", "activityType": {"typeKey": "running"}}
    ]

    result = server.list_activities(limit=10, start=5)

    fake_client.get_activities.assert_called_once_with(5, 10)
    assert result == [
        {
            "activityId": 1,
            "name": "Run",
            "type": "running",
            "startTimeLocal": None,
            "distanceMeters": None,
            "durationSeconds": None,
            "calories": None,
            "averageHR": None,
        }
    ]


def test_search_activities_by_date_passes_args_and_summarizes(fake_client):
    fake_client.get_activities_by_date.return_value = [
        {"activityId": 2, "activityName": "Ride"}
    ]

    result = server.search_activities_by_date("2026-01-01", "2026-01-31", "cycling")

    fake_client.get_activities_by_date.assert_called_once_with(
        "2026-01-01", "2026-01-31", "cycling"
    )
    assert result[0]["activityId"] == 2
    assert result[0]["name"] == "Ride"


@pytest.mark.parametrize(
    "tool_func, client_method, args",
    [
        (server.get_activity_details, "get_activity_details", (42,)),
        (server.get_activity_splits, "get_activity_splits", (42,)),
        (server.get_activity_weather, "get_activity_weather", (42,)),
        (server.get_activity_gear, "get_activity_gear", (42,)),
        (server.get_activity_hr_zones, "get_activity_hr_in_timezones", (42,)),
        (server.get_personal_records, "get_personal_record", ()),
        (server.get_sleep_data, "get_sleep_data", ("2026-07-15",)),
        (server.get_stress_data, "get_stress_data", ("2026-07-15",)),
        (server.get_body_battery, "get_body_battery", ("2026-07-15",)),
        (server.get_hrv_data, "get_hrv_data", ("2026-07-15",)),
        (server.get_resting_heart_rate, "get_rhr_day", ("2026-07-15",)),
        (server.get_training_readiness, "get_training_readiness", ("2026-07-15",)),
        (server.get_training_status, "get_training_status", ("2026-07-15",)),
        (server.get_max_metrics, "get_max_metrics", ("2026-07-15",)),
        (server.get_race_predictions, "get_race_predictions", ()),
        (server.get_endurance_score, "get_endurance_score", ("2026-07-15",)),
    ],
)
def test_passthrough_tool_calls_expected_client_method(fake_client, tool_func, client_method, args):
    sentinel = {"sentinel": True}
    getattr(fake_client, client_method).return_value = sentinel

    result = tool_func(*args)

    getattr(fake_client, client_method).assert_called_once_with(*args)
    assert result is sentinel


@pytest.mark.parametrize(
    "tool_func, client_method, args",
    [
        (server.list_workouts, "get_workouts", (0, 100)),
        (server.get_workout, "get_workout_by_id", (7,)),
        (server.schedule_workout, "schedule_workout", (7, "2026-08-11")),
        (server.list_scheduled_workouts, "get_scheduled_workouts", (2026, 8)),
        (server.unschedule_workout, "unschedule_workout", (99,)),
        (server.delete_workout, "delete_workout", (7,)),
    ],
)
def test_workout_passthrough_tool_calls_expected_client_method(
    fake_client, tool_func, client_method, args
):
    sentinel = {"sentinel": True}
    getattr(fake_client, client_method).return_value = sentinel

    result = tool_func(*args)

    getattr(fake_client, client_method).assert_called_once_with(*args)
    assert result is sentinel


def test_create_running_workout_uploads_built_workout(fake_client):
    fake_client.upload_workout.return_value = {"workoutId": 42}

    result = server.create_running_workout(
        "Easy 5k", [{"kind": "warmup", "distance_meters": 5000}]
    )

    fake_client.upload_workout.assert_called_once()
    uploaded = fake_client.upload_workout.call_args[0][0]
    assert uploaded["workoutName"] == "Easy 5k"
    assert result == {"workoutId": 42}

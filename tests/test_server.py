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


def test_summarize_workout_full():
    workout = {
        "workoutId": 99,
        "workoutName": "5x400m",
        "sportType": {"sportTypeKey": "running"},
        "estimatedDurationInSecs": 1800,
        "updatedDate": "2026-08-01",
    }
    assert server._summarize_workout(workout) == {
        "workoutId": 99,
        "name": "5x400m",
        "sportType": "running",
        "estimatedDurationInSecs": 1800,
        "updatedDate": "2026-08-01",
    }


def test_summarize_workout_handles_missing_fields():
    assert server._summarize_workout({}) == {
        "workoutId": None,
        "name": None,
        "sportType": None,
        "estimatedDurationInSecs": None,
        "updatedDate": None,
    }


def test_list_workouts_summarizes_and_passes_pagination(fake_client):
    fake_client.get_workouts.return_value = [
        {"workoutId": 1, "workoutName": "Easy Run", "sportType": {"sportTypeKey": "running"}}
    ]

    result = server.list_workouts(limit=10, start=5)

    fake_client.get_workouts.assert_called_once_with(5, 10)
    assert result[0]["workoutId"] == 1
    assert result[0]["name"] == "Easy Run"


def test_get_workout_passes_through(fake_client):
    fake_client.get_workout_by_id.return_value = {"workoutId": 7}
    assert server.get_workout(7) == {"workoutId": 7}
    fake_client.get_workout_by_id.assert_called_once_with(7)


def test_delete_workout_looks_up_name_then_deletes(fake_client):
    fake_client.get_workout_by_id.return_value = {"workoutId": 7, "workoutName": "Easy Run"}

    result = server.delete_workout(7)

    fake_client.get_workout_by_id.assert_called_once_with(7)
    fake_client.delete_workout.assert_called_once_with(7)
    assert result == "Deleted workout 7 ('Easy Run')"


def test_delete_workout_falls_back_to_generic_name(fake_client):
    fake_client.get_workout_by_id.return_value = {"workoutId": 7}

    result = server.delete_workout(7)

    assert result == "Deleted workout 7 ('workout')"


def test_delete_workout_does_not_delete_if_lookup_fails(fake_client):
    fake_client.get_workout_by_id.side_effect = ValueError("not found")

    with pytest.raises(RuntimeError):
        server.delete_workout(7)

    fake_client.delete_workout.assert_not_called()


def test_create_running_workout_builds_and_uploads(fake_client):
    fake_client.upload_workout.return_value = {"workoutId": 42, "workoutName": "Easy Run"}

    result = server.create_running_workout(
        "Easy Run", [{"kind": "warmup", "duration_seconds": 600}]
    )

    assert fake_client.upload_workout.call_count == 1
    (uploaded_json,), _kwargs = fake_client.upload_workout.call_args
    assert uploaded_json["workoutName"] == "Easy Run"
    assert result == {"workoutId": 42, "workoutName": "Easy Run"}


def test_create_running_workout_rejects_invalid_steps_without_calling_client(fake_client):
    with pytest.raises(ValueError):
        server.create_running_workout("Bad Workout", [{"kind": "warmup"}])
    fake_client.upload_workout.assert_not_called()


def test_create_running_workout_sanitizes_upload_errors(fake_client):
    fake_client.upload_workout.side_effect = ValueError(
        "boom: leaked internal detail, session=abc123"
    )

    with pytest.raises(RuntimeError) as exc_info:
        server.create_running_workout(
            "Easy Run", [{"kind": "warmup", "duration_seconds": 600}]
        )

    assert "leaked internal detail" not in str(exc_info.value)
    assert "session=abc123" not in str(exc_info.value)
    assert "ValueError" in str(exc_info.value)


@pytest.mark.parametrize(
    "tool_func, client_method, args",
    [
        (server.list_activities, "get_activities", ()),
        (server.get_activity_details, "get_activity_details", (42,)),
        (server.get_personal_records, "get_personal_record", ()),
        (server.get_sleep_data, "get_sleep_data", ("2026-07-15",)),
        (server.list_workouts, "get_workouts", ()),
        (server.get_workout, "get_workout_by_id", (7,)),
        (server.schedule_workout, "schedule_workout", (42, "2026-08-10")),
        (server.list_scheduled_workouts, "get_scheduled_workouts", (2026, 8)),
    ],
)
def test_tool_calls_sanitize_client_exceptions(fake_client, tool_func, client_method, args):
    getattr(fake_client, client_method).side_effect = ValueError(
        "boom: sensitive detail should not leak"
    )

    with pytest.raises(RuntimeError) as exc_info:
        tool_func(*args)

    assert "sensitive detail" not in str(exc_info.value)
    assert "ValueError" in str(exc_info.value)


def test_create_running_workout_schedules_when_date_given(fake_client):
    fake_client.upload_workout.return_value = {"workoutId": 42, "workoutName": "Easy Run"}
    fake_client.schedule_workout.return_value = {"scheduleId": 99, "date": "2026-08-10"}

    result = server.create_running_workout(
        "Easy Run",
        [{"kind": "warmup", "duration_seconds": 600}],
        date="2026-08-10",
    )

    fake_client.schedule_workout.assert_called_once_with(42, "2026-08-10")
    assert result["workoutId"] == 42
    assert result["scheduled"] == {"scheduleId": 99, "date": "2026-08-10"}


def test_create_running_workout_does_not_schedule_without_date(fake_client):
    fake_client.upload_workout.return_value = {"workoutId": 42, "workoutName": "Easy Run"}

    result = server.create_running_workout(
        "Easy Run", [{"kind": "warmup", "duration_seconds": 600}]
    )

    fake_client.schedule_workout.assert_not_called()
    assert "scheduled" not in result


def test_create_running_workout_raises_clearly_if_no_workout_id_to_schedule(fake_client):
    fake_client.upload_workout.return_value = {"workoutName": "Easy Run"}  # no workoutId

    with pytest.raises(RuntimeError, match="workoutId"):
        server.create_running_workout(
            "Easy Run",
            [{"kind": "warmup", "duration_seconds": 600}],
            date="2026-08-10",
        )
    fake_client.schedule_workout.assert_not_called()


def test_schedule_workout_passes_through(fake_client):
    fake_client.schedule_workout.return_value = {"scheduleId": 99}
    assert server.schedule_workout(42, "2026-08-10") == {"scheduleId": 99}
    fake_client.schedule_workout.assert_called_once_with(42, "2026-08-10")


def test_unschedule_workout_calls_client_and_confirms(fake_client):
    result = server.unschedule_workout(99)
    fake_client.unschedule_workout.assert_called_once_with(99)
    assert result == "Removed scheduled workout 99 from the calendar"


def test_list_scheduled_workouts_passes_through(fake_client):
    fake_client.get_scheduled_workouts.return_value = {"days": []}
    assert server.list_scheduled_workouts(2026, 8) == {"days": []}
    fake_client.get_scheduled_workouts.assert_called_once_with(2026, 8)

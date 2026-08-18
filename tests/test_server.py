from unittest.mock import MagicMock

import pytest

from ismiseeanna_mcp import server
from ismiseeanna_mcp.server import _summarize


@pytest.fixture
def fake_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(server, "get_client", lambda: client)
    return client


def test_build_mcp_returns_unauthenticated_instance_when_env_unset(monkeypatch):
    monkeypatch.delenv("WORKOS_AUTHKIT_DOMAIN", raising=False)
    monkeypatch.delenv("MCP_RESOURCE_URL", raising=False)

    built = server._build_mcp()

    assert built._token_verifier is None
    assert built.settings.auth is None


def test_build_mcp_stays_local_only_when_unauthenticated(monkeypatch):
    """Fail-closed check: even if a hosted deployment's env accidentally
    sets MCP_HOST=0.0.0.0 without the WorkOS auth vars, the unauthenticated
    fallback must not pick that up and bind publicly - it should stay on
    FastMCP's own local-only default regardless."""
    monkeypatch.delenv("WORKOS_AUTHKIT_DOMAIN", raising=False)
    monkeypatch.delenv("MCP_RESOURCE_URL", raising=False)
    monkeypatch.setenv("MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9000")

    built = server._build_mcp()

    assert built.settings.host == "127.0.0.1"
    assert built.settings.port == 8000


@pytest.mark.parametrize("missing_var", ["WORKOS_AUTHKIT_DOMAIN", "MCP_RESOURCE_URL"])
def test_build_mcp_falls_back_when_only_one_var_set(monkeypatch, missing_var):
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "https://example-project.authkit.app")
    monkeypatch.setenv("MCP_RESOURCE_URL", "https://mcp.example.com/mcp")
    monkeypatch.delenv(missing_var, raising=False)

    built = server._build_mcp()

    assert built._token_verifier is None
    assert built.settings.auth is None


def test_build_mcp_wires_auth_when_both_vars_set(monkeypatch):
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "https://example-project.authkit.app")
    monkeypatch.setenv("MCP_RESOURCE_URL", "https://mcp.example.com/mcp")
    monkeypatch.setenv("MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9000")

    built = server._build_mcp()

    from ismiseeanna_mcp.auth import WorkOSTokenVerifier

    assert isinstance(built._token_verifier, WorkOSTokenVerifier)
    assert str(built.settings.auth.issuer_url) == "https://example-project.authkit.app/"
    assert str(built.settings.auth.resource_server_url) == "https://mcp.example.com/mcp"
    assert built.settings.host == "0.0.0.0"
    assert built.settings.port == 9000


def test_build_mcp_defaults_host_and_port_when_unset(monkeypatch):
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "https://example-project.authkit.app")
    monkeypatch.setenv("MCP_RESOURCE_URL", "https://mcp.example.com/mcp")
    monkeypatch.delenv("MCP_HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    built = server._build_mcp()

    assert built.settings.host == "0.0.0.0"
    assert built.settings.port == 8000


def test_build_mcp_derives_transport_security_allowlist_from_resource_url(monkeypatch):
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "https://example-project.authkit.app")
    monkeypatch.setenv("MCP_RESOURCE_URL", "https://mcp.example.com/mcp")

    built = server._build_mcp()

    ts = built.settings.transport_security
    assert ts.enable_dns_rebinding_protection is True
    assert ts.allowed_hosts == ["mcp.example.com", "mcp.example.com:*"]
    assert ts.allowed_origins == ["https://mcp.example.com"]


def test_build_mcp_transport_security_handles_explicit_port_in_resource_url(monkeypatch):
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "https://example-project.authkit.app")
    monkeypatch.setenv("MCP_RESOURCE_URL", "https://mcp.example.com:8443/mcp")

    built = server._build_mcp()

    ts = built.settings.transport_security
    assert ts.allowed_hosts == ["mcp.example.com:8443", "mcp.example.com:8443:*"]
    assert ts.allowed_origins == ["https://mcp.example.com:8443"]


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


def test_generate_marathon_plan_uses_real_race_predictions(fake_client, monkeypatch):
    fake_client.get_race_predictions.return_value = {
        "time5K": 1200,
        "time10K": 2500,
        "timeHalfMarathon": 5500,
        "timeMarathon": 12000,
    }
    captured = {}

    def fake_generate(race_date, current_weekly_km, race_predictions, strategy):
        captured["args"] = (race_date, current_weekly_km, race_predictions, strategy)
        return [{"weekStart": "2026-08-17"}]

    monkeypatch.setattr(server, "_generate_marathon_plan", fake_generate)

    result = server.generate_marathon_plan("2026-10-03", 55.0, "aggressive")

    fake_client.get_race_predictions.assert_called_once()
    assert captured["args"] == (
        "2026-10-03",
        55.0,
        fake_client.get_race_predictions.return_value,
        "aggressive",
    )
    assert result == [{"weekStart": "2026-08-17"}]


def test_get_weekly_check_in_gathers_calendar_activity_and_recovery_data(
    fake_client, monkeypatch
):
    import datetime as dt

    from ismiseeanna_mcp import realignment as realignment_module

    class _FixedDate(dt.date):
        @classmethod
        def today(cls):
            return dt.date(2026, 8, 16)  # Sunday -> week is Mon 08-10..Sun 08-16

    monkeypatch.setattr(realignment_module, "date", _FixedDate)

    fake_client.get_scheduled_workouts.return_value = {
        "calendarItems": [
            {
                "date": "2026-08-11",
                "title": "Tempo Run",
                "id": 555,
                "workoutId": 999,
            },
            {"date": "2026-08-09", "title": "Previous week, must be excluded"},
        ]
    }
    fake_client.get_activities_by_date.return_value = [
        {"activityId": 1, "activityName": "Tempo", "startTimeLocal": "2026-08-11 07:00:00"}
    ]
    fake_client.get_training_readiness.return_value = [{"score": 65}]
    fake_client.get_hrv_data.return_value = {"hrvSummary": {"lastNightAvg": 55}}

    result = server.get_weekly_check_in()

    fake_client.get_scheduled_workouts.assert_called_once_with(2026, 8)
    fake_client.get_activities_by_date.assert_called_once_with(
        "2026-08-10", "2026-08-16", "running"
    )
    assert result["weekStart"] == "2026-08-10"
    assert result["weekEnd"] == "2026-08-16"
    assert result["recoveryTrend"]["trainingReadiness"] == [65] * 7
    assert result["recoveryTrend"]["hrv"] == [55] * 7
    assert result["sessionsCompleted"] == [
        {"date": "2026-08-11", "name": "Tempo Run", "scheduledWorkoutId": 555, "workoutId": 999}
    ]
    assert result["sessionsMissed"] == []


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


def test_move_scheduled_workout_unschedules_then_reschedules_same_workout(fake_client):
    fake_client.schedule_workout.return_value = {"scheduleId": 100, "date": "2026-08-16"}

    result = server.move_scheduled_workout(
        scheduled_workout_id=555, workout_id=999, new_date="2026-08-16"
    )

    fake_client.unschedule_workout.assert_called_once_with(555)
    fake_client.schedule_workout.assert_called_once_with(999, "2026-08-16")
    assert result == {"scheduleId": 100, "date": "2026-08-16"}


def test_move_scheduled_workout_does_not_reschedule_if_unschedule_fails(fake_client):
    fake_client.unschedule_workout.side_effect = ValueError("boom")

    with pytest.raises(RuntimeError):
        server.move_scheduled_workout(scheduled_workout_id=555, workout_id=999, new_date="2026-08-16")

    fake_client.schedule_workout.assert_not_called()


def test_list_scheduled_workouts_passes_through(fake_client):
    fake_client.get_scheduled_workouts.return_value = {"days": []}
    assert server.list_scheduled_workouts(2026, 8) == {"days": []}
    fake_client.get_scheduled_workouts.assert_called_once_with(2026, 8)


def _running_activity(pace_min_per_km, distance_m=10000):
    duration = pace_min_per_km * 60 * (distance_m / 1000)
    return {"activityType": {"typeKey": "running"}, "distance": distance_m, "duration": duration}


def test_estimate_recovery_pace_uses_slowest_third_average(fake_client):
    paces = [4.0, 4.2, 4.4, 4.6, 4.8, 5.0, 5.2, 5.4, 5.6]
    fake_client.get_activities.return_value = [_running_activity(p) for p in paces]

    result = server._estimate_recovery_pace_min_per_km()

    assert result == (5.25, 5.55)
    fake_client.get_activities.assert_called_once_with(0, 20)


def test_estimate_recovery_pace_ignores_non_running_and_incomplete_activities(fake_client):
    paces = [5.0, 5.2, 5.4, 5.6, 5.8, 6.0]
    activities = [_running_activity(p) for p in paces]
    activities.append({"activityType": {"typeKey": "cycling"}, "distance": 1, "duration": 1})
    activities.append({"activityType": {"typeKey": "running"}, "distance": None, "duration": 1000})
    activities.append({"activityType": {"typeKey": "running"}, "distance": 1000, "duration": None})
    fake_client.get_activities.return_value = activities

    result = server._estimate_recovery_pace_min_per_km()

    assert result == (5.75, 6.05)


def test_estimate_recovery_pace_returns_none_with_too_little_history(fake_client):
    fake_client.get_activities.return_value = [_running_activity(5.0), _running_activity(5.2)]
    assert server._estimate_recovery_pace_min_per_km() is None


def test_estimate_recovery_pace_returns_none_on_client_error(fake_client):
    fake_client.get_activities.side_effect = ValueError("boom")
    assert server._estimate_recovery_pace_min_per_km() is None


def test_normalize_standalone_recovery_steps_rewrites_top_level_recovery():
    steps = [{"kind": "recovery", "distance_meters": 5000}]

    result = server._normalize_standalone_recovery_steps(steps)

    assert result == [{"kind": "interval", "distance_meters": 5000, "effort": "easy"}]


def test_normalize_standalone_recovery_steps_leaves_nested_recovery_alone():
    steps = [
        {
            "kind": "repeat",
            "iterations": 5,
            "steps": [
                {"kind": "interval", "distance_meters": 400},
                {"kind": "recovery", "duration_seconds": 90},
            ],
        }
    ]

    result = server._normalize_standalone_recovery_steps(steps)

    assert result == steps


def test_normalize_standalone_recovery_steps_leaves_other_kinds_alone():
    steps = [{"kind": "warmup", "duration_seconds": 600}]

    result = server._normalize_standalone_recovery_steps(steps)

    assert result == steps


def test_create_running_workout_renders_standalone_recovery_as_run_step(fake_client, monkeypatch):
    """A whole standalone "Recovery 5K" must render in Garmin Connect as a
    "Run" step (stepTypeId 3 / "interval"), not "Recover" - confirmed
    against a real "Run" step saved through Garmin's own UI."""
    monkeypatch.setattr(server, "_estimate_recovery_pace_min_per_km", lambda: (5.25, 5.55))
    fake_client.upload_workout.return_value = {"workoutId": 1, "workoutName": "Recovery 5K"}

    server.create_running_workout("Recovery 5K", [{"kind": "recovery", "distance_meters": 5000}])

    (uploaded_json,), _ = fake_client.upload_workout.call_args
    built_step = uploaded_json["workoutSegments"][0]["workoutSteps"][0]
    assert built_step["stepType"]["stepTypeKey"] == "interval"


def test_create_running_workout_keeps_nested_recovery_as_recover_step(fake_client):
    """A recovery jog between repeat reps must stay a "Recover" step."""
    fake_client.upload_workout.return_value = {"workoutId": 1, "workoutName": "Intervals"}

    server.create_running_workout(
        "Intervals",
        [
            {
                "kind": "repeat",
                "iterations": 5,
                "steps": [
                    {
                        "kind": "interval",
                        "distance_meters": 400,
                        "target_pace_min_per_km": [3.9, 4.1],
                    },
                    {"kind": "recovery", "duration_seconds": 90},
                ],
            }
        ],
    )

    (uploaded_json,), _ = fake_client.upload_workout.call_args
    repeat_step = uploaded_json["workoutSegments"][0]["workoutSteps"][0]
    recovery_step = repeat_step["workoutSteps"][1]
    assert recovery_step["stepType"]["stepTypeKey"] == "recovery"


def test_fill_easy_pace_defaults_fills_bare_recovery_step(monkeypatch):
    monkeypatch.setattr(server, "_estimate_recovery_pace_min_per_km", lambda: (5.25, 5.55))
    steps = [{"kind": "recovery", "duration_seconds": 90}]

    result = server._fill_easy_pace_defaults(steps)

    assert result == [
        {"kind": "recovery", "duration_seconds": 90, "target_pace_min_per_km": [5.25, 5.55]}
    ]


def test_fill_easy_pace_defaults_leaves_explicit_pace_target_alone(monkeypatch):
    estimate = MagicMock(return_value=(5.25, 5.55))
    monkeypatch.setattr(server, "_estimate_recovery_pace_min_per_km", estimate)
    steps = [{"kind": "recovery", "duration_seconds": 90, "target_pace_min_per_km": [6.0, 6.2]}]

    result = server._fill_easy_pace_defaults(steps)

    assert result == steps
    estimate.assert_not_called()


def test_fill_easy_pace_defaults_leaves_hr_target_alone(monkeypatch):
    estimate = MagicMock(return_value=(5.25, 5.55))
    monkeypatch.setattr(server, "_estimate_recovery_pace_min_per_km", estimate)
    steps = [{"kind": "recovery", "duration_seconds": 90, "target_heart_rate_bpm": [125, 140]}]

    result = server._fill_easy_pace_defaults(steps)

    assert result == steps
    estimate.assert_not_called()


def test_fill_easy_pace_defaults_recurses_into_repeat_blocks(monkeypatch):
    monkeypatch.setattr(server, "_estimate_recovery_pace_min_per_km", lambda: (5.25, 5.55))
    steps = [
        {
            "kind": "repeat",
            "iterations": 5,
            "steps": [
                {"kind": "interval", "distance_meters": 400, "target_pace_min_per_km": [3.9, 4.1]},
                {"kind": "recovery", "duration_seconds": 90},
            ],
        }
    ]

    result = server._fill_easy_pace_defaults(steps)

    assert result[0]["steps"][1]["target_pace_min_per_km"] == [5.25, 5.55]
    assert result[0]["steps"][0]["target_pace_min_per_km"] == [3.9, 4.1]


def test_fill_easy_pace_defaults_computes_estimate_at_most_once(monkeypatch):
    estimate = MagicMock(return_value=(5.25, 5.55))
    monkeypatch.setattr(server, "_estimate_recovery_pace_min_per_km", estimate)
    steps = [
        {"kind": "recovery", "duration_seconds": 90},
        {"kind": "recovery", "duration_seconds": 90},
    ]

    server._fill_easy_pace_defaults(steps)

    estimate.assert_called_once()


def test_fill_easy_pace_defaults_noop_when_estimate_unavailable(monkeypatch):
    monkeypatch.setattr(server, "_estimate_recovery_pace_min_per_km", lambda: None)
    steps = [{"kind": "recovery", "duration_seconds": 90}]

    result = server._fill_easy_pace_defaults(steps)

    assert result == steps


def test_fill_easy_pace_defaults_fills_standalone_easy_run_marked_by_effort(monkeypatch):
    """A whole standalone easy run is a plain "interval" step (Garmin's own
    "Run" step type), not a "recovery" one - it only gets the automatic
    pace default when explicitly marked "effort": "easy"."""
    monkeypatch.setattr(server, "_estimate_recovery_pace_min_per_km", lambda: (5.25, 5.55))
    steps = [{"kind": "interval", "distance_meters": 5000, "effort": "easy"}]

    result = server._fill_easy_pace_defaults(steps)

    assert result == [
        {
            "kind": "interval",
            "distance_meters": 5000,
            "effort": "easy",
            "target_pace_min_per_km": [5.25, 5.55],
        }
    ]


def test_fill_easy_pace_defaults_leaves_untagged_interval_step_alone(monkeypatch):
    """A hard interval (e.g. one rep of 5x400m at race pace) must never get
    an easy-pace default just because it has no target yet at this point in
    the tool's logic - only "recovery" kind or explicit "effort": "easy"
    steps do."""
    estimate = MagicMock(return_value=(5.25, 5.55))
    monkeypatch.setattr(server, "_estimate_recovery_pace_min_per_km", estimate)
    steps = [{"kind": "interval", "distance_meters": 400}]

    result = server._fill_easy_pace_defaults(steps)

    assert result == steps
    estimate.assert_not_called()


def test_create_running_workout_fills_recovery_pace_from_history(fake_client, monkeypatch):
    monkeypatch.setattr(server, "_estimate_recovery_pace_min_per_km", lambda: (5.25, 5.55))
    fake_client.upload_workout.return_value = {"workoutId": 1, "workoutName": "Recovery 5K"}

    server.create_running_workout("Recovery 5K", [{"kind": "recovery", "distance_meters": 5000}])

    (uploaded_json,), _ = fake_client.upload_workout.call_args
    built_step = uploaded_json["workoutSegments"][0]["workoutSteps"][0]
    from ismiseeanna_mcp.workout_builder import _PACE_TARGET

    assert built_step["targetType"] == _PACE_TARGET
    assert built_step["targetValueOne"] is not None

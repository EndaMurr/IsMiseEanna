import json
from unittest.mock import MagicMock

import anthropic
import pytest
from fastapi.testclient import TestClient

from ismiseeanna_mcp import api, server
from ismiseeanna_mcp.garmin_client import GarminClientError


@pytest.fixture(autouse=True)
def api_token(monkeypatch):
    monkeypatch.setenv("GARMIN_UI_API_TOKEN", "test-token")


@pytest.fixture
def client():
    return TestClient(api.app)


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}


@pytest.fixture
def fake_garmin_client(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(api, "get_client", lambda: fake)
    monkeypatch.setattr(server, "get_client", lambda: fake)
    return fake


def test_requires_auth(client):
    response = client.get("/status")
    assert response.status_code == 401  # no Authorization header at all


def test_rejects_wrong_token(client, auth_headers, fake_garmin_client):
    response = client.get("/status", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_status_connected(client, auth_headers, fake_garmin_client, monkeypatch):
    monkeypatch.setenv("GARMIN_EMAIL", "me@example.com")
    response = client.get("/status", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["account"] == "me••••••.com"


def test_status_disconnected(client, auth_headers, monkeypatch):
    monkeypatch.setattr(api, "get_client", MagicMock(side_effect=GarminClientError("no creds")))
    response = client.get("/status", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["connected"] is False


def test_dashboard_extracts_today_and_trend(client, auth_headers, fake_garmin_client):
    fake_garmin_client.get_body_battery.return_value = [
        {"bodyBatteryValuesArray": [[0, 50, "x", 1], [1, 72, "x", 1]]}
    ]
    fake_garmin_client.get_training_readiness.return_value = [{"score": 68}]
    fake_garmin_client.get_sleep_data.return_value = {
        "dailySleepDTO": {"sleepScores": {"overall": {"value": 84}}}
    }
    fake_garmin_client.get_rhr_day.return_value = {
        "allMetrics": {"metricsMap": {"WELLNESS_RESTING_HEART_RATE": [{"value": 52}]}}
    }
    fake_garmin_client.get_hrv_data.return_value = {"hrvSummary": {"lastNightAvg": 45}}

    response = client.get("/dashboard", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["today"] == {
        "bodyBattery": 72,
        "trainingReadiness": 68,
        "sleepScore": 84,
        "restingHeartRate": 52,
        "hrv": 45,
    }
    assert len(body["trends"]["bodyBattery"]) == 7


def test_dashboard_tolerates_missing_data(client, auth_headers, fake_garmin_client):
    fake_garmin_client.get_body_battery.side_effect = RuntimeError("boom")
    fake_garmin_client.get_training_readiness.return_value = None
    fake_garmin_client.get_sleep_data.return_value = {}
    fake_garmin_client.get_rhr_day.return_value = {}
    fake_garmin_client.get_hrv_data.return_value = None

    response = client.get("/dashboard", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["today"]["bodyBattery"] is None


def test_weekly_check_in_endpoint_returns_tool_result(client, auth_headers, fake_garmin_client):
    fake_garmin_client.get_scheduled_workouts.return_value = {"calendarItems": []}
    fake_garmin_client.get_activities_by_date.return_value = []
    fake_garmin_client.get_training_readiness.return_value = None
    fake_garmin_client.get_hrv_data.return_value = None

    response = client.get("/weekly-check-in", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert "weekStart" in body
    assert "sessionsScheduled" in body


def test_weekly_check_in_endpoint_sanitizes_garmin_errors(
    client, auth_headers, fake_garmin_client
):
    fake_garmin_client.get_scheduled_workouts.side_effect = RuntimeError(
        "http://internal-detail leaked"
    )

    response = client.get("/weekly-check-in", headers=auth_headers)

    assert response.status_code == 502
    assert "internal-detail" not in response.text


def test_plan_progress_endpoint_returns_tool_result(client, auth_headers, fake_garmin_client):
    fake_garmin_client.get_scheduled_workouts.return_value = {
        "calendarItems": [{"date": "2026-08-11", "title": "W6 Tue Tempo - 2km Repeats"}]
    }

    response = client.get(
        "/plan-progress", headers=auth_headers, params={"race_date": "2026-10-03"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["currentWeek"] == 6
    assert body["raceDate"] == "2026-10-03"


def test_plan_progress_endpoint_requires_race_date_query_param(client, auth_headers):
    response = client.get("/plan-progress", headers=auth_headers)
    assert response.status_code == 422


def test_plan_progress_endpoint_rejects_bad_race_date(client, auth_headers, fake_garmin_client):
    fake_garmin_client.get_scheduled_workouts.return_value = {"calendarItems": []}

    response = client.get(
        "/plan-progress", headers=auth_headers, params={"race_date": "not-a-date"}
    )

    assert response.status_code == 400


def test_chat_returns_text_reply_without_tools(client, auth_headers, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    text_block = MagicMock(type="text", text="Hello from Claude")
    fake_response = MagicMock(stop_reason="end_turn", content=[text_block])
    fake_anthropic_client = MagicMock()
    fake_anthropic_client.messages.create.return_value = fake_response
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda: fake_anthropic_client)

    response = client.post(
        "/chat",
        headers=auth_headers,
        json={"messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    assert response.json() == {"reply": "Hello from Claude"}


def test_chat_executes_tool_then_replies(client, auth_headers, fake_garmin_client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake_garmin_client.get_training_readiness.return_value = {"score": 68}

    tool_use_block = MagicMock(type="tool_use", id="tool_1", input={"date": "2026-08-10"})
    tool_use_block.name = "get_training_readiness"  # "name" is a reserved MagicMock() kwarg
    tool_response = MagicMock(stop_reason="tool_use", content=[tool_use_block])
    text_block = MagicMock(type="text", text="Your readiness is 68.")
    final_response = MagicMock(stop_reason="end_turn", content=[text_block])

    fake_anthropic_client = MagicMock()
    fake_anthropic_client.messages.create.side_effect = [tool_response, final_response]
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda: fake_anthropic_client)

    response = client.post(
        "/chat",
        headers=auth_headers,
        json={"messages": [{"role": "user", "content": "how's my recovery?"}]},
    )

    assert response.status_code == 200
    assert response.json() == {"reply": "Your readiness is 68."}
    fake_garmin_client.get_training_readiness.assert_called_once_with("2026-08-10")

    # Both recorded calls share a reference to the same (mutated-in-place) list,
    # so its final state has all 4 turns: user, assistant(tool_use), user(tool_result),
    # assistant(final reply). The tool result is second-to-last.
    final_messages = fake_anthropic_client.messages.create.call_args_list[1].kwargs["messages"]
    tool_result_message = final_messages[-2]
    assert tool_result_message["role"] == "user"
    assert json.loads(tool_result_message["content"][0]["content"]) == {"score": 68}


def test_run_tool_reports_unknown_tool():
    assert api._run_tool("not_a_real_tool", {}) == {"error": "Unknown tool: not_a_real_tool"}


def test_chat_tools_have_descriptions():
    for tool in api.CHAT_TOOLS:
        assert tool["description"], f"{tool['name']} is missing a description"


def test_create_running_workout_schema_types_steps_as_object_array():
    schema = next(t for t in api.CHAT_TOOLS if t["name"] == "create_running_workout")
    steps_schema = schema["input_schema"]["properties"]["steps"]
    assert steps_schema == {"type": "array", "items": {"type": "object"}}
    assert schema["input_schema"]["required"] == ["name", "steps"]


def test_param_schema_handles_list_and_dict_annotations():
    assert api._param_schema(list[dict]) == {"type": "array", "items": {"type": "object"}}
    assert api._param_schema(dict) == {"type": "object"}
    assert api._param_schema(str | None) == {"type": "string"}


def test_chat_reports_missing_anthropic_key(client, auth_headers, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = client.post(
        "/chat",
        headers=auth_headers,
        json={"messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 500
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_chat_maps_anthropic_failure_to_502(client, auth_headers, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake_anthropic_client = MagicMock()
    fake_anthropic_client.messages.create.side_effect = anthropic.APIConnectionError(
        request=MagicMock()
    )
    monkeypatch.setattr(api.anthropic, "Anthropic", lambda: fake_anthropic_client)

    response = client.post(
        "/chat",
        headers=auth_headers,
        json={"messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 502

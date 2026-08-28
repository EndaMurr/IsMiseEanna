from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from ismiseeanna_mcp import garmin_client, server, web

USER_ID = "user-01ABC"


@pytest.fixture(autouse=True)
def reset_client_cache():
    garmin_client._clients_by_user.clear()
    yield
    garmin_client._clients_by_user.clear()


@pytest.fixture
def client():
    return TestClient(web.app, follow_redirects=False)


@pytest.fixture
def logged_in_client(client, monkeypatch):
    """A TestClient whose session cookie resolves (via a faked WorkOS
    sealed session) to USER_ID - exercises the real GarminContextMiddleware,
    not a shortcut around it."""
    fake_session = MagicMock()
    fake_session.authenticate.return_value = MagicMock(authenticated=True, user={"id": USER_ID})
    monkeypatch.setattr(
        web._workos.user_management, "load_sealed_session", lambda **_: fake_session
    )
    client.cookies.set(web._SESSION_COOKIE, "sealed-session-value")
    return client


@pytest.fixture
def fake_garmin_client(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(web, "get_client", lambda: fake)
    monkeypatch.setattr(server, "get_client", lambda: fake)
    return fake


def test_api_status_requires_login(client):
    response = client.get("/api/status")
    assert response.status_code == 401


def test_api_status_with_no_session_refresh_stays_logged_out(client, monkeypatch):
    fake_session = MagicMock()
    fake_session.authenticate.return_value = MagicMock(authenticated=False)
    fake_session.refresh.return_value = MagicMock(authenticated=False)
    monkeypatch.setattr(
        web._workos.user_management, "load_sealed_session", lambda **_: fake_session
    )
    client.cookies.set(web._SESSION_COOKIE, "expired-session")

    response = client.get("/api/status")

    assert response.status_code == 401


def test_api_status_connected(logged_in_client, fake_garmin_client):
    response = logged_in_client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {"connected": True}


def test_api_status_not_connected(logged_in_client, monkeypatch):
    monkeypatch.setattr(
        web,
        "get_client",
        MagicMock(side_effect=garmin_client.GarminNotConnectedError("nope")),
    )
    response = logged_in_client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {"connected": False}


def test_api_dashboard_returns_not_connected_as_409(logged_in_client, monkeypatch):
    monkeypatch.setattr(
        web,
        "get_client",
        MagicMock(side_effect=garmin_client.GarminNotConnectedError("nope")),
    )
    response = logged_in_client.get("/api/dashboard")
    assert response.status_code == 409


def test_api_dashboard_extracts_today_and_trend(logged_in_client, fake_garmin_client):
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

    response = logged_in_client.get("/api/dashboard")

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


def test_api_weekly_check_in_resolves_the_logged_in_users_garmin_client(
    logged_in_client, fake_garmin_client
):
    fake_garmin_client.get_scheduled_workouts.return_value = {"calendarItems": []}
    fake_garmin_client.get_activities_by_date.return_value = []
    fake_garmin_client.get_training_readiness.return_value = None
    fake_garmin_client.get_hrv_data.return_value = None

    response = logged_in_client.get("/api/weekly-check-in")

    assert response.status_code == 200
    assert "weekStart" in response.json()


def test_api_plan_progress_rejects_bad_race_date(logged_in_client, fake_garmin_client):
    fake_garmin_client.get_scheduled_workouts.return_value = {"calendarItems": []}
    response = logged_in_client.get("/api/plan-progress", params={"race_date": "not-a-date"})
    assert response.status_code == 400


def test_api_disconnect_clears_the_logged_in_users_session(logged_in_client, monkeypatch):
    called_with = []
    monkeypatch.setattr(web, "disconnect_user", lambda user_id: called_with.append(user_id))

    response = logged_in_client.post("/api/disconnect")

    assert response.status_code == 200
    assert called_with == [USER_ID]


def test_login_redirects_to_workos_authorization_url(client, monkeypatch):
    monkeypatch.setattr(
        web._workos.user_management,
        "get_authorization_url",
        lambda **kwargs: "https://auth.example.com/authorize?state=abc",
    )
    response = client.get("/login")
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://auth.example.com/authorize?state=abc"


def test_callback_exchanges_code_and_sets_session_cookie(client, monkeypatch):
    fake_user = MagicMock()
    fake_user.to_dict.return_value = {"id": USER_ID, "email": "me@example.com"}
    fake_auth_response = MagicMock(
        access_token="at", refresh_token="rt", user=fake_user
    )
    monkeypatch.setattr(
        web._workos.user_management,
        "authenticate_with_code",
        lambda **_: fake_auth_response,
    )
    monkeypatch.setattr(web, "seal_session_from_auth_response", lambda **_: "sealed-value")

    response = client.get("/callback", params={"code": "abc123"})

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/"
    assert web._SESSION_COOKIE in response.cookies


def test_callback_rejects_a_failed_code_exchange(client, monkeypatch):
    monkeypatch.setattr(
        web._workos.user_management,
        "authenticate_with_code",
        MagicMock(side_effect=RuntimeError("boom: sensitive detail")),
    )
    response = client.get("/callback", params={"code": "bad"})
    assert response.status_code == 401
    assert "boom" not in response.text


def test_logout_clears_cookie_and_redirects_to_workos_logout_url(client, monkeypatch):
    fake_session = MagicMock()
    fake_session.get_logout_url.return_value = "https://auth.example.com/logout"
    monkeypatch.setattr(
        web._workos.user_management, "load_sealed_session", lambda **_: fake_session
    )
    client.cookies.set(web._SESSION_COOKIE, "sealed-session-value")

    response = client.get("/logout")

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://auth.example.com/logout"


def test_connect_garmin_creates_a_session_and_redirects(logged_in_client, tmp_path, monkeypatch):
    monkeypatch.setattr(garmin_client, "TOKEN_STORE", str(tmp_path / "store"))

    response = logged_in_client.get("/connect-garmin")

    assert response.status_code in (302, 307)
    assert response.headers["location"].startswith("/connect?token=")


def test_connect_garmin_redirects_home_if_already_connected(
    logged_in_client, tmp_path, monkeypatch
):
    monkeypatch.setattr(garmin_client, "TOKEN_STORE", str(tmp_path / "store"))
    token_path = garmin_client._user_token_path(USER_ID)
    import os

    os.makedirs(os.path.dirname(token_path), exist_ok=True)
    with open(token_path, "w") as f:
        f.write("already-connected")

    response = logged_in_client.get("/connect-garmin")

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/"


def test_connect_page_shows_credentials_form_for_a_live_session():
    from ismiseeanna_mcp import onboarding

    token = onboarding.create_session(USER_ID)
    client = TestClient(web.app)

    response = client.get(f"/connect?token={token}")

    assert response.status_code == 200
    assert "Garmin email" in response.text


def test_connect_page_shows_expired_for_an_unknown_token():
    client = TestClient(web.app)
    response = client.get("/connect?token=bogus")
    assert response.status_code == 404

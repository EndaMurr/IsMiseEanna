import json
import os
import stat
from datetime import date, timedelta

import pytest
from cryptography.fernet import Fernet

from ismiseeanna_mcp import garmin_client
from ismiseeanna_mcp.garmin_client import (
    GarminClientError,
    GarminNotConnectedError,
    _resolve_token_store,
    summarize_training_load,
)


@pytest.fixture(autouse=True)
def reset_client_singleton():
    garmin_client._client = None
    garmin_client._clients_by_user.clear()
    yield
    garmin_client._client = None
    garmin_client._clients_by_user.clear()


def test_resolve_token_store_defaults_to_home_dotfile(monkeypatch):
    monkeypatch.delenv("GARMINTOKENS", raising=False)
    resolved = _resolve_token_store()
    assert resolved == os.path.realpath(os.path.expanduser("~/.garminconnect"))


def test_resolve_token_store_accepts_path_under_home(monkeypatch, tmp_path, home_dir):
    custom = home_dir / "custom-tokens"
    monkeypatch.setenv("GARMINTOKENS", str(custom))
    assert _resolve_token_store() == os.path.realpath(str(custom))


def test_resolve_token_store_rejects_path_outside_home(monkeypatch, tmp_path, home_dir):
    outside = tmp_path / "outside-home" / "tokens"
    monkeypatch.setenv("GARMINTOKENS", str(outside))
    with pytest.raises(GarminClientError):
        _resolve_token_store()


def test_secure_token_store_locks_down_file(monkeypatch, tmp_path):
    token_file = tmp_path / "token.json"
    token_file.write_text("secret")
    token_file.chmod(0o644)
    monkeypatch.setattr(garmin_client, "TOKEN_STORE", str(token_file))

    garmin_client._secure_token_store()

    mode = stat.S_IMODE(os.stat(token_file).st_mode)
    assert mode == stat.S_IRUSR | stat.S_IWUSR


def test_secure_token_store_locks_down_directory(monkeypatch, tmp_path):
    token_dir = tmp_path / "tokens"
    token_dir.mkdir(mode=0o755)
    nested_file = token_dir / "oauth2_token.json"
    nested_file.write_text("secret")
    nested_file.chmod(0o644)
    monkeypatch.setattr(garmin_client, "TOKEN_STORE", str(token_dir))

    garmin_client._secure_token_store()

    assert stat.S_IMODE(os.stat(token_dir).st_mode) == stat.S_IRWXU
    assert stat.S_IMODE(os.stat(nested_file).st_mode) == stat.S_IRUSR | stat.S_IWUSR


def test_get_client_raises_without_credentials_or_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(garmin_client, "TOKEN_STORE", str(tmp_path / "no-such-token"))
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)

    with pytest.raises(GarminClientError, match="GARMIN_EMAIL"):
        garmin_client.get_client()


def test_get_client_returns_cached_singleton(monkeypatch):
    sentinel = object()
    garmin_client._client = sentinel
    assert garmin_client.get_client() is sentinel


def test_get_client_wraps_login_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(garmin_client, "TOKEN_STORE", str(tmp_path / "no-such-token"))
    monkeypatch.setenv("GARMIN_EMAIL", "test@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "hunter2")

    class FakeGarmin:
        def __init__(self, email=None, password=None):
            pass

        def login(self, tokenstore):
            raise ValueError("boom: some unexpected error with sensitive payload")

    monkeypatch.setattr(garmin_client, "Garmin", FakeGarmin)

    with pytest.raises(GarminClientError) as exc_info:
        garmin_client.get_client()

    assert "boom" not in str(exc_info.value)
    assert "ValueError" in str(exc_info.value)


def test_get_client_secures_token_store_after_login(monkeypatch, tmp_path):
    token_store = tmp_path / "token.json"
    monkeypatch.setattr(garmin_client, "TOKEN_STORE", str(token_store))
    monkeypatch.setenv("GARMIN_EMAIL", "test@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "hunter2")

    class FakeGarmin:
        def __init__(self, email=None, password=None):
            pass

        def login(self, tokenstore):
            with open(tokenstore, "w") as f:
                f.write("token")
            os.chmod(tokenstore, 0o644)

    monkeypatch.setattr(garmin_client, "Garmin", FakeGarmin)

    client = garmin_client.get_client()

    assert isinstance(client, FakeGarmin)
    assert stat.S_IMODE(os.stat(token_store).st_mode) == stat.S_IRUSR | stat.S_IWUSR


# ---------------------------------------------------------------------------
# Multi-user (hosted) sessions
# ---------------------------------------------------------------------------


class _FakeInnerClient:
    def __init__(self):
        self.data = {"di_token": "t", "di_refresh_token": "r", "di_client_id": "c"}

    def dumps(self):
        return json.dumps(self.data)

    def loads(self, s):
        self.data = json.loads(s)


class FakeGarminForStorage:
    """Mimics enough of Garmin for the encrypt/decrypt round trip: a real
    login() that reads whatever the temp-file loader wrote, same as the
    real Garmin.login() would when resuming from a cached token."""

    def __init__(self, email=None, password=None):
        self.client = _FakeInnerClient()

    def login(self, tokenstore_path):
        path = os.path.join(tokenstore_path, "garmin_tokens.json")
        with open(path) as f:
            self.client.loads(f.read())


@pytest.mark.parametrize(
    "user_id,valid",
    [
        ("user_123-ABC", True),
        ("a" * 128, True),
        ("../etc/passwd", False),
        ("a/b", False),
        ("", False),
        ("a" * 129, False),
    ],
)
def test_safe_user_dirname_rejects_unsafe_ids(user_id, valid):
    if valid:
        assert garmin_client._safe_user_dirname(user_id) == user_id
    else:
        with pytest.raises(GarminClientError):
            garmin_client._safe_user_dirname(user_id)


def test_write_then_read_user_tokens_round_trips_through_encryption(monkeypatch, tmp_path):
    monkeypatch.setattr(garmin_client, "TOKEN_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(garmin_client, "Garmin", FakeGarminForStorage)

    original = FakeGarminForStorage()
    original.client.data = {"di_token": "abc", "di_refresh_token": "def", "di_client_id": "ghi"}
    garmin_client._write_user_tokens("user-1", original)

    raw = (tmp_path / "store" / "user-1" / "garmin_tokens.json").read_bytes()
    assert b"di_token" not in raw  # not plaintext on disk

    restored = garmin_client._read_user_tokens("user-1")
    assert restored.client.data == original.client.data


def test_read_user_tokens_rejects_wrong_encryption_key(monkeypatch, tmp_path):
    monkeypatch.setattr(garmin_client, "TOKEN_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(garmin_client, "Garmin", FakeGarminForStorage)
    garmin_client._write_user_tokens("user-1", FakeGarminForStorage())

    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())  # different key
    with pytest.raises(GarminClientError, match="decrypted"):
        garmin_client._read_user_tokens("user-1")


def test_get_client_for_user_returns_cached_client(monkeypatch):
    sentinel = object()
    garmin_client._clients_by_user["user-1"] = sentinel
    assert garmin_client._get_client_for_user("user-1") is sentinel


def test_get_client_for_user_raises_not_connected_when_no_tokens(monkeypatch, tmp_path):
    monkeypatch.setattr(garmin_client, "TOKEN_STORE", str(tmp_path / "store"))
    with pytest.raises(GarminNotConnectedError, match="start_garmin_connection"):
        garmin_client._get_client_for_user("user-1")


def test_get_client_for_user_wraps_login_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(garmin_client, "TOKEN_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(garmin_client, "Garmin", FakeGarminForStorage)
    garmin_client._write_user_tokens("user-1", FakeGarminForStorage())

    class FailingFakeGarmin:
        def __init__(self, email=None, password=None):
            self.client = _FakeInnerClient()

        def login(self, tokenstore_path):
            raise ValueError("boom: sensitive detail")

    monkeypatch.setattr(garmin_client, "Garmin", FailingFakeGarmin)

    with pytest.raises(GarminClientError) as exc_info:
        garmin_client._get_client_for_user("user-1")
    assert "boom" not in str(exc_info.value)


def test_get_client_for_user_requires_a_user_id():
    with pytest.raises(GarminClientError):
        garmin_client._get_client_for_user(None)


def test_disconnect_user_clears_cache_and_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(garmin_client, "TOKEN_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(garmin_client, "Garmin", FakeGarminForStorage)
    garmin_client._write_user_tokens("user-1", FakeGarminForStorage())
    garmin_client._clients_by_user["user-1"] = object()

    garmin_client.disconnect_user("user-1")

    assert "user-1" not in garmin_client._clients_by_user
    assert not os.path.exists(tmp_path / "store" / "user-1")


def test_get_client_dispatches_to_legacy_singleton_when_unauthenticated(monkeypatch):
    monkeypatch.setattr(
        "mcp.server.auth.middleware.auth_context.get_access_token", lambda: None
    )
    sentinel = object()
    garmin_client._client = sentinel
    assert garmin_client.get_client() is sentinel


def test_get_client_dispatches_to_per_user_client_when_authenticated(monkeypatch):
    fake_access_token = type("FakeAccessToken", (), {"subject": "user-1"})()
    monkeypatch.setattr(
        "mcp.server.auth.middleware.auth_context.get_access_token",
        lambda: fake_access_token,
    )
    sentinel = object()
    garmin_client._clients_by_user["user-1"] = sentinel
    assert garmin_client.get_client() is sentinel


def _activity(days_ago: int, today: date, type_key: str, distance: float, duration: float) -> dict:
    activity_date = today - timedelta(days=days_ago)
    return {
        "activityType": {"typeKey": type_key},
        "startTimeLocal": f"{activity_date.isoformat()} 07:00:00",
        "distance": distance,
        "duration": duration,
    }


def test_summarize_training_load_buckets_this_week_and_last_week():
    today = date(2026, 8, 29)
    activities = [
        _activity(0, today, "running", distance=8000, duration=2400),  # this week
        _activity(6, today, "strength_training", distance=0, duration=1800),  # this week (edge)
        _activity(7, today, "running", distance=10000, duration=3000),  # last week (edge)
        _activity(13, today, "running", distance=5000, duration=1500),  # last week (edge)
        _activity(14, today, "running", distance=99999, duration=99999),  # outside both weeks
    ]

    result = summarize_training_load(activities, today=today)

    assert result["thisWeek"] == {
        "durationSeconds": 2400 + 1800,
        "runningDistanceMeters": 8000,
        "workoutCount": 2,
    }
    assert result["lastWeek"] == {
        "durationSeconds": 3000 + 1500,
        "runningDistanceMeters": 15000,
        "workoutCount": 2,
    }


def test_summarize_training_load_ignores_activities_with_no_parseable_date():
    today = date(2026, 8, 29)
    activities = [{"activityType": {"typeKey": "running"}, "distance": 5000, "duration": 1500}]

    result = summarize_training_load(activities, today=today)

    assert result["thisWeek"] == {"durationSeconds": 0, "runningDistanceMeters": 0, "workoutCount": 0}

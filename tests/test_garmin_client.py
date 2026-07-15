import os
import stat
import threading
import time

import pytest

from ismiseeanna_mcp import garmin_client
from ismiseeanna_mcp.garmin_client import GarminClientError, _resolve_token_store


@pytest.fixture(autouse=True)
def reset_client_singleton():
    garmin_client._client = None
    yield
    garmin_client._client = None


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


def test_get_client_only_logs_in_once_under_concurrent_calls(monkeypatch, tmp_path):
    token_store = tmp_path / "token.json"
    monkeypatch.setattr(garmin_client, "TOKEN_STORE", str(token_store))
    monkeypatch.setenv("GARMIN_EMAIL", "test@example.com")
    monkeypatch.setenv("GARMIN_PASSWORD", "hunter2")

    login_count = 0
    login_lock = threading.Lock()

    class FakeGarmin:
        def __init__(self, email=None, password=None):
            pass

        def login(self, tokenstore):
            nonlocal login_count
            time.sleep(0.05)
            with login_lock:
                login_count += 1
            with open(tokenstore, "w") as f:
                f.write("token")

    monkeypatch.setattr(garmin_client, "Garmin", FakeGarmin)

    results = []

    def call_get_client():
        results.append(garmin_client.get_client())

    threads = [threading.Thread(target=call_get_client) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert login_count == 1
    assert len(results) == 8
    assert all(result is results[0] for result in results)

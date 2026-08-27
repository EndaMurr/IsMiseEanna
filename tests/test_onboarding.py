import json
import os
import time

import pytest
from cryptography.fernet import Fernet
from garminconnect import GarminConnectAuthenticationError

from ismiseeanna_mcp import garmin_client, onboarding


@pytest.fixture(autouse=True)
def isolated_token_store(monkeypatch, tmp_path):
    monkeypatch.setattr(garmin_client, "TOKEN_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    onboarding._sessions.clear()
    yield
    onboarding._sessions.clear()


class _FakeInnerClient:
    def __init__(self):
        self.data = {}

    def dumps(self):
        return json.dumps(self.data)

    def loads(self, s):
        self.data = json.loads(s)


class FakeGarminNoMfa:
    """A clean, no-MFA login - garminconnect never calls dump() itself when
    return_on_mfa=True, even on this immediate-success path."""

    def __init__(self, email=None, password=None, return_on_mfa=False):
        self.client = _FakeInnerClient()
        self.client.data = {"di_token": "fresh-token"}

    def login(self, tokenstore):
        return (None, None)


class FakeGarminNeedsMfa:
    def __init__(self, email=None, password=None, return_on_mfa=False):
        self.client = _FakeInnerClient()
        self.resumed = False

    def login(self, tokenstore):
        return ("needs_mfa", None)

    def resume_login(self, client_state, mfa_code):
        if mfa_code != "123456":
            raise GarminConnectAuthenticationError("bad code")
        self.resumed = True
        self.client.data = {"di_token": "post-mfa-token"}
        return (None, None)


class FakeGarminRejectsCredentials:
    def __init__(self, email=None, password=None, return_on_mfa=False):
        self.client = _FakeInnerClient()

    def login(self, tokenstore):
        raise GarminConnectAuthenticationError("invalid")


def _stored_tokens(user_id: str) -> dict:
    path = os.path.join(garmin_client.TOKEN_STORE, user_id, "garmin_tokens.json")
    encrypted = open(path, "rb").read()
    plaintext = garmin_client._fernet().decrypt(encrypted).decode()
    return json.loads(plaintext)


def test_create_session_starts_awaiting_credentials():
    token = onboarding.create_session("user-1")
    assert onboarding.get_session_state(token) == "awaiting_credentials"


def test_get_session_state_none_for_unknown_token():
    assert onboarding.get_session_state("not-a-real-token") is None


def test_sessions_expire_after_ttl(monkeypatch):
    token = onboarding.create_session("user-1")
    real_monotonic = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: real_monotonic + 999999)
    assert onboarding.get_session_state(token) is None


def test_submit_credentials_persists_tokens_on_immediate_success(monkeypatch):
    monkeypatch.setattr(onboarding, "Garmin", FakeGarminNoMfa)
    token = onboarding.create_session("user-1")

    result = onboarding.submit_credentials(token, "me@example.com", "hunter2")

    assert result == {"status": "connected"}
    assert _stored_tokens("user-1") == {"di_token": "fresh-token"}
    assert onboarding.get_session_state(token) is None  # single-use, now consumed


def test_submit_credentials_rejects_wrong_password(monkeypatch):
    monkeypatch.setattr(onboarding, "Garmin", FakeGarminRejectsCredentials)
    token = onboarding.create_session("user-1")

    result = onboarding.submit_credentials(token, "me@example.com", "wrong")

    assert result["status"] == "error"
    assert onboarding.get_session_state(token) == "awaiting_credentials"  # can retry


def test_submit_credentials_with_invalid_token():
    result = onboarding.submit_credentials("bogus", "me@example.com", "hunter2")
    assert result == {"status": "invalid_token"}


def test_submit_credentials_requiring_mfa_moves_to_awaiting_mfa(monkeypatch):
    monkeypatch.setattr(onboarding, "Garmin", FakeGarminNeedsMfa)
    token = onboarding.create_session("user-1")

    result = onboarding.submit_credentials(token, "me@example.com", "hunter2")

    assert result == {"status": "mfa_required"}
    assert onboarding.get_session_state(token) == "awaiting_mfa"
    # not persisted yet - only the credentials step happened
    assert not os.path.exists(garmin_client._user_token_path("user-1"))


def test_submit_mfa_persists_tokens_on_success(monkeypatch):
    monkeypatch.setattr(onboarding, "Garmin", FakeGarminNeedsMfa)
    token = onboarding.create_session("user-1")
    onboarding.submit_credentials(token, "me@example.com", "hunter2")

    result = onboarding.submit_mfa(token, "123456")

    assert result == {"status": "connected"}
    assert _stored_tokens("user-1") == {"di_token": "post-mfa-token"}
    assert onboarding.get_session_state(token) is None


def test_submit_mfa_wrong_code_allows_retry_until_cap(monkeypatch):
    monkeypatch.setattr(onboarding, "Garmin", FakeGarminNeedsMfa)
    token = onboarding.create_session("user-1")
    onboarding.submit_credentials(token, "me@example.com", "hunter2")

    for _ in range(onboarding._MAX_MFA_ATTEMPTS):
        result = onboarding.submit_mfa(token, "000000")
        assert result["status"] == "error"

    # cap now reached - one more attempt is rejected outright, session gone
    result = onboarding.submit_mfa(token, "000000")
    assert result == {"status": "too_many_attempts"}
    assert onboarding.get_session_state(token) is None


def test_submit_mfa_with_invalid_token():
    result = onboarding.submit_mfa("bogus", "123456")
    assert result == {"status": "invalid_token"}


def test_submit_mfa_before_credentials_step_is_invalid_token():
    token = onboarding.create_session("user-1")
    result = onboarding.submit_mfa(token, "123456")
    assert result == {"status": "invalid_token"}

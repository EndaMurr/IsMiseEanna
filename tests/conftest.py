import os

import pytest

# web.py reads these at import time (fails fast on a real deployment with
# missing config) - set harmless dummy values so importing it in tests
# doesn't require real WorkOS credentials. No network call happens just
# from constructing a WorkOSClient with fake ones.
os.environ.setdefault("WORKOS_API_KEY", "sk_test_dummy")
os.environ.setdefault("WORKOS_CLIENT_ID", "client_test_dummy")
os.environ.setdefault("WEB_REDIRECT_URI", "https://example.com/callback")
os.environ.setdefault("WORKOS_COOKIE_PASSWORD", "test-cookie-password-at-least-32-bytes-long")


@pytest.fixture
def home_dir(tmp_path, monkeypatch):
    """A fake $HOME, isolated from the real one and from other tmp_path dirs."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home

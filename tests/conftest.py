import pytest


@pytest.fixture
def home_dir(tmp_path, monkeypatch):
    """A fake $HOME, isolated from the real one and from other tmp_path dirs."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home

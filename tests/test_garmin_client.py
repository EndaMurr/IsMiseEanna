import os
import stat

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


def test_build_structured_running_workout_requires_at_least_one_step():
    with pytest.raises(GarminClientError):
        garmin_client.build_structured_running_workout("Run", [])


def test_build_structured_running_workout_requires_exactly_one_end_condition():
    with pytest.raises(GarminClientError):
        garmin_client.build_structured_running_workout("Run", [{"kind": "warmup"}])
    with pytest.raises(GarminClientError):
        garmin_client.build_structured_running_workout(
            "Run",
            [{"kind": "warmup", "distance_meters": 1000, "duration_seconds": 300}],
        )


def test_build_structured_running_workout_rejects_unknown_kind():
    with pytest.raises(GarminClientError):
        garmin_client.build_structured_running_workout(
            "Run", [{"kind": "sprint", "distance_meters": 400}]
        )


def test_build_structured_running_workout_by_distance_no_target():
    workout = garmin_client.build_structured_running_workout(
        "Easy 5k", [{"kind": "warmup", "distance_meters": 5000}]
    )

    assert workout["workoutName"] == "Easy 5k"
    assert workout["estimatedDurationInSecs"] == 1800
    step = workout["workoutSegments"][0]["workoutSteps"][0]
    assert step["stepType"]["stepTypeKey"] == "warmup"
    assert step["endCondition"]["conditionTypeKey"] == "distance"
    assert step["endConditionValue"] == 5000
    assert step["targetType"]["workoutTargetTypeKey"] == "no.target"
    assert "targetValueOne" not in step


def test_build_structured_running_workout_by_duration():
    workout = garmin_client.build_structured_running_workout(
        "Easy run", [{"kind": "recovery", "duration_seconds": 1800}]
    )

    assert workout["estimatedDurationInSecs"] == 1800
    step = workout["workoutSegments"][0]["workoutSteps"][0]
    assert step["endCondition"]["conditionTypeKey"] == "time"
    assert step["endConditionValue"] == 1800


def test_build_structured_running_workout_rejects_both_pace_and_hr_target():
    with pytest.raises(GarminClientError):
        garmin_client.build_structured_running_workout(
            "Run",
            [
                {
                    "kind": "interval",
                    "duration_seconds": 300,
                    "target_pace_min_per_km": 240,
                    "target_pace_max_per_km": 255,
                    "target_hr_min": 150,
                    "target_hr_max": 160,
                }
            ],
        )


def test_build_structured_running_workout_rejects_incomplete_pace_target():
    with pytest.raises(GarminClientError):
        garmin_client.build_structured_running_workout(
            "Run",
            [{"kind": "interval", "duration_seconds": 300, "target_pace_min_per_km": 240}],
        )


def test_build_structured_running_workout_pace_target_converts_to_ordered_speed():
    # 4:00/km (faster) and 5:00/km (slower) -> speeds 4.1667 m/s and 3.3333 m/s.
    # targetValueOne must be the slower pace's (lower) speed, targetValueTwo the faster.
    workout = garmin_client.build_structured_running_workout(
        "Tempo",
        [
            {
                "kind": "interval",
                "duration_seconds": 300,
                "target_pace_min_per_km": 240,
                "target_pace_max_per_km": 300,
            }
        ],
    )

    step = workout["workoutSegments"][0]["workoutSteps"][0]
    assert step["targetType"]["workoutTargetTypeKey"] == "speed.zone"
    assert step["targetValueOne"] == pytest.approx(1000 / 300)
    assert step["targetValueTwo"] == pytest.approx(1000 / 240)


def test_build_structured_running_workout_hr_target_orders_bounds():
    workout = garmin_client.build_structured_running_workout(
        "Tempo",
        [{"kind": "interval", "duration_seconds": 300, "target_hr_min": 160, "target_hr_max": 150}],
    )

    step = workout["workoutSegments"][0]["workoutSteps"][0]
    assert step["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert step["targetValueOne"] == 150
    assert step["targetValueTwo"] == 160


def test_build_structured_running_workout_multi_step_orders_sequentially():
    workout = garmin_client.build_structured_running_workout(
        "Session",
        [
            {"kind": "warmup", "distance_meters": 1000},
            {"kind": "interval", "distance_meters": 3000},
            {"kind": "cooldown", "distance_meters": 1000},
        ],
    )

    steps = workout["workoutSegments"][0]["workoutSteps"]
    assert [s["stepOrder"] for s in steps] == [1, 2, 3]
    assert [s["stepType"]["stepTypeKey"] for s in steps] == ["warmup", "interval", "cooldown"]


def test_build_structured_running_workout_repeat_block():
    workout = garmin_client.build_structured_running_workout(
        "Intervals",
        [
            {"kind": "warmup", "duration_seconds": 600},
            {
                "repeat": {
                    "count": 4,
                    "steps": [
                        {
                            "kind": "interval",
                            "duration_seconds": 180,
                            "target_pace_min_per_km": 240,
                            "target_pace_max_per_km": 255,
                        },
                        {"kind": "recovery", "duration_seconds": 120},
                    ],
                }
            },
            {"kind": "cooldown", "duration_seconds": 600},
        ],
    )

    steps = workout["workoutSegments"][0]["workoutSteps"]
    assert len(steps) == 3
    repeat_group = steps[1]
    assert repeat_group["numberOfIterations"] == 4
    assert len(repeat_group["workoutSteps"]) == 2
    assert repeat_group["workoutSteps"][0]["stepType"]["stepTypeKey"] == "interval"
    assert repeat_group["workoutSteps"][1]["stepType"]["stepTypeKey"] == "recovery"

    # 600 warmup + 4 * (180 + 120) + 600 cooldown = 2400
    assert workout["estimatedDurationInSecs"] == 2400


def test_build_structured_running_workout_rejects_bad_repeat_count():
    with pytest.raises(GarminClientError):
        garmin_client.build_structured_running_workout(
            "Run",
            [{"repeat": {"count": 0, "steps": [{"kind": "interval", "duration_seconds": 60}]}}],
        )


def test_build_structured_running_workout_rejects_empty_repeat_steps():
    with pytest.raises(GarminClientError):
        garmin_client.build_structured_running_workout(
            "Run", [{"repeat": {"count": 3, "steps": []}}]
        )


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

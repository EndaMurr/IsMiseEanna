"""Authenticated Garmin Connect client, shared across MCP tool calls."""

import logging
import os
import stat
from datetime import date, timedelta
from typing import Any

from garminconnect import Garmin, GarminConnectAuthenticationError

logger = logging.getLogger(__name__)


class GarminClientError(RuntimeError):
    pass


def _resolve_token_store() -> str:
    """Resolve GARMINTOKENS to a real path, rejecting anything outside $HOME."""
    raw = os.environ.get("GARMINTOKENS", "~/.garminconnect")
    resolved = os.path.realpath(os.path.expanduser(raw))
    home = os.path.realpath(os.path.expanduser("~"))
    if os.path.commonpath([resolved, home]) != home:
        raise GarminClientError(
            f"GARMINTOKENS ({raw!r}) must resolve to a path under the home "
            "directory."
        )
    return resolved


TOKEN_STORE = _resolve_token_store()

_client: Garmin | None = None


def _secure_token_store() -> None:
    """Restrict the token cache to owner-only access."""
    if os.path.isdir(TOKEN_STORE):
        os.chmod(TOKEN_STORE, stat.S_IRWXU)
        for root, dirs, files in os.walk(TOKEN_STORE):
            for name in dirs:
                os.chmod(os.path.join(root, name), stat.S_IRWXU)
            for name in files:
                os.chmod(os.path.join(root, name), stat.S_IRUSR | stat.S_IWUSR)
    elif os.path.isfile(TOKEN_STORE):
        os.chmod(TOKEN_STORE, stat.S_IRUSR | stat.S_IWUSR)


def get_client() -> Garmin:
    """Return a logged-in Garmin client, resuming a cached session when possible.

    ``Garmin.login(tokenstore)`` handles both paths itself: it resumes from a
    cached token at ``tokenstore`` if one exists, and otherwise logs in with
    the constructor's email/password and saves the resulting token there.
    """
    global _client
    if _client is not None:
        return _client

    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not (email and password) and not os.path.exists(TOKEN_STORE):
        raise GarminClientError(
            "No cached Garmin session found and GARMIN_EMAIL/GARMIN_PASSWORD "
            "are not set. Set both env vars for the first login; the session "
            f"is then cached at {TOKEN_STORE} so future calls don't need the "
            "password."
        )

    client = Garmin(email=email, password=password)
    try:
        client.login(TOKEN_STORE)
    except GarminConnectAuthenticationError as e:
        logger.exception("Garmin login failed (authentication rejected)")
        raise GarminClientError(
            "Garmin login failed: invalid credentials or authentication was "
            "rejected. If this is the first run, set GARMIN_EMAIL and "
            "GARMIN_PASSWORD; the session is then cached at "
            f"{TOKEN_STORE} so future calls don't need the password."
        ) from e
    except Exception as e:
        logger.exception("Garmin login failed unexpectedly")
        raise GarminClientError(
            f"Garmin login failed unexpectedly ({type(e).__name__})."
        ) from e

    _secure_token_store()
    _client = client
    return _client


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------
#
# garminconnect passes through Garmin Connect's own undocumented,
# reverse-engineered API responses verbatim. The field paths below are a
# best-effort reading of that shape; spot-check extracted values against the
# real Garmin Connect app before trusting them, and adjust these extractors
# if a field path turns out to be wrong.


def _extract_body_battery(day_data: Any) -> float | None:
    entry = (day_data or [None])[0] if isinstance(day_data, list) else day_data
    if not entry:
        return None
    samples = entry.get("bodyBatteryValuesArray") or []
    if samples:
        return samples[-1][1]
    return entry.get("charged")


def _extract_training_readiness(day_data: Any) -> float | None:
    entry = (day_data or [None])[0] if isinstance(day_data, list) else day_data
    return (entry or {}).get("score")


def _extract_sleep_score(day_data: Any) -> float | None:
    dto = (day_data or {}).get("dailySleepDTO") or {}
    scores = dto.get("sleepScores") or {}
    overall = scores.get("overall") or {}
    return overall.get("value")


def _extract_resting_heart_rate(day_data: Any) -> float | None:
    metrics_map = ((day_data or {}).get("allMetrics") or {}).get("metricsMap") or {}
    entries = metrics_map.get("WELLNESS_RESTING_HEART_RATE") or []
    return entries[-1]["value"] if entries else None


def _extract_hrv(day_data: Any) -> float | None:
    summary = (day_data or {}).get("hrvSummary") or {}
    return summary.get("lastNightAvg")


def _n_day_trend(fetch_day, extract, days: int = 7, end: date | None = None) -> list[float | None]:
    """Best-effort per-day trend ending on ``end`` (default today), oldest first.

    Any single day's fetch/extract failure yields ``None`` for that day rather
    than failing the whole trend, since transient per-day Garmin errors
    shouldn't blank out the rest of a week's data.
    """
    end = end or date.today()
    values = []
    for i in range(days - 1, -1, -1):
        day_str = (end - timedelta(days=i)).isoformat()
        try:
            values.append(extract(fetch_day(day_str)))
        except Exception:
            values.append(None)
    return values

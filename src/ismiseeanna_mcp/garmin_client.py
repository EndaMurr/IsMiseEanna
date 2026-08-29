"""Authenticated Garmin Connect client, shared across MCP tool calls."""

import logging
import os
import re
import shutil
import stat
import tempfile
import threading
from datetime import date, timedelta
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from garminconnect import Garmin, GarminConnectAuthenticationError

logger = logging.getLogger(__name__)


class GarminClientError(RuntimeError):
    pass


class GarminNotConnectedError(GarminClientError):
    """A hosted/authenticated caller has no cached Garmin session yet."""


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

_clients_by_user: dict[str, Garmin] = {}
_clients_lock = threading.Lock()

_SAFE_USER_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _secure_token_store(path: str | None = None) -> None:
    """Restrict a token cache path to owner-only access."""
    path = path or TOKEN_STORE
    if os.path.isdir(path):
        os.chmod(path, stat.S_IRWXU)
        for root, dirs, files in os.walk(path):
            for name in dirs:
                os.chmod(os.path.join(root, name), stat.S_IRWXU)
            for name in files:
                os.chmod(os.path.join(root, name), stat.S_IRUSR | stat.S_IWUSR)
    elif os.path.isfile(path):
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def get_client() -> Garmin:
    """Resolve the Garmin client for the current request.

    Hosted/authenticated callers (a verified WorkOS bearer token on this
    request) each get their own Garmin session, cached and stored separately
    by their WorkOS user id. Local stdio use (no auth configured, so no
    access token to read) falls back to the single-account behavior this
    always had, keyed off GARMIN_EMAIL/GARMIN_PASSWORD.
    """
    from mcp.server.auth.middleware.auth_context import get_access_token

    access_token = get_access_token()
    if access_token is None:
        return _get_legacy_singleton_client()
    return _get_client_for_user(access_token.subject)


def _get_legacy_singleton_client() -> Garmin:
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
# Multi-user (hosted) Garmin sessions
# ---------------------------------------------------------------------------
#
# Each WorkOS-authenticated caller gets their own Garmin session, encrypted
# at rest and keyed by their verified `sub` claim - never mixed with the
# single-account path above, which only ever runs when there's no
# authenticated caller at all (local stdio use).


def _safe_user_dirname(user_id: str) -> str:
    """Validate a WorkOS user id before using it as a directory name.

    This should never fail for a real WorkOS id, but the token store layout
    depends on it being a plain identifier - refuse anything unexpected
    (e.g. path-traversal shaped) rather than guessing.
    """
    if not _SAFE_USER_ID.match(user_id):
        raise GarminClientError(
            "Unusable identity claim; refusing to derive a token path from it."
        )
    return user_id


def _user_token_store(user_id: str) -> str:
    """Per-user token directory nested under TOKEN_STORE (hosted mode only)."""
    return os.path.join(TOKEN_STORE, _safe_user_dirname(user_id))


def _user_token_path(user_id: str) -> str:
    return os.path.join(_user_token_store(user_id), "garmin_tokens.json")


def _fernet() -> Fernet:
    key = os.environ.get("TOKEN_ENCRYPTION_KEY")
    if not key:
        raise GarminClientError(
            "TOKEN_ENCRYPTION_KEY is required in hosted mode. Generate one "
            'with: python3 -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode())


def _write_user_tokens(user_id: str, garmin: Garmin) -> None:
    """Persist ``garmin``'s session, encrypted at rest, for ``user_id``.

    Uses garminconnect's string-based dumps() rather than its file-writing
    dump() so the plaintext token JSON only ever exists in memory, for as
    long as it takes to encrypt it - never touching disk unencrypted.
    """
    store_dir = _user_token_store(user_id)
    os.makedirs(store_dir, exist_ok=True)
    encrypted = _fernet().encrypt(garmin.client.dumps().encode())
    with open(_user_token_path(user_id), "wb") as fh:
        fh.write(encrypted)
    _secure_token_store(store_dir)


def _read_user_tokens(user_id: str) -> Garmin:
    """Restore a fully logged-in Garmin client from a user's encrypted tokens.

    Deliberately routes the decrypted tokens through Garmin.login() (via a
    throwaway temp file) rather than the lower-level client.loads() - login()
    also fetches and populates display_name/full_name/unit_system, which
    several endpoints (get_personal_records, get_sleep_data, and others)
    interpolate directly into their request URL and 404/403 without. Running
    the library's own tested load-and-populate path avoids re-implementing
    (and risking drift from) that logic. The plaintext token only exists in
    a process-local temp directory for the duration of this call; the
    persistent copy on disk stays encrypted throughout.
    """
    with open(_user_token_path(user_id), "rb") as fh:
        encrypted = fh.read()
    try:
        plaintext = _fernet().decrypt(encrypted).decode()
    except InvalidToken as e:
        raise GarminClientError(
            "Stored Garmin session couldn't be decrypted (wrong or rotated "
            "TOKEN_ENCRYPTION_KEY?). Reconnect via start_garmin_connection."
        ) from e

    garmin = Garmin()
    with tempfile.TemporaryDirectory() as tmp_dir:
        with open(os.path.join(tmp_dir, "garmin_tokens.json"), "w") as fh:
            fh.write(plaintext)
        try:
            garmin.login(tmp_dir)
        except GarminConnectAuthenticationError as e:
            raise GarminClientError(
                "Stored Garmin session was rejected (expired or revoked). "
                "Reconnect via start_garmin_connection."
            ) from e
        except Exception as e:
            raise GarminClientError(
                f"Garmin login failed unexpectedly ({type(e).__name__})."
            ) from e

    # login() may have refreshed the access token in memory without writing
    # it anywhere (it only dumps on a fresh credentials login) - persist
    # whatever it ended up with back to the encrypted store.
    _write_user_tokens(user_id, garmin)
    return garmin


def _get_client_for_user(user_id: str | None) -> Garmin:
    if not user_id:
        raise GarminClientError("Authenticated request has no usable identity claim (sub).")

    with _clients_lock:
        cached = _clients_by_user.get(user_id)
        if cached is not None:
            return cached

        if not os.path.exists(_user_token_path(user_id)):
            raise GarminNotConnectedError(
                "Garmin account not connected yet. Call start_garmin_connection "
                "and open the link it returns to link your Garmin account."
            )

        client = _read_user_tokens(user_id)
        _clients_by_user[user_id] = client
        return client


def disconnect_user(user_id: str) -> None:
    """Remove a hosted user's cached client and stored tokens entirely."""
    with _clients_lock:
        _clients_by_user.pop(user_id, None)
    store_dir = _user_token_store(user_id)
    if os.path.isdir(store_dir):
        shutil.rmtree(store_dir, ignore_errors=True)


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


def summarize_activity(activity: dict) -> dict:
    """Reduce a raw get_activities()/get_activities_by_date() entry to the
    fields the dashboard and MCP tools both need. Shared here (rather than
    living in server.py, which only server.py used to import) since web.py
    needs the exact same shape for the dashboard's "recent workouts" list."""
    return {
        "activityId": activity.get("activityId"),
        "name": activity.get("activityName"),
        "type": (activity.get("activityType") or {}).get("typeKey"),
        "startTimeLocal": activity.get("startTimeLocal"),
        "distanceMeters": activity.get("distance"),
        "durationSeconds": activity.get("duration"),
        "calories": activity.get("calories"),
        "averageHR": activity.get("averageHR"),
    }

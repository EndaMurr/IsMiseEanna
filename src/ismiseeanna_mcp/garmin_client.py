"""Authenticated Garmin Connect client, shared across MCP tool calls."""

import logging
import os
import stat

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

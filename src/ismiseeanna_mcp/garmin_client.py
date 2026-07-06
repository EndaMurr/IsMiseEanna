"""Authenticated Garmin Connect client, shared across MCP tool calls."""

import os

from garminconnect import Garmin, GarminConnectAuthenticationError

TOKEN_STORE = os.environ.get("GARMINTOKENS", os.path.expanduser("~/.garminconnect"))

_client: Garmin | None = None


class GarminClientError(RuntimeError):
    pass


def get_client() -> Garmin:
    """Return a logged-in Garmin client, resuming a cached session when possible.

    ``Garmin.login(tokenstore)`` handles both paths itself: it resumes from a
    cached token at ``tokenstore`` if one exists, and otherwise logs in with
    the constructor's email/password and saves the resulting token there.
    """
    global _client
    if _client is not None:
        return _client

    client = Garmin(
        email=os.environ.get("GARMIN_EMAIL"),
        password=os.environ.get("GARMIN_PASSWORD"),
    )
    try:
        client.login(TOKEN_STORE)
    except GarminConnectAuthenticationError as e:
        raise GarminClientError(
            f"Garmin login failed ({e}). If this is the first run, set "
            "GARMIN_EMAIL and GARMIN_PASSWORD; the session is then cached at "
            f"{TOKEN_STORE} so future calls don't need the password."
        ) from e

    _client = client
    return _client

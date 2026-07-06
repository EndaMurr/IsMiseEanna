"""Authenticated Garmin Connect client, shared across MCP tool calls."""

import os

from garminconnect import Garmin, GarminConnectAuthenticationError

TOKEN_STORE = os.environ.get("GARMINTOKENS", os.path.expanduser("~/.garminconnect"))

_client: Garmin | None = None


class GarminClientError(RuntimeError):
    pass


def get_client() -> Garmin:
    """Return a logged-in Garmin client, resuming a cached session when possible."""
    global _client
    if _client is not None:
        return _client

    try:
        client = Garmin()
        client.login(TOKEN_STORE)
    except (FileNotFoundError, GarminConnectAuthenticationError):
        email = os.environ.get("GARMIN_EMAIL")
        password = os.environ.get("GARMIN_PASSWORD")
        if not email or not password:
            raise GarminClientError(
                "No cached Garmin session found at "
                f"{TOKEN_STORE}, and GARMIN_EMAIL/GARMIN_PASSWORD are not set. "
                "Set both env vars for the first login; the session is then "
                "cached so future calls don't need the password."
            )
        client = Garmin(email=email, password=password)
        client.login()
        client.garth.dump(TOKEN_STORE)

    _client = client
    return _client

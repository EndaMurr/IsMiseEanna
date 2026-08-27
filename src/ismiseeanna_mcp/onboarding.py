"""Garmin account connection flow for hosted (multi-tenant) mode.

A WorkOS-authenticated caller gets a one-time link (start_garmin_connection)
rather than being asked to paste their Garmin email/password into an MCP
tool argument, which would sit in claude.ai's own conversation history.
Opening that link hits a plain HTML form (server.py's /connect routes) that
posts credentials straight to this server - never through the chat/tool-call
path at all.

Garmin's MFA-capable login (garminconnect's Garmin(..., return_on_mfa=True))
returns a distinguishable "needs_mfa" status rather than raising; resuming
it requires calling resume_login() on the *exact same* in-memory Garmin
instance, since its MFA session state (cookies, flow params) isn't
serializable. That instance is held here, in-process, between the
credentials POST and the MFA-code POST - this deliberately doesn't survive a
process restart, matching this deployment's single-process model.
"""

import logging
import secrets
import tempfile
import time
from dataclasses import dataclass, field

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from .garmin_client import GarminClientError, _write_user_tokens

logger = logging.getLogger(__name__)

_SESSION_TTL_SECONDS = 15 * 60
_MFA_TTL_SECONDS = 5 * 60
_MAX_MFA_ATTEMPTS = 5


@dataclass
class _Session:
    user_id: str
    created_at: float = field(default_factory=time.monotonic)
    state: str = "awaiting_credentials"  # -> "awaiting_mfa" -> consumed (removed)
    pending_client: Garmin | None = None
    mfa_attempts: int = 0


_sessions: dict[str, _Session] = {}


def _ttl_for(session: _Session) -> float:
    return _MFA_TTL_SECONDS if session.state == "awaiting_mfa" else _SESSION_TTL_SECONDS


def _sweep_expired() -> None:
    now = time.monotonic()
    expired = [t for t, s in _sessions.items() if now - s.created_at > _ttl_for(s)]
    for token in expired:
        _sessions.pop(token, None)


def create_session(user_id: str) -> str:
    """Start a new connection attempt for ``user_id``, returning a single-use token."""
    _sweep_expired()
    token = secrets.token_urlsafe(32)
    _sessions[token] = _Session(user_id=user_id)
    return token


def get_session_state(token: str) -> str | None:
    """Return "awaiting_credentials"/"awaiting_mfa" for a live token, else None."""
    _sweep_expired()
    session = _sessions.get(token)
    return session.state if session else None


def submit_credentials(token: str, email: str, password: str) -> dict:
    """Try a plain (non-MFA) Garmin login for the session's user.

    Returns {"status": "connected"} | {"status": "mfa_required"} |
    {"status": "error", "message": ...} | {"status": "invalid_token"}.
    """
    _sweep_expired()
    session = _sessions.get(token)
    if session is None or session.state != "awaiting_credentials":
        return {"status": "invalid_token"}

    client = Garmin(email=email, password=password, return_on_mfa=True)
    try:
        # Garmin.login(tokenstore=None) falls back to the GARMINTOKENS env
        # var (the shared TOKEN_STORE root in hosted mode) rather than doing
        # nothing - passing a guaranteed-empty temp dir forces a real fresh
        # login with the submitted credentials instead of risking it loading
        # an unrelated cached session from that root path.
        with tempfile.TemporaryDirectory() as empty_dir:
            mfa_status, _ = client.login(empty_dir)
    except GarminConnectAuthenticationError:
        return {"status": "error", "message": "Incorrect Garmin email or password."}
    except GarminConnectTooManyRequestsError:
        return {
            "status": "error",
            "message": "Too many attempts - wait a few minutes and try again.",
        }
    except Exception:
        logger.exception("Unexpected error during Garmin credential submission")
        return {"status": "error", "message": "Garmin login failed unexpectedly."}

    if mfa_status == "needs_mfa":
        session.state = "awaiting_mfa"
        session.pending_client = client
        return {"status": "mfa_required"}

    # return_on_mfa=True means login() never calls dump() itself, even on an
    # immediate success with no MFA involved - persist explicitly.
    try:
        _write_user_tokens(session.user_id, client)
    except GarminClientError as e:
        return {"status": "error", "message": str(e)}
    _sessions.pop(token, None)
    return {"status": "connected"}


def submit_mfa(token: str, mfa_code: str) -> dict:
    """Resume a login that returned "mfa_required", with the code the user received.

    Returns the same status shapes as submit_credentials, plus
    {"status": "too_many_attempts"}.
    """
    _sweep_expired()
    session = _sessions.get(token)
    if session is None or session.state != "awaiting_mfa" or session.pending_client is None:
        return {"status": "invalid_token"}

    if session.mfa_attempts >= _MAX_MFA_ATTEMPTS:
        _sessions.pop(token, None)
        return {"status": "too_many_attempts"}

    client = session.pending_client
    try:
        client.resume_login({}, mfa_code)
    except GarminConnectAuthenticationError:
        session.mfa_attempts += 1
        return {"status": "error", "message": "Incorrect code, try again."}
    except Exception:
        session.mfa_attempts += 1
        logger.exception("Unexpected error during Garmin MFA submission")
        return {"status": "error", "message": "MFA verification failed unexpectedly."}

    # resume_login() doesn't call dump() either - persist explicitly.
    try:
        _write_user_tokens(session.user_id, client)
    except GarminClientError as e:
        return {"status": "error", "message": str(e)}
    _sessions.pop(token, None)
    return {"status": "connected"}


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------
#
# Deliberately plain inline templates, not a templating dependency - this is
# a two-field form, not an app. Every page: no-store (nothing here should be
# cached anywhere), and visible consent language, since this touches a real
# Garmin password.

_CONSENT_NOTE = (
    "<p style='color:#666;font-size:0.85em'>This uses Garmin's unofficial API "
    "(not a Garmin-sanctioned OAuth connection) to link your account. Your "
    "password itself is never stored - only the resulting session is, "
    "encrypted. Disconnect any time by asking Claude to run "
    "disconnect_garmin_account.</p>"
)


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="font-family:system-ui,sans-serif;max-width:480px;margin:40px auto;padding:0 20px">
<h2>{title}</h2>
{body}
{_CONSENT_NOTE}
</body></html>"""


def render_credentials_form(token: str, error: str | None = None) -> str:
    error_html = f"<p style='color:#c00'>{error}</p>" if error else ""
    return _page(
        "Connect your Garmin account",
        f"""{error_html}
<form method="post" action="/connect/submit">
<input type="hidden" name="token" value="{token}">
<p><label>Garmin email<br><input type="email" name="email" required style="width:100%"></label></p>
<p><label>Garmin password<br><input type="password" name="password" required style="width:100%"></label></p>
<button type="submit">Connect</button>
</form>""",
    )


def render_mfa_form(token: str, error: str | None = None) -> str:
    error_html = f"<p style='color:#c00'>{error}</p>" if error else ""
    return _page(
        "Enter your Garmin MFA code",
        f"""{error_html}
<form method="post" action="/connect/mfa">
<input type="hidden" name="token" value="{token}">
<p><label>Code<br><input type="text" name="mfa_code" required style="width:100%"></label></p>
<button type="submit">Verify</button>
</form>""",
    )


def render_result(success: bool, message: str) -> str:
    return _page(
        "Garmin connected" if success else "Couldn't connect",
        f"<p>{message}</p>",
    )


def render_invalid_token() -> str:
    return _page(
        "Link expired",
        "<p>This connection link has expired or already been used. Ask "
        "Claude to run start_garmin_connection again for a new one.</p>",
    )

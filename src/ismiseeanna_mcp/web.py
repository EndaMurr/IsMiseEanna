"""Multi-user dashboard website backend.

Reuses the exact same per-user Garmin session machinery the MCP server uses
(garmin_client.get_client(), server.py's tool functions) rather than
building a parallel one. garmin_client.get_client() resolves per-user by
reading a request-scoped identity marker (a contextvars.ContextVar) that,
until now, only the MCP SDK's own auth middleware ever set. Nothing about
that marker is actually MCP-specific, so GarminContextMiddleware below sets
the exact same one after verifying a website visitor's WorkOS session -
which means every existing per-user Garmin function (get_client(), and
every server.py tool function that calls it internally) resolves correctly
for this website with zero changes to either of those modules.

Runs as its own process/deployment (console script `ismiseeanna-web`),
separate from the MCP server, sharing only two things on disk: the
encrypted per-user token store (TOKEN_STORE) and TOKEN_ENCRYPTION_KEY - see
README's "Website" section for why those two must match exactly between
this process's env file and the MCP server's.
"""

import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from mcp.server.auth.middleware.auth_context import auth_context_var, get_access_token
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from starlette.middleware.base import BaseHTTPMiddleware
from workos import WorkOSClient
from workos.session import seal_session_from_auth_response

from . import onboarding
from . import server as garmin_tools
from .garmin_client import (
    GarminClientError,
    GarminNotConnectedError,
    _extract_body_battery,
    _extract_hrv,
    _extract_resting_heart_rate,
    _extract_sleep_score,
    _extract_training_readiness,
    _n_day_trend,
    _user_token_path,
    disconnect_user,
    get_client,
)

logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required to run the website backend.")
    return value


WORKOS_API_KEY = _require_env("WORKOS_API_KEY")
WORKOS_CLIENT_ID = _require_env("WORKOS_CLIENT_ID")
WEB_REDIRECT_URI = _require_env("WEB_REDIRECT_URI")
WORKOS_COOKIE_PASSWORD = _require_env("WORKOS_COOKIE_PASSWORD")

_workos = WorkOSClient(api_key=WORKOS_API_KEY, client_id=WORKOS_CLIENT_ID)

_SESSION_COOKIE = "wos_session"

app = FastAPI(title="ismiseeanna dashboard")


def _set_session_cookie(response, sealed: str) -> None:
    response.set_cookie(
        _SESSION_COOKIE,
        sealed,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )


class GarminContextMiddleware(BaseHTTPMiddleware):
    """Resolves the logged-in website visitor (if any) from their session
    cookie and sets the same request-scoped identity marker the MCP SDK's
    own auth middleware sets for /mcp requests - see module docstring.

    Also transparently refreshes an expired-but-still-refreshable session,
    updating the cookie on the way out, so a visitor doesn't get logged out
    just because their access token's short lifetime elapsed mid-session.
    """

    async def dispatch(self, request: Request, call_next):
        sealed = request.cookies.get(_SESSION_COOKIE)
        ctx_token = None
        refreshed_cookie = None

        if sealed:
            try:
                session = _workos.user_management.load_sealed_session(
                    session_data=sealed, cookie_password=WORKOS_COOKIE_PASSWORD
                )
                result = session.authenticate()
                if not result.authenticated:
                    refresh_result = session.refresh(cookie_password=WORKOS_COOKIE_PASSWORD)
                    if refresh_result.authenticated:
                        refreshed_cookie = refresh_result.sealed_session
                        result = refresh_result

                if result.authenticated and result.user:
                    fake_access_token = AccessToken(
                        token="website-session",  # never sent anywhere; only .subject is read
                        client_id="ismiseeanna-web",
                        scopes=[],
                        subject=result.user["id"],
                    )
                    ctx_token = auth_context_var.set(AuthenticatedUser(fake_access_token))
            except Exception:
                logger.exception("Failed to resolve website session from cookie")

        try:
            response = await call_next(request)
        finally:
            if ctx_token is not None:
                auth_context_var.reset(ctx_token)

        if refreshed_cookie:
            _set_session_cookie(response, refreshed_cookie)
        return response


app.add_middleware(GarminContextMiddleware)


def _require_user_id() -> str:
    access_token = get_access_token()
    if access_token is None or not access_token.subject:
        raise HTTPException(status_code=401, detail="Not logged in.")
    return access_token.subject


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@app.get("/login")
def login() -> RedirectResponse:
    url = _workos.user_management.get_authorization_url(
        provider="authkit", redirect_uri=WEB_REDIRECT_URI
    )
    return RedirectResponse(url)


@app.get("/callback")
def callback(code: str) -> RedirectResponse:
    try:
        auth_response = _workos.user_management.authenticate_with_code(code=code)
    except Exception as e:
        logger.exception("WorkOS code exchange failed")
        raise HTTPException(status_code=401, detail="Login failed.") from e

    sealed = seal_session_from_auth_response(
        access_token=auth_response.access_token,
        refresh_token=auth_response.refresh_token,
        user=auth_response.user.to_dict(),
        cookie_password=WORKOS_COOKIE_PASSWORD,
    )
    response = RedirectResponse("/")
    _set_session_cookie(response, sealed)
    return response


@app.get("/logout")
def logout(request: Request) -> RedirectResponse:
    sealed = request.cookies.get(_SESSION_COOKIE)
    logout_url = "/login"
    if sealed:
        try:
            session = _workos.user_management.load_sealed_session(
                session_data=sealed, cookie_password=WORKOS_COOKIE_PASSWORD
            )
            logout_url = session.get_logout_url()
        except Exception:
            logger.exception("Failed to build WorkOS logout URL")
    response = RedirectResponse(logout_url)
    response.delete_cookie(_SESSION_COOKIE)
    return response


# ---------------------------------------------------------------------------
# Garmin account connection - reuses onboarding.py exactly as the MCP
# server's /connect routes do (server.py, gated behind `if _HOSTED:`)
# ---------------------------------------------------------------------------


def _connect_result_response(token: str, result: dict) -> HTMLResponse:
    headers = {"Cache-Control": "no-store"}
    status = result["status"]
    if status == "connected":
        return HTMLResponse(
            onboarding.render_result(
                True, "Garmin account connected. You can close this page and return to the dashboard."
            ),
            headers=headers,
        )
    if status == "mfa_required":
        return HTMLResponse(onboarding.render_mfa_form(token), headers=headers)
    if status == "invalid_token":
        return HTMLResponse(onboarding.render_invalid_token(), status_code=404, headers=headers)
    if status == "too_many_attempts":
        return HTMLResponse(
            onboarding.render_result(
                False, "Too many incorrect codes. Go back to the dashboard and try connecting again."
            ),
            headers=headers,
        )
    # "error" - re-render whichever form the session is still waiting on
    message = result.get("message", "Something went wrong.")
    if onboarding.get_session_state(token) == "awaiting_mfa":
        return HTMLResponse(onboarding.render_mfa_form(token, error=message), headers=headers)
    return HTMLResponse(onboarding.render_credentials_form(token, error=message), headers=headers)


@app.get("/connect-garmin")
def start_connect() -> RedirectResponse:
    """Website-initiated equivalent of the MCP server's start_garmin_connection
    tool: creates a one-time connection session for the logged-in visitor and
    sends them to the form. Safe to hit again if already connected."""
    user_id = _require_user_id()
    if os.path.exists(_user_token_path(user_id)):
        return RedirectResponse("/")
    token = onboarding.create_session(user_id)
    return RedirectResponse(f"/connect?token={token}")


@app.get("/connect")
async def connect_page(request: Request) -> HTMLResponse:
    token = request.query_params.get("token", "")
    state = onboarding.get_session_state(token)
    headers = {"Cache-Control": "no-store"}
    if state == "awaiting_credentials":
        return HTMLResponse(onboarding.render_credentials_form(token), headers=headers)
    if state == "awaiting_mfa":
        return HTMLResponse(onboarding.render_mfa_form(token), headers=headers)
    return HTMLResponse(onboarding.render_invalid_token(), status_code=404, headers=headers)


@app.post("/connect/submit")
async def connect_submit(request: Request) -> HTMLResponse:
    form = await request.form()
    token = str(form.get("token", ""))
    email = str(form.get("email", ""))
    password = str(form.get("password", ""))
    result = onboarding.submit_credentials(token, email, password)
    return _connect_result_response(token, result)


@app.post("/connect/mfa")
async def connect_mfa(request: Request) -> HTMLResponse:
    form = await request.form()
    token = str(form.get("token", ""))
    mfa_code = str(form.get("mfa_code", ""))
    result = onboarding.submit_mfa(token, mfa_code)
    return _connect_result_response(token, result)


# ---------------------------------------------------------------------------
# Dashboard JSON API
# ---------------------------------------------------------------------------


@app.get("/api/status")
def api_status() -> dict:
    _require_user_id()
    try:
        get_client()
        connected = True
    except GarminClientError:
        connected = False
    return {"connected": connected}


@app.get("/api/dashboard")
def api_dashboard() -> dict:
    _require_user_id()
    try:
        client = get_client()
    except GarminNotConnectedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except GarminClientError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    body_battery = _n_day_trend(client.get_body_battery, _extract_body_battery)
    training_readiness = _n_day_trend(client.get_training_readiness, _extract_training_readiness)
    sleep_score = _n_day_trend(client.get_sleep_data, _extract_sleep_score)
    resting_hr = _n_day_trend(client.get_rhr_day, _extract_resting_heart_rate)
    hrv = _n_day_trend(client.get_hrv_data, _extract_hrv)

    return {
        "today": {
            "bodyBattery": body_battery[-1],
            "trainingReadiness": training_readiness[-1],
            "sleepScore": sleep_score[-1],
            "restingHeartRate": resting_hr[-1],
            "hrv": hrv[-1],
        },
        "trends": {
            "bodyBattery": body_battery,
            "trainingReadiness": training_readiness,
            "sleepScore": sleep_score,
            "restingHeartRate": resting_hr,
            "hrv": hrv,
        },
    }


@app.get("/api/weekly-check-in")
def api_weekly_check_in() -> dict:
    _require_user_id()
    try:
        return garmin_tools.get_weekly_check_in()
    except GarminNotConnectedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except (GarminClientError, RuntimeError) as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get("/api/plan-progress")
def api_plan_progress(race_date: str) -> dict:
    _require_user_id()
    try:
        return garmin_tools.get_plan_progress(race_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except GarminNotConnectedError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except (GarminClientError, RuntimeError) as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.post("/api/disconnect")
def api_disconnect() -> dict:
    user_id = _require_user_id()
    disconnect_user(user_id)
    return {"status": "disconnected"}


def main() -> None:
    import uvicorn

    host = os.environ.get("WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8001"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()

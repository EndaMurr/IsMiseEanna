"""HTTP API backing the Garmin UI mobile app.

Exposes the dashboard, connection status, and an Anthropic-powered chat over
the same Garmin functions the MCP server exposes. A phone can't speak MCP's
stdio protocol directly, so this is a thin HTTP wrapper that calls those
functions in-process and runs the Claude tool-use loop server-side.
"""

import inspect
import json
import os
import typing
from datetime import date, timedelta
from typing import Any

import anthropic
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from . import server as garmin_tools
from .garmin_client import GarminClientError, get_client

app = FastAPI(title="Garmin UI API")
security = HTTPBearer()


def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> None:
    token = os.environ.get("GARMIN_UI_API_TOKEN")
    if not token:
        raise HTTPException(
            status_code=500, detail="GARMIN_UI_API_TOKEN is not configured on the server."
        )
    if credentials.credentials != token:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


@app.get("/status")
def get_status(_: None = Depends(require_auth)) -> dict:
    try:
        get_client()
        connected = True
    except GarminClientError:
        connected = False

    email = os.environ.get("GARMIN_EMAIL", "")
    masked_account = f"{email[:2]}••••••.com" if email else None

    return {
        "connected": connected,
        "server": "ismiseeanna-garmin",
        "account": masked_account,
        "runningVia": "Garmin UI backend",
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
#
# NOTE: garminconnect passes through Garmin Connect's own undocumented,
# reverse-engineered API responses verbatim. The field paths below are a
# best-effort reading of that shape; they haven't been verified against a
# live account in this environment. Spot-check the extracted values against
# the real Garmin Connect app before trusting the dashboard numbers, and
# adjust these extractors if a field path turns out to be wrong.


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


def _seven_day_trend(fetch_day, extract) -> list[float | None]:
    today = date.today()
    values = []
    for i in range(6, -1, -1):
        day_str = (today - timedelta(days=i)).isoformat()
        try:
            values.append(extract(fetch_day(day_str)))
        except Exception:
            values.append(None)
    return values


@app.get("/dashboard")
def get_dashboard(_: None = Depends(require_auth)) -> dict:
    client = get_client()

    body_battery = _seven_day_trend(client.get_body_battery, _extract_body_battery)
    training_readiness = _seven_day_trend(
        client.get_training_readiness, _extract_training_readiness
    )
    sleep_score = _seven_day_trend(client.get_sleep_data, _extract_sleep_score)
    resting_hr = _seven_day_trend(client.get_rhr_day, _extract_resting_heart_rate)
    hrv = _seven_day_trend(client.get_hrv_data, _extract_hrv)

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


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

_EXPOSED_TOOLS = [
    garmin_tools.list_activities,
    garmin_tools.search_activities_by_date,
    garmin_tools.get_activity_details,
    garmin_tools.get_activity_splits,
    garmin_tools.get_activity_weather,
    garmin_tools.get_activity_gear,
    garmin_tools.get_activity_hr_zones,
    garmin_tools.get_personal_records,
    garmin_tools.get_sleep_data,
    garmin_tools.get_stress_data,
    garmin_tools.get_body_battery,
    garmin_tools.get_hrv_data,
    garmin_tools.get_resting_heart_rate,
    garmin_tools.get_training_readiness,
    garmin_tools.get_training_status,
    garmin_tools.get_max_metrics,
    garmin_tools.get_race_predictions,
    garmin_tools.get_endurance_score,
    garmin_tools.list_workouts,
    garmin_tools.get_workout,
    garmin_tools.create_running_workout,
    garmin_tools.schedule_workout,
    garmin_tools.list_scheduled_workouts,
    garmin_tools.unschedule_workout,
    garmin_tools.delete_workout,
]

_TOOLS_BY_NAME = {f.__name__: f for f in _EXPOSED_TOOLS}


def _json_type(annotation: Any) -> str:
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if typing.get_origin(annotation) is typing.Union:
        real_args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if real_args:
            return _json_type(real_args[0])
    return "string"


def _tool_schema(func) -> dict:
    properties = {}
    required = []
    for name, param in inspect.signature(func).parameters.items():
        properties[name] = {"type": _json_type(param.annotation)}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {
        "name": func.__name__,
        "description": (func.__doc__ or "").strip(),
        "input_schema": {"type": "object", "properties": properties, "required": required},
    }


CHAT_TOOLS = [_tool_schema(f) for f in _EXPOSED_TOOLS]

SYSTEM_PROMPT = (
    "You are the assistant embedded in the Garmin UI app, a personal fitness "
    "dashboard reading the user's own Garmin Connect account. Answer questions "
    "about their activities, sleep, recovery, and training load using the "
    "tools available; don't guess at numbers you can look up. To schedule a "
    "workout, create it with create_running_workout and then schedule it with "
    "schedule_workout, then confirm the date and distance or duration back to "
    "the user in one short sentence."
)

_MAX_TOOL_ITERATIONS = 8


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    reply: str


def _run_tool(name: str, tool_input: dict) -> Any:
    func = _TOOLS_BY_NAME.get(name)
    if func is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return func(**tool_input)
    except GarminClientError as e:
        return {"error": str(e)}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, _: None = Depends(require_auth)) -> ChatResponse:
    client = anthropic.Anthropic()
    messages: list[dict] = [{"role": m.role, "content": m.content} for m in request.messages]

    response = None
    for _ in range(_MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=CHAT_TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        tool_results = [
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(_run_tool(block.name, block.input), default=str),
            }
            for block in response.content
            if block.type == "tool_use"
        ]
        messages.append({"role": "user", "content": tool_results})

    reply = "".join(block.text for block in response.content if block.type == "text")
    return ChatResponse(reply=reply)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104 -- personal LAN tool

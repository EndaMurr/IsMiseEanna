"""Generates a periodized marathon training plan as structured workout sessions.

Each session's ``steps`` follow the same shape
``garmin_client.build_structured_running_workout`` accepts, so a generated
plan can be turned into real Garmin workouts with the existing
``create_running_workout``/``schedule_workout`` tools without any
translation step.
"""

from datetime import date, timedelta

from .garmin_client import GarminClientError

_LONG_RUN_CAP_KM = 32.0
_MAX_WEEKLY_INCREASE = 1.10  # cap week-over-week volume growth during the build phase

_SESSION_SHARE = {"long": 0.45, "tempo": 0.28, "interval": 0.27}
_SESSION_DAY_OFFSETS = {"interval": 1, "tempo": 3, "long": 5}  # Tue, Thu, Sat

_STRATEGY_PEAK_MULTIPLIER = {"aggressive": 1.20, "conservative": 1.00}

MARATHON_KM = 42.195
HALF_MARATHON_KM = 21.0975

_REQUIRED_PREDICTION_FIELDS = ("timeMarathon", "timeHalfMarathon", "time10K")


def _paces_from_predictions(race_predictions: dict) -> dict:
    """Derive training paces (seconds/km) from Garmin's predicted race times."""
    missing = [f for f in _REQUIRED_PREDICTION_FIELDS if not race_predictions.get(f)]
    if missing:
        raise GarminClientError(
            f"Garmin's race predictions are missing {', '.join(missing)} — usually "
            "means there isn't enough running history yet for a reliable prediction."
        )
    return {
        "marathon": race_predictions["timeMarathon"] / MARATHON_KM,
        "tempo": race_predictions["timeHalfMarathon"] / HALF_MARATHON_KM,
        "interval": race_predictions["time10K"] / 10,
        "easy": race_predictions["timeMarathon"] / MARATHON_KM + 60,
    }


def _pace_target(pace_sec_per_km: float, spread: float = 5.0) -> dict:
    return {
        "target_pace_min_per_km": round(pace_sec_per_km - spread),
        "target_pace_max_per_km": round(pace_sec_per_km + spread),
    }


def _week_mondays(today: date, race: date) -> list[date]:
    first_monday = today + timedelta(days=(7 - today.weekday()) % 7)
    race_monday = race - timedelta(days=race.weekday())
    weeks = []
    d = first_monday
    while d <= race_monday:
        weeks.append(d)
        d += timedelta(days=7)
    return weeks


def _phase_for_week(index: int, total: int) -> str:
    if index == total - 1:
        return "race"
    if index == total - 2:
        return "taper"
    build_weeks = (total - 2) // 2
    return "build" if index < build_weeks else "peak"


def _build_step_index(index: int, total: int) -> int:
    """1-based position of this week within the build phase."""
    return sum(1 for i in range(index + 1) if _phase_for_week(i, total) == "build")


def _target_weekly_km(phase: str, index: int, total: int, current_km: float, peak_km: float) -> float:
    if phase == "peak":
        return round(peak_km, 1)
    if phase == "taper":
        return round(peak_km * 0.6, 1)
    step = _build_step_index(index, total)
    return round(min(current_km * (_MAX_WEEKLY_INCREASE**step), peak_km), 1)


def _interval_session(week_km: float, paces: dict) -> dict:
    reps = 6
    rep_km = max(round((week_km * _SESSION_SHARE["interval"] - 2.0) / reps, 2), 0.4)
    return {
        "name": "Intervals",
        "steps": [
            {"kind": "warmup", "distance_meters": 1500, **_pace_target(paces["easy"])},
            {
                "repeat": {
                    "count": reps,
                    "steps": [
                        {
                            "kind": "interval",
                            "distance_meters": round(rep_km * 1000),
                            **_pace_target(paces["interval"]),
                        },
                        {"kind": "recovery", "duration_seconds": 120},
                    ],
                }
            },
            {"kind": "cooldown", "distance_meters": 1000, **_pace_target(paces["easy"])},
        ],
    }


def _tempo_session(week_km: float, paces: dict) -> dict:
    tempo_km = max(round(week_km * _SESSION_SHARE["tempo"] - 2.5, 1), 3.0)
    return {
        "name": "Tempo Run",
        "steps": [
            {"kind": "warmup", "distance_meters": 1500, **_pace_target(paces["easy"])},
            {
                "kind": "interval",
                "distance_meters": round(tempo_km * 1000),
                **_pace_target(paces["tempo"]),
            },
            {"kind": "cooldown", "distance_meters": 1000, **_pace_target(paces["easy"])},
        ],
    }


def _long_run_session(phase: str, week_km: float, paces: dict) -> dict:
    total_km = min(week_km * _SESSION_SHARE["long"], _LONG_RUN_CAP_KM)
    if phase == "peak":
        # dress-rehearsal long run: steady easy running finishing at marathon pace
        mp_km = round(total_km * 0.35, 1)
        easy_km = round(total_km - mp_km, 1)
        steps = [
            {
                "kind": "warmup",
                "distance_meters": round(easy_km * 1000),
                **_pace_target(paces["easy"]),
            },
            {
                "kind": "interval",
                "distance_meters": round(mp_km * 1000),
                **_pace_target(paces["marathon"]),
            },
            {"kind": "cooldown", "distance_meters": 500, **_pace_target(paces["easy"])},
        ]
    else:
        steps = [
            {"kind": "warmup", "distance_meters": 500, **_pace_target(paces["easy"])},
            {
                "kind": "interval",
                "distance_meters": round((total_km - 0.5) * 1000),
                **_pace_target(paces["easy"]),
            },
        ]
    return {"name": "Long Run", "steps": steps}


def _shakeout_session(paces: dict) -> dict:
    return {
        "name": "Race Week Shakeout",
        "steps": [
            {"kind": "warmup", "distance_meters": 1000, **_pace_target(paces["easy"])},
            {
                "kind": "interval",
                "distance_meters": 3000,
                **_pace_target(paces["easy"]),
            },
            {"kind": "cooldown", "distance_meters": 500, **_pace_target(paces["easy"])},
        ],
    }


def _sharpener_session(paces: dict) -> dict:
    return {
        "name": "Pre-Race Sharpener",
        "steps": [
            {"kind": "warmup", "distance_meters": 1000, **_pace_target(paces["easy"])},
            {
                "repeat": {
                    "count": 4,
                    "steps": [
                        {
                            "kind": "interval",
                            "distance_meters": 200,
                            **_pace_target(paces["interval"]),
                        },
                        {"kind": "recovery", "distance_meters": 200},
                    ],
                }
            },
            {"kind": "cooldown", "distance_meters": 500, **_pace_target(paces["easy"])},
        ],
    }


def generate_marathon_plan(
    race_date: str,
    current_weekly_km: float,
    race_predictions: dict,
    strategy: str = "aggressive",
    today: date | None = None,
) -> list[dict]:
    """Generate a periodized marathon plan from today through race day.

    Weeks run Monday-Sunday. Each non-race week has three sessions
    (interval Tue, tempo Thu, long run Sat); training paces are derived from
    Garmin's own race-time predictions rather than guessed. ``strategy`` is
    "aggressive" (ramp toward ~120% of current weekly volume) or
    "conservative" (hold near current volume). Weekly volume growth during
    the build phase is capped at +10%/week regardless of strategy.

    Returns a list of week dicts: ``{weekStart, phase, targetWeeklyKm,
    sessions}``, where each session is ``{date, name, steps}`` — ``steps``
    is ``None`` for the race-day entry itself (nothing to schedule as a
    workout) and otherwise matches
    ``garmin_client.build_structured_running_workout``'s step format.
    """
    today = today or date.today()
    try:
        race = date.fromisoformat(race_date)
    except (TypeError, ValueError) as e:
        raise GarminClientError(
            f"race_date must be an ISO date (YYYY-MM-DD), got {race_date!r}."
        ) from e
    if race <= today:
        raise GarminClientError("race_date must be in the future.")
    if strategy not in _STRATEGY_PEAK_MULTIPLIER:
        raise GarminClientError(f"strategy must be one of {sorted(_STRATEGY_PEAK_MULTIPLIER)}.")

    paces = _paces_from_predictions(race_predictions)
    weeks = _week_mondays(today, race)
    total = len(weeks)
    peak_km = round(current_weekly_km * _STRATEGY_PEAK_MULTIPLIER[strategy], 1)

    plan = []
    for i, monday in enumerate(weeks):
        phase = _phase_for_week(i, total)

        if phase == "race":
            shakeout = _shakeout_session(paces)
            sharpener = _sharpener_session(paces)
            # Anchored to race day's own weekday (not a fixed Tue/Thu) so both
            # sessions always fall before race day, whatever day it lands on.
            race_offset = race.weekday()
            sessions = [
                {
                    "date": (monday + timedelta(days=race_offset - 4)).isoformat(),
                    **shakeout,
                },
                {
                    "date": (monday + timedelta(days=race_offset - 2)).isoformat(),
                    **sharpener,
                },
                {"date": race.isoformat(), "name": "Marathon (Race Day)", "steps": None},
            ]
            week_km = round(3.0 + 1.6 + MARATHON_KM, 1)
        else:
            week_km = _target_weekly_km(phase, i, total, current_weekly_km, peak_km)
            sessions = [
                {
                    "date": (monday + timedelta(days=_SESSION_DAY_OFFSETS["interval"])).isoformat(),
                    **_interval_session(week_km, paces),
                },
                {
                    "date": (monday + timedelta(days=_SESSION_DAY_OFFSETS["tempo"])).isoformat(),
                    **_tempo_session(week_km, paces),
                },
                {
                    "date": (monday + timedelta(days=_SESSION_DAY_OFFSETS["long"])).isoformat(),
                    **_long_run_session(phase, week_km, paces),
                },
            ]

        plan.append(
            {
                "weekStart": monday.isoformat(),
                "phase": phase,
                "targetWeeklyKm": week_km,
                "sessions": sessions,
            }
        )
    return plan

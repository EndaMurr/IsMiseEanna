# IsMiseEanna Garmin MCP Server

A local MCP server that queries your own Garmin Connect activity data,
using the unofficial [`garminconnect`](https://github.com/cyberjunky/python-garminconnect)
client library (the same API the Garmin Connect app itself uses).

There is no official, self-service Garmin API for this — Garmin's official
Connect Developer APIs require applying for partner access. This server
instead logs in with your own Garmin credentials, the same way the mobile
app does.

## Setup

```bash
uv sync   # or: pip install -e .
```

## First run (authentication)

Set your Garmin credentials as environment variables for the first login:

```bash
export GARMIN_EMAIL="you@example.com"
export GARMIN_PASSWORD="your-password"
```

The session token is cached to `~/.garminconnect` (override with
`GARMINTOKENS`) after the first successful login, so subsequent runs don't
need the password.

## Tools

- `list_activities(limit, start)` — recent activities, most recent first
- `search_activities_by_date(start_date, end_date, activity_type)` — activities in a date range (`YYYY-MM-DD`)
- `get_activity_details(activity_id)` — full metrics for one activity
- `get_activity_splits(activity_id)` — lap/split data for one activity
- `get_activity_weather(activity_id)` — recorded weather conditions for one activity
- `get_activity_gear(activity_id)` — gear (shoes, bike, etc.) logged against one activity
- `get_activity_hr_zones(activity_id)` — time spent in each heart rate zone for one activity
- `get_personal_records()` — current personal records (fastest 5K, longest run, etc.)
- `get_sleep_data(date)` — sleep data for one date
- `get_stress_data(date)` — stress level data for one date
- `get_body_battery(date)` — Body Battery (energy level) data for one date
- `get_hrv_data(date)` — heart rate variability for one date
- `get_resting_heart_rate(date)` — resting heart rate for one date
- `get_training_readiness(date)` — training readiness score and contributing factors for one date
- `get_training_status(date)` — training status (productive, peaking, detraining, etc.) for one date
- `get_max_metrics(date)` — fitness age and VO2 max for one date
- `get_race_predictions()` — predicted 5K/10K/half/marathon times as of today
- `get_endurance_score(date)` — endurance score for one date

## Using with Claude Desktop / Claude Code

Add to your MCP client config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "garmin": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/IsMiseEanna", "run", "ismiseeanna-mcp"],
      "env": {
        "GARMIN_EMAIL": "you@example.com",
        "GARMIN_PASSWORD": "your-password"
      }
    }
  }
}
```

Once a cached token exists at `~/.garminconnect`, the `env` block can be
dropped.

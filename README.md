# IsMiseEanna Garmin MCP Server

A local MCP server for your own Garmin Connect account: it queries activity
and wellness data, and lets you create structured workouts (warmups,
intervals, pace/HR targets, repeats) from plain-English descriptions typed
into Claude - no separate app needed. It uses the unofficial
[`garminconnect`](https://github.com/cyberjunky/python-garminconnect) client
library (the same API the Garmin Connect app itself uses).

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

### Workouts

- `list_workouts(limit, start)` — saved workouts in your Garmin workout library
- `get_workout(workout_id)` — full step-by-step definition of one saved workout
- `delete_workout(workout_id)` — delete a saved workout
- `create_running_workout(name, steps, description, date)` — build and save
  a structured running workout from a list of steps (warmup/cooldown/
  recovery/rest/interval, each with a duration or distance, and an optional
  pace or heart-rate target) and/or repeat blocks (e.g. 5x400m). See the
  tool's docstring for the exact step schema. Pass `date` (`YYYY-MM-DD`) to
  also schedule it onto the Garmin Connect calendar in the same call.
- `schedule_workout(workout_id, date)` — put an existing saved workout onto
  the Garmin Connect calendar for a date (`YYYY-MM-DD`)
- `unschedule_workout(scheduled_workout_id)` — remove a workout from the
  calendar without deleting the underlying workout template
- `list_scheduled_workouts(year, month)` — what's on the Garmin Connect
  calendar for a given month

## Creating workouts with natural language

There's no separate "parse this workout" step - Claude reads the tool
descriptions and does the translation itself. Just describe the workout in
the chat:

> Create a Garmin workout called "Track 5x400" - 10 min warmup, 5x400m at
> 5K pace (~4:00/km) with 90 seconds of jog recovery between reps, then a
> 10 min cooldown.

Claude turns that into a `create_running_workout` call with structured
`steps`, e.g.:

```json
{
  "name": "Track 5x400",
  "steps": [
    {"kind": "warmup", "duration_seconds": 600},
    {"kind": "repeat", "iterations": 5, "steps": [
      {"kind": "interval", "distance_meters": 400,
       "target_pace_min_per_km": [3.9, 4.1]},
      {"kind": "recovery", "duration_seconds": 90}
    ]},
    {"kind": "cooldown", "duration_seconds": 600}
  ]
}
```

The workout is saved to your Garmin workout library, ready to sync to a
watch. Add "...and put it on my calendar for Saturday" (or just include a
date up front) and Claude will also pass `date` so the workout lands on
that day's calendar entry in the same call - no separate scheduling step
needed, and no need to drag it onto a day in the Garmin Connect app
yourself. Already-created workouts can be scheduled or unscheduled
afterwards too, with `schedule_workout`/`unschedule_workout`.

A few caveats worth knowing:

- Only running workouts are supported for now (cycling/swimming/walking
  would follow the same pattern if you need them).
- The distance and heart-rate-zone target field names in
  `workout_builder.py` are inferred from Garmin's undocumented schema (only
  the time/iterations fields could be confirmed against the `garminconnect`
  library itself) - check the created workout in the Garmin Connect app
  after your first real use, and open an issue/PR if something doesn't
  render as expected.
- Step values are sanity-checked (durations up to 24h, distances up to
  200km, paces between 1-60 min/km, heart rates between 30-250bpm, up to
  100 repeat iterations, and repeat blocks can't be nested) so a malformed
  or unexpected request fails with a clear error instead of silently
  producing a nonsensical workout.

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

## Hosted deployment (remote access from claude.ai)

By default this server runs over stdio for local use, as above. It can
instead run as a remote MCP server reachable over HTTPS, protected by OAuth,
so it can be added as a [custom connector](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
in claude.ai (web, desktop, or mobile) rather than only from a local client
config.

claude.ai requires a custom connector's server to act as an OAuth 2.1
*resource server* backed by an authorization server that supports Dynamic
Client Registration (RFC 7591) - there's no "paste an API key" option in its
UI. Rather than hand-rolling an authorization server, this deployment uses
[WorkOS AuthKit](https://workos.com/docs/authkit/mcp) as that authorization
server; `src/ismiseeanna_mcp/auth.py` implements the resource-server side
(verifying AuthKit's tokens via its published JWKS, and checking that a
token was actually issued for *this* deployment before accepting it).

### 1. Set up WorkOS AuthKit

1. Create a free [WorkOS](https://workos.com) account and a new project.
2. Under **Connect → Configuration**, note your AuthKit Domain (looks like
   `https://your-project-xxxxx.authkit.app`) - this is `WORKOS_AUTHKIT_DOMAIN`
   below.
3. Under **Applications → Configuration**, enable **Dynamic Client
   Registration** (this is what lets claude.ai register itself as a client
   automatically the first time you add the connector).
4. Add your server's MCP endpoint URL as a valid **resource indicator**
   (e.g. `https://<your-app>.fly.dev/mcp`) - it must exactly match
   `MCP_RESOURCE_URL` below, since that's what's checked as the token
   audience.

### 2. Deploy

The Garmin session token needs a durable disk to survive restarts, so this
targets [Fly.io](https://fly.io) (a small always-on VM + a persistent
volume, roughly $2-5/mo) via the included `Dockerfile`/`fly.toml`. Any host
that gives you a persistent volume works the same way.

```bash
fly launch --no-deploy          # creates the app; pick a name/region
fly volumes create data --size 1 --region <your-region>
fly secrets set \
  WORKOS_AUTHKIT_DOMAIN=https://your-project-xxxxx.authkit.app \
  MCP_RESOURCE_URL=https://<your-app>.fly.dev/mcp \
  GARMIN_EMAIL=you@example.com \
  GARMIN_PASSWORD=your-password    # only needed for the very first login
fly deploy
```

After the first successful login the Garmin session token is cached on the
volume (`GARMINTOKENS=/data/.garminconnect`, set in the `Dockerfile`), so
`GARMIN_EMAIL`/`GARMIN_PASSWORD` can be removed again:

```bash
fly secrets unset GARMIN_EMAIL GARMIN_PASSWORD
```

### 3. Add the connector in claude.ai

Go to **Settings → Connectors → Add custom connector** and enter
`https://<your-app>.fly.dev/mcp`. claude.ai will discover the AuthKit
authorization server from the server's metadata, register itself as a
client, and walk you through logging in - after that the connector is
available in any chat.

### Relevant environment variables

| Variable | Required for | Purpose |
|---|---|---|
| `WORKOS_AUTHKIT_DOMAIN` | hosted mode | Your AuthKit project domain; also enables OAuth (unset = plain local stdio server) |
| `MCP_RESOURCE_URL` | hosted mode | This deployment's public MCP URL; checked as the token audience |
| `MCP_TRANSPORT` | hosted mode | Set to `streamable-http` (default `stdio`) |
| `GARMINTOKENS` | optional | Where the Garmin session token is cached (default `~/.garminconnect`) |
| `GARMIN_EMAIL` / `GARMIN_PASSWORD` | first login only | Not needed once a session token is cached |

Both `WORKOS_AUTHKIT_DOMAIN` and `MCP_RESOURCE_URL` must be set together to
enable OAuth - if either is missing, the server falls back to a plain,
unauthenticated instance, which is fine for local stdio use but should never
be exposed to the public internet.

# IsMiseEanna Garmin MCP Server

A local MCP server for your own Garmin Connect account: it queries activity,
wellness, and training data, and lets you create structured workouts and
periodized training plans from plain-English descriptions typed into
Claude - no separate app needed. It uses the unofficial
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
- `generate_marathon_plan(race_date, current_weekly_km, strategy)` — preview a periodized marathon plan (paces derived from `get_race_predictions`); returns weeks of sessions to review, doesn't create or schedule anything
- `get_weekly_check_in()` — compares this week's scheduled Garmin-calendar sessions (from any app — Runna, ismiseeanna, or manual) against completed activities, plus the recent training-readiness/HRV trend; read-only, returns data rather than a recommendation
- `get_plan_progress(race_date)` — parses this week's calendar session names for Runna's "W# Day Type" naming convention to report which week of the plan you're in, plus weeks remaining until `race_date`; returns `currentWeek`/`totalWeeks` as null (not an error) if nothing this week matches that convention

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
- `move_scheduled_workout(scheduled_workout_id, workout_id, new_date)` —
  shift an existing scheduled session (from any app — Runna included) to a
  new date without changing what it actually asks for
- `list_scheduled_workouts(year, month)` — what's on the Garmin Connect
  calendar for a given month

### Account connection (hosted mode only)

- `start_garmin_connection()` — returns a one-time link to connect your own
  Garmin account to this server; open it in your own browser, never paste
  your Garmin password into the chat. See "Connecting your Garmin account"
  under "Hosted deployment" below.
- `disconnect_garmin_account()` — disconnect your Garmin account and delete
  your stored session from this server

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

`generate_marathon_plan` builds on the same step format: it returns a
multi-week plan whose sessions can be passed straight into
`create_running_workout` once you've reviewed it, and `get_weekly_check_in`
reads back against whatever ends up on the calendar - from this tool or any
other training app - to flag missed sessions or a sustained drop in
readiness/HRV.

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

## HTTP backend

`ismiseeanna-api` runs a small HTTP API for a phone or browser client that
can't speak this project's MCP stdio protocol directly - it wraps the same
Garmin functions behind HTTP and runs the chat's Claude tool-use loop
server-side.

```bash
export GARMIN_UI_API_TOKEN="a long random shared secret"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
uv run ismiseeanna-api   # serves on 0.0.0.0:8000
```

Every request needs `Authorization: Bearer $GARMIN_UI_API_TOKEN`.

- `GET /status` — connection state, masked account, and which server is running
- `GET /dashboard` — today + 7-day trend for Body Battery, Training Readiness, Sleep Score, resting HR, and HRV
- `POST /chat` — `{"messages": [{"role": "user", "content": "..."}]}`, runs Claude (`claude-opus-5`) with the same tools listed above and returns `{"reply": "..."}`

This binds to all interfaces so a phone on the same network/VPN can reach
it — run it only on a trusted network (home LAN, Tailscale, etc.), never
exposed directly to the internet. The dashboard's field extraction reads
Garmin Connect's undocumented response shapes on a best-effort basis; spot
check the numbers against the real Garmin Connect app after first setup.

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
3. In that same **Connect → Configuration** page, find **MCP Auth** and
   enable **Dynamic Client Registration** and **Client ID Metadata
   Document** (this is what lets claude.ai register itself as a client
   automatically the first time you add the connector).
4. In the **MCP resource indicators** section further down that page, add
   your server's MCP endpoint URL (e.g. `https://<your-hostname>/mcp`) - it
   must exactly match `MCP_RESOURCE_URL` below, since that's what's checked
   as the token audience.

### 2. Deploy

The Garmin session token needs a durable disk to survive restarts, and the
server needs a public HTTPS hostname (claude.ai requires TLS). Two deploy
targets are set up below; either works the same way from WorkOS's and
claude.ai's point of view - only the hostname you register as the resource
indicator changes.

<details>
<summary><strong>Option A: Fly.io</strong> (a few $/mo, least setup)</summary>

A small always-on VM + a persistent volume, via the included
`Dockerfile`/`fly.toml`.

```bash
fly launch --no-deploy          # creates the app; pick a name/region
fly volumes create data --size 1 --region <your-region>
fly secrets set \
  WORKOS_AUTHKIT_DOMAIN=https://your-project-xxxxx.authkit.app \
  MCP_RESOURCE_URL=https://<your-app>.fly.dev/mcp \
  TOKEN_ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
fly deploy
```

No `GARMIN_EMAIL`/`GARMIN_PASSWORD` here - in hosted mode, every person who
adds this connector (including you) connects their own Garmin account
through `start_garmin_connection` after logging in via claude.ai (see
"Connecting your Garmin account" below), not a deploy-time secret.

</details>

<details>
<summary><strong>Option B: Google Cloud's Always Free <code>e2-micro</code></strong> ($0/mo indefinitely, more manual setup)</summary>

GCP's Always Free tier includes one `e2-micro` VM (in `us-west1`,
`us-central1`, or `us-east1` only) plus 30GB of persistent disk, with no
expiration. This runs the server directly on the VM via systemd, behind
[Caddy](https://caddyserver.com) for automatic HTTPS - no Docker needed.
Since a free VM doesn't come with a domain name, this uses
[sslip.io](https://sslip.io) to turn the VM's own IP into a valid public
hostname for Caddy to get a Let's Encrypt certificate for.

Everything below can be run from [Google Cloud Shell](https://shell.cloud.google.com)
in a browser - no local `gcloud` install needed.

```bash
# Reserve a static IP so the hostname doesn't change on restart, then create
# the VM using it and a firewall rule allowing Caddy's ports.
gcloud compute addresses create ismiseeanna-mcp-ip --region=us-central1

gcloud compute instances create ismiseeanna-mcp \
  --zone=us-central1-a --machine-type=e2-micro \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=30GB --boot-disk-type=pd-standard \
  --address=ismiseeanna-mcp-ip --tags=ismiseeanna-mcp

gcloud compute firewall-rules create allow-ismiseeanna-mcp-https \
  --allow=tcp:80,tcp:443 --target-tags=ismiseeanna-mcp --source-ranges=0.0.0.0/0

# Derive the sslip.io hostname from the reserved IP, e.g. 34.71.12.9 -> 34-71-12-9.sslip.io
IP=$(gcloud compute addresses describe ismiseeanna-mcp-ip --region=us-central1 --format='get(address)')
HOSTNAME="${IP//./-}.sslip.io"
echo "Hostname: $HOSTNAME"   # register this exact value as the WorkOS resource indicator
```

Then SSH in (add `--tunnel-through-iap` if a direct SSH firewall rule isn't
set up) and run the provisioning script (also in `deploy/gcp/`), which
installs Caddy and `uv`, fetches the app, and sets up both as systemd
services:

```bash
gcloud compute ssh ismiseeanna-mcp --zone=us-central1-a
sudo apt-get install -y git
git clone --branch claude/garmin-mcp-server-b3sj3m https://github.com/EndaMurr/IsMiseEanna.git /tmp/setup
sudo /tmp/setup/deploy/gcp/setup.sh "$HOSTNAME" claude/garmin-mcp-server-b3sj3m
```

It writes `/etc/ismiseeanna-mcp.env` from `deploy/gcp/ismiseeanna-mcp.env.example`
on first run and tells you to fill in the real `WORKOS_AUTHKIT_DOMAIN` and a
generated `TOKEN_ENCRYPTION_KEY`
(`python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
there, then:

```bash
sudo systemctl restart ismiseeanna-mcp
```

No `GARMIN_EMAIL`/`GARMIN_PASSWORD` here either - see "Connecting your
Garmin account" below.

To redeploy after pulling new commits:

```bash
gcloud compute ssh ismiseeanna-mcp --zone=us-central1-a --tunnel-through-iap --command="sudo -u ismiseeanna git -C /opt/ismiseeanna-mcp pull && cd /opt/ismiseeanna-mcp && sudo /root/.local/bin/uv sync --frozen && sudo chown -R ismiseeanna:ismiseeanna /opt/ismiseeanna-mcp/.venv && sudo systemctl restart ismiseeanna-mcp && sudo systemctl status ismiseeanna-mcp --no-pager"
```

</details>

### 3. Add the connector in claude.ai

Go to **Settings → Connectors → Add custom connector** and enter your
server's MCP URL (e.g. `https://<your-app>.fly.dev/mcp` or
`https://<your-sslip-hostname>/mcp`). claude.ai will discover the AuthKit
authorization server from the server's metadata, register itself as a
client, and walk you through logging in - after that the connector is
available in any chat.

### 4. Connecting your Garmin account

Hosted mode is multi-tenant: every person who adds the connector - including
you - connects their own separate Garmin account, verified by their own
claude.ai/WorkOS login. There's no deploy-time Garmin credential at all.

From any chat with the connector enabled, ask Claude to run
`start_garmin_connection`. It returns a one-time link, good for 15 minutes
and usable once - **open it in your own browser, never paste your Garmin
email or password into the chat itself** (that'd sit in claude.ai's own
conversation history). The linked page posts your credentials straight to
this server; if your account has MFA enabled it'll ask for the code as a
second step. Every tool call after that resolves to your own Garmin data,
kept completely separate from anyone else's.

To disconnect later (revoking this server's access and deleting your stored
session), ask Claude to run `disconnect_garmin_account`.

Each connected user's session is encrypted at rest with `TOKEN_ENCRYPTION_KEY`
(set once per deployment, not per user - see the env var table below for how
to generate it). Losing that key means every connected user has to
reconnect, so back it up somewhere durable, not just the one env file.

### 5. Auto-deploy on merge to the GCP VM (optional)

`.github/workflows/deploy.yml` redeploys the GCP option automatically after
`CI` passes on `claude/garmin-mcp-server-b3sj3m` - the exact `git pull` +
`uv sync` + `systemctl restart` from the manual redeploy above, run by
GitHub Actions instead of by hand. It needs a GCP service account scoped to
just "SSH into this one instance via IAP":

```bash
gcloud iam service-accounts create ismiseeanna-deployer \
  --project=garmin-mcp-505007 \
  --display-name="ismiseeanna-mcp GitHub Actions deployer"

DEPLOYER="ismiseeanna-deployer@garmin-mcp-505007.iam.gserviceaccount.com"

# Log in and run sudo commands over OS Login, and open an IAP tunnel to
# reach the instance - nothing broader (no project-wide compute access).
gcloud projects add-iam-policy-binding garmin-mcp-505007 \
  --member="serviceAccount:$DEPLOYER" --role="roles/compute.osAdminLogin"
gcloud projects add-iam-policy-binding garmin-mcp-505007 \
  --member="serviceAccount:$DEPLOYER" --role="roles/iap.tunnelResourceAccessor"
gcloud projects add-iam-policy-binding garmin-mcp-505007 \
  --member="serviceAccount:$DEPLOYER" --role="roles/compute.viewer"
```

Newer GCP projects block downloadable service-account keys by default
(`constraints/iam.disableServiceAccountKeyCreation`), and a key would be a
permanent, non-expiring secret anyway - so instead of a key, GitHub Actions
authenticates via **Workload Identity Federation**: GCP trusts a
short-lived OIDC token that GitHub mints for each workflow run, scoped so
only runs from this exact repo can assume the deployer identity.

```bash
PROJECT_NUMBER=$(gcloud projects describe garmin-mcp-505007 --format="value(projectNumber)")

gcloud iam workload-identity-pools create "github-pool" \
  --project=garmin-mcp-505007 --location="global" \
  --display-name="GitHub Actions pool"

gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --project=garmin-mcp-505007 --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Actions provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='EndaMurr/IsMiseEanna'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER" \
  --project=garmin-mcp-505007 \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/EndaMurr/IsMiseEanna"
```

The provider's resource name (`projects/<number>/locations/global/workloadIdentityPools/github-pool/providers/github-provider`)
and the deployer's email are already hardcoded into `deploy.yml` - neither
is a secret, since the `attribute-condition` above is what actually
restricts who can use them. No GitHub secret to add at all.

Three more one-time gaps `gcloud compute ssh` hits that the roles above
don't cover on their own - each only shows up by actually running the
workflow and reading the next error, so do all three now rather than
discovering them one deploy at a time:

```bash
# gcloud impersonates the deployer via WIF using this API; it's off by
# default on new projects.
gcloud services enable iamcredentials.googleapis.com --project=garmin-mcp-505007

# Without OS Login enabled, gcloud falls back to legacy SSH keys in
# instance metadata, which needs a much broader compute.instances.setMetadata
# permission we deliberately didn't grant. Scoped to just this instance.
gcloud compute instances add-metadata ismiseeanna-mcp \
  --project=garmin-mcp-505007 --zone=us-central1-a \
  --metadata enable-oslogin=TRUE

# gcloud compute ssh also checks the deployer can act as the VM's own
# attached service account, separately from the roles granted above.
INSTANCE_SA=$(gcloud compute instances describe ismiseeanna-mcp \
  --project=garmin-mcp-505007 --zone=us-central1-a \
  --format="value(serviceAccounts[0].email)")

gcloud iam service-accounts add-iam-policy-binding "$INSTANCE_SA" \
  --project=garmin-mcp-505007 \
  --member="serviceAccount:$DEPLOYER" \
  --role="roles/iam.serviceAccountUser"
```

From then on, every push to `claude/garmin-mcp-server-b3sj3m` that passes
CI redeploys automatically; check the **Actions** tab for status, and the
workflow's "Show recent service logs" step captures `journalctl` output on
a failed deploy.

### Relevant environment variables

| Variable | Required for | Purpose |
|---|---|---|
| `WORKOS_AUTHKIT_DOMAIN` | hosted mode | Your AuthKit project domain; also enables OAuth (unset = plain local stdio server) |
| `MCP_RESOURCE_URL` | hosted mode | This deployment's public MCP URL; checked as the token audience |
| `MCP_TRANSPORT` | hosted mode | Set to `streamable-http` (default `stdio`) |
| `TOKEN_ENCRYPTION_KEY` | hosted mode | Encrypts every connected user's Garmin session at rest. Generate with `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `GARMINTOKENS` | optional | Root of the Garmin session token cache (default `~/.garminconnect`) - a flat file/dir in local mode, one encrypted subdirectory per user in hosted mode |
| `GARMIN_EMAIL` / `GARMIN_PASSWORD` | local stdio mode only | Not used in hosted mode - see "Connecting your Garmin account" above. In local mode, only needed for the very first login |

Both `WORKOS_AUTHKIT_DOMAIN` and `MCP_RESOURCE_URL` must be set together to
enable OAuth - if either is missing, the server falls back to a plain,
unauthenticated instance, which is fine for local stdio use but should never
be exposed to the public internet.

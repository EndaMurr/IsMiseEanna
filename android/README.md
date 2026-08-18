# Garmin UI (Android)

A personal, single-user Android client for the `ismiseeanna-api` backend
(`../README.md` → "Garmin UI mobile app backend"): Dashboard, Plan, Chat,
and Status screens over a bottom tab bar, styled after the Modernist design
system (flat, red-on-white, 2px rules, zero corner radius).

## Opening the project

This directory has no committed Gradle wrapper — the sandbox this was
written in had no network access to Google's Maven repo, so the wrapper
couldn't be generated and verified here. Two ways to get one:

- Open `android/` in Android Studio. It detects the missing wrapper and
  generates one during the initial Gradle sync.
- Or, with network access, run `gradle wrapper --gradle-version 8.7` from
  this directory yourself.

**This code has not been compiled or run** — there's no Android SDK in the
environment it was written in. Kotlin/Compose syntax and API usage were
written carefully, but treat the first build as the first real check, and
expect to fix a few things Android Studio's compiler flags.

## Configuring the backend

On first launch, open the **Status** tab and fill in:

- **Server address** — where `ismiseeanna-api` is reachable, e.g.
  `http://192.168.1.20:8000` (your machine's LAN IP, not `localhost` — that
  resolves to the phone itself). Must be reachable from the phone's network
  (same Wi-Fi, or a VPN like Tailscale).
- **API token** — the same value as the backend's `GARMIN_UI_API_TOKEN`.

Both are stored locally via Jetpack DataStore.

The **Plan** tab shows this week's check-in (scheduled vs. completed
sessions, recovery trend) plus which week of your plan you're in — the
latter needs a race date, entered once inline on that screen; it's parsed
against Runna's "W# Day Type" calendar-session naming convention, so it
only resolves to a real week number if that's what's actually scheduled.

## Known simplifications vs. the original mockup

- The design mockup showed inline mini-chart "cards" in chat replies for
  data-backed answers. The current `/chat` backend returns plain text only,
  so the chat screen renders plain message bubbles — the numbers still come
  through in Claude's prose. Structured cards would need the backend to
  emit them alongside `reply`.
- Dashboard stat tiles skip the mockup's qualitative tag chip ("Charged",
  "Moderate", "Good", "Stable") — those thresholds aren't documented
  anywhere verifiable, so showing a value with a guessed label felt worse
  than just showing the value.
- Archivo (the Modernist system's typeface) isn't bundled; the app currently
  uses the platform default sans-serif. Add an Archivo `.ttf` under
  `app/src/main/res/font/` to match the mockup's type exactly.

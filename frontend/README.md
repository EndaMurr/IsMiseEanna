# ismiseeanna dashboard

The multi-user dashboard website's frontend: a Vite + React + TypeScript
SPA. Login, logout, and Garmin-account connection are plain server
redirects handled by `ismiseeanna-web` (see `../src/ismiseeanna_mcp/web.py`)
rather than SPA routes - this app only renders once a session cookie is
already set, calling `/api/*` for data.

## Development

```
npm install
npm run dev
```

`vite.config.ts` proxies `/api`, `/login`, `/callback`, `/logout`, and
`/connect*` to `http://127.0.0.1:8001`, so run a local `ismiseeanna-web`
instance on that port alongside `npm run dev` to exercise the full app.

## Build

```
npm run build
```

Output goes to `dist/`, which is not committed here - CI builds it and the
deploy step packages it for the VM (see `../deploy/gcp/`), since the VM
itself never runs a Node toolchain.

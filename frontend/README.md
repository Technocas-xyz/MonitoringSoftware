# Sentry — Frontend

A sleek, dark, animated web dashboard for the Remote Workforce Monitoring platform.
Next.js 14 (App Router) + TypeScript + Framer Motion, talking to the FastAPI backend.

## Design
- Dark glassmorphism aesthetic with a blue→purple→teal gradient accent.
- Framer Motion throughout: page transitions, animated counters, an SVG productivity ring,
  sliding nav indicator, staggered table rows, and micro-interactions on buttons/toggles.
- Fully responsive; respects `prefers-reduced-motion`.

## Screens
- **Login** — animated split-screen glass card.
- **Dashboard** — workforce stats, productivity ring, workforce-pulse bars, open alerts.
- **Live board** — real-time employee status table.
- **Employees** — searchable directory → **employee detail** with productivity mix + timeline.
- **Attendance** — filterable attendance records.
- **Shifts** — shift state, scheduled vs actual.
- **Alerts** — acknowledge / resolve open alerts.
- **Settings** — toggle optional modules (SSO, geolocation) + view your access.

## Run it locally (needs Node.js 18.17+ )

> Install Node from https://nodejs.org (LTS). Confirm with `node -v`.

```bash
cd frontend
copy .env.local.example .env.local     # macOS/Linux: cp
# edit .env.local if your backend isn't on http://localhost:8000
npm install
npm run dev
```

Open http://localhost:3000. It will redirect to `/login`.

### You need the backend running too
The UI calls the FastAPI backend at `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000`).
Start the backend first (see `../backend/README.md`), then bootstrap an admin so you can log in:

```bash
# in the backend
python -m app.core.bootstrap root@platform.local "a-strong-password"
```

Then log in with:
- **Organization:** `platform`
- **Email:** `root@platform.local`
- **Password:** the one you set

Provision a tenant org via the API (`POST /api/v1/organizations`) and log in with that org's
slug to see populated dashboards.

### CORS
The backend already allows `http://localhost:3000` by default (`CORS_ORIGINS`). If you run the
frontend on a different port/host, add it to the backend's `CORS_ORIGINS`.

## Configuration
| Var | Default | Purpose |
|-----|---------|---------|
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8000` | Backend API base URL |

## Status / caveat
This frontend was authored without a Node.js runtime available in the build environment, so it
has **not been compiled or run** here. Treat `npm install && npm run dev` as the first
validation step; expect to fix a small issue or two on first run (a dependency version, a type
nit). Share any error output and it can be resolved quickly.

## Structure
```
src/
  app/
    layout.tsx            root layout + AuthProvider
    page.tsx              auth-aware redirect
    login/                animated login
    (app)/                authenticated shell (sidebar + topbar + transitions)
      dashboard/  live/  employees/  employees/[id]/  attendance/  shifts/  alerts/  settings/
  components/             ui primitives (Card, Stat, Ring, Badge, …), Sidebar, Topbar
  lib/                    api client, auth context, types, format, useApi hook
```

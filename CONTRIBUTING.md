# Contributing & Branch Model

## Branches
- **`main`** — production. Only release-ready, production-configured code. Deployments are cut from here. Do **not** push work-in-progress or local-dev-only configuration directly to `main`.
- **`dev`** — integration + local development. All feature work lands here first; this is the day-to-day working branch.
- **`feature/*`** — branch **from `dev`**, open the PR back **into `dev`**. Never branch features from `main`.

**Flow:** `feature/* → dev → (release) → main`

## Environment & secrets
- Real environment values and secrets are **never committed**. `.env` is gitignored and supplied **per environment** — copied from the template for local development, injected by the platform/secret store in production. `main` therefore carries **no runtime secrets or environment-specific values**.
- `*.env.example` files are version-controlled **templates**: they list the required variables with safe local-development defaults (e.g. `http://localhost`). Copy to `.env` and adjust for your environment. Production values live only in the production `.env` / secret store, never in git.

## Local development
Local development happens on **`dev`** (or a `feature/*` branch off it). See `README.md` for setup; copy each `*.env.example` to `.env`, then `docker compose up -d --build`.

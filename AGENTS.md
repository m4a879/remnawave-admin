# Repository Guidelines

## Project Structure & Module Organization

`src/` contains the Aiogram bot and `src/tests/`. `web/backend/` is the FastAPI REST/WebSocket service; keep routes in `api/`, business logic in `core/`, models in `schemas/`, and tests in `tests/`. `web/frontend/` is the React 18 + TypeScript SPA: feature code lives in `src/`, static assets in `public/`, unit tests in `src/__tests__/`, and Playwright tests in `e2e/`. Cross-service database, API, cache, RBAC, and analyzer code lives in `shared/`; import new database code from `shared.db`, not the compatibility module `shared.database`. `node-agent/` is the standalone collector, and `alembic/versions/` holds migrations.

## Build, Test, and Development Commands

- `python -m venv .venv && pip install -r requirements.txt`: prepare the bot; copy `.env.example` to `.env`, then run `python -m src.main`.
- `python -m uvicorn web.backend.main:app --reload --port 8081`: run the backend locally after installing `web/backend/requirements.txt`.
- `cd web/frontend && npm ci && npm run dev`: install Node 20 dependencies and start Vite on port 3000.
- `npm run build:check`: type-check and create a production frontend build.
- `docker compose up -d`: start the complete local stack; use `docker compose config` to validate configuration.

## Coding Style & Naming Conventions

Use four spaces in Python and two in TypeScript/TSX. Follow `snake_case` for Python functions/modules, `PascalCase` for classes/components, `camelCase` for frontend values, `useX` for hooks, and `UPPER_SNAKE_CASE` for constants. Prefer async I/O and typed interfaces. TypeScript is strict; use the `@/` alias. No formatter or ESLint configuration is committed, so match adjacent style. Keep shared Python compatible with 3.11. Update both English and Russian locale files for user-facing text.

## Testing Guidelines

Run `python -m pytest web/backend/tests -v --tb=short` and `python -m pytest src/tests -v --tb=short` from the root. From `web/frontend/`, run `npm test` for Vitest and `npm run test:e2e` for Playwright. Name tests `test_<behavior>`, `*.test.ts(x)`, or `e2e/*.spec.ts`. Add regressions beside the affected feature; no coverage threshold is enforced. Migrations use `YYYYMMDD_NNNN_slug.py`, require `upgrade()` and `downgrade()`, and should pass `alembic upgrade heads`.

## Commit & Pull Request Guidelines

History follows Conventional Commit-style subjects such as `feat(ui): ...`, `fix(auth): ...`, and `chore: ...`. Keep commits focused. PRs should explain behavior, list validation, link issues, and include screenshots for UI changes. First-time contributors must sign `CLA.md` through CLA Assistant.

## Security & Configuration

Never commit `.env`, tokens, credentials, logs, backups, or `web/backend/secrets/`. Generate the secrets described in `.env.example`, and keep database credentials, `WEB_SECRET_KEY`, `WEBHOOK_SECRET`, and matching internal API secrets consistent across services.

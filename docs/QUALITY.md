# Quality And Verification

This document lists the expected checks before publishing a release or merging relevant changes.

## Backend: Lint And Typecheck

```bash
set -a
. ./.env.example
set +a
uv run ruff format --check backend/app backend/scripts
uv run ruff check backend/app backend/scripts
uv run mypy backend/app
```

## Backend: Tests

CI runs the backend tests with MongoDB and Mailcatcher from Docker Compose. Locally, if port `27017` is already in use, start MongoDB on a different port and export `MONGODB_PORT`.

```bash
docker compose --env-file .env.example up -d db mailcatcher
cd backend
uv run bash scripts/prestart.sh
uv run bash scripts/tests-start.sh
```

## Frontend: Lint And Typecheck

```bash
bun install
bun run --filter frontend build
cd frontend
bunx biome check --no-errors-on-unmatched --files-ignore-unknown=true ./
```

## Playwright

```bash
docker compose --env-file .env.example build
docker compose --env-file .env.example run --rm playwright bunx playwright test --fail-on-flaky-tests --trace=retain-on-failure
```

## Docker Compose: Smoke Test

```bash
docker compose --env-file .env.example build
docker compose --env-file .env.example up -d --wait backend frontend mongo-express
curl http://localhost:8000/api/v1/utils/health-check
curl http://localhost:5173
docker compose --env-file .env.example down -v --remove-orphans
```

## Local Verification: 2026-06-18

Environment notes:

- The local machine did not have `bun` installed, so the frontend build/Biome checks could not run outside Docker.
- Docker required elevated permissions.
- Port `27017` was already in use by another MongoDB container, so backend tests ran against an isolated MongoDB container on `27018`.

Results:

- Passed: backend Ruff format/check and mypy.
- Passed: `docker compose --env-file .env.example config`.
- Passed: backend subset `tests/api/routes/test_chats.py tests/api/routes/test_items.py` after fixing per-event-loop MongoDB initialization.
- Incomplete: the full backend suite started, but the run was interrupted before final tracebacks after reaching failures in `test_users`.
- Pending: Playwright and the Docker Compose smoke test in a session with Docker/Bun available.

Before publishing `v0.1.0`, rerun all the checks in CI or in a clean local environment where Docker and Bun are available.

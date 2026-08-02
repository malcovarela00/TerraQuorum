# TerraQuorum — Development Guide

This guide describes how to start the local stack, which services are involved and how to keep your environment aligned with [README.md](./README.md) (FastAPI, React, MongoDB, Docker Compose).

## Docker Compose

Before starting the project for the first time, create your local environment files from the sanitized examples:

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
```

Edit `.env` with your local values. Do not use real credentials in versioned files and never commit `.env` to the repository.

To start the full environment (database, backend, optional proxy, Mailcatcher, etc.):

```bash
docker compose watch
```

Once the backend is healthy, you can load an offline demo dataset:

```bash
./scripts/seed-demo.sh
```

That command inserts a small set of countries and indicators marked as demo data, useful for testing the UI and the comparison tools without depending on AI provider keys.

The first startup can take a while: the `prestart` service and the backend wait for MongoDB to be healthy. Check the logs in another terminal if you want to follow the progress:

```bash
docker compose logs
```

Logs for a specific service:

```bash
docker compose logs backend
```

### Common local URLs

| Service | URL | Notes |
| ------- | --- | ----- |
| Frontend (Vite in Docker) | <http://localhost:5173> | Main UI |
| Backend (API) | <http://localhost:8000> | JSON / OpenAPI |
| Interactive API docs (Swagger) | <http://localhost:8000/docs> | Generated from OpenAPI |
| ReDoc | <http://localhost:8000/redoc> | Alternative API docs |
| Traefik (dashboard) | <http://localhost:8090> | Only with the proxy from `compose.override.yml` |
| Mongo Express | <http://localhost:8081> | MongoDB web admin (development) |
| Mailcatcher | <http://localhost:1080> | Emails captured locally |
| Playwright (UI reports) | <http://localhost:9323> | When using the Playwright container/service |

The **MongoDB** database exposes port **27017** on localhost thanks to the development override, in case you connect with an external client (mongosh, an IDE extension, etc.).

## Mailcatcher

[Mailcatcher](https://mailcatcher.me/) acts as a testing SMTP server: the backend sends to `mailcatcher:1025` and the messages appear in the web UI. No real email is ever sent. In [compose.override.yml](./compose.override.yml) the backend already points to Mailcatcher in development.

## Hybrid development (Docker + local process)

Ports match a "local only" setup: backend `8000`, frontend `5173`. You can stop a service in Compose and run the equivalent on your machine.

**Frontend** (recommended for hot reload; from the repository root with Bun workspaces, or from `frontend/`):

```bash
docker compose stop frontend
```

```bash
bun install
bun run dev
```

(This runs the workspace `dev` script; you can also use `cd frontend && bun run dev`.)

**Backend**:

```bash
docker compose stop backend
```

```bash
cd backend
uv sync
source .venv/bin/activate
fastapi dev app/main.py
```

Make sure MongoDB (and any other dependencies you need) stay up in Docker if you are not running them separately.

## Local subdomains and Traefik

Locally, the default setup uses `localhost` with different ports. In deployments, traffic usually goes through subdomains (`api.`, `dashboard.`, etc.); [deployment.md](./deployment.md) covers Traefik and certificates.

To test subdomain routing on the same machine, add entries to your hosts file:

```text
127.0.0.1 api.terraquorum.local
127.0.0.1 dashboard.terraquorum.local
127.0.0.1 mongo.terraquorum.local
```

Then, in `.env` you can set:

```dotenv
DOMAIN=terraquorum.local
```

After the change, restart the stack:

```bash
docker compose watch
```

With the Traefik proxy from the override, the backend becomes reachable at `api.terraquorum.local` and the frontend at `dashboard.terraquorum.local` (port 80). Mongo Express has rules with host `mongo.${DOMAIN}`. **Mongo Express** can still be opened directly on the mapped port (e.g. `8081`) according to your `compose.override.yml`.

## Compose files and environment variables

- [compose.yml](./compose.yml): base stack definition (images, networks, Traefik labels in environments with an external `traefik-public` network).
- [compose.override.yml](./compose.override.yml): local development only (volumes, `fastapi run --reload`, ports, Mailcatcher, a **non**-external `traefik-public` network, etc.).

Docker Compose loads the base file and applies the override automatically. Variables usually come from `.env` (never commit secrets to public repositories; in CI, inject the same keys through the secrets system).

After changing relevant variables, restart the stack.

## Prek (hooks before `git commit`)

The project uses [prek](https://prek.j178.dev/) with the configuration in [`.pre-commit-config.yaml`](./.pre-commit-config.yaml) (Ruff, Biome, mypy, OpenAPI client generation in some cases, etc.).

Install the hook (from the `backend` directory, with `uv` dependencies already synced):

```bash
cd backend
uv run prek install -f
```

The `-f` flag replaces a previous `pre-commit` hook if one existed. On every `git commit`, prek formats and analyzes; if it modifies files, re-stage them and repeat the commit.

Manual run over the whole repository:

```bash
cd backend
uv run prek run --all-files
```

## Quick URL reference (development)

- Frontend: <http://localhost:5173>
- Backend: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Mongo Express: <http://localhost:8081>
- Traefik (local): <http://localhost:8090>
- Mailcatcher: <http://localhost:1080>

In staging/production the URLs will be those of your domain, keeping the same API path patterns (`/docs`, `/redoc`, etc.).

## More documentation

- Backend: [backend/README.md](./backend/README.md) (uv, tests, override description).
- Frontend: [frontend/README.md](./frontend/README.md) (Bun, generated client, Playwright).
- Deployment: [deployment.md](./deployment.md).

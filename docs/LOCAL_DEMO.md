# Local Demo

This guide gets TerraQuorum running locally with demo country data. It does not require AI provider keys unless you want to test live model responses.

## Requirements

- Docker Engine or Docker Desktop
- Git

Optional for hybrid development:

- Bun
- uv

## 1. Create Local Environment

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
```

The example file is safe for local bootstrapping. Before production or public deployment, replace every placeholder secret with strong values.

## 2. Start The Stack

```bash
docker compose watch
```

Wait until the backend is healthy. In another terminal, you can follow logs with:

```bash
docker compose logs -f backend
```

## 3. Load Demo Country Data

```bash
./scripts/seed-demo.sh
```

This inserts or updates a small offline dataset for Argentina, Brazil, Spain, India and Kenya. The dataset is intentionally small and marked with `demo_data=true` inside `custom_data`.

To preview what would change:

```bash
./scripts/seed-demo.sh --dry-run
```

To reset previously seeded demo rows first:

```bash
./scripts/seed-demo.sh --reset-demo
```

## 4. Open The App

- Frontend: <http://localhost:5173>
- Backend docs: <http://localhost:8000/docs>
- Mongo Express: <http://localhost:8081>
- Mailcatcher: <http://localhost:1080>

The initial admin user is controlled by:

```dotenv
FIRST_SUPERUSER=admin@example.com
FIRST_SUPERUSER_PASSWORD=replace-with-a-strong-admin-password
```

## Using AI Providers

The local demo data lets you inspect country records without provider keys. Live chat completions, transcription and provider-backed research need the corresponding variables in `.env`:

```dotenv
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
DEEPSEEK_API_KEY=
GOOGLE_API_KEY=
```

Only configure the providers you plan to use.

## Reset Local Data

To remove containers and volumes:

```bash
docker compose down -v
```

Then start again and rerun the demo seed.

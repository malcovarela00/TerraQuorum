# Contributing To TerraQuorum

Thanks for helping improve TerraQuorum. The project combines a FastAPI backend, a React/Vite frontend, MongoDB, AI provider integrations and country-analysis tools, so small focused contributions are easiest to review.

Please read [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) and [SECURITY.md](./SECURITY.md) before contributing.

## Good First Contributions

See [docs/INITIAL_ISSUES.md](./docs/INITIAL_ISSUES.md) for a starter backlog that can be turned into public GitHub issues.

- Improve README, setup docs or screenshots.
- Add tests for existing backend routes or AI service behavior.
- Improve frontend accessibility, empty states or loading states.
- Add small UI polish that does not change product behavior.
- Improve country data documentation or seed-data instructions.
- Fix reproducible bugs with clear steps and tests.

## Discuss First

Open a GitHub Discussion before starting:

- new product areas or major UX changes;
- database model changes;
- new AI provider integrations;
- large refactors;
- deployment or security changes;
- anything that needs new long-lived configuration.

You can open a pull request directly for small docs fixes, narrow bugs, tests and minor internal cleanup.

## Local Setup

Create the local environment files:

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
```

Start the stack:

```bash
docker compose watch
```

Common URLs:

- Frontend: <http://localhost:5173>
- Backend: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>
- Mongo Express: <http://localhost:8081>
- Mailcatcher: <http://localhost:1080>

See [development.md](./development.md) for hybrid Docker/local workflows.

## Project Areas

- `backend/app/api/`: FastAPI routes and dependencies.
- `backend/app/models.py`: Beanie/MongoDB documents.
- `backend/app/services/`: AI, chat and transcription services.
- `backend/app/mcp_servers/`: country-analysis MCP tools.
- `backend/tests/`: backend tests.
- `frontend/src/routes/`: application routes.
- `frontend/src/components/`: UI and product components.
- `frontend/tests/`: Playwright E2E tests.
- `.github/`: CI, issue templates and repository automation.

## Quality Checks

Run the checks relevant to your change.

Backend:

```bash
cd backend
uv sync
uv run ruff check .
uv run mypy app
uv run bash scripts/tests-start.sh
```

Frontend:

```bash
bun install
bun run lint
cd frontend
bun run build
bunx playwright test
```

Whole-stack smoke test:

```bash
docker compose build
docker compose up -d --wait backend frontend
```

If you cannot run a check locally, say so in the PR and explain why.

## Pull Requests

Keep PRs small and focused. A good PR should include:

- a concise summary of the user-facing change;
- linked issues or discussions;
- screenshots or clips for UI changes;
- tests for behavior changes;
- docs updates for configuration, setup or public behavior changes;
- a clear test plan.

Do not mix unrelated refactors with product changes.

## Secrets And Data

Never commit:

- `.env` or `.env.*` files except `.env.example`;
- API keys, tokens, passwords or private URLs;
- database dumps;
- production logs with user data;
- private prompts or proprietary datasets.

If you accidentally expose a secret, rotate it immediately and report it privately following [SECURITY.md](./SECURITY.md).

## AI-Assisted Contributions

AI tools are welcome when they help you work, but every contribution must include human review and judgment. You are responsible for correctness, tests, licensing, security and clarity.

Do not submit large generated changes that you cannot explain or maintain.

## Commit Style

Use short, descriptive commit messages in English or Spanish. Prefer verbs that describe intent:

- `fix chat provider error handling`
- `add setup notes for local subdomains`
- `improve country comparison loading state`

## Questions

Use GitHub Discussions for setup questions, architecture ideas and roadmap proposals. Use issues for reproducible bugs and scoped feature requests.

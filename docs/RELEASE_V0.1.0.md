# Release v0.1.0

First alpha release of TerraQuorum oriented towards the open source publication.

## Highlights

- Refreshed README with badges, quickstart, visual architecture, stack and roadmap.
- Safe configuration with `.env.example`, hardened `.gitignore` and Gitleaks in GitHub Actions.
- Initial public documentation: security, contributing, code of conduct, local demo, quality and verification.
- Issue templates, pull request template, labels and an initial backlog for contributors.
- Local demo with an offline country dataset and the `./scripts/seed-demo.sh` script.
- Visual assets for the AI chat, comparison/map, parliament/voting and architecture.
- More robust backend tests with per-event-loop MongoDB initialization.

## Verification

- Backend Ruff format/check: passed.
- Backend mypy: passed.
- `docker compose --env-file .env.example config`: passed.
- Backend subset `test_chats + test_items`: passed.
- Full backend suite, Playwright and Docker Compose smoke test: pending a rerun in CI or in a clean environment with Docker/Bun available.

## Publication Notes

Before publishing the release:

- confirm that no `.env` files or real secrets are committed;
- run Gitleaks against the final history;
- rerun the backend tests, Playwright and the full smoke test;
- review the self-hosted deploy workflows and keep them disabled unless `ENABLE_SELF_HOSTED_DEPLOY=true`;
- add or update real screenshots if a demo is deployed.

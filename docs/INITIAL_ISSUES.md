# Initial Issues

Use this backlog to create the first public GitHub issues after publishing TerraQuorum. Each item is scoped to be understandable for contributors and includes suggested labels.

## 1. Add Screenshots To The README

Labels: `docs`, `frontend`, `good first issue`

Goal: add screenshots or short clips showing the chat, country analysis flow and any map/table views.

Acceptance criteria:

- README includes at least 3 visual examples.
- Images are stored in `img/` with descriptive names.
- No private data, tokens, emails or real user prompts are visible.

## 2. Add Demo Seed Data For Local Development

Labels: `country-data`, `backend`, `help wanted`

Goal: provide a small reproducible dataset so new users can see value without first calling AI providers.

Acceptance criteria:

- A documented script or command seeds a small set of countries and indicators.
- Seed data is clearly marked as demo data.
- README or `development.md` explains how to load it.

## 3. Document Provider Setup For OpenAI, Anthropic, DeepSeek And Google

Labels: `docs`, `ai`, `good first issue`

Goal: document which environment variables enable each provider and what happens when a key is missing.

Acceptance criteria:

- Docs list required variables for each provider.
- Docs explain that keys must only live in local `.env` or GitHub Secrets.
- Docs include a minimal smoke-test prompt.

## 4. Improve Empty States In The Chat UI

Labels: `frontend`, `good first issue`

Goal: make first-run UX clearer when there are no conversations, no selected model or missing provider keys.

Acceptance criteria:

- Empty states explain the next action.
- Loading and error states remain accessible.
- UI copy avoids exposing internal stack traces.

## 5. Add Backend Tests For Missing AI Provider Keys

Labels: `backend`, `ai`, `tests`

Goal: ensure provider selection fails with helpful messages when required keys are not configured.

Acceptance criteria:

- Tests cover OpenAI-compatible providers, Google and Anthropic behavior as applicable.
- Error messages remain actionable.
- Tests do not call external provider APIs.

## 6. Add Playwright Coverage For The Main Chat Flow

Labels: `frontend`, `tests`, `help wanted`

Goal: cover the core UI path for opening the app, creating/selecting a conversation and seeing an expected state.

Acceptance criteria:

- Test uses stable locators.
- Test avoids real AI network calls.
- CI remains deterministic.

## 7. Harden Mongo Express Production Exposure

Labels: `security`, `deployment`, `backend`

Goal: avoid exposing Mongo Express by default in production-like deployments.

Acceptance criteria:

- Production compose behavior is safer by default.
- Development access remains documented.
- Deployment docs explain recommended access patterns, such as VPN or Basic Auth.

## 8. Add Architecture Diagram Image

Labels: `docs`, `good first issue`

Goal: turn the README architecture into a reusable image for GitHub previews and external posts.

Acceptance criteria:

- Diagram is stored under `img/`.
- README references it or keeps Mermaid as fallback.
- Diagram reflects frontend, backend, MongoDB, MCP tools and AI providers.

## 9. Add Accessibility Pass For Core Forms

Labels: `frontend`, `help wanted`

Goal: improve keyboard navigation and labels for auth, settings and chat inputs.

Acceptance criteria:

- Inputs have accessible labels.
- Buttons have clear names.
- Basic keyboard navigation works for the main paths.

## 10. Create A Public Roadmap Discussion

Labels: `discussion needed`, `docs`

Goal: turn the README roadmap into a GitHub Discussion with priorities for the first public milestones.

Acceptance criteria:

- Discussion lists candidate milestones for `v0.1`, `v0.2` and `v1.0`.
- Maintainers can link accepted issues to roadmap items.
- The README links to the discussion once it exists.

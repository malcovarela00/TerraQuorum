# Changelog

All notable changes to TerraQuorum will be documented in this file.

The format follows the spirit of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning for public releases.

## Unreleased

### Added

- `frontend/.env.example` so the frontend environment file is no longer versioned.
- Quick deployment overview in the README.

### Changed

- All public documentation (README, security policy, changelog, development, deployment, quality and release notes) translated to English.
- CI and deploy workflows now target the `main` branch instead of `master`.
- Default local backend port unified to `8000` across `.env.example`, Compose and docs.

### Removed

- Copier template leftovers (`copier.yml`, `.copier/`, `hooks/`), the empty root `openapi.json` and the placeholder funding file.

## 0.1.0 - 2026-06-18

### Added

- README oriented towards the open source release, with quickstart, architecture, stack and roadmap.
- Sanitized `.env.example` to bootstrap local and CI environments without real secrets.
- Secret-scanning workflow with Gitleaks.
- Dedicated security policy for TerraQuorum.
- Code of conduct, contributing guide, issue and pull request templates.
- Recommended labels and an initial backlog for contributors.
- Offline demo dataset for local onboarding.
- Local demo guide and quality/verification documentation.
- Visual assets for the architecture, chat, comparison and parliamentary simulation.
- GitHub Actions, license and Docker smoke test badges in the README.

### Changed

- Repository metadata, documentation and license prepared for the project's public identity.
- Public workflows adjusted to create `.env` from `.env.example` during CI.
- Backend Dockerfile aligned with the `terraquorum-backend` package.
- More robust backend MongoDB initialization for multiple event loops in tests.

### Removed

- Release notes inherited from the base template.
- Community and security references pointing to external projects.

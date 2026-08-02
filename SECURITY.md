# Security Policy

Security is a priority for TerraQuorum, especially because the project integrates authentication, a database, AI providers and Docker-based deployments.

## Supported Versions

While the project is in its early phase, security support is only provided for the main branch and the most recent published release.

## Reporting A Vulnerability

Do not disclose vulnerabilities in issues, pull requests, discussions or social media.

To report a security issue:

1. Use GitHub Security Advisories if they are enabled for the repository.
2. If advisories are not available, contact the main maintainer through a private channel before publishing any details.
3. Include a clear description, reproduction steps, potential impact and any minimal proof of concept that helps validate the issue.

We will try to acknowledge the report, assess the impact and coordinate a fix before publicly disclosing the technical details.

## Secrets And Credentials

Never commit `.env` files, AI provider keys, passwords, tokens, database dumps or deployment credentials.

If a secret leaks:

1. Revoke or rotate the credential with the corresponding provider.
2. Remove the secret from the repository and its history before publishing the repo.
3. Review logs, deployments and environments that could have used that credential.
4. Add a test or scanning rule to prevent it from happening again.

The repository includes a secret-scanning workflow based on Gitleaks to detect accidental leaks in pushes and pull requests.

## Initial Scope

The following areas are considered especially sensitive:

- authentication, sessions and JWT tokens;
- user and superuser permissions;
- backend endpoints;
- the MongoDB connection;
- AI provider integrations;
- CI/CD and deployment workflows;
- exposure of admin services such as Mongo Express.

# TerraQuorum — Deployment

You can deploy the application with Docker Compose on a remote server. You need a **Traefik** proxy in front of HTTP/HTTPS traffic (Let's Encrypt certificates) and the **`traefik-public`** Docker network, shared between Traefik and this stack.

The **GitHub Actions** integration (self-hosted runners) lives in [`.github/workflows/`](.github/workflows/); the deployment workflows require specific secrets (see below).

## Prerequisites

* A server with Docker Engine installed (not Docker Desktop). Guide: [Install Docker](https://docs.docker.com/engine/install/).
* Your domain's **DNS** pointing to the server IP.
* A **wildcard** subdomain, for example `*.yourdomain.com`, for services such as `api.yourdomain.com`, `dashboard.yourdomain.com`, `traefik.yourdomain.com`, `mongo.yourdomain.com`, and in staging-like environments `*.staging.yourdomain.com` if you use it.
* The code on the server or checked out on the runner. The example deployments use the repository on the runner machine.

## "Public" Traefik (once per server)

### Copy the Traefik compose file

Create a directory on the server and copy [compose.traefik.yml](compose.traefik.yml), for example with `rsync` from your local machine:

```bash
mkdir -p /root/code/traefik-public/
```

```bash
rsync -a compose.traefik.yml root@your-server.example.com:/root/code/traefik-public/
```

### `traefik-public` network

Create the shared network (only once):

```bash
docker network create traefik-public
```

This way a single Traefik instance can route to one or more stacks sharing the same host.

### Environment variables for the Traefik compose file

Before starting Traefik, export at least the following on the server:

* Username and password (plain text) for the dashboard's *Basic auth*, plus its *apr1* hash:
  * `USERNAME` — for example `admin`
  * `PASSWORD` — plain-text password, only used to generate the hash
  * `HASHED_PASSWORD` — e.g. `export HASHED_PASSWORD=$(openssl passwd -apr1 "$PASSWORD")`
* `DOMAIN` — your base domain, e.g. `yourdomain.com`
* `EMAIL` — email for Let's Encrypt (do not use an invalid example address)

Then, in the directory containing the file:

```bash
cd /root/code/traefik-public/
docker compose -f compose.traefik.yml up -d
```

## Deploy TerraQuorum

With Traefik and the `traefik-public` network ready, deploy the app stack (without `compose.override.yml`, which is local development only). From the code directory:

```bash
cd /path/to/code
docker compose -f compose.yml build
docker compose -f compose.yml up -d
```

`compose.yml` starts **MongoDB** (the `db` service), **Mongo Express** (exposed through the `mongo.${DOMAIN}` subdomain via Traefik), the **backend** (`api.${DOMAIN}`) and the **frontend** (`dashboard.${DOMAIN}`).

## Copying the repository to the server

```bash
rsync -av --filter=":- .gitignore" ./ root@your-server.example.com:/destination/path/
```

`--filter=":- .gitignore"` skips, among other things, virtual environments and unversioned files, aligned with Git.

## Environment variables (`.env` and deployment)

Generate strong secrets, for example:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

In production or staging, always use values different from `changethis` or any default placeholders.

### Required (consistent with [compose.yml](compose.yml))

* `ENVIRONMENT` — `staging` or `production` (usually `local` for development).
* `DOMAIN` — base domain; the stack hosts are `api.` and `dashboard.`, and Mongo Express `mongo.`.
* `STACK_NAME` — identifier for Traefik labels and the project name; different in staging and production, e.g. `yourdomain-com` and `staging-yourdomain-com`.
* `SECRET_KEY` — token signing.
* `FRONTEND_HOST` — public frontend URL, e.g. `https://dashboard.yourdomain.com` (usually enforced with `?Variable not set` in Compose).
* `BACKEND_CORS_ORIGINS` — allowed origins, comma-separated, e.g. `https://dashboard.yourdomain.com,https://api.yourdomain.com`.
* `FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD` — first admin user.
* **Database (MongoDB)** (the Compose service is called `db`):
  * `MONGODB_USER` / `MONGODB_PASSWORD` / `MONGODB_DB` — credentials and database name; the backend uses `MONGODB_SERVER=db` and `MONGODB_PORT=27017` inside the container.
* Build images: `DOCKER_IMAGE_BACKEND`, `DOCKER_IMAGE_FRONTEND` (and optionally `TAG` for the image tag).
* `EMAILS_FROM_EMAIL` and, if you send email, `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` (plus `SMTP_TLS`, `SMTP_PORT`, etc. as needed).
* `SENTRY_DSN` — optional, for monitoring.
* `PROJECT_NAME` — name displayed in the API (e.g. `TerraQuorum`).

Adjust any other variables your `compose.yml` or the backend requires (e.g. AI provider keys) according to your secrets policy: `.env` on the server (never committed) or secrets injected through CI.

## GitHub Actions (self-hosted)

The workflows [`.github/workflows/deploy-staging.yml`](.github/workflows/deploy-staging.yml) and [`.github/workflows/deploy-production.yml`](.github/workflows/deploy-production.yml) run `docker compose -f compose.yml` with the appropriate project name. They are designed for your own infrastructure with self-hosted runners and secrets configured in GitHub.

To enable them, define the repository variable `ENABLE_SELF_HOSTED_DEPLOY=true`. Without that variable, deployments stay disabled by default so the public repository never tries to use private infrastructure.

**Staging:** push to the `main` branch.

**Production:** publishing a *release*.

### GitHub secrets used by those deployments

According to the workflows, configure at least:

* `DOMAIN_STAGING` / `DOMAIN_PRODUCTION`
* `STACK_NAME_STAGING` / `STACK_NAME_PRODUCTION` (each workflow uses its own in `--project-name`)
* `SECRET_KEY`
* `FIRST_SUPERUSER`, `FIRST_SUPERUSER_PASSWORD`
* `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAILS_FROM_EMAIL`
* `MONGODB_USER`, `MONGODB_PASSWORD`, `MONGODB_DB`
* `SENTRY_DSN` (may be empty depending on your secrets provider, if it supports empty values)

It is convenient to keep a `.env` or extra variables on the runner for anything the workflow does not export (e.g. `FRONTEND_HOST`, `BACKEND_CORS_ORIGINS`, `DOCKER_IMAGE_*`, `PROJECT_NAME`, API keys), or to extend the workflow with those variables.

Other CI tasks (e.g. *latest-changes* or *Smokeshow*) use additional optional secrets; they are not part of the minimal deployment described above.

### Self-hosted runner (summary)

* A user with Docker permissions, runner installed following [the GitHub documentation](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners#adding-a-self-hosted-runner-to-a-repository), labeled `staging` or `production` depending on the environment.
* Register the runner service with `svc.sh` so it survives reboots, as described in [Configuring the runner application as a service](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/configuring-the-self-hosted-runner-application-as-a-service).

## Reference URLs (replace `yourdomain.com`)

### Traefik dashboard

`https://traefik.yourdomain.com` (protected with the *Basic auth* from `compose.traefik.yml`).

### Production (example)

* Frontend: `https://dashboard.yourdomain.com`
* API (docs): `https://api.yourdomain.com/docs`
* API (base): `https://api.yourdomain.com`
* Mongo Express: `https://mongo.yourdomain.com` (do not expose it without proper protection; consider a VPN or additional *Basic auth* in production)

### Staging (with the wildcard `*.staging.yourdomain.com`, if applicable)

* `https://dashboard.staging.yourdomain.com`
* `https://api.staging.yourdomain.com` and `https://api.staging.yourdomain.com/docs`
* `https://mongo.staging.yourdomain.com`

The exact convention depends on how you define `DOMAIN` and the DNS; the stack uses the same `DOMAIN` to compose `api.` and `dashboard.`.

## Related documentation

* Local development: [development.md](development.md)
* README: [README.md](README.md)

# InfoAmazonia Boto

FastAPI application that powers InfoAmazonia's WhatsApp chatbot, article discovery workflows, and analytics dashboards. The service orchestrates PostgreSQL (with pgvector), Redis, OpenAI/Azure OpenAI, and external content APIs to deliver personalized conversations and newsroom tooling.

- WhatsApp chatbot with stateful flows and message templates
- Article search and CTR statistics backed by hybrid vector/text queries
- Admin portal for managing sources, messages, and scheduled digests
- APScheduler jobs for ingestion, newsletters, and cleanups

👉 For a deeper architectural breakdown see [`docs/MAINTAINERS.md`](docs/MAINTAINERS.md).

## Table of contents

1. [Quick start](#quick-start)
2. [Database management](#database-management)
3. [Docker workflow](#docker-workflow)
4. [Deploying to Azure](#deploying-to-azure-with-azd)
5. [Troubleshooting & tips](#troubleshooting--tips)

## Quick start

### Prerequisites

- Python 3.11+
- PostgreSQL 14+ with `pgvector` extension available
- Redis 6+
- `pip install -e .` dependencies (see `pyproject.toml`)
- Optional: `OPENAI_API_KEY` or Azure OpenAI credentials

### 1. Configure environment

1. Copy `.env.example` to `.env` (create one if it doesn't exist) and fill in database, Redis, OpenAI, WhatsApp, Mailgun, and Google Maps settings. For Redis specify `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB`, and set `REDIS_USE_TLS=true` if you connect over TLS (the Azure-hosted cache enforces this automatically). For PostgreSQL set `DATABASE_URL` (or the `PG*` variables) to point at your local/favorite instance.
2. Apply any secrets required by APScheduler jobs (ingestion URLs, etc.). Missing keys degrade gracefully but limit features.

### 2. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Prepare the database (optional but recommended)

```bash
python reset_database.py
python create_admin.py  # creates the default admin login
```

### 4. Run the development server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Visit `http://localhost:8000/docs` for the interactive API or `/admin` for the dashboard (requires login).

### 5. Run the test suite

```bash
python test_chatgpt_service.py
```

Add additional pytest-style tests under `tests/` (if created) and wire them into your CI.

## Database management

### Automatic reset

```bash
python reset_database.py
```

This script will:

1. Drop all existing tables
2. Recreate the database schema (including `pgvector`)
3. Populate optional sample data

### Manual reset

```sql
-- Drop the public schema and recreate it
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;

-- Recreate tables by running the app once
python main.py
```

Automatic reset is preferred because it enables extensions and seeds defaults in the right order.

### Create a database dump

Use the helper script to generate a `pg_dump` backup using whatever `DATABASE_URL` is defined in your `.env`:

```bash
python dump_database.py --output backups/boto_dump.sql
# or override the connection URL explicitly
python dump_database.py postgresql://user:pass@host/dbname
```

The script defaults to a timestamped file under `backups/`, auto-creates the directory, and forwards additional flags straight to `pg_dump` if you append them after `--`.

## Docker workflow

Use the provided `Dockerfile` for parity between local, CI, and Azure deployments.

```bash
# Build the image (replace v1 with any tag)
docker build -t infoamazonia-boto:v1 .

# Run the container with your local env vars
docker run --rm \
  -p 8000:8000 \
  --env-file .env \
  infoamazonia-boto:v1
```

Once the container is up, access `http://localhost:8000`. The image expects `WEBSITES_PORT=8000`; override `PORT` as needed.

### Docker Compose stack

Use [`docker-compose.yml`](docker-compose.yml) when you want PostgreSQL and Redis provisioned alongside the app:

```bash
# Build images (app) and start all services in the foreground
docker compose up --build

# Stop everything and remove containers
docker compose down

# Stop and wipe persisted databases/caches
docker compose down -v
```

Key details:

- The `app` service builds from the local `Dockerfile`, exposes port `8000`, and automatically depends on healthy PostgreSQL/Redis containers before starting `uvicorn`.
- PostgreSQL uses the `ankane/pgvector` image (pgvector preinstalled, currently Postgres 16) with credentials `boto/boto` and persists data in the `postgres_data` volume. The API container receives a connection string via `DATABASE_URL=postgresql+psycopg://boto:boto@postgres:5432/boto`.
- Redis uses `redis:7-alpine`, stores data in the `redis_data` volume, and is wired into the app through `REDIS_HOST=redis` plus the default port/db.
- The stack loads every variable from `.env` (so you can keep WhatsApp/Mailgun/OpenAI secrets there) while overriding just the database/cache values needed for the internal network.
- Run administrative scripts inside the container, e.g. `docker compose exec app python reset_database.py` or `docker compose exec app python create_admin.py`, so they reuse the same networked services.

Customize credentials/ports in `docker-compose.yml` if you already have local services that conflict with the defaults, and mirror those changes in your `.env` when running CLI utilities outside Docker.

## Deploying to Azure with azd

The `infra/` folder contains modular Bicep templates that provision:
- A Linux App Service plan + Web App (runs the FastAPI container or the built-in Python runtime).
- Azure Database for PostgreSQL Flexible Server (pgvector-ready connection string injected into the app).
- Azure Cache for Redis (credentials injected; TLS enforced by default).

Use Azure Developer CLI (`azd`) for reproducible deployments.

### Prerequisites

- Azure subscription with contributor rights
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
- [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) 1.9+
- Docker (required by azd to build/push the container)

### Deployment steps

1. **Bootstrap an environment**

	```bash
	azd init --template .
	azd env new <env-name>
	```

2. **Set secrets and database credentials**

	```bash
	azd env set OPENAI_API_KEY "your-real-key"
	azd env set USE_AZURE_OPENAI true
	azd env set POSTGRES_ADMIN_PASSWORD "super-secure-password"
	# repeat for WHATSAPP_*, MAILGUN_*, etc.
	```

	Avoid hard-coding secrets in `infra/main.parameters.json`; keep it committed with safe defaults and feed real values through `azd env set`. Redis credentials are injected automatically from Azure Cache, so leave `REDIS_*` vars unset. The PostgreSQL server host, port, database, and connection string are generated from the managed Flexible Server—only the admin password is required.

		Prefer automating this with the helper script so you don’t mistype anything:

		```bash
		python scripts/sync_env_to_azd.py --env-file .env --environment dev
		```

		Use `--skip KEY` for vars you don’t want to push or `--dry-run` to preview the commands before they execute.

3. *(Optional)* **Use a custom container image**

	If you prefer App Service for Containers instead of the built-in Python runtime, push the image to a registry and set:

	```bash
	azd env set CONTAINER_IMAGE "myregistry.azurecr.io/infoamazonia-boto:latest"
	azd env set CONTAINER_REGISTRY_SERVER "https://myregistry.azurecr.io"
	azd env set CONTAINER_REGISTRY_USERNAME "<user>"
	azd env set CONTAINER_REGISTRY_PASSWORD "<token>"
	```

	Leave these empty to let `azd` deploy the source code via Oryx.

4. **Authenticate and select your subscription**

	```bash
	azd auth login
	az account set --subscription <subscription-id>
	```

5. **Provision + deploy**

	```bash
	azd up
	```

	This validates the Bicep files, creates the App Service resources plus Azure Cache for Redis **and** Azure Database for PostgreSQL, applies configuration (including `WEBSITES_PORT=8000`), and uploads the container.

6. **Custom domains (optional)**

	Set `customDomainName` in `infra/main.parameters.json`, create the CNAME record, then rerun `azd up`. SSL certs can be added later.

7. **Redeploy updates**

	- App/service code only: `azd deploy`
	- Infra changes: edit Bicep/parameters and rerun `azd up`

Check the command output for the deployed URL (`https://<service>-<env>-app.azurewebsites.net`).

## Troubleshooting & tips

- Ensure Redis is reachable before boot; otherwise caching and password resets are degraded. The Azure deployment provisions a dedicated cache automatically—local setups still need their own Redis instance.
- Likewise, make sure your local `.env` points to a PostgreSQL instance. Azure deployments will receive a managed Flexible Server connection string automatically.
- Scheduler jobs start automatically when the app boots—watch the logs for job failures.
- When switching between OpenAI providers, set `USE_AZURE_OPENAI` and the Azure keys together; `services/location` still needs the standard `OPENAI_API_KEY`.
- If you change short-link storage formats, update both `services/search.py` helpers and the `/r/{short_id}` redirect in `main.py`.

Need the full architecture overview? Check [`docs/MAINTAINERS.md`](docs/MAINTAINERS.md) for directory-by-directory notes.

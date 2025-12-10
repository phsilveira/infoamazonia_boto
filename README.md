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

1. Copy `.env.example` to `.env` (create one if it doesn't exist) and fill in database, Redis, OpenAI, WhatsApp, Mailgun, and Google Maps settings.
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

## Deploying to Azure with azd

The `infra/` folder contains Bicep templates that provision a Linux App Service plan, Web App, and supporting resources. Use Azure Developer CLI (`azd`) for reproducible deployments.

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

2. **Set secrets** (mirrors `.env` keys)

	```bash
	azd env set OPENAI_API_KEY "your-real-key"
	azd env set USE_AZURE_OPENAI true
	azd env set DATABASE_URL "postgresql+psycopg://..."
	# repeat for WHATSAPP_*, MAILGUN_*, etc.
	```

	These flow into the `appSettings` map defined in `infra/main.parameters.json`.

3. **Authenticate and select your subscription**

	```bash
	azd auth login
	az account set --subscription <subscription-id>
	```

4. **Provision + deploy**

	```bash
	azd up
	```

	This validates the Bicep files, creates the App Service resources, applies configuration (including `WEBSITES_PORT=8000`), and uploads the container.

5. **Custom domains (optional)**

	Set `customDomainName` in `infra/main.parameters.json`, create the CNAME record, then rerun `azd up`. SSL certs can be added later.

6. **Redeploy updates**

	- App/service code only: `azd deploy`
	- Infra changes: edit Bicep/parameters and rerun `azd up`

Check the command output for the deployed URL (`https://<service>-<env>-app.azurewebsites.net`).

## Troubleshooting & tips

- Ensure Redis is reachable before boot; otherwise caching and password resets are degraded.
- Scheduler jobs start automatically when the app boots—watch the logs for job failures.
- When switching between OpenAI providers, set `USE_AZURE_OPENAI` and the Azure keys together; `services/location` still needs the standard `OPENAI_API_KEY`.
- If you change short-link storage formats, update both `services/search.py` helpers and the `/r/{short_id}` redirect in `main.py`.

Need the full architecture overview? Check [`docs/MAINTAINERS.md`](docs/MAINTAINERS.md) for directory-by-directory notes.

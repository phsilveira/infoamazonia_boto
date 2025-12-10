# Maintainers Guide

This document helps new contributors understand how InfoAmazonia Boto is organized, which services it depends on, and the workflows required to keep it running in production.

## High-level architecture

- **FastAPI application (`main.py`)** hosts the HTTP entry point, mounts static assets/templates, and wires routers (`admin`, `webhook`, `routers.location`, `api_endpoints`).
- **Lifecycle hook** creates database tables, checks PostgreSQL/Redis connectivity, and spins up APScheduler via `start_scheduler()`.
- **Admin portal (`admin/`)** provides Jinja-powered dashboards for managing users, news sources, WhatsApp copy, articles, metrics, and scheduled jobs.
- **WhatsApp chatbot (`webhook.py` + `services/chatbot.py`)** receives Meta callbacks, routes conversations through a state machine, and sends replies via `services/whatsapp.send_message`.
- **Search & analytics (`services/search.py`)** offer hybrid vector/text queries, article stats, CTR tracking, and URL shortening shared by FastAPI endpoints (`/api/search`, `/api/article-stats`, `/api/ctr-stats`).
- **Background jobs (`scheduler.py`)** handle ingestion, digests, cleanup tasks, and run in the São Paulo timezone.

### Data plane

| Resource | Purpose |
| --- | --- |
| PostgreSQL + `pgvector` | Primary data store for users, articles, embeddings, and analytics. `init_db()` enables the extension and creates the IVFFLAT index. |
| Redis (async client) | Caching layer, chatbot session store, password-reset tokens, short URL metrics. Code should degrade gracefully if Redis is missing. |
| External APIs | WhatsApp Cloud API, Mailgun, Google Maps, ingestion/search backends, OpenAI/Azure OpenAI. |

## Environment & secrets

Configuration comes from `config.Settings` (Pydantic). Required keys typically include:

- Database/Redis URLs (`DATABASE_URL`, `REDIS_URL`).
- `OPENAI_API_KEY` plus `USE_AZURE_OPENAI` + `AZURE_*` if using Azure OpenAI; `services/location` still relies on the standard OpenAI key.
- `WHATSAPP_*`, `MAILGUN_*`, `GOOGLEMAPS_API_KEY`, `ARTICLES_API_URL`, `SEARCH_BASE_URL`.
- Feature toggles for scheduler jobs.

Store secrets in `.env` for local development and `azd env set` for Azure deployments. Missing keys should trigger degraded-mode log messages rather than crashes.

## Directory map

| Path | Highlights |
| --- | --- |
| `admin/` | FastAPI routers for admin features plus templates helpers (`base.py`). Call `invalidate_dashboard_caches()` after writes. |
| `routers/` | Public API routers (articles, ingestion, etc.). Ensure new endpoints reuse async services under `services/`. |
| `services/` | Domain logic (chatbot, chatgpt, embeddings, article ingestion, news, search, location, email, whatsapp). Keep I/O isolated here. |
| `scheduler.py` & `admin/scheduler.py` | Job definitions and admin controls. Register new jobs in `start_scheduler()` so they persist across restarts. |
| `cache_utils.py` | Cache helpers and `@cached` decorator; keys must avoid non-serializable objects. |
| `messages.yml` / `prompts.yml` | WhatsApp copy and LLM prompts loaded via singleton loaders (`utils/message_loader.py`, `utils/prompt_loader.py`). |
| `infra/` | Bicep templates + parameters for Azure App Service deployments. |
| `tests/` & scripts (`reset_database.py`, `create_admin.py`, `insert_fake_interactions.py`) | Local tooling for DB prep and analytics seeding. |

## Request flows

1. **Admin UI**: Browser → FastAPI admin router → Jinja templates → SQLAlchemy CRUD → invalidate caches.
2. **Chatbot**: Meta webhook → `webhook.py` → `services.chatbot.ChatBot` → state handler in `services/handlers.py` → outgoing message via WhatsApp API → Redis state update.
3. **Search/Analytics APIs**: FastAPI endpoint → async helper in `services/search.py` → SQL/text query with pgvector + caching → JSON response.

## Background jobs

- Defined in `scheduler.py` and registered in `start_scheduler()`.
- APScheduler runs in-process; failures surface in application logs.
- Jobs often depend on external ingestion endpoints or email providers—guard for missing credentials.

## Development workflow

1. Create a virtual environment and run `pip install -e .`.
2. Start PostgreSQL (with `pgvector`) and Redis locally; use Docker compose or managed services.
3. Run `python reset_database.py` followed by `python create_admin.py` to bootstrap data.
4. Launch `uvicorn main:app --reload` and verify `/docs` and `/admin`.
5. Use `python test_chatgpt_service.py` to validate OpenAI/Azure OpenAI integration; set `USE_AZURE_OPENAI=True` when covering that branch.

## Deployment workflow

- Preferred path is `azd up`, which validates Bicep templates, provisions the App Service plan/Web App, sets `WEBSITES_PORT=8000`, and deploys the container built from the repository `Dockerfile`.
- For updates: `azd deploy` (code only) or edit `infra/*.bicep` + rerun `azd up` (infra + code).
- Keep `.env`, `config.py`, and `infra/main.parameters.json` aligned when adding new secrets/resources.

## Maintenance tips

- Cache invalidation: admin writes should call `invalidate_dashboard_caches()` to keep analytics fresh.
- Redis fallbacks: wrap cache lookups with guards so the app works (with reduced performance) if Redis is offline.
- URL shortener: `/r/{short_id}` shares storage with services in `services/search.py`; update both sides if you change key formats.
- Password resets: tokens live in Redis under `reset:{token}`; make sure expiry policies match the UI copy.
- Scheduler TZ: ensure São Paulo timezone is respected when adding jobs.

## Troubleshooting checklist

- **Chatbot stuck**: verify Redis connectivity and that `processing:{phone}` keys are cleared in `webhook.py`'s `finally` block.
- **Search endpoints returning 500**: ensure embeddings are normalized before casting to `vector` literals and that `pgvector` is installed.
- **Azure deploy fails**: run `azd pipeline config` to re-auth and confirm Docker is available. Check `infra/main.parameters.json` for mismatched app settings.
- **LLM issues**: confirm whether you're using OpenAI or Azure mode; mismatched toggles lead to authentication errors.

Keep this guide updated when you add new services, jobs, or dependencies so future maintainers can ramp up quickly.

# InfoAmazonia Boto – Copilot Instructions

## Architecture snapshot
- `main.py` hosts the FastAPI app, mounts static/templates, wires routers (`admin`, `webhook`, `routers.location`, `api_endpoints`) and manages lifecycle: it creates tables, verifies PostgreSQL/Redis, and boots APScheduler via `start_scheduler()` during the lifespan hook.
- Admin functionality lives under `admin/` in focused routers (users, news_sources, messages, interactions, articles, admin_users, metrics, scheduler) that share helpers from `admin/base.py` (Jinja templates, DB deps, cache invalidation).
- WhatsApp chatbot traffic flows through `webhook.py` → `services.chatbot.ChatBot` (transitions state machine + Redis state) → state-specific handlers in `services/handlers.py`, with outbound messages sent via `services.whatsapp.send_message`.
- Search, article stats, CTR data, and URL shortening sit in `services/search.py`; FastAPI endpoints should call the async helpers (`search_term_service`, `get_article_stats_service`, `get_ctr_stats_service`, etc.) instead of the legacy Flask blueprint functions.
- Domain logic is centralized in `services/` (chatgpt, embeddings, article_ingestion, news, location, email, whatsapp). Shared content lives in `messages.yml` (WhatsApp copy) and `prompts.yml` (LLM prompts) loaded via singleton helpers in `utils/`.

## Data & dependencies
- PostgreSQL is accessed via SQLAlchemy (`database.py`) with `pgvector` (1536-dim embeddings, ivfflat index). `init_db()` enables the extension; you need superuser rights when resetting the DB.
- Redis (async client) backs caching, chatbot/session state, password-reset tokens, and short-URL metrics; guard all cache calls for missing `app.state.redis` and fall back to TTL caches when absent.
- LLM usage toggles through `config.Settings`: set `OPENAI_API_KEY` for standard OpenAI or flip `USE_AZURE_OPENAI` and provide `AZURE_*` vars; prompts are templated via `PromptLoader`.
- External services: WhatsApp Cloud API (`WHATSAPP_*`), Mailgun (`MAILGUN_*`), Google Maps (`GOOGLEMAPS_API_KEY`). Missing keys should degrade gracefully or be mocked in tests.

## Setup & workflows
- Install deps with `pip install -e .` (pyproject) or `pip install -r requirements.txt`; Docker builds rely on the editable install defined in `Dockerfile`.
- Provision data: `python reset_database.py` (drops/recreates schema + pgvector) and `python create_admin.py` (creates default admin). `insert_fake_interactions.py` seeds sample analytics data.
- Run locally via `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`; `python main.py` wraps the same command and respects the `PORT` env var.
- Redis must be reachable before boot to avoid degraded caching/password resets; scheduler jobs (news digests, ingestion, cleanup) spin up automatically once the app starts.
- `API_DOCUMENTATION.md` mirrors the FastAPI schema for `/api/*`; use it to keep request/response models in sync with `api_endpoints.py`.

## Coding patterns & conventions
- Reuse `cache_utils` (`get_cache`, `set_cache`, `invalidate_cache`) and the `@cached` decorator in `main.py` for expensive analytics endpoints; keys should exclude non-serializable objects (see decorator’s filtering logic).
- Admin routes expect `get_current_admin_dependency()` and often call `invalidate_dashboard_caches()` after writes to keep metrics cards fresh.
- Chatbot handlers pull copy from `message_loader.get_message("section.key")`; keep locale strings in `messages.yml` rather than hard-coding.
- Search helpers combine vector + full-text SQL; prefer composing SQL via `text()` and keep embeddings normalized before casting to `vector` literals.
- Long-running/background work should go through APScheduler tasks in `scheduler.py`; when adding jobs, register them inside `start_scheduler()` so they survive restarts and respect the São Paulo timezone.

## Testing & validation
- `python test_chatgpt_service.py` exercises both standard and Azure OpenAI paths; set `USE_AZURE_OPENAI=True` plus the Azure env vars to cover that branch.
- For WhatsApp flows, simulate inbound payloads against `/webhook` (see `webhook.py` for the Facebook callback shape) and confirm Redis keys like `processing:{phone}` are cleared in the `finally` block.
- When touching article search/stat logic, hit `/api/search`, `/api/article-stats`, and `/api/ctr-stats` with the auth cookie to ensure the FastAPI wrappers still marshal the service responses described in `API_DOCUMENTATION.md`.

## Gotchas & tips
- `services/location` still calls the standard OpenAI SDK directly; supply `OPENAI_API_KEY` even if you mainly use Azure for the rest of the app.
- `services/search` mixes sync (Flask) and async (FastAPI) contexts—use `_store_url_in_memory_cache` or `_store_url_in_redis_async` variants that match your call site.
- URL redirects share storage with the `/r/{short_id}` route in `main.py`; if you change the key format, update both the service helpers and the redirect endpoint.
- Password resets write tokens to Redis (`reset:{token}`); without Redis the flow short-circuits, so guard UI changes accordingly.
- Infra-as-code lives under `infra/` (Bicep). If you add new Azure resources or env vars, keep `config.py`, `.env*`, and the Bicep parameters aligned.

## Handy commands
- `pip install -e .`
- `python reset_database.py`
- `python create_admin.py`
- `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
- `python test_chatgpt_service.py`
